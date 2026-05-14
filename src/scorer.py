"""
LLM scorer using LangChain + GPT-4o-mini with Pydantic structured output.

Mirrors the design of llm_analysis.py in pietroruzzante/linkedin_scraper_pipeline.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.prompts import EXTRACT_KEYWORDS_PROMPT, RANK_OFFERS_PROMPT
from src.scraper import JobListing

logger = logging.getLogger(__name__)


class ScoredOffer(BaseModel):
    id: int = Field(description="Unique identifier of the job offer")
    title: str = Field(description="Job title")
    company: str = Field(description="Company name")
    link: str = Field(description="URL of the job offer")
    score: int = Field(ge=1, le=10, description="Relevance score, 1-10")
    comment: str = Field(description="Brief explanation of the score, 1 sentence")
    summary: str = Field(description="Brief summary of the offer, 2-3 sentences")


class RankedOffers(BaseModel):
    offers: list[ScoredOffer]


class KeywordList(BaseModel):
    keywords: list[str]


@dataclass
class ScoredJob:
    """Job listing enriched with LLM score and metadata."""

    listing: JobListing
    score: int
    comment: str
    summary: str
    keywords: list[str]


def _llm(model: str = "gpt-4o-mini") -> ChatOpenAI:
    return ChatOpenAI(model=model, temperature=0, model_kwargs={"seed": 42})


def _rank_chain():
    return (
        ChatPromptTemplate.from_messages(
            [("system", RANK_OFFERS_PROMPT), ("human", "{offers}")]
        )
        | _llm().with_structured_output(RankedOffers, method="function_calling")
    )


def _keywords_chain():
    return (
        ChatPromptTemplate.from_messages(
            [("system", EXTRACT_KEYWORDS_PROMPT), ("human", "{offer_description}")]
        )
        | _llm().with_structured_output(KeywordList, method="function_calling")
    )


def _offers_payload(jobs: list[JobListing]) -> list[dict]:
    """Build a minimal JSON-serializable payload for the LLM."""
    return [
        {
            "id": i,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "link": j.url,
            "description": j.description[:3000],
        }
        for i, j in enumerate(jobs)
    ]


def rank_offers(
    jobs: list[JobListing],
    role: str,
    candidate_profile: str,
    cv_text: str,
    priority_keywords: list[str],
) -> list[ScoredJob]:
    """Rank a batch of offers with the LLM."""
    if not jobs:
        return []
    if not os.environ.get("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY not set — skipping LLM ranking")
        return []

    logger.info(f"Requesting LLM ranking of {len(jobs)} offers")
    result = _rank_chain().invoke(
        {
            "role": role,
            "candidate_profile": candidate_profile,
            "cv": cv_text,
            "priority_keywords": json.dumps(priority_keywords),
            "offers": json.dumps(_offers_payload(jobs)),
        }
    )
    if isinstance(result, dict):
        result = RankedOffers(**result)

    scored: list[ScoredJob] = []
    for offer in result.offers:
        try:
            listing = jobs[offer.id]
        except IndexError:
            logger.warning(f"LLM returned out-of-range id {offer.id}; skipping")
            continue
        scored.append(
            ScoredJob(
                listing=listing,
                score=offer.score,
                comment=offer.comment,
                summary=offer.summary,
                keywords=[],
            )
        )

    scored.sort(key=lambda s: s.score, reverse=True)
    if scored:
        logger.info(f"Ranking done. Top score: {scored[0].score}")
    return scored


def extract_keywords(description: str) -> list[str]:
    """Run the ATS keyword extraction chain on a single JD."""
    if not description.strip():
        return []
    result = _keywords_chain().invoke({"offer_description": description})
    if isinstance(result, dict):
        result = KeywordList(**result)
    logger.info(f"  → keywords: {result.keywords}")
    return result.keywords


def score_jobs(jobs: list[JobListing], config: dict) -> list[ScoredJob]:
    """Top-level entry point used by main.py."""
    scoring = config.get("scoring", {})
    search = config.get("search", {})
    role = (search.get("roles") or search.get("keywords") or ["software engineer"])[0]
    profile = scoring.get("candidate_profile", "")
    priority_keywords = search.get("priority_keywords", [])

    cv_text = ""
    cv_path = os.environ.get("CV_PATH")
    if cv_path and os.path.exists(cv_path):
        from src.cv_parser import parse_cv

        cv_text = parse_cv(cv_path)
    else:
        logger.warning("CV_PATH not set or file missing — ranking without CV text")

    return rank_offers(
        jobs=jobs,
        role=role,
        candidate_profile=profile,
        cv_text=cv_text,
        priority_keywords=priority_keywords,
    )
