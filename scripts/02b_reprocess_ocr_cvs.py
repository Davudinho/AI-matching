"""
scripts/02b_reprocess_ocr_cvs.py — OCR Re-Processing for Scanned PDFs

PURPOSE:
    Identifies CVs in data/processed/cvs_raw.json that have fewer than
    OCR_CHAR_THRESHOLD characters extracted (indicating a scanned/image-based
    PDF where native extraction failed), removes them from the cache, and
    re-runs them through the full extraction pipeline — this time triggering
    the Gemini Vision OCR fallback in document_parser.py.

    After this script completes, re-run the downstream pipeline steps:
        python scripts/03_anonymise_cvs.py
        python scripts/04_embed_cvs.py
        python scripts/08_ai_match.py
        python scripts/11_export_results_en.py

HOW TO RUN:
    From the project root:
        python scripts/02b_reprocess_ocr_cvs.py

    Dry-run (see which CVs would be reprocessed, without making changes):
        python scripts/02b_reprocess_ocr_cvs.py --dry-run
"""

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---- Project root setup ----
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from backend.app.services.gemini_service import gemini
from backend.app.services.document_parser import extract_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---- Paths ----
CVS_INPUT_DIR = PROJECT_ROOT / "data" / "raw" / "cvs"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "cvs_raw.json"

# CVs with fewer than this many characters are considered "unreadable via native extraction"
OCR_CHAR_THRESHOLD = 100


# ============================================================
# Extraction helpers (mirrors 02_parse_cvs.py)
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

  "profession_domain": "MUST be exactly one of: Finance | Legal | Procurement | Risk & Audit | Creative & Media | Technology | Healthcare | HR & People | General Management | Other. Choose the PRIMARY professional domain this candidate works in, based on their ENTIRE career history (not just the most recent role).",
  "career_summary": "2-sentence professional summary: (1) what they do and at what level, (2) their strongest domain expertise and sector.",

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


def _build_cv_embedding_text(fields: dict) -> str:
    """Build embedding text (mirrors 02_parse_cvs.py)."""
    parts = []
    if fields.get("profession_domain"):
        parts.append(f"Professional Domain: {fields['profession_domain']}")
    if fields.get("career_summary"):
        parts.append(f"Professional Summary: {fields['career_summary']}")
    if fields.get("current_title"):
        parts.append(f"Job Title: {fields['current_title']}")
    if fields.get("years_experience"):
        parts.append(f"Years of Experience: {fields['years_experience']}")
    if fields.get("sector_experience") and isinstance(fields["sector_experience"], list):
        parts.append(f"Sectors: {', '.join(fields['sector_experience'])}")
    if fields.get("skills_technical") and isinstance(fields["skills_technical"], list):
        parts.append(f"Technical Skills: {', '.join(fields['skills_technical'][:15])}")
    if fields.get("skills_soft") and isinstance(fields["skills_soft"], list):
        parts.append(f"Soft Skills: {', '.join(fields['skills_soft'][:10])}")
    if fields.get("work_history") and isinstance(fields["work_history"], list):
        history_texts = []
        for role in fields["work_history"][:3]:
            if isinstance(role, dict):
                role_text = f"{role.get('title', '')} at {role.get('organisation', '')}"
                if role.get("description"):
                    role_text += f": {role['description']}"
                history_texts.append(role_text)
        if history_texts:
            parts.append("Work History: " + " | ".join(history_texts))
    if fields.get("education") and isinstance(fields["education"], list):
        edu_texts = [
            f"{e.get('degree', '')} ({e.get('institution', '')})"
            for e in fields["education"][:3]
            if isinstance(e, dict)
        ]
        if edu_texts:
            parts.append("Education: " + "; ".join(edu_texts))
    if fields.get("certifications") and isinstance(fields["certifications"], list):
        parts.append(f"Certifications: {', '.join(fields['certifications'][:5])}")
    return "\n".join(parts)


def extract_cv_fields(raw_text: str, filename: str) -> dict:
    """Ask Gemini to extract structured fields from CV text."""
    logger.info(f"  Extracting fields from {filename} ({len(raw_text)} chars)...")
    prompt = CV_EXTRACTION_PROMPT.format(cv_text=raw_text[:15000])
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


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Re-process scanned CVs via Gemini Vision OCR")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which CVs would be reprocessed without making any changes",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=OCR_CHAR_THRESHOLD,
        help=f"Character count below which a CV is considered unreadable (default: {OCR_CHAR_THRESHOLD})",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("OCR Re-Processing — Scanned PDFs")
    logger.info("=" * 60)

    if not OUTPUT_FILE.exists():
        logger.error(f"Output file not found: {OUTPUT_FILE}")
        logger.error("Run scripts/02_parse_cvs.py first.")
        sys.exit(1)

    # Load existing CVs
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        all_cvs: list[dict] = json.load(f)

    logger.info(f"Loaded {len(all_cvs)} CVs from {OUTPUT_FILE.name}")

    # Identify candidates for OCR reprocessing
    to_reprocess = []
    keep = []
    for cv in all_cvs:
        raw = cv.get("raw_text", "") or ""
        if len(raw.strip()) < args.threshold:
            to_reprocess.append(cv)
        else:
            keep.append(cv)

    if not to_reprocess:
        logger.info(f"✅ No CVs found with fewer than {args.threshold} chars. Nothing to do.")
        sys.exit(0)

    logger.info(f"\nFound {len(to_reprocess)} CV(s) to reprocess via OCR:")
    for cv in to_reprocess:
        raw_chars = len((cv.get("raw_text", "") or "").strip())
        logger.info(f"  • {cv.get('filename')} ({raw_chars} chars)")

    if args.dry_run:
        logger.info("\n[DRY RUN] No changes made.")
        sys.exit(0)

    logger.info(f"\nKeeping {len(keep)} existing CVs unchanged.")
    logger.info(f"Re-running OCR for {len(to_reprocess)} CVs...\n")

    results = keep.copy()
    success_count = 0
    fail_count = 0

    for cv in to_reprocess:
        filename = cv.get("filename")
        original_cv_id = cv.get("cv_id")  # Preserve the original cv_id
        cv_file = CVS_INPUT_DIR / filename

        logger.info(f"\n{'─' * 50}")
        logger.info(f"OCR Processing: {filename}")

        if not cv_file.exists():
            logger.error(f"  ✗ File not found in {CVS_INPUT_DIR}: {filename}")
            logger.error("  → Keeping original (empty) record")
            results.append(cv)
            fail_count += 1
            continue

        try:
            # extract_text will trigger Gemini Vision OCR since native extraction yields < threshold chars
            raw_text = extract_text(cv_file)
            ocr_chars = len(raw_text.strip())
            logger.info(f"  OCR result: {ocr_chars} chars extracted")

            if ocr_chars < args.threshold:
                logger.warning(
                    f"  ⚠ OCR still returned very few chars ({ocr_chars}). "
                    "The file may be corrupted or password-protected."
                )

            fields = extract_cv_fields(raw_text, filename)

            cv_record = {
                "cv_id": original_cv_id or str(uuid.uuid4()),
                "filename": filename,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "ocr_reprocessed": True,
                **fields,
            }

            results.append(cv_record)

            # Save incrementally after each CV (safe resumption if interrupted)
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)

            logger.info(f"  ✓ Saved. Total CVs in file: {len(results)}")
            success_count += 1

        except Exception as e:
            logger.error(f"  ✗ Failed to reprocess {filename}: {e}")
            logger.error("  → Keeping original (empty) record")
            results.append(cv)
            fail_count += 1

    # Final save (ensure file is consistent)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Summary
    logger.info(f"\n{'=' * 60}")
    logger.info("SUMMARY")
    logger.info(f"{'=' * 60}")
    logger.info(f"CVs reprocessed successfully : {success_count}")
    logger.info(f"CVs failed / kept as-is      : {fail_count}")
    logger.info(f"Total CVs in output file     : {len(results)}")
    logger.info(f"\n✅ Updated: {OUTPUT_FILE}")

    if success_count > 0:
        logger.info("\nNext steps:")
        logger.info("  1. python scripts/03_anonymise_cvs.py")
        logger.info("  2. python scripts/04_embed_cvs.py")
        logger.info("  3. python scripts/08_ai_match.py")
        logger.info("  4. python scripts/11_export_results_en.py")


if __name__ == "__main__":
    main()
