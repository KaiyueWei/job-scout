"""
Job scraper module.
Fetches job listings from free sources:
- Indeed RSS feeds (no auth required)
- Adzuna API (free tier, optional)
- Arbeitnow API (no auth required)
- Remotive API (no auth, remote jobs only)
"""

import os
import re
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus

import feedparser
import requests

logger = logging.getLogger(__name__)


@dataclass
class JobListing:
    """Standardized job listing across all sources."""
    title: str
    company: str
    location: str
    url: str
    source: str
    description: str = ""
    posted_at: Optional[datetime] = None
    salary: str = ""
    job_id: str = ""

    def __post_init__(self):
        if not self.job_id:
            # Generate a stable ID from URL
            self.job_id = str(hash(self.url))


def scrape_indeed_rss(keywords: list[str], locations: list[str]) -> list[JobListing]:
    """
    Fetch jobs from Indeed RSS feeds.
    Indeed RSS format: https://www.indeed.com/rss?q=QUERY&l=LOCATION&sort=date
    Note: Indeed may block or limit RSS feeds. This is best-effort.
    """
    jobs = []
    # Use a subset of keyword+location combos to avoid rate limiting
    search_pairs = []
    priority_keywords = [
        "software engineer intern",
        "software developer co-op",
        "backend engineer intern",
        "devops intern",
    ]
    priority_locations = ["Canada", "Remote", "Vancouver"]

    for kw in priority_keywords:
        for loc in priority_locations:
            search_pairs.append((kw, loc))

    for keyword, location in search_pairs:
        url = (
            f"https://www.indeed.com/rss"
            f"?q={quote_plus(keyword)}"
            f"&l={quote_plus(location)}"
            f"&sort=date"
            f"&fromage=1"  # Last 24 hours
        )
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                # Parse location from title if possible
                # Indeed titles often look like "Job Title - Company - Location"
                title = entry.get("title", "")
                link = entry.get("link", "")
                summary = entry.get("summary", "")
                published = entry.get("published_parsed")

                posted = None
                if published:
                    posted = datetime(*published[:6], tzinfo=timezone.utc)

                # Try to extract company from Indeed's format
                company = ""
                if " - " in title:
                    parts = title.rsplit(" - ", 2)
                    if len(parts) >= 2:
                        company = parts[-1].strip()
                        title = parts[0].strip()

                jobs.append(JobListing(
                    title=title,
                    company=company,
                    location=location,
                    url=link,
                    source="Indeed",
                    description=_strip_html(summary),
                    posted_at=posted,
                ))
            logger.info(f"Indeed RSS: {len(feed.entries)} results for '{keyword}' in '{location}'")
        except Exception as e:
            logger.warning(f"Indeed RSS failed for '{keyword}' in '{location}': {e}")

        time.sleep(1)  # Rate limiting

    return jobs


def scrape_adzuna(keywords: list[str], locations: list[str]) -> list[JobListing]:
    """
    Fetch jobs from Adzuna API (free tier: 250 req/day).
    Requires ADZUNA_APP_ID and ADZUNA_APP_KEY env vars.
    Supports: ca (Canada), us (United States).
    """
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")

    if not app_id or not app_key:
        logger.info("Adzuna credentials not set, skipping")
        return []

    jobs = []
    # Map to Adzuna country codes
    country_searches = [
        ("ca", "software intern"),
        ("ca", "software co-op"),
        ("ca", "devops intern"),
        ("us", "software engineer intern remote"),
        ("us", "backend engineer intern remote"),
    ]

    for country, query in country_searches:
        url = (
            f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
            f"?app_id={app_id}"
            f"&app_key={app_key}"
            f"&results_per_page=20"
            f"&what={quote_plus(query)}"
            f"&max_days_old=1"
            f"&sort_by=date"
            f"&content-type=application/json"
        )
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            for result in data.get("results", []):
                posted = None
                created = result.get("created")
                if created:
                    try:
                        posted = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

                loc = result.get("location", {})
                location_str = ", ".join(filter(None, loc.get("area", [])))

                jobs.append(JobListing(
                    title=result.get("title", ""),
                    company=result.get("company", {}).get("display_name", ""),
                    location=location_str or country.upper(),
                    url=result.get("redirect_url", ""),
                    source="Adzuna",
                    description=_strip_html(result.get("description", "")),
                    posted_at=posted,
                    salary=result.get("salary_display_value", ""),
                    job_id=str(result.get("id", "")),
                ))
            logger.info(f"Adzuna: {len(data.get('results', []))} results for '{query}' in {country}")
        except Exception as e:
            logger.warning(f"Adzuna failed for '{query}' in {country}: {e}")

        time.sleep(0.5)

    return jobs


def scrape_arbeitnow() -> list[JobListing]:
    """
    Fetch jobs from Arbeitnow API (free, no auth).
    Good for remote-friendly tech roles.
    https://www.arbeitnow.com/api/job-board-api
    """
    jobs = []
    url = "https://www.arbeitnow.com/api/job-board-api?page=1"

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("data", []):
            tags = [t.lower() for t in item.get("tags", [])]
            title_lower = item.get("title", "").lower()

            # Filter for relevant roles
            is_relevant = any(kw in title_lower for kw in [
                "intern", "co-op", "coop", "junior", "entry",
                "software", "backend", "devops", "sre", "platform",
            ])
            if not is_relevant:
                continue

            posted = None
            created = item.get("created_at")
            if created:
                try:
                    posted = datetime.fromtimestamp(created, tz=timezone.utc)
                except (ValueError, TypeError, OSError):
                    pass

            jobs.append(JobListing(
                title=item.get("title", ""),
                company=item.get("company_name", ""),
                location=item.get("location", "Remote"),
                url=item.get("url", ""),
                source="Arbeitnow",
                description=_strip_html(item.get("description", "")),
                posted_at=posted,
                job_id=str(item.get("slug", "")),
            ))
        logger.info(f"Arbeitnow: {len(jobs)} relevant results")
    except Exception as e:
        logger.warning(f"Arbeitnow failed: {e}")

    return jobs


def scrape_remotive() -> list[JobListing]:
    """
    Fetch remote jobs from Remotive API (free, no auth).
    https://remotive.com/api/remote-jobs
    """
    jobs = []
    url = "https://remotive.com/api/remote-jobs?category=software-dev&limit=50"

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("jobs", []):
            title_lower = item.get("title", "").lower()

            is_relevant = any(kw in title_lower for kw in [
                "intern", "co-op", "coop", "junior", "entry level",
            ])
            if not is_relevant:
                continue

            posted = None
            pub_date = item.get("publication_date")
            if pub_date:
                try:
                    posted = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            # Check if candidate_required_location includes NA
            req_location = item.get("candidate_required_location", "")

            jobs.append(JobListing(
                title=item.get("title", ""),
                company=item.get("company_name", ""),
                location=req_location or "Remote",
                url=item.get("url", ""),
                source="Remotive",
                description=_strip_html(item.get("description", "")),
                posted_at=posted,
                salary=item.get("salary", ""),
                job_id=str(item.get("id", "")),
            ))
        logger.info(f"Remotive: {len(jobs)} relevant results")
    except Exception as e:
        logger.warning(f"Remotive failed: {e}")

    return jobs


def scrape_all(config: dict) -> list[JobListing]:
    """Run all scrapers and return combined results."""
    keywords = config.get("search", {}).get("keywords", [])
    locations = config.get("search", {}).get("locations", [])

    all_jobs = []

    logger.info("Starting job scrape...")
    all_jobs.extend(scrape_indeed_rss(keywords, locations))
    all_jobs.extend(scrape_adzuna(keywords, locations))
    all_jobs.extend(scrape_arbeitnow())
    all_jobs.extend(scrape_remotive())

    logger.info(f"Total raw listings: {len(all_jobs)}")
    return all_jobs


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    clean = re.sub(r'<[^>]+>', ' ', text)
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()
