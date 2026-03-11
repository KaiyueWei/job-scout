# Job Scout Pipeline

Automated job discovery, scoring, and resume tailoring for SDE/DevOps co-op and internship roles. Runs twice daily on GitHub Actions (free).

## What It Does

1. **Scouts** — Polls free job APIs (Indeed RSS, Adzuna, Remotive, Arbeitnow) for new postings matching your criteria
2. **Filters** — Deduplicates, filters by location (North America, remote-Canada), recency (last 24h)
3. **Scores** — Sends each JD to Claude API to get a fit score (1-10) and recommended resume variant
4. **Tailors** — For high-scoring matches (7+), auto-generates a tailored resume using your LaTeX template
5. **Emails** — Sends a twice-daily digest with scored listings and attached tailored resumes
6. **Repo Scan (weekly)** — Scans your GitHub repos every Sunday, detects new/updated projects, extracts tech stacks, and auto-updates your candidate profile so the scorer always reflects your latest work

## Architecture

```
GitHub Actions (cron: 8am, 6pm PT — daily)
  │
  ├── src/scraper.py        — Fetch jobs from free APIs
  ├── src/filter.py          — Deduplicate, location/recency filter
  ├── src/scorer.py          — Claude API scoring + resume variant recommendation
  ├── src/tailor.py          — LaTeX resume generation per match
  ├── src/emailer.py         — Gmail SMTP digest sender
  └── src/main.py            — Orchestrator

GitHub Actions (cron: Sundays — weekly)
  │
  ├── src/repo_scanner.py    — Scan GitHub repos, extract tech stacks
  └── src/scan_repos_cli.py  — Update profile.yaml with latest skills
```

## Setup

### 1. Fork/Clone This Repo

```bash
git clone https://github.com/YOUR_USERNAME/job-scout.git
cd job-scout
```

### 2. Get API Keys (All Free Tier)

| Service | Purpose | Free Tier | Sign Up |
|---------|---------|-----------|---------|
| Adzuna | Job listings | 250 req/day | https://developer.adzuna.com |
| Anthropic | JD scoring | Pay-per-use (~$0.50/day) | https://console.anthropic.com |
| Gmail App Password | Email delivery | Free | Google Account → Security → App Passwords |

**Note:** Adzuna is optional. The pipeline works with Indeed RSS + Arbeitnow (no keys needed) alone.

### 3. Configure GitHub Secrets

Go to your repo → Settings → Secrets and variables → Actions, and add:

| Secret | Required? | Value |
|--------|-----------|-------|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |
| `GMAIL_ADDRESS` | Yes | Your Gmail address |
| `GMAIL_APP_PASSWORD` | Yes | Gmail App Password (not your regular password) |
| `ADZUNA_APP_ID` | Optional | Adzuna application ID |
| `ADZUNA_APP_KEY` | Optional | Adzuna API key |

### 4. Configure Your Profile

Edit `config/profile.yaml` with your details, target roles, and keywords.

### 5. Add Your Resume Template

Replace `templates/base_resume.tex` with your LaTeX resume template. Use `{{SUMMARY}}`, `{{EXPERIENCE_BULLETS}}`, and `{{SKILLS_LINE}}` placeholders where you want auto-tailoring to happen.

### 6. Enable GitHub Actions

Push to `main` branch. The workflow runs automatically at 8am and 6pm Pacific. You can also trigger manually from the Actions tab.

## Local Development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run once locally
python src/main.py
```

## Cost Estimate

- **GitHub Actions:** Free (2,000 min/month on free tier; each run ~3-5 min)
- **Adzuna API:** Free (250 requests/day)
- **Claude API:** ~$0.30-0.80/day depending on number of listings scored
- **Gmail:** Free
- **Total:** ~$10-25/month (Claude API only)
