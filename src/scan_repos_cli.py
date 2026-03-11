"""
Standalone repo scanner CLI.
Used by the weekly GitHub Actions workflow to scan repos and update profile.
"""

import logging
import os
import sys

import yaml

from src.repo_scanner import scan_repos, update_profile_skills, generate_scan_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main():
    username = os.environ.get("GITHUB_USERNAME", "KaiyueWei")
    token = os.environ.get("GITHUB_TOKEN")  # Optional, increases rate limit

    logger.info(f"Scanning repos for: {username}")

    # Load config
    with open("config/profile.yaml") as f:
        config = yaml.safe_load(f)

    # Scan
    repos = scan_repos(username, token)

    # Update profile
    updated = update_profile_skills(repos, config)
    if updated:
        logger.info("Profile updated with new tech stack data")
    else:
        logger.info("No profile changes needed")

    # Generate report
    report = generate_scan_report(repos)
    if report:
        logger.info("Scan report:")
        # Strip HTML for console output
        import re
        clean = re.sub(r'<[^>]+>', ' ', report)
        clean = re.sub(r'\s+', ' ', clean).strip()
        logger.info(clean[:500])

    # Summary
    new_count = sum(1 for r in repos if r.is_new)
    updated_count = sum(1 for r in repos if r.is_updated)
    logger.info(f"Done: {len(repos)} total repos, {new_count} new, {updated_count} updated")


if __name__ == "__main__":
    main()
