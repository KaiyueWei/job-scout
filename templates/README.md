# Templates

Place two files here (both git-ignored if they contain personal data):

## `cv.pdf`

Your existing CV as a PDF. The LLM ranker reads its text content with `pypdf`
to score job offers against your actual experience.

Set `CV_PATH` to point at this file (defaults to `templates/cv.pdf` in CI).

## `cv_template.docx`

A Word document with five placeholder tokens that the LLM fills in per offer:

| Placeholder           | What the LLM writes                                       |
| --------------------- | --------------------------------------------------------- |
| `{{ROLE}}`            | A single role title (e.g. `BACKEND ENGINEER`)             |
| `{{CORE_COMPETENCIES}}` | 4–5 items from `cv.competencies` in `config/profile.yaml` |
| `{{LIBRARIES}}`       | 4–5 items from `cv.libraries`                             |
| `{{LANGUAGES}}`       | items from `cv.languages` relevant to the JD              |
| `{{TOOLS}}`           | up to 4 items from `cv.tools`                             |

Type the tokens literally (including the double braces) in the document.
`{{ROLE}}` will be bold-cased and blue automatically; the others are inserted
as plain text.

Set `CV_TEMPLATE_PATH` to point at this file.
