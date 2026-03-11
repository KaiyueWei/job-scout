"""
GitHub repo scanner module.
Scans your public GitHub repos to detect new/updated projects,
extract tech stacks, and update the candidate profile and resume template.

Runs weekly on a separate schedule.
Uses GitHub's public API (no auth needed for public repos, but a token increases rate limits).
"""

import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
import yaml

logger = logging.getLogger(__name__)

REPO_CACHE_FILE = "output/repo_cache.json"
PROFILE_PATH = "config/profile.yaml"


@dataclass
class RepoInfo:
    """Parsed info about a GitHub repository."""
    name: str
    description: str
    url: str
    languages: dict[str, int]  # language -> bytes
    topics: list[str]
    stars: int
    updated_at: str
    created_at: str
    default_branch: str
    has_readme: bool = False
    readme_excerpt: str = ""
    tech_stack: list[str] = field(default_factory=list)
    is_new: bool = False
    is_updated: bool = False


def fetch_repos(username: str, token: Optional[str] = None) -> list[dict]:
    """Fetch all public repos for a GitHub user."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    repos = []
    page = 1
    while True:
        url = f"https://api.github.com/users/{username}/repos?per_page=100&page={page}&sort=updated"
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        repos.extend(data)
        page += 1
        if len(data) < 100:
            break

    logger.info(f"Fetched {len(repos)} repos for {username}")
    return repos


def fetch_languages(repo_full_name: str, token: Optional[str] = None) -> dict[str, int]:
    """Fetch language breakdown for a repo."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    url = f"https://api.github.com/repos/{repo_full_name}/languages"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"Failed to fetch languages for {repo_full_name}: {e}")
        return {}


def fetch_readme_excerpt(repo_full_name: str, token: Optional[str] = None) -> str:
    """Fetch first 500 chars of README for tech stack extraction."""
    headers = {"Accept": "application/vnd.github.v3.raw"}
    if token:
        headers["Authorization"] = f"token {token}"

    url = f"https://api.github.com/repos/{repo_full_name}/readme"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.text[:2000]
    except Exception:
        pass
    return ""


def extract_tech_stack(repo: dict, languages: dict, readme: str) -> list[str]:
    """
    Extract tech stack from repo metadata, languages, and README.
    Returns a list of technology keywords.
    """
    stack = set()

    # From GitHub language detection
    lang_map = {
        "Go": "Go", "Python": "Python", "TypeScript": "TypeScript",
        "JavaScript": "JavaScript", "Rust": "Rust", "Java": "Java",
        "C": "C", "C++": "C++", "Shell": "Bash", "HCL": "Terraform",
        "Dockerfile": "Docker",
    }
    for lang in languages:
        if lang in lang_map:
            stack.add(lang_map[lang])

    # From topics
    topic_map = {
        "docker": "Docker", "kubernetes": "Kubernetes", "k8s": "Kubernetes",
        "terraform": "Terraform", "aws": "AWS", "gcp": "GCP",
        "postgresql": "PostgreSQL", "postgres": "PostgreSQL",
        "mongodb": "MongoDB", "redis": "Redis", "rabbitmq": "RabbitMQ",
        "grpc": "gRPC", "rest-api": "REST APIs", "graphql": "GraphQL",
        "react": "React", "nextjs": "Next.js", "fastapi": "FastAPI",
        "express": "Express", "gin": "Gin", "ebpf": "eBPF",
        "microservices": "Microservices", "ci-cd": "CI/CD",
    }
    for topic in repo.get("topics", []):
        if topic.lower() in topic_map:
            stack.add(topic_map[topic.lower()])

    # From README content (lightweight pattern matching)
    readme_lower = readme.lower()
    readme_patterns = {
        r'\bkubernetes\b': "Kubernetes", r'\bdocker\b': "Docker",
        r'\bterraform\b': "Terraform", r'\baws\b': "AWS",
        r'\bgcp\b': "GCP", r'\bpostgresql\b': "PostgreSQL",
        r'\bmongodb\b': "MongoDB", r'\bredis\b': "Redis",
        r'\brabbitmq\b': "RabbitMQ", r'\bgrpc\b': "gRPC",
        r'\bfastapi\b': "FastAPI", r'\bexpress\b': "Express",
        r'\bgin\b': "Gin", r'\bebpf\b': "eBPF",
        r'\bjaeger\b': "Jaeger", r'\bstripe\b': "Stripe",
        r'\bjest\b': "Jest", r'\bplaywright\b': "Playwright",
        r'\bgithub actions\b': "GitHub Actions",
        r'\bjenkins\b': "Jenkins", r'\bnginx\b': "Nginx",
    }
    for pattern, tech in readme_patterns.items():
        if re.search(pattern, readme_lower):
            stack.add(tech)

    return sorted(stack)


def load_repo_cache() -> dict:
    """Load previously scanned repo data."""
    if os.path.exists(REPO_CACHE_FILE):
        try:
            with open(REPO_CACHE_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_repo_cache(cache: dict):
    """Save repo scan data."""
    os.makedirs(os.path.dirname(REPO_CACHE_FILE), exist_ok=True)
    with open(REPO_CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)


def scan_repos(username: str, token: Optional[str] = None) -> list[RepoInfo]:
    """
    Scan all public repos for a user.
    Detects new and recently updated repos since last scan.
    """
    cache = load_repo_cache()
    last_scan = cache.get("_last_scan", "2000-01-01T00:00:00Z")

    raw_repos = fetch_repos(username, token)
    results = []

    for repo in raw_repos:
        # Skip forks unless they have significant changes
        if repo.get("fork") and repo.get("stargazers_count", 0) == 0:
            continue

        name = repo["name"]
        full_name = repo["full_name"]
        updated = repo.get("updated_at", "")

        # Check if new or updated since last scan
        cached = cache.get(name, {})
        is_new = name not in cache or name == "_last_scan"
        is_updated = not is_new and updated > cached.get("updated_at", "")

        if not is_new and not is_updated:
            # Repo unchanged, use cached data
            results.append(RepoInfo(
                name=name,
                description=repo.get("description") or "",
                url=repo.get("html_url", ""),
                languages=cached.get("languages", {}),
                topics=repo.get("topics", []),
                stars=repo.get("stargazers_count", 0),
                updated_at=updated,
                created_at=repo.get("created_at", ""),
                default_branch=repo.get("default_branch", "main"),
                tech_stack=cached.get("tech_stack", []),
                is_new=False,
                is_updated=False,
            ))
            continue

        # Fetch detailed info for new/updated repos
        logger.info(f"Scanning {'new' if is_new else 'updated'} repo: {name}")
        languages = fetch_languages(full_name, token)
        readme = fetch_readme_excerpt(full_name, token)
        tech_stack = extract_tech_stack(repo, languages, readme)

        info = RepoInfo(
            name=name,
            description=repo.get("description") or "",
            url=repo.get("html_url", ""),
            languages=languages,
            topics=repo.get("topics", []),
            stars=repo.get("stargazers_count", 0),
            updated_at=updated,
            created_at=repo.get("created_at", ""),
            default_branch=repo.get("default_branch", "main"),
            has_readme=bool(readme),
            readme_excerpt=readme[:500],
            tech_stack=tech_stack,
            is_new=is_new,
            is_updated=is_updated,
        )
        results.append(info)

        # Update cache
        cache[name] = {
            "updated_at": updated,
            "languages": languages,
            "tech_stack": tech_stack,
        }

    # Save updated cache
    cache["_last_scan"] = datetime.now(timezone.utc).isoformat()
    save_repo_cache(cache)

    # Sort: new first, then updated, then by stars
    results.sort(key=lambda r: (not r.is_new, not r.is_updated, -r.stars))

    new_count = sum(1 for r in results if r.is_new)
    updated_count = sum(1 for r in results if r.is_updated)
    logger.info(f"Scan complete: {len(results)} repos ({new_count} new, {updated_count} updated)")

    return results


def update_profile_skills(repos: list[RepoInfo], config: dict) -> bool:
    """
    Update the candidate profile's tech stack based on scanned repos.
    Returns True if profile was updated.
    """
    # Aggregate all tech across repos, weighted by recency and repo size
    tech_counts: dict[str, float] = {}
    now = datetime.now(timezone.utc)

    for repo in repos:
        # Weight by recency (repos updated in last 3 months get 2x)
        try:
            updated = datetime.fromisoformat(repo.updated_at.replace("Z", "+00:00"))
            age_days = (now - updated).days
            recency_weight = 2.0 if age_days < 90 else 1.0 if age_days < 180 else 0.5
        except (ValueError, TypeError):
            recency_weight = 0.5

        # Weight by language bytes (proxy for project size)
        total_bytes = sum(repo.languages.values()) if repo.languages else 1
        size_weight = min(total_bytes / 10000, 3.0)  # Cap at 3x

        weight = recency_weight * size_weight
        for tech in repo.tech_stack:
            tech_counts[tech] = tech_counts.get(tech, 0) + weight

    # Sort by weighted count
    sorted_tech = sorted(tech_counts.items(), key=lambda x: -x[1])
    top_tech = [t[0] for t in sorted_tech[:25]]

    if not top_tech:
        return False

    # Update profile's candidate_profile tech stack line
    current_profile = config.get("scoring", {}).get("candidate_profile", "")
    tech_line = f"Tech stack (auto-detected from GitHub): {', '.join(top_tech)}"

    # Check if there's already an auto-detected line
    if "Tech stack (auto-detected from GitHub):" in current_profile:
        updated_profile = re.sub(
            r'Tech stack \(auto-detected from GitHub\):.*',
            tech_line,
            current_profile,
        )
    else:
        updated_profile = current_profile.rstrip() + f"\n    {tech_line}"

    config["scoring"]["candidate_profile"] = updated_profile

    # Write back to profile.yaml
    with open(PROFILE_PATH, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Updated profile with {len(top_tech)} technologies from GitHub scan")
    return True


def generate_scan_report(repos: list[RepoInfo]) -> str:
    """Generate a human-readable summary of the scan for the email digest."""
    new_repos = [r for r in repos if r.is_new]
    updated_repos = [r for r in repos if r.is_updated]

    if not new_repos and not updated_repos:
        return ""

    lines = ["<h2>📦 GitHub Repo Updates This Week</h2>"]

    if new_repos:
        lines.append("<h3>New Repositories</h3>")
        for repo in new_repos:
            tech = ", ".join(repo.tech_stack[:8]) if repo.tech_stack else "No stack detected"
            lines.append(
                f'<div style="margin-bottom:8px;">'
                f'<strong><a href="{repo.url}">{repo.name}</a></strong> — '
                f'{repo.description[:100] or "No description"}<br/>'
                f'<span style="color:#6b7280;font-size:12px;">Stack: {tech}</span>'
                f'</div>'
            )

    if updated_repos:
        lines.append("<h3>Recently Updated</h3>")
        for repo in updated_repos[:5]:
            tech = ", ".join(repo.tech_stack[:8]) if repo.tech_stack else "—"
            lines.append(
                f'<div style="margin-bottom:8px;">'
                f'<strong><a href="{repo.url}">{repo.name}</a></strong> — '
                f'{repo.description[:100] or "No description"}<br/>'
                f'<span style="color:#6b7280;font-size:12px;">Stack: {tech}</span>'
                f'</div>'
            )

    return "\n".join(lines)
