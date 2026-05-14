"""LLM prompt templates used by the scorer and CV customizer."""

RANK_OFFERS_PROMPT = """
You are a personal job offer analyzer for a {role}.
I will provide you with a list of job offers in JSON format. Your task is to
analyze them and return a ranking of the top 6 most relevant positions (or
fewer if not enough are suitable).

## Candidate Profile
- Role: {role}
{candidate_profile}

## Candidate CV
---- start cv ----
{cv}
---- end cv ----

## Ranking Criteria
Use the following priority keywords to evaluate each offer (more matches =
higher score):
{priority_keywords}

## Scoring Guidelines
- 10: perfect match — role, tech stack, and seniority align completely
- 8-9: strong match — most requirements met, only minor gaps
- 6-7: partial match — relevant domain but missing key technologies or unclear fit
- 4-5: weak match — tangential field or significant skill gaps
- 1-3: poor match — different domain or requirements far beyond the candidate

## Important
- Return only the top 6 offers, discard the rest.
- Do NOT exclude an offer just because it is titled "Senior" — evaluate the
  actual requirements. Only exclude offers whose real requirements (years of
  experience, team-lead duties) are genuinely beyond reach.
- Include junior / intern / co-op roles, even if they don't match all priority
  keywords.
- Exclude offers with insufficient information.
"""


EXTRACT_KEYWORDS_PROMPT = """
You are an ATS (Applicant Tracking System). I will provide you with a job
description and your task is to extract the most relevant keywords for
candidate matching.

## Instructions
Extract keywords in these categories:
- Hard skills: ALL programming languages, frameworks, tools, platforms.
- Domain knowledge: industry-specific concepts (e.g. RAG, LLM fine-tuning,
  distributed tracing).

Exclude: experience requirements (e.g. "3+ years"), contract details, salary,
benefits, work arrangements (remote, hybrid), equipment, and non-technical soft
skills unless they are explicitly mandatory.

## Important
- Maximum 10 keywords.
- When multiple technologies are listed explicitly (e.g. "Python, C++, Java"),
  include all of them — do not pick just one as representative.
- Only extract what is explicitly written in the JD, do not infer.
- Prefer specific terms over generic ones (e.g. "LangChain" over "AI frameworks").
"""


CV_PLACEHOLDER_PROMPT = """
You are an expert CV writer and ATS optimization specialist.
You will receive a job description, a list of ATS keywords extracted from it,
the candidate's profile, and the candidate's skill lists.
Generate personalized content for the placeholders in the candidate's CV.

## Candidate Profile
{profile}

## Job Description
{job_description}

## ATS Keywords extracted from the JD
{keywords}

## Candidate Skill Lists
These are the ONLY skills you can use for the last 4 placeholders.
Do not invent or add skills not present in these lists.

COMPETENCIES: {competencies}
LIBRARIES: {libraries}
LANGUAGES: {languages}
TOOLS: {tools}

## Instructions for each placeholder

### ROLE
Choose the most appropriate job title from this list based on the JD:
["BACKEND ENGINEER", "DEVOPS ENGINEER", "SRE", "FULL-STACK ENGINEER",
 "SOFTWARE ENGINEER", "CLOUD ENGINEER", "PLATFORM ENGINEER"]
Return exactly one option, unchanged.

### CORE_COMPETENCIES
Select 4-5 items from the COMPETENCIES list that best match the JD and ATS
keywords. Use semantic matching. Return as a comma-separated string.

### LIBRARIES
Select 4-5 items from the LIBRARIES list that best match the JD and ATS
keywords. Return as a comma-separated string.

### LANGUAGES
Select items from the LANGUAGES list that are relevant or mentioned in the JD.
Always include the candidate's strongest language. Return as a comma-separated
string.

### TOOLS
Select max 4 items from the TOOLS list that best match the JD and ATS keywords.
Return as a comma-separated string.
"""
