# Job Scout Pipeline

Automated job discovery, LLM ranking, and CV tailoring for SDE/DevOps co-op
and internship roles. Runs twice daily on GitHub Actions (free).

## What It Does

1. **Scrape** — Queries LinkedIn's public guest jobs API and parses results
   with BeautifulSoup (one search per role × location).
2. **Filter** — Deduplicates by URL, drops jobs seen in the last 7 days, and
   pre-filters out blacklisted keywords (e.g. *principal*, *10+ years*).
3. **Rank** — Sends the batch to `gpt-4o-mini` via LangChain with Pydantic
   structured output; gets a 1–10 score, comment, and summary per offer.
4. **ATS keywords** — For each high-score offer, a second LLM call extracts
   up to 10 hard-skill keywords from the JD.
5. **Tailor** — Fills five placeholders in a DOCX CV template with role,
   competencies, libraries, languages, and tools chosen from your profile's
   skill lists. Converts to PDF via CloudConvert (ConvertAPI fallback).
6. **Email** — Sends a twice-daily Gmail digest with the ranked list and
   tailored PDFs attached.

## Architecture

```
GitHub Actions (cron: 8am, 6pm PT)
  │
  ├── src/scraper.py     — LinkedIn guest API + BeautifulSoup
  ├── src/filter.py      — Dedup, seen-jobs cache, exclude-keyword pre-filter
  ├── src/scorer.py      — LangChain + GPT-4o-mini ranking (Pydantic output)
  ├── src/cv_parser.py   — Reads your PDF CV with pypdf for ranking context
  ├── src/prompts.py     — LLM prompt templates (rank, keywords, placeholders)
  ├── src/tailor.py      — python-docx placeholder fill + CloudConvert → PDF
  ├── src/emailer.py     — Gmail SMTP digest with PDF attachments
  └── src/main.py        — Orchestrator
```

## Setup

### 1. Fork / Clone

```bash
git clone https://github.com/YOUR_USERNAME/job-scout.git
cd job-scout
```

### 2. API Keys

| Service       | Purpose                          | Free Tier                |
| ------------- | -------------------------------- | ------------------------ |
| OpenAI        | LLM ranking + placeholder fill   | Pay-as-you-go            |
| CloudConvert  | DOCX → PDF (primary)             | 25 conv/day              |
| ConvertAPI    | DOCX → PDF (fallback)            | Free tier available      |
| Gmail App PW  | Email delivery                   | Free                     |

### 3. GitHub Secrets

Repo → Settings → Secrets and variables → Actions:

| Secret                  | Required? | Value                              |
| ----------------------- | --------- | ---------------------------------- |
| `OPENAI_API_KEY`        | Yes       | OpenAI API key                     |
| `GMAIL_ADDRESS`         | Yes       | Gmail address                      |
| `GMAIL_APP_PASSWORD`    | Yes       | Gmail App Password                 |
| `CLOUDCONVERT_API_KEY`  | One of    | CloudConvert API key               |
| `CONVERTAPI_SECRET`     | One of    | ConvertAPI secret (fallback)       |

### 4. Profile + CV

- Edit `config/profile.yaml`: roles, locations, exclude/priority keywords,
  candidate profile, and the four skill lists used to fill the DOCX CV.
- Place `templates/cv.pdf` (your existing CV — used as ranking context).
- Place `templates/cv_template.docx` with `{{ROLE}}`, `{{CORE_COMPETENCIES}}`,
  `{{LIBRARIES}}`, `{{LANGUAGES}}`, `{{TOOLS}}` placeholders. See
  `templates/README.md`.

### 5. Run

Push to `main`. The workflow runs at 8am and 6pm Pacific. Manual triggers
are available in the Actions tab.

## Local Development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env  # then fill in keys
python -m src.main
```

`.env` keys: `OPENAI_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`,
`CLOUDCONVERT_API_KEY` (or `CONVERTAPI_SECRET`), `CV_PATH`, `CV_TEMPLATE_PATH`.

## Cost Estimate

- **GitHub Actions:** Free (≈ 5 min/run × 60 runs/month)
- **OpenAI (gpt-4o-mini + occasional gpt-4o for CV placeholders):** ~$0.20–0.60/day
- **CloudConvert:** Free up to 25 PDFs/day
- **Gmail:** Free
