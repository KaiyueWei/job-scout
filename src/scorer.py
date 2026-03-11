"""
Scorer module.
Uses Claude API to score each job listing against the candidate profile
and recommend a resume variant.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

import anthropic

from src.scraper import JobListing

logger = logging.getLogger(__name__)


@dataclass
class ScoredJob:
    """Job listing with fit score and recommendations."""
    listing: JobListing
    score: int  # 1-10
    variant: str  # Recommended resume variant
    reasoning: str  # Why this score
    tailoring_notes: str  # Specific suggestions for tailoring


SCORING_PROMPT = """You are evaluating a job listing against a candidate profile for fit.

<candidate_profile>
{profile}
</candidate_profile>

<job_listing>
Title: {title}
Company: {company}
Location: {location}
Source: {source}

Description:
{description}
</job_listing>

<available_resume_variants>
{variants}
</available_resume_variants>

Evaluate this job listing and respond with ONLY a JSON object (no markdown, no backticks):
{{
    "score": <1-10 integer>,
    "variant": "<recommended variant name from the list above>",
    "reasoning": "<1-2 sentences explaining the score>",
    "tailoring_notes": "<specific keywords, skills, or experiences to emphasize in the resume for this role>"
}}

Scoring criteria:
- 9-10: Almost perfect match — role matches core skills, level is right, location works
- 7-8: Strong match — most requirements align, minor gaps
- 5-6: Decent match — some alignment but notable gaps or uncertainty
- 3-4: Weak match — significant misalignment in skills or level
- 1-2: Poor match — wrong field, wrong level, or clearly not suitable

Be honest and calibrated. Most intern/co-op SDE roles for this candidate should score 6-8.
A role requiring 3+ years experience should score lower. A Go/distributed systems role should score higher."""


def score_jobs(
    jobs: list[JobListing],
    config: dict,
) -> list[ScoredJob]:
    """Score each job listing using Claude API."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set — skipping scoring")
        # Return all jobs with default score
        return [
            ScoredJob(
                listing=job,
                score=5,
                variant="backend_sde",
                reasoning="Scoring unavailable (no API key)",
                tailoring_notes="",
            )
            for job in jobs
        ]

    client = anthropic.Anthropic(api_key=api_key)
    profile = config.get("scoring", {}).get("candidate_profile", "")
    variants_list = config.get("scoring", {}).get("resume_variants", [])
    variants_str = "\n".join(
        f"- {v['name']}: {v['description']}" for v in variants_list
    )

    scored = []
    for i, job in enumerate(jobs):
        logger.info(f"Scoring {i+1}/{len(jobs)}: {job.title} @ {job.company}")
        try:
            prompt = SCORING_PROMPT.format(
                profile=profile,
                title=job.title,
                company=job.company,
                location=job.location,
                source=job.source,
                description=job.description[:3000],  # Truncate long descriptions
                variants=variants_str,
            )

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()
            # Clean potential markdown fences
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

            data = json.loads(text)

            scored.append(ScoredJob(
                listing=job,
                score=int(data.get("score", 5)),
                variant=data.get("variant", "backend_sde"),
                reasoning=data.get("reasoning", ""),
                tailoring_notes=data.get("tailoring_notes", ""),
            ))

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse scoring response for {job.title}: {e}")
            scored.append(ScoredJob(
                listing=job, score=5, variant="backend_sde",
                reasoning="Parse error", tailoring_notes="",
            ))
        except Exception as e:
            logger.warning(f"Scoring failed for {job.title}: {e}")
            scored.append(ScoredJob(
                listing=job, score=5, variant="backend_sde",
                reasoning=f"Error: {e}", tailoring_notes="",
            ))

    # Sort by score descending
    scored.sort(key=lambda s: s.score, reverse=True)
    logger.info(f"Scoring complete. Top score: {scored[0].score if scored else 'N/A'}")

    return scored
