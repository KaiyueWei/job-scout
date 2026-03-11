"""
Filter module.
Deduplicates listings, filters by location and recency.
Maintains a seen-jobs cache to avoid re-processing across runs.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.scraper import JobListing

logger = logging.getLogger(__name__)

SEEN_JOBS_FILE = "output/seen_jobs.json"

# Location patterns for North America + remote-Canada filtering
CANADA_PATTERNS = [
    r'\bcanada\b', r'\bvancouver\b', r'\btoronto\b', r'\bmontreal\b',
    r'\bcalgary\b', r'\bottawa\b', r'\bwaterloo\b', r'\b(?:bc|on|qc|ab)\b',
    r'\bbritish columbia\b', r'\bontario\b', r'\bquebec\b', r'\balberta\b',
]
US_PATTERNS = [
    r'\bunited states\b', r'\busa\b', r'\bus\b',
    r'\bsan francisco\b', r'\bseattle\b', r'\bnew york\b', r'\baustin\b',
    r'\bremote\b.*\b(?:us|usa|united states|north america)\b',
]
REMOTE_PATTERNS = [
    r'\bremote\b', r'\bwork from home\b', r'\banywhere\b',
    r'\bdistributed\b', r'\bfully remote\b',
]


def load_seen_jobs() -> set[str]:
    """Load previously seen job IDs from cache file."""
    if os.path.exists(SEEN_JOBS_FILE):
        try:
            with open(SEEN_JOBS_FILE, 'r') as f:
                data = json.load(f)
                # Keep only IDs from the last 7 days to prevent unbounded growth
                cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
                return {
                    k for k, v in data.items()
                    if v.get("seen_at", "") > cutoff
                }
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def save_seen_jobs(seen: dict):
    """Save seen job IDs to cache file."""
    os.makedirs(os.path.dirname(SEEN_JOBS_FILE), exist_ok=True)
    # Keep only last 7 days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    pruned = {k: v for k, v in seen.items() if v.get("seen_at", "") > cutoff}
    with open(SEEN_JOBS_FILE, 'w') as f:
        json.dump(pruned, f, indent=2)


def _matches_location(job: JobListing) -> bool:
    """Check if job location matches North America + remote criteria."""
    text = f"{job.location} {job.title} {job.description[:500]}".lower()

    # Check Canada locations
    for pattern in CANADA_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    # Check US locations (only if remote-friendly for visa reasons)
    for pattern in US_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            # US jobs are only useful if remote
            if any(re.search(rp, text, re.IGNORECASE) for rp in REMOTE_PATTERNS):
                return True
            # Or if no location restriction mentioned
            if "remote" in text:
                return True

    # Check generic remote
    for pattern in REMOTE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    return False


def _is_recent(job: JobListing, max_age_hours: int) -> bool:
    """Check if job was posted within the time window."""
    if not job.posted_at:
        # If no date, include it (benefit of the doubt)
        return True

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    return job.posted_at >= cutoff


def _is_likely_intern_coop(job: JobListing) -> bool:
    """Verify the job is actually an intern/co-op role (not senior)."""
    title_lower = job.title.lower()
    text = f"{title_lower} {job.description[:300].lower()}"

    # Must have intern/co-op signal
    has_intern_signal = any(kw in text for kw in [
        "intern", "co-op", "coop", "co op", "new grad", "entry level",
        "junior", "student", "practicum", "apprentice",
    ])

    # Exclude senior/lead/manager roles
    is_senior = any(kw in title_lower for kw in [
        "senior", "sr.", "lead", "principal", "staff", "manager",
        "director", "architect", "vp ", "head of",
    ])

    return has_intern_signal and not is_senior


def filter_jobs(jobs: list[JobListing], config: dict) -> list[JobListing]:
    """
    Apply all filters:
    1. Deduplicate by URL
    2. Remove previously seen jobs
    3. Filter by location (North America + remote)
    4. Filter by recency
    5. Verify intern/co-op level
    """
    max_age = config.get("search", {}).get("max_age_hours", 24)
    seen_ids = load_seen_jobs()
    seen_dict = {}

    # Load existing seen data for merging
    if os.path.exists(SEEN_JOBS_FILE):
        try:
            with open(SEEN_JOBS_FILE, 'r') as f:
                seen_dict = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    # Step 1: Deduplicate by URL
    seen_urls = set()
    deduped = []
    for job in jobs:
        url_key = job.url.split("?")[0].rstrip("/")  # Normalize URL
        if url_key not in seen_urls:
            seen_urls.add(url_key)
            deduped.append(job)
    logger.info(f"After dedup: {len(deduped)} (removed {len(jobs) - len(deduped)} duplicates)")

    # Step 2: Remove previously seen
    new_jobs = [j for j in deduped if j.job_id not in seen_ids]
    logger.info(f"After removing seen: {len(new_jobs)} (skipped {len(deduped) - len(new_jobs)} seen)")

    # Step 3: Location filter
    located = [j for j in new_jobs if _matches_location(j)]
    logger.info(f"After location filter: {len(located)}")

    # Step 4: Recency filter
    recent = [j for j in located if _is_recent(j, max_age)]
    logger.info(f"After recency filter: {len(recent)}")

    # Step 5: Intern/co-op verification
    verified = [j for j in recent if _is_likely_intern_coop(j)]
    logger.info(f"After intern/co-op verification: {len(verified)}")

    # Mark all processed jobs as seen
    now = datetime.now(timezone.utc).isoformat()
    for job in deduped:
        seen_dict[job.job_id] = {
            "title": job.title,
            "seen_at": now,
        }
    save_seen_jobs(seen_dict)

    return verified
