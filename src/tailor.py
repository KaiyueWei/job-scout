"""
Customize a DOCX CV template per high-scoring job offer and convert to PDF.

Placeholder substitution uses python-docx. PDF conversion uses CloudConvert,
with ConvertAPI as a fallback. Mirrors customize_cv.py in
pietroruzzante/linkedin_scraper_pipeline.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
from pathlib import Path

import requests
from docx import Document
from docx.shared import Pt, RGBColor
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from src.prompts import CV_PLACEHOLDER_PROMPT
from src.scorer import ScoredJob, extract_keywords

logger = logging.getLogger(__name__)

OUTPUT_DIR = "output"


class CVPlaceholders(BaseModel):
    ROLE: str
    CORE_COMPETENCIES: str
    LIBRARIES: str
    LANGUAGES: str
    TOOLS: str


def _placeholders_chain():
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    return (
        ChatPromptTemplate.from_messages([("human", CV_PLACEHOLDER_PROMPT)])
        | llm.with_structured_output(CVPlaceholders, method="function_calling")
    )


def _generate_placeholders(
    scored_job: ScoredJob, candidate_profile: str, cv_skills: dict
) -> dict:
    """Run the placeholder LLM chain. Returns a dict of placeholder values."""
    result = _placeholders_chain().invoke(
        {
            "profile": candidate_profile,
            "job_description": scored_job.listing.description[:3000],
            "keywords": json.dumps(scored_job.keywords),
            "competencies": cv_skills.get("competencies", []),
            "libraries": cv_skills.get("libraries", []),
            "languages": cv_skills.get("languages", []),
            "tools": cv_skills.get("tools", []),
        }
    )
    if isinstance(result, dict):
        result = CVPlaceholders(**result)
    logger.info(f"  → ROLE={result.ROLE}")
    return result.model_dump()


def _replace_in_doc(doc: Document, placeholders: dict) -> None:
    """Replace {{KEY}} tokens across all runs in the document."""
    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            for key, value in placeholders.items():
                token = f"{{{{{key}}}}}"
                if token in run.text:
                    run.text = run.text.replace(token, value)
                    if key == "ROLE":
                        run.bold = True
                        run.font.size = Pt(14)
                        run.font.color.rgb = RGBColor(0x1B, 0x73, 0xC8)


def _convert_to_pdf(doc_path: str, pdf_path: str) -> None:
    """Convert docx → pdf via CloudConvert, falling back to ConvertAPI."""
    cc_key = os.environ.get("CLOUDCONVERT_API_KEY")
    if cc_key:
        try:
            _cloudconvert_to_pdf(doc_path, pdf_path, cc_key)
            return
        except Exception as e:
            logger.warning(f"CloudConvert failed ({e}); falling back to ConvertAPI")

    ca_secret = os.environ.get("CONVERTAPI_SECRET")
    if not ca_secret:
        raise RuntimeError(
            "PDF conversion failed: set CLOUDCONVERT_API_KEY and/or CONVERTAPI_SECRET"
        )

    import convertapi  # type: ignore

    convertapi.api_credentials = ca_secret
    convertapi.convert("pdf", {"File": doc_path}, from_format="docx").save_files(
        os.path.dirname(pdf_path)
    )
    saved = sorted(
        glob.glob(os.path.join(os.path.dirname(pdf_path), "*.pdf")),
        key=os.path.getmtime,
    )
    if not saved:
        raise RuntimeError("ConvertAPI did not produce a PDF file")
    if saved[-1] != pdf_path:
        os.rename(saved[-1], pdf_path)


def _cloudconvert_to_pdf(doc_path: str, pdf_path: str, api_key: str) -> None:
    import cloudconvert  # type: ignore

    cloudconvert.configure(api_key=api_key)
    job = cloudconvert.Job.create(
        payload={
            "tasks": {
                "upload": {"operation": "import/upload"},
                "convert": {
                    "operation": "convert",
                    "input": "upload",
                    "input_format": "docx",
                    "output_format": "pdf",
                },
                "export": {"operation": "export/url", "input": "convert"},
            }
        }
    )
    upload_task = next(t for t in job["tasks"] if t["name"] == "upload")
    cloudconvert.Task.upload(file_name=doc_path, task=upload_task)
    job = cloudconvert.Job.wait(id=job["id"])
    export_task = next(t for t in job["tasks"] if t["name"] == "export")
    url = export_task["result"]["files"][0]["url"]
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    with open(pdf_path, "wb") as f:
        f.write(response.content)


def _sanitize_filename(name: str) -> str:
    clean = re.sub(r"[^\w\s-]", "", name)
    clean = re.sub(r"\s+", "_", clean)
    return clean[:40].strip("_").lower()


def tailor_resume(
    scored_job: ScoredJob,
    template_path: str,
    candidate_name: str,
    candidate_profile: str,
    cv_skills: dict,
) -> str | None:
    """Produce a tailored PDF for one offer. Returns PDF path or None."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not scored_job.keywords:
        try:
            scored_job.keywords = extract_keywords(scored_job.listing.description)
        except Exception as e:
            logger.warning(f"Keyword extraction failed: {e}")

    try:
        placeholders = _generate_placeholders(scored_job, candidate_profile, cv_skills)
    except Exception as e:
        logger.error(f"Placeholder generation failed: {e}")
        return None

    doc = Document(template_path)
    _replace_in_doc(doc, placeholders)

    company = _sanitize_filename(scored_job.listing.company)
    name = _sanitize_filename(candidate_name)
    base = f"CV_{name}_{company}"
    doc_path = os.path.join(OUTPUT_DIR, f"{base}.docx")
    pdf_path = os.path.join(OUTPUT_DIR, f"{base}.pdf")
    doc.save(doc_path)

    try:
        _convert_to_pdf(doc_path, pdf_path)
    except Exception as e:
        logger.error(f"PDF conversion failed for {company}: {e}")
        return None

    logger.info(f"Tailored resume: {pdf_path}")
    return pdf_path


def tailor_resumes(scored_jobs: list[ScoredJob], config: dict) -> dict[str, str]:
    """Tailor PDFs for all jobs at or above the tailor threshold."""
    threshold = config.get("search", {}).get("tailor_threshold", 8)
    template_path = os.environ.get(
        "CV_TEMPLATE_PATH", config.get("cv", {}).get("template_path", "templates/cv_template.docx")
    )
    if not Path(template_path).exists():
        logger.error(
            f"DOCX template not found at '{template_path}'. "
            "Set CV_TEMPLATE_PATH or place templates/cv_template.docx."
        )
        return {}

    candidate_name = config.get("profile", {}).get("name", "Candidate")
    candidate_profile = config.get("scoring", {}).get("candidate_profile", "")
    cv_skills = config.get("cv", {})

    results: dict[str, str] = {}
    high = [sj for sj in scored_jobs if sj.score >= threshold]
    logger.info(f"Tailoring {len(high)} resumes (score >= {threshold})")

    for sj in high:
        pdf_path = tailor_resume(
            sj,
            template_path=template_path,
            candidate_name=candidate_name,
            candidate_profile=candidate_profile,
            cv_skills=cv_skills,
        )
        if pdf_path:
            results[sj.listing.job_id] = pdf_path

    return results
