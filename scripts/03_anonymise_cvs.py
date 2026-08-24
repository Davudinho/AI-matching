"""
scripts/03_anonymise_cvs.py — Week 2, Task 3: Anonymise CVs (GDPR Compliance)

PURPOSE:
    Removes Personally Identifiable Information (PII) from CVs so the dataset
    can be used freely for AI training and evaluation without privacy risks.

WHY THIS MATTERS (GDPR):
    Under UK GDPR, personal data (names, contact details, addresses) cannot be
    stored or processed without consent and a lawful basis. By anonymising CVs:
    - The anonymised dataset can be used for AI development freely
    - Candidates are protected from data breaches
    - Diversifying.io complies with UK GDPR obligations

WHAT WE ANONYMISE:
    Names, emails, phone numbers, home addresses, LinkedIn/social URLs,
    National Insurance numbers, dates of birth, and similar personal data.

HOW WE DO IT:
    1. Regex patterns catch structured PII (emails, phones, URLs)
    2. Named entity replacement: we replace detected names with [NAME]
    3. The original name→placeholder mapping is saved separately (pii_mapping.json)
       so we can reconnect anonymised data to real candidates if ever needed.

HOW TO RUN:
    python scripts/03_anonymise_cvs.py

INPUT:  data/processed/cvs_raw.json
OUTPUT:
    data/processed/cvs_anonymised.json   ← Safe to share / use in AI pipeline
    data/processed/pii_mapping.json      ← KEEP SECRET — maps cv_id to real PII
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# Paths
# ============================================================

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
INPUT_FILE = PROCESSED_DIR / "cvs_raw.json"
OUTPUT_ANON = PROCESSED_DIR / "cvs_anonymised.json"
OUTPUT_PII_MAP = PROCESSED_DIR / "pii_mapping.json"  # ← KEEP SECRET, NEVER COMMIT

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# STEP 1: Regex patterns for structured PII
# ============================================================

# These patterns detect common PII formats in text.
# Regex is perfect for structured PII like emails/phones because they
# follow predictable formats.

EMAIL_PATTERN = re.compile(
    r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b'
)

PHONE_PATTERN = re.compile(
    r'(?:'
    r'\+44[\s\-]?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}'    # +44 format
    r'|0\d{3,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}'              # 07xxx or 01xxx
    r'|\(\d{3,5}\)[\s\-]?\d{3,4}[\s\-]?\d{3,4}'           # (020) format
    r')'
)

# URLs (LinkedIn, personal websites, GitHub)
URL_PATTERN = re.compile(
    r'https?://[^\s<>"{}|\\^`\[\]]+'
    r'|linkedin\.com/in/[^\s]+'
    r'|github\.com/[^\s]+'
    r'|www\.[^\s]+'
)

# UK National Insurance Number (e.g. AB 12 34 56 C)
NI_PATTERN = re.compile(
    r'\b[A-CEGHJ-PR-TW-Z]{1}[A-CEGHJ-NPR-TW-Z]{1}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]{1}\b',
    re.IGNORECASE
)

# UK Postcode
POSTCODE_PATTERN = re.compile(
    r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}\b',
    re.IGNORECASE
)

# Date of Birth patterns (e.g. "DOB: 15/03/1990", "Born: March 1990")
DOB_PATTERN = re.compile(
    r'(?:DOB|Date of Birth|Born)[:\s]+\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}'
    r'|(?:DOB|Date of Birth|Born)[:\s]+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{2,4}',
    re.IGNORECASE
)


def anonymise_text_with_regex(text: str, pii_found: dict) -> str:
    """
    Apply regex-based anonymisation to raw text.
    
    Args:
        text: The raw CV text to anonymise
        pii_found: Dict to collect what was found (for the PII mapping file)
    
    Returns:
        Text with PII replaced by placeholder tokens.
    
    How it works:
    We use re.sub() with a lambda function. The lambda is called for EACH
    match — it records what was found and returns the replacement string.
    """
    # Emails: capture and replace
    emails_found = []
    def replace_email(m):
        emails_found.append(m.group())
        return "[EMAIL]"
    text = EMAIL_PATTERN.sub(replace_email, text)
    if emails_found:
        pii_found["emails"] = emails_found

    # Phone numbers
    phones_found = []
    def replace_phone(m):
        phones_found.append(m.group())
        return "[PHONE]"
    text = PHONE_PATTERN.sub(replace_phone, text)
    if phones_found:
        pii_found["phones"] = phones_found

    # URLs (LinkedIn, GitHub, personal sites)
    urls_found = []
    def replace_url(m):
        urls_found.append(m.group())
        return "[URL]"
    text = URL_PATTERN.sub(replace_url, text)
    if urls_found:
        pii_found["urls"] = urls_found

    # NI Numbers
    ni_found = []
    def replace_ni(m):
        ni_found.append(m.group())
        return "[NI_NUMBER]"
    text = NI_PATTERN.sub(replace_ni, text)
    if ni_found:
        pii_found["ni_numbers"] = ni_found

    # UK Postcodes
    postcodes_found = []
    def replace_postcode(m):
        postcodes_found.append(m.group())
        return "[POSTCODE]"
    text = POSTCODE_PATTERN.sub(replace_postcode, text)
    if postcodes_found:
        pii_found["postcodes"] = postcodes_found

    # Date of Birth
    dob_found = []
    def replace_dob(m):
        dob_found.append(m.group())
        return "[DATE_OF_BIRTH]"
    text = DOB_PATTERN.sub(replace_dob, text)
    if dob_found:
        pii_found["dob"] = dob_found

    return text


def anonymise_name_in_text(text: str, full_name: str) -> str:
    """
    Replace all occurrences of a person's name in the text.
    
    We replace:
    - Full name: "Jane Smith" → "[NAME]"
    - First name alone: "Jane" → "[FIRSTNAME]"  (only if >= 4 chars to avoid false positives)
    - Last name alone: "Smith" → "[LASTNAME]"   (only if >= 4 chars)
    
    Why minimum 4 chars?
    Short names like "Lee", "Kim" appear in many words (e.g. "likelihood", "kimono")
    and replacing them would garble the CV text.
    """
    if not full_name or not isinstance(full_name, str):
        return text

    name = full_name.strip()

    # Full name (case-insensitive, word boundary)
    text = re.sub(
        r'\b' + re.escape(name) + r'\b',
        "[NAME]",
        text,
        flags=re.IGNORECASE
    )

    # Individual name parts
    parts = name.split()
    for part in parts:
        if len(part) >= 4:  # Only replace if name part is long enough
            text = re.sub(
                r'\b' + re.escape(part) + r'\b',
                "[NAME_PART]",
                text,
                flags=re.IGNORECASE
            )

    return text


# ============================================================
# STEP 2: Anonymise a single CV record
# ============================================================

def anonymise_cv(cv: dict, anon_ref: str) -> tuple[dict, dict]:
    """
    Anonymise a single CV record.
    
    Args:
        cv: Raw CV dict (from cvs_raw.json)
        anon_ref: Human-readable reference like "CAND-001"
    
    Returns:
        Tuple of:
        - anon_cv: The anonymised CV dict (safe to share)
        - pii_record: Dict containing all extracted PII (keep secret)
    """
    # ---- Collect PII ----
    pii_record = {
        "cv_id": cv["cv_id"],
        "anon_ref": anon_ref,
        "filename": cv["filename"],
        "full_name": cv.get("full_name"),
        "email": cv.get("email"),
        "phone": cv.get("phone"),
        "address": cv.get("address"),
        "linkedin_url": cv.get("linkedin_url"),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }

    # ---- Build anonymised CV ----
    # Start with a copy, then remove all PII fields
    anon_cv = {
        # Identity
        "cv_id": cv["cv_id"],
        "anon_ref": anon_ref,
        "filename": cv["filename"],  # Filename may contain name — we keep it for traceability
        "processed_at": cv.get("processed_at"),

        # Professional info (non-PII)
        "current_title": cv.get("current_title"),
        "years_experience": cv.get("years_experience"),
        "skills_technical": cv.get("skills_technical", []),
        "skills_soft": cv.get("skills_soft", []),
        "education": cv.get("education", []),
        "work_history": _anonymise_work_history(cv.get("work_history", []), cv.get("full_name")),
        "certifications": cv.get("certifications", []),
        "languages": cv.get("languages", []),
        "right_to_work_uk": cv.get("right_to_work_uk"),
        "sector_experience": cv.get("sector_experience", []),

        # Week 4: Profession domain fields (no PII — safe to pass through)
        "profession_domain": cv.get("profession_domain"),
        "career_summary": cv.get("career_summary"),


        # Anonymised full text
        "raw_text_anon": _anonymise_raw_text(
            cv.get("raw_text", ""),
            cv.get("full_name"),
            pii_record,
        ),

        # Embedding text (already focused on professional content, but let's clean it too)
        "embedding_text": _anonymise_raw_text(
            cv.get("embedding_text", ""),
            cv.get("full_name"),
            {},  # Don't double-record PII
        ),

        "missing_fields": cv.get("missing_fields", []),
        "extraction_status": cv.get("extraction_status"),
    }

    return anon_cv, pii_record


def _anonymise_raw_text(text: str, full_name: str | None, pii_found: dict) -> str:
    """Apply all anonymisation steps to a text block."""
    if not text:
        return ""
    text = anonymise_text_with_regex(text, pii_found)
    if full_name:
        text = anonymise_name_in_text(text, full_name)
    return text


def _anonymise_work_history(work_history: list, full_name: str | None) -> list:
    """
    Remove candidate's name from work history descriptions.
    Company names and job titles are kept — they're not PII.
    """
    if not work_history or not isinstance(work_history, list):
        return work_history

    cleaned = []
    for role in work_history:
        if not isinstance(role, dict):
            cleaned.append(role)
            continue

        # Only clean the description field — title and org are fine
        role_copy = role.copy()
        if full_name and role_copy.get("description"):
            role_copy["description"] = anonymise_name_in_text(
                role_copy["description"], full_name
            )
        cleaned.append(role_copy)

    return cleaned


# ============================================================
# STEP 3: Main processing loop
# ============================================================

def main():
    logger.info("=" * 60)
    logger.info("Week 2 — Task 3: Anonymising CVs (GDPR Compliance)")
    logger.info("=" * 60)

    # Load raw CVs
    if not INPUT_FILE.exists():
        logger.error(f"Input file not found: {INPUT_FILE}")
        logger.error("Please run scripts/02_parse_cvs.py first.")
        sys.exit(1)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        raw_cvs = json.load(f)

    logger.info(f"Loaded {len(raw_cvs)} raw CVs from {INPUT_FILE}")

    # Load existing anonymised CVs to allow resumption
    existing_anon = []
    processed_ids = set()
    if OUTPUT_ANON.exists():
        with open(OUTPUT_ANON, "r", encoding="utf-8") as f:
            existing_anon = json.load(f)
        processed_ids = {cv["cv_id"] for cv in existing_anon}
        logger.info(f"Resuming: {len(existing_anon)} CVs already anonymised")

    existing_pii = []
    if OUTPUT_PII_MAP.exists():
        with open(OUTPUT_PII_MAP, "r", encoding="utf-8") as f:
            existing_pii = json.load(f)

    anon_results = existing_anon.copy()
    pii_results = existing_pii.copy()

    # Counter for generating CAND-001, CAND-002, ...
    # Start from where we left off
    cand_counter = len(anon_results) + 1

    for cv in raw_cvs:
        cv_id = cv.get("cv_id")

        if cv_id in processed_ids:
            logger.info(f"⏭  Skipping {cv.get('filename')} (already anonymised)")
            continue

        anon_ref = f"CAND-{cand_counter:03d}"
        logger.info(f"Anonymising: {cv.get('filename')} → {anon_ref}")

        try:
            anon_cv, pii_record = anonymise_cv(cv, anon_ref)
            anon_results.append(anon_cv)
            pii_results.append(pii_record)
            cand_counter += 1

            # Incremental saves
            with open(OUTPUT_ANON, "w", encoding="utf-8") as f:
                json.dump(anon_results, f, indent=2, ensure_ascii=False)

            with open(OUTPUT_PII_MAP, "w", encoding="utf-8") as f:
                json.dump(pii_results, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"  ✗ Failed to anonymise {cv.get('filename')}: {e}")

    # ---- Summary ----
    logger.info(f"\n{'=' * 60}")
    logger.info("SUMMARY")
    logger.info(f"{'=' * 60}")
    logger.info(f"Anonymised CVs:     {len(anon_results)}")
    logger.info(f"PII records stored: {len(pii_results)}")

    # Validate: check no PII leaked into anonymised output
    pii_checks = {"[NAME]", "[EMAIL]", "[PHONE]", "[ADDRESS]", "[URL]"}
    leaked = 0
    for cv in anon_results:
        text = cv.get("raw_text_anon", "") or ""
        # Check for patterns that look like real emails/phones that weren't caught
        if EMAIL_PATTERN.search(text):
            logger.warning(f"  ⚠ Possible email leak in {cv.get('anon_ref')}")
            leaked += 1
        if PHONE_PATTERN.search(text):
            logger.warning(f"  ⚠ Possible phone leak in {cv.get('anon_ref')}")
            leaked += 1

    if leaked == 0:
        logger.info("✅ No obvious PII leaks detected in anonymised output")
    else:
        logger.warning(f"⚠ {leaked} potential PII issues found — please review manually")

    logger.info(f"\n✅ Anonymised data: {OUTPUT_ANON}")
    logger.info(f"🔒 PII mapping:     {OUTPUT_PII_MAP}")
    logger.info("\n⚠  IMPORTANT:")
    logger.info("   • Add data/processed/pii_mapping.json to .gitignore")
    logger.info("   • Add data/processed/cvs_raw.json to .gitignore")
    logger.info("   • Only cvs_anonymised.json is safe to use in the AI pipeline")
    logger.info("\nNext step: Run scripts/04_build_dataset.py")


if __name__ == "__main__":
    main()
