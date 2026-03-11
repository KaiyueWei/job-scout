"""
Resume tailor module.
Generates tailored LaTeX resumes based on the recommended variant
and tailoring notes from the scorer.

SETUP: Place your base LaTeX resume template at templates/base_resume.tex
Use these placeholders in your template:
  {{SUMMARY}} — will be replaced with a role-specific summary line
  {{SKILLS_LINE}} — will be replaced with reordered skills emphasis

The module modifies the summary and skills ordering based on the variant.
For a full auto-rewrite of bullets, you'd need to expand this with Claude API calls.
"""

import logging
import os
import re
import subprocess
from pathlib import Path

from src.scorer import ScoredJob

logger = logging.getLogger(__name__)

OUTPUT_DIR = "output"

# Pre-defined summary lines per variant
VARIANT_SUMMARIES = {
    "backend_sde": (
        "Go backend developer experienced in building scalable REST APIs, event-driven microservices, "
        "and AI-augmented development workflows, with a strong analytical foundation from six years "
        "in intellectual property law."
    ),
    "devops_sre": (
        "Infrastructure and reliability engineer experienced in Terraform, Kubernetes, Docker, "
        "and CI/CD pipeline optimization. Open-source contributor to HashiCorp Terraform AWS Provider, "
        "with a strong analytical foundation from six years in intellectual property law."
    ),
    "fullstack": (
        "Full-stack developer experienced in building scalable web platforms with Node.js/TypeScript "
        "backends and cloud-native infrastructure including PostgreSQL, Redis, and Docker, "
        "with a strong analytical foundation from six years in intellectual property law."
    ),
    "cyber_risk": (
        "Cybersecurity-focused developer with kernel-level security research (eBPF), competitive "
        "CTF experience (CyberSci Regional top 6), and six years of regulatory compliance "
        "background in intellectual property law."
    ),
}

# Skills line ordering per variant (front-load the most relevant)
VARIANT_SKILLS_EMPHASIS = {
    "backend_sde": (
        "\\textbf{Languages:} Go, Python, TypeScript, C/C++, Bash, SQL \\\\\n"
        "\\textbf{Cloud \\& Infrastructure:} GCP (GKE, BigQuery), AWS (EC2, S3, CloudWatch), "
        "Docker, Kubernetes, Terraform, CI/CD \\\\\n"
        "\\textbf{Data \\& Messaging:} PostgreSQL, MongoDB, Redis, RabbitMQ, Stripe \\\\\n"
        "\\textbf{Systems \\& Observability:} Linux, Jaeger, distributed tracing, performance analysis, "
        "automated testing, Git \\\\\n"
        "\\textbf{AI Development Tools:} GitHub Copilot, Cursor, Claude -- integrated into daily "
        "development for code generation, debugging, and testing"
    ),
    "devops_sre": (
        "\\textbf{Cloud \\& Infrastructure:} Terraform, Docker, Kubernetes, AWS (EC2, S3, CloudWatch), "
        "GCP (GKE, BigQuery), CI/CD, GitHub Actions \\\\\n"
        "\\textbf{Languages:} Go, Python, Bash, TypeScript, C/C++, HCL, SQL \\\\\n"
        "\\textbf{Systems \\& Observability:} Linux, Jaeger, distributed tracing, CloudWatch, "
        "performance analysis, automated testing, Git \\\\\n"
        "\\textbf{Data \\& Messaging:} PostgreSQL, MongoDB, Redis, RabbitMQ \\\\\n"
        "\\textbf{AI Development Tools:} GitHub Copilot, Cursor, Claude -- integrated into daily "
        "development for code generation, debugging, and testing"
    ),
    "fullstack": (
        "\\textbf{Languages:} TypeScript, Go, Python, C/C++, Bash, SQL \\\\\n"
        "\\textbf{Backend \\& Data:} Node.js, Express, PostgreSQL, MongoDB, Redis, RabbitMQ, "
        "Stripe Connect, REST APIs, WebSocket \\\\\n"
        "\\textbf{Cloud \\& Infrastructure:} GCP (GKE, BigQuery), AWS (EC2, S3, CloudWatch), "
        "Docker, Kubernetes, Terraform, CI/CD \\\\\n"
        "\\textbf{Systems \\& Observability:} Linux, Jaeger, distributed tracing, performance analysis, "
        "automated testing, Git \\\\\n"
        "\\textbf{AI Development Tools:} GitHub Copilot, Cursor, Claude -- integrated into daily "
        "development for code generation, debugging, and testing"
    ),
    "cyber_risk": (
        "\\textbf{Security:} Ghidra, OWASP vulnerability assessment, digital forensics, "
        "reverse engineering, kernel observability (eBPF) \\\\\n"
        "\\textbf{Languages:} Go, Python, C/C++, TypeScript, Bash, SQL \\\\\n"
        "\\textbf{Cloud \\& Infrastructure:} AWS (EC2, S3, CloudWatch), GCP, Docker, Kubernetes, "
        "Terraform, CI/CD \\\\\n"
        "\\textbf{Systems \\& Observability:} Linux, Jaeger, distributed tracing, performance analysis, "
        "automated testing, Git \\\\\n"
        "\\textbf{AI Development Tools:} GitHub Copilot, Cursor, Claude -- integrated into daily "
        "development for code generation, debugging, and testing"
    ),
}


def tailor_resume(scored_job: ScoredJob) -> str | None:
    """
    Generate a tailored resume PDF for a scored job.
    Returns the path to the generated PDF, or None on failure.
    """
    template_path = Path("templates/base_resume.tex")
    if not template_path.exists():
        logger.error("Base resume template not found at templates/base_resume.tex")
        return None

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    variant = scored_job.variant
    company = _sanitize_filename(scored_job.listing.company)
    title = _sanitize_filename(scored_job.listing.title)

    # Read template
    template = template_path.read_text()

    # Apply variant-specific substitutions
    summary = VARIANT_SUMMARIES.get(variant, VARIANT_SUMMARIES["backend_sde"])
    skills = VARIANT_SKILLS_EMPHASIS.get(variant, VARIANT_SKILLS_EMPHASIS["backend_sde"])

    tailored = template.replace("{{SUMMARY}}", summary)
    tailored = template if "{{SUMMARY}}" not in template else tailored
    tailored = tailored.replace("{{SKILLS_LINE}}", skills)

    # Write tailored .tex file
    tex_filename = f"resume_{company}_{title}.tex"
    tex_path = os.path.join(OUTPUT_DIR, tex_filename)

    # Sanitize for LaTeX (escape special chars in the substituted text)
    with open(tex_path, 'w') as f:
        f.write(tailored)

    # Compile to PDF
    pdf_path = _compile_latex(tex_path)
    if pdf_path:
        logger.info(f"Generated tailored resume: {pdf_path}")
    else:
        logger.warning(f"Failed to compile resume for {company} - {title}")

    return pdf_path


def tailor_resumes(scored_jobs: list[ScoredJob], config: dict) -> dict[str, str]:
    """
    Generate tailored resumes for all jobs above the tailor threshold.
    Returns a dict mapping job_id -> pdf_path.
    """
    threshold = config.get("search", {}).get("tailor_threshold", 7)
    results = {}

    high_scoring = [sj for sj in scored_jobs if sj.score >= threshold]
    logger.info(f"Tailoring resumes for {len(high_scoring)} jobs (score >= {threshold})")

    for sj in high_scoring:
        pdf_path = tailor_resume(sj)
        if pdf_path:
            results[sj.listing.job_id] = pdf_path

    return results


def _compile_latex(tex_path: str) -> str | None:
    """Compile a .tex file to PDF using pdflatex."""
    output_dir = os.path.dirname(tex_path)

    try:
        result = subprocess.run(
            [
                "pdflatex",
                "-interaction=nonstopmode",
                "-output-directory", output_dir,
                tex_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        pdf_path = tex_path.replace(".tex", ".pdf")
        if os.path.exists(pdf_path):
            # Clean up auxiliary files
            for ext in [".aux", ".log", ".out"]:
                aux_file = tex_path.replace(".tex", ext)
                if os.path.exists(aux_file):
                    os.remove(aux_file)
            return pdf_path
        else:
            logger.error(f"pdflatex produced no PDF. Stderr: {result.stderr[:500]}")
            return None
    except subprocess.TimeoutExpired:
        logger.error(f"pdflatex timed out for {tex_path}")
        return None
    except FileNotFoundError:
        logger.error("pdflatex not found — install texlive")
        return None


def _sanitize_filename(name: str) -> str:
    """Sanitize a string for use in filenames."""
    clean = re.sub(r'[^\w\s-]', '', name)
    clean = re.sub(r'\s+', '_', clean)
    return clean[:30].strip('_')
