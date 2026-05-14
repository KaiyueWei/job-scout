"""
LinkedIn job scraper.

Uses LinkedIn's public guest jobs API plus BeautifulSoup to parse listings.
Mirrors the approach used by pietroruzzante/linkedin_scraper_pipeline.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

LINKEDIN_SEARCH_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class JobListing:
    """Standardized LinkedIn job listing."""

    title: str
    company: str
    location: str
    url: str
    source: str = "LinkedIn"
    description: str = ""
    job_id: str = ""
    language: str = "english"

    def __post_init__(self) -> None:
        if not self.job_id:
            self.job_id = str(hash(self.url.split("?")[0]))


def _hours_to_f_tpr(hours: int) -> str:
    """LinkedIn's f_TPR parameter expects 'r<seconds>'."""
    return f"r{int(hours) * 3600}"


def request_offers(role: str, location: str, max_age_hours: int) -> str:
    """Query LinkedIn's guest jobs API. Returns raw HTML."""
    params = {
        "keywords": role,
        "location": location,
        "f_TPR": _hours_to_f_tpr(max_age_hours),
    }
    headers = {"User-Agent": USER_AGENT}

    resp = requests.get(LINKEDIN_SEARCH_URL, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.text


def _request_description(offer_link: str) -> str:
    """Fetch the JD detail page and return raw HTML."""
    time.sleep(1)  # be polite
    resp = requests.get(offer_link, headers={"User-Agent": USER_AGENT}, timeout=15)
    resp.raise_for_status()
    return resp.text


def _parse_description(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    div = soup.find("div", class_="description__text")
    if div is None:
        return ""
    return div.get_text(strip=True)


def parse_offers(
    html_string: str, fallback_location: str
) -> list[JobListing]:
    """Parse the search-results HTML into JobListing objects."""
    soup = BeautifulSoup(html_string, "html.parser")
    cards = soup.find_all("li")
    offers: list[JobListing] = []

    for card in cards:
        title_el = card.find("h3", class_="base-search-card__title")
        company_el = card.find("h4", class_="base-search-card__subtitle")
        location_el = card.find("div", class_="base-search-card__metadata")
        link_el = card.find("a")

        if not all([title_el, company_el, location_el, link_el]):
            continue

        company_a = company_el.find("a")
        location_span = location_el.find("span")
        if not all([company_a, location_span]):
            continue

        title = title_el.get_text(strip=True)
        company = company_a.get_text(strip=True)
        location = location_span.get_text(strip=True) or fallback_location
        link = link_el.get("href", "")
        if not link:
            continue

        try:
            description = _parse_description(_request_description(link))
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch JD for {title} @ {company}: {e}")
            description = ""

        offers.append(
            JobListing(
                title=title,
                company=company,
                location=location,
                url=link,
                description=description,
            )
        )

    return offers


def scrape_all(config: dict) -> list[JobListing]:
    """Run a LinkedIn search per (role, location) pair from config.

    Config shape (search section):
        roles: ["software engineer intern", ...]
        locations: ["Vancouver", "Toronto", ...]
        max_age_hours: 24
    """
    search = config.get("search", {})
    roles: list[str] = search.get("roles") or search.get("keywords", [])
    locations: list[str] = search.get("locations", [])
    max_age_hours: int = int(search.get("max_age_hours", 24))

    if not roles or not locations:
        logger.error("config.search.roles and config.search.locations are required")
        return []

    all_offers: list[JobListing] = []
    for role in roles:
        for location in locations:
            logger.info(f"LinkedIn search: '{role}' in '{location}'")
            try:
                html = request_offers(role, location, max_age_hours)
                offers = parse_offers(html, fallback_location=location)
                logger.info(f"  → {len(offers)} listings")
                all_offers.extend(offers)
            except requests.RequestException as e:
                logger.warning(f"LinkedIn search failed for '{role}' / '{location}': {e}")
            time.sleep(1)

    logger.info(f"Total raw LinkedIn listings: {len(all_offers)}")
    return all_offers
