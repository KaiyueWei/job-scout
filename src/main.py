"""
Job Scout — Main Orchestrator.

Pipeline:
1. Scrape LinkedIn (guest API + BeautifulSoup)
2. Dedup, drop seen jobs, pre-filter by exclude_keywords
3. Rank with GPT-4o-mini via LangChain (structured output)
4. For high-scoring offers, extract ATS keywords and tailor a DOCX → PDF CV
5. Send digest via Gmail SMTP with attached PDFs
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.emailer import send_digest
from src.filter import filter_jobs
from src.scorer import extract_keywords, score_jobs
from src.scraper import scrape_all
from src.tailor import tailor_resumes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    config_path = Path("config/profile.yaml")
    if not config_path.exists():
        logger.error("Config file not found: config/profile.yaml")
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f)


def main() -> None:
    load_dotenv()

    logger.info("=" * 60)
    logger.info("JOB SCOUT — Starting run")
    logger.info("=" * 60)

    config = load_config()
    logger.info(f"Profile loaded: {config['profile']['name']}")

    logger.info("--- STEP 1: Scraping LinkedIn ---")
    raw_jobs = scrape_all(config)
    if not raw_jobs:
        logger.warning("No jobs scraped. Exiting.")
        return

    logger.info("--- STEP 2: Filtering ---")
    filtered = filter_jobs(raw_jobs, config)
    if not filtered:
        logger.info("No new jobs after filtering. Nothing to send.")
        return

    logger.info(f"--- STEP 3: Ranking {len(filtered)} offers with GPT-4o-mini ---")
    scored = score_jobs(filtered, config)
    if not scored:
        logger.info("No offers ranked. Exiting.")
        return

    threshold = config.get("search", {}).get("tailor_threshold", 8)
    high = [sj for sj in scored if sj.score >= threshold]
    logger.info(f"Above tailor threshold ({threshold}): {len(high)}/{len(scored)}")

    logger.info("--- STEP 4: Extracting ATS keywords for high-score offers ---")
    for sj in high:
        try:
            sj.keywords = extract_keywords(sj.listing.description)
        except Exception as e:
            logger.warning(f"Keyword extraction failed for {sj.listing.title}: {e}")

    logger.info("--- STEP 5: Tailoring CVs ---")
    resume_map = tailor_resumes(scored, config)

    logger.info("--- STEP 6: Sending digest ---")
    send_digest(scored, resume_map, config)

    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info(
        f"  Scraped: {len(raw_jobs)} | Filtered: {len(filtered)} | "
        f"Ranked: {len(scored)} | Tailored: {len(resume_map)}"
    )
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
