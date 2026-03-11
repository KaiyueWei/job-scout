"""
Job Scout Pipeline — Main Orchestrator.

Runs the full pipeline:
1. Scrape jobs from free APIs
2. Filter by location, recency, and level
3. Score against candidate profile using Claude API
4. Generate tailored resumes for high-scoring matches
5. Send email digest
"""

import logging
import sys
from pathlib import Path

import yaml

from src.scraper import scrape_all
from src.filter import filter_jobs
from src.scorer import score_jobs
from src.tailor import tailor_resumes
from src.emailer import send_digest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load configuration from profile.yaml."""
    config_path = Path("config/profile.yaml")
    if not config_path.exists():
        logger.error("Config file not found: config/profile.yaml")
        sys.exit(1)

    with open(config_path) as f:
        return yaml.safe_load(f)


def main():
    logger.info("=" * 60)
    logger.info("JOB SCOUT PIPELINE — Starting run")
    logger.info("=" * 60)

    # Load config
    config = load_config()
    logger.info(f"Profile loaded: {config['profile']['name']}")

    # Step 1: Scrape
    logger.info("\n--- STEP 1: Scraping job listings ---")
    raw_jobs = scrape_all(config)
    if not raw_jobs:
        logger.warning("No jobs scraped from any source. Exiting.")
        return

    # Step 2: Filter
    logger.info("\n--- STEP 2: Filtering ---")
    filtered_jobs = filter_jobs(raw_jobs, config)
    if not filtered_jobs:
        logger.info("No new jobs after filtering. Nothing to report.")
        return

    # Step 3: Score
    logger.info(f"\n--- STEP 3: Scoring {len(filtered_jobs)} jobs ---")
    scored_jobs = score_jobs(filtered_jobs, config)

    # Log score distribution
    min_score = config.get("search", {}).get("min_score", 5)
    above_threshold = [sj for sj in scored_jobs if sj.score >= min_score]
    logger.info(f"Jobs above min_score ({min_score}): {len(above_threshold)}/{len(scored_jobs)}")

    if not above_threshold:
        logger.info("No jobs above minimum score. Skipping digest.")
        return

    # Step 4: Tailor resumes for high-scoring matches
    logger.info(f"\n--- STEP 4: Tailoring resumes ---")
    resume_map = tailor_resumes(scored_jobs, config)

    # Step 5: Send digest
    logger.info(f"\n--- STEP 5: Sending digest ---")
    send_digest(above_threshold, resume_map, config)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info(f"  Scraped:  {len(raw_jobs)} raw listings")
    logger.info(f"  Filtered: {len(filtered_jobs)} after dedup/location/recency")
    logger.info(f"  Scored:   {len(scored_jobs)} total, {len(above_threshold)} above threshold")
    logger.info(f"  Tailored: {len(resume_map)} resumes generated")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
