"""PDF CV reader."""

from __future__ import annotations

from pypdf import PdfReader


def parse_cv(cv_path: str) -> str:
    """Extract all text from a PDF CV."""
    reader = PdfReader(cv_path)
    return "".join(page.extract_text() or "" for page in reader.pages)
