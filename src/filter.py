"""
Lightweight filter for LinkedIn offers.

- Deduplicates by normalized URL
- Drops previously seen jobs (7-day cache)
- Pre-filters by exclude_keywords (e.g. "principal", "10+ years")
- Optional location-string filter to keep North America / remote
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

from src.scraper import JobListing

logger = logging.getLogger(__name__)

SEEN_JOBS_FILE = "output/seen_jobs.json"

EXCLUDE_LOCATION_PATTERNS = [
    r"\bgermany\b", r"\bdeutschland\b", r"\bberlin\b", r"\bmunich\b",
    r"\bunited kingdom\b", r"\buk\b", r"\blondon\b", r"\bmanchester\b",
    r"\baustralia\b", r"\bsydney\b", r"\bmelbourne\b",
    r"\bindia\b", r"\bbangalore\b", r"\bmumbai\b",
    r"\beurope\b", r"\beu\b",
]


def _load_seen() -> dict:
    if not os.path.exists(SEEN_JOBS_FILE):
        return {}
    try:
        with open(SEEN_JOBS_FILE) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    return {k: v for k, v in data.items() if v.get("seen_at", "") > cutoff}


def _save_seen(seen: dict) -> None:
    os.makedirs(os.path.dirname(SEEN_JOBS_FILE), exist_ok=True)
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(seen, f, indent=2)


def _location_excluded(job: JobListing) -> bool:
    text = job.location.lower()
    return any(re.search(p, text) for p in EXCLUDE_LOCATION_PATTERNS)


def _has_exclude_keyword(job: JobListing, exclude_keywords: list[str]) -> bool:
    text = f"{job.title} {job.description}".lower()
    return any(kw.lower() in text for kw in exclude_keywords)


def filter_jobs(jobs: list[JobListing], config: dict) -> list[JobListing]:
    search = config.get("search", {})
    exclude_keywords: list[str] = search.get("exclude_keywords", [])

    seen = _load_seen()

    # 1. Dedup by normalized URL
    url_seen: set[str] = set()
    deduped: list[JobListing] = []
    for job in jobs:
        key = job.url.split("?")[0].rstrip("/")
        if key in url_seen:
            continue
        url_seen.add(key)
        deduped.append(job)
    logger.info(f"After dedup: {len(deduped)} (removed {len(jobs) - len(deduped)})")

    # 2. Drop previously seen
    new = [j for j in deduped if j.job_id not in seen]
    logger.info(f"After seen-jobs filter: {len(new)} (skipped {len(deduped) - len(new)})")

    # 3. Location filter
    located = [j for j in new if not _location_excluded(j)]
    logger.info(f"After location filter: {len(located)}")

    # 4. Exclude-keyword pre-filter
    pre = [j for j in located if not _has_exclude_keyword(j, exclude_keywords)]
    logger.info(f"After exclude-keyword filter: {len(pre)}")

    # Mark all deduped jobs as seen
    now = datetime.now(timezone.utc).isoformat()
    for job in deduped:
        seen[job.job_id] = {"title": job.title, "seen_at": now}
    _save_seen(seen)

    return pre
