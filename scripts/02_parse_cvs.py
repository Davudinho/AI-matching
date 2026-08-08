"""
scripts/02_parse_cvs.py — Week 2, Task 2: Parse CVs

PURPOSE:
    Reads every CV file from data/raw/cvs/ (supports .docx and .pdf),
    extracts plain text, then asks Gemini to extract structured fields
    (work history, skills, education, etc.) and saves the result as
    data/processed/cvs_raw.json.

    NOTE: This script keeps PII (names, emails, etc.) in the output.
    The NEXT script (03_anonymise_cvs.py) will remove it.

HOW TO RUN:
    1. Copy your CV files into: data/raw/cvs/
       Supported formats: .docx, .pdf
    2. Make sure GEMINI_API_KEY is set in your .env
    3. From the project root, run:
       python scripts/02_parse_cvs.py

OUTPUT:
    data/processed/cvs_raw.json   ← Structured CVs (still contains PII)
"""

import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from backend.app.services.gemini_service import gemini

import docx        # python-docx: reads .docx files
import fitz        # PyMuPDF: reads .pdf files (imported as 'fitz')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# Paths
# ============================================================

CVS_INPUT_DIR = PROJECT_ROOT / "data" / "raw" / "cvs"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_FILE = PROCESSED_DIR / "cvs_raw.json"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Text Extraction
# ============================================================

def extract_text_from_docx(filepath: Path) -> str:
    """Extract plain text from a .docx Word document."""
    doc = docx.Document(str(filepath))
    paragraphs = [para.text.strip() for para in doc.paragraphs if para.text.strip()]
    # Also include tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if text and text not in paragraphs:
                    paragraphs.append(text)
    return "\n".join(paragraphs)


def extract_text_from_pdf(filepath: Path) -> str:
    """
    Extract plain text from a .pdf file using PyMuPDF.
    
    PyMuPDF (imported as 'fitz') is one of the fastest PDF libraries.
    It can handle most PDF types including scanned documents with embedded text.
    
    For scanned/image PDFs, we'd need OCR (tesseract) — let's keep it simple for now.
    """
    doc = fitz.open(str(filepath))
    pages_text = []

    for page_num, page in enumerate(doc, start=1):
        # Extract text with layout preservation
        # "blocks" mode groups text by position — better structure than "text" mode
        text = page.get_text("text")
        if text.strip():
            pages_text.append(f"[Page {page_num}]\n{text.strip()}")

    doc.close()
    return "\n\n".join(pages_text)


def extract_text(filepath: Path) -> str:
    """
    Route a file to the correct text extractor based on its extension.
    Returns extracted text, or raises an error for unsupported formats.
    """
    suffix = filepath.suffix.lower()
    if suffix == ".docx":
        return extract_text_from_docx(filepath)
    elif suffix == ".pdf":
        return extract_text_from_pdf(filepath)
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Only .docx and .pdf are supported.")


# ============================================================
# AI Extraction Prompt
# ============================================================

SYSTEM_INSTRUCTION = """You are an expert HR analyst specialising in CV (resume) analysis.
Extract structured information from CVs. Return valid JSON only.
For fields that are not mentioned, use null for strings, [] for arrays, and false for booleans.
Do NOT invent information — only extract what is explicitly stated in the CV."""

CV_EXTRACTION_PROMPT = """Analyse this CV and extract structured information.
Return ONLY a valid JSON object with exactly these keys.

CV TEXT:
---
{cv_text}
---

Extract:
{{
  "full_name": "candidate's full name",
  "email": "email address or null",
  "phone": "phone number or null",
  "address": "home address if mentioned, else null",
  "linkedin_url": "LinkedIn profile URL if mentioned, else null",
  "current_title": "most recent job title",
  "years_experience": <estimated total years of professional experience as integer, or null>,
  "skills_technical": ["Python", "SQL", "Salesforce", "etc."],
  "skills_soft": ["communication", "leadership", "etc."],
  "education": [
    {{
      "degree": "BSc Computer Science",
      "institution": "University College London",
      "year": 2019,
      "grade": "2:1 or First Class etc., or null"
    }}
  ],
  "work_history": [
    {{
      "title": "Software Engineer",
      "organisation": "Company Name",
      "start_date": "2021-03",
      "end_date": "2023-09 or Present",
      "duration_years": <approximate years as float, e.g. 2.5>,
      "description": "brief summary of role and achievements"
    }}
  ],
  "certifications": ["AWS Certified Solutions Architect", "etc."],
  "languages": ["English (Native)", "French (Professional)", "etc."],
  "right_to_work_uk": <true if explicitly stated, false if explicitly not, null if not mentioned>,
  "sector_experience": ["Charity", "Finance", "Tech", "etc. — infer from work history"],
  "missing_fields": ["list fields you couldn't determine"],
  "notes": "any other relevant information not captured above"
}}"""


def extract_cv_fields(raw_text: str, filename: str) -> dict:
    """
    Ask Gemini to extract structured fields from CV text.
    Same pattern as extract_jd_fields() in 01_parse_jds.py.
    """
    logger.info(f"  Extracting fields from {filename} ({len(raw_text)} chars)...")

    prompt = CV_EXTRACTION_PROMPT.format(
        cv_text=raw_text[:15000]  # CVs can be long — truncate to fit token budget
    )

    result = gemini.generate_json(
        prompt=prompt,
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0.0,
    )

    if result is None:
        logger.error(f"  ✗ Gemini returned None for {filename}")
        return {"extraction_status": "failed", "error": "No response from Gemini"}

    result["extraction_status"] = "success"
    result["raw_text"] = raw_text
    result["embedding_text"] = _build_cv_embedding_text(result)

    logger.info(
        f"  ✓ Extracted: name='{result.get('full_name')}' | "
        f"title='{result.get('current_title')}' | "
        f"exp={result.get('years_experience')}yrs"
    )
    return result


def _build_cv_embedding_text(fields: dict) -> str:
    """
    Build a focused text representation of a CV for embedding.
    
    We use anonymised-friendly text here — NO name or contact info.
    Just professional content: title, skills, experience, education.
    """
    parts = []

    if fields.get("current_title"):
        parts.append(f"Job Title: {fields['current_title']}")
    if fields.get("years_experience"):
        parts.append(f"Years of Experience: {fields['years_experience']}")
    if fields.get("sector_experience"):
        sectors = fields["sector_experience"]
        if isinstance(sectors, list):
            parts.append(f"Sectors: {', '.join(sectors)}")
    if fields.get("skills_technical"):
        skills = fields["skills_technical"]
        if isinstance(skills, list):
            parts.append(f"Technical Skills: {', '.join(skills[:15])}")
    if fields.get("skills_soft"):
        skills = fields["skills_soft"]
        if isinstance(skills, list):
            parts.append(f"Soft Skills: {', '.join(skills[:10])}")
    if fields.get("work_history"):
        history = fields["work_history"]
        if isinstance(history, list):
            # Include descriptions from the 3 most recent roles
            history_texts = []
            for role in history[:3]:
                if isinstance(role, dict):
                    role_text = f"{role.get('title', '')} at {role.get('organisation', '')}"
                    if role.get("description"):
                        role_text += f": {role['description']}"
                    history_texts.append(role_text)
            if history_texts:
                parts.append("Work History: " + " | ".join(history_texts))
    if fields.get("education"):
        edu = fields["education"]
        if isinstance(edu, list) and edu:
            edu_texts = []
            for e in edu[:3]:
                if isinstance(e, dict):
                    edu_texts.append(f"{e.get('degree', '')} ({e.get('institution', '')})")
            if edu_texts:
                parts.append("Education: " + "; ".join(edu_texts))
    if fields.get("certifications"):
        certs = fields["certifications"]
        if isinstance(certs, list):
            parts.append(f"Certifications: {', '.join(certs[:5])}")

    return "\n".join(parts)


# ============================================================
# Main Loop
# ============================================================

def main():
    logger.info("=" * 60)
    logger.info("Week 2 — Task 2: Parsing CVs")
    logger.info("=" * 60)

    # Find all supported CV files
    cv_files = sorted(
        list(CVS_INPUT_DIR.glob("*.docx")) + list(CVS_INPUT_DIR.glob("*.pdf"))
    )

    if not cv_files:
        logger.error(
            f"No .docx or .pdf files found in {CVS_INPUT_DIR}\n"
            f"Please copy your CV files there and run again."
        )
        sys.exit(1)

    logger.info(f"Found {len(cv_files)} CV file(s):")
    for f in cv_files:
        logger.info(f"  • {f.name}")

    # Load existing results to allow resumption
    existing_cvs = []
    processed_filenames = set()
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing_cvs = json.load(f)
        processed_filenames = {cv["filename"] for cv in existing_cvs}
        logger.info(f"Resuming: {len(existing_cvs)} CVs already processed")

    results = existing_cvs.copy()

    for cv_file in cv_files:
        filename = cv_file.name

        if filename in processed_filenames:
            logger.info(f"⏭  Skipping {filename} (already processed)")
            continue

        logger.info(f"\n{'─' * 50}")
        logger.info(f"Processing: {filename}")

        try:
            raw_text = extract_text(cv_file)

            if len(raw_text) < 50:
                logger.warning(f"  ⚠ Very short document ({len(raw_text)} chars)")

            fields = extract_cv_fields(raw_text, filename)

            cv_record = {
                "cv_id": str(uuid.uuid4()),
                "filename": filename,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                **fields,
            }

            results.append(cv_record)

            # Save incrementally after each CV
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)

            logger.info(f"  ✓ Saved. Total CVs processed: {len(results)}")

        except Exception as e:
            logger.error(f"  ✗ Failed: {filename}: {e}")

    # Summary
    logger.info(f"\n{'=' * 60}")
    logger.info("SUMMARY")
    logger.info(f"{'=' * 60}")
    logger.info(f"Total CVs processed: {len(results)}")

    with_name = sum(1 for cv in results if cv.get("full_name"))
    with_email = sum(1 for cv in results if cv.get("email"))
    with_rtw = sum(1 for cv in results if cv.get("right_to_work_uk") is True)
    logger.info(f"CVs with name detected: {with_name}/{len(results)}")
    logger.info(f"CVs with email detected: {with_email}/{len(results)}")
    logger.info(f"CVs with UK right-to-work stated: {with_rtw}/{len(results)}")

    logger.info(f"\n✅ Raw CV data saved to: {OUTPUT_FILE}")
    logger.info("⚠  This file contains PII — do not share or commit to Git!")
    logger.info("\nNext step: Run scripts/03_anonymise_cvs.py")


if __name__ == "__main__":
    main()
