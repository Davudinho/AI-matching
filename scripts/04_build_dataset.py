"""
scripts/04_build_dataset.py — Week 2, Task 4: Build PostgreSQL Dataset

PURPOSE:
    Reads the processed JD and CV JSON files and imports them into
    PostgreSQL. Also validates data quality and generates the dataset
    documentation markdown file.

    This script completes Week 2 — after running it, you have a clean,
    structured, queryable dataset ready for the Week 3 AI matching work.

HOW TO RUN:
    1. Make sure Docker is running and PostgreSQL is up:
       docker compose up -d
    2. Run:
       python scripts/04_build_dataset.py

INPUT:
    data/processed/jds.json
    data/processed/cvs_anonymised.json

OUTPUT:
    PostgreSQL tables populated: job_descriptions, candidates
    docs/dataset_documentation.md
    data/processed/dataset_summary.json
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# Use psycopg2 (sync) for this script — simpler than async for one-off data loading
import psycopg2
import psycopg2.extras  # For execute_values (bulk inserts)

from backend.app.core.config import settings

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
JDS_FILE = PROCESSED_DIR / "jds.json"
CVS_FILE = PROCESSED_DIR / "cvs_anonymised.json"
DOCS_DIR = PROJECT_ROOT / "docs"
DOCS_DIR.mkdir(parents=True, exist_ok=True)
DOC_OUTPUT = DOCS_DIR / "dataset_documentation.md"
SUMMARY_OUTPUT = PROCESSED_DIR / "dataset_summary.json"


# ============================================================
# STEP 1: Database connection
# ============================================================

def get_connection():
    """
    Create a synchronous PostgreSQL connection using psycopg2.
    
    We use the standard DATABASE_URL from settings, but psycopg2
    needs a slightly different format (no 'postgresql+asyncpg://').
    """
    # Clean up the URL for psycopg2 (remove async driver prefix)
    db_url = settings.DATABASE_URL
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        logger.info("✓ Connected to PostgreSQL")
        return conn
    except Exception as e:
        logger.error(f"✗ Failed to connect to PostgreSQL: {e}")
        logger.error("Make sure Docker is running: docker compose up -d")
        raise


# ============================================================
# STEP 2: Data validation
# ============================================================

def validate_jd(jd: dict) -> tuple[bool, list[str]]:
    """
    Validate a JD record and return (is_valid, list_of_warnings).
    
    We don't reject JDs for having missing fields — we just flag them
    so the dataset documentation accurately describes data quality.
    """
    warnings = []

    if not jd.get("title"):
        warnings.append("missing title")
    if not jd.get("organisation"):
        warnings.append("missing organisation")
    if not jd.get("skills_technical") and not jd.get("skills_soft"):
        warnings.append("no skills listed")
    if not jd.get("essential_requirements"):
        warnings.append("no essential requirements")
    if not jd.get("sector"):
        warnings.append("sector unknown")
    if not jd.get("salary_range"):
        warnings.append("no salary information")

    return True, warnings  # Always valid — warnings are informational


def validate_cv(cv: dict) -> tuple[bool, list[str]]:
    """Validate an anonymised CV record."""
    warnings = []

    if not cv.get("current_title"):
        warnings.append("missing current title")
    if not cv.get("years_experience"):
        warnings.append("years of experience unknown")
    if not cv.get("skills_technical") and not cv.get("skills_soft"):
        warnings.append("no skills listed")
    if not cv.get("work_history"):
        warnings.append("no work history")
    if not cv.get("sector_experience"):
        warnings.append("sector experience unknown")

    return True, warnings


# ============================================================
# STEP 3: Database insertion
# ============================================================

def insert_jds(conn, jds: list[dict]) -> list[dict]:
    """
    Insert JD records into the job_descriptions table.
    
    We use psycopg2.extras.execute_values for bulk inserts — 
    much faster than inserting one row at a time.
    
    Returns list of JDs with any validation warnings added.
    """
    cursor = conn.cursor()
    inserted = 0
    skipped = 0
    jds_with_warnings = []

    for jd in jds:
        _, warnings = validate_jd(jd)
        jd["validation_warnings"] = warnings
        jds_with_warnings.append(jd)

        try:
            # We use ON CONFLICT DO NOTHING so re-running the script
            # doesn't duplicate data — it just skips existing records.
            cursor.execute("""
                INSERT INTO job_descriptions (
                    jd_id, filename, title, organisation, location,
                    salary_range, contract_type, seniority_level, sector,
                    responsibilities, essential_requirements, desirable_requirements,
                    skills_technical, skills_soft, qualifications,
                    profession_domain, profession_keywords, min_years_experience,
                    raw_text, embedding_text, missing_fields, quality_flags
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (jd_id) DO UPDATE SET
                    profession_domain    = EXCLUDED.profession_domain,
                    profession_keywords  = EXCLUDED.profession_keywords,
                    min_years_experience = EXCLUDED.min_years_experience,
                    embedding_text       = EXCLUDED.embedding_text
            """, (
                jd["jd_id"],
                jd.get("filename"),
                jd.get("title"),
                jd.get("organisation"),
                jd.get("location"),
                jd.get("salary_range"),
                jd.get("contract_type"),
                jd.get("seniority_level"),
                jd.get("sector"),
                json.dumps(jd.get("responsibilities") or []),
                json.dumps(jd.get("essential_requirements") or []),
                json.dumps(jd.get("desirable_requirements") or []),
                json.dumps(jd.get("skills_technical") or []),
                json.dumps(jd.get("skills_soft") or []),
                json.dumps(jd.get("qualifications") or []),
                # New Week 4 fields
                jd.get("profession_domain"),
                json.dumps(jd.get("profession_keywords") or []),
                jd.get("min_years_experience"),
                jd.get("raw_text"),
                jd.get("embedding_text"),
                json.dumps(jd.get("missing_fields") or []),
                json.dumps(jd.get("quality_flags") or []),
            ))

            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1  # Already existed

        except Exception as e:
            logger.error(f"  ✗ Failed to insert JD {jd.get('jd_id')}: {e}")
            conn.rollback()

    conn.commit()
    cursor.close()
    logger.info(f"JDs: {inserted} inserted, {skipped} already existed")
    return jds_with_warnings


def insert_candidates(conn, cvs: list[dict]) -> list[dict]:
    """
    Insert anonymised CV records into the candidates table.
    Same pattern as insert_jds().
    """
    cursor = conn.cursor()
    inserted = 0
    skipped = 0
    cvs_with_warnings = []

    for cv in cvs:
        _, warnings = validate_cv(cv)
        cv["validation_warnings"] = warnings
        cvs_with_warnings.append(cv)

        try:
            cursor.execute("""
                INSERT INTO candidates (
                    cv_id, filename, anon_ref, current_title, years_experience,
                    skills_technical, skills_soft, education, work_history,
                    certifications, languages, right_to_work_uk, sector_experience,
                    profession_domain, career_summary,
                    raw_text_anon, embedding_text, missing_fields
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s
                )
                ON CONFLICT (cv_id) DO UPDATE SET
                    profession_domain = EXCLUDED.profession_domain,
                    career_summary    = EXCLUDED.career_summary,
                    embedding_text    = EXCLUDED.embedding_text
            """, (
                cv["cv_id"],
                cv.get("filename"),
                cv.get("anon_ref"),
                cv.get("current_title"),
                cv.get("years_experience"),
                json.dumps(cv.get("skills_technical") or []),
                json.dumps(cv.get("skills_soft") or []),
                json.dumps(cv.get("education") or []),
                json.dumps(cv.get("work_history") or []),
                json.dumps(cv.get("certifications") or []),
                json.dumps(cv.get("languages") or []),
                cv.get("right_to_work_uk"),
                json.dumps(cv.get("sector_experience") or []),
                # New Week 4 fields
                cv.get("profession_domain"),
                cv.get("career_summary"),
                cv.get("raw_text_anon"),
                cv.get("embedding_text"),
                json.dumps(cv.get("missing_fields") or []),
            ))

            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1

        except Exception as e:
            logger.error(f"  ✗ Failed to insert CV {cv.get('cv_id')}: {e}")
            conn.rollback()

    conn.commit()
    cursor.close()
    logger.info(f"Candidates: {inserted} inserted, {skipped} already existed")
    return cvs_with_warnings


# ============================================================
# STEP 4: Generate dataset documentation
# ============================================================

def generate_documentation(jds: list[dict], cvs: list[dict]) -> str:
    """
    Generate a markdown documentation file describing the dataset.
    
    This is a required Week 2 deliverable. It describes:
    - What the dataset contains
    - How it was created
    - Data quality metrics
    - Field definitions
    - Known limitations
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Calculate statistics
    jd_sectors = {}
    for jd in jds:
        sector = jd.get("sector") or "Unknown"
        jd_sectors[sector] = jd_sectors.get(sector, 0) + 1

    jd_with_salary = sum(1 for jd in jds if jd.get("salary_range"))
    jd_with_skills = sum(1 for jd in jds if jd.get("skills_technical"))
    jd_warnings = sum(len(jd.get("validation_warnings", [])) for jd in jds)

    cv_with_exp = sum(1 for cv in cvs if cv.get("years_experience"))
    cv_with_skills = sum(1 for cv in cvs if cv.get("skills_technical"))
    cv_with_rtw = sum(1 for cv in cvs if cv.get("right_to_work_uk") is True)
    cv_warnings = sum(len(cv.get("validation_warnings", [])) for cv in cvs)

    sectors_table = "\n".join([
        f"| {sector} | {count} |"
        for sector, count in sorted(jd_sectors.items(), key=lambda x: -x[1])
    ])

    doc = f"""# Diversifying.io — Dataset Documentation

**Generated:** {now}  
**Week:** 2 (Data Preparation)  
**Status:** Complete

---

## Overview

This dataset was created as part of the Week 2 data preparation phase of the
Diversifying.io AI Recruitment Tool internship project. It contains structured,
anonymised job descriptions and candidate CVs for use in the Week 3 AI matching
experiments.

---

## Dataset Summary

| Metric | Value |
|--------|-------|
| Job Descriptions | {len(jds)} |
| Candidate CVs (anonymised) | {len(cvs)} |
| Possible JD × CV pairs | {len(jds) * len(cvs)} |

---

## Job Descriptions

### Sources
JDs were collected from UNICEF UK and similar UK-based organisations.
All JDs are in the public domain (advertised roles).

### Statistics

| Metric | Value |
|--------|-------|
| Total JDs | {len(jds)} |
| JDs with salary info | {jd_with_salary} / {len(jds)} |
| JDs with technical skills | {jd_with_skills} / {len(jds)} |
| Total validation warnings | {jd_warnings} |

### Sector Breakdown

| Sector | Count |
|--------|-------|
{sectors_table}

### Fields Extracted

| Field | Type | Description |
|-------|------|-------------|
| `jd_id` | UUID | Unique identifier |
| `filename` | String | Source filename |
| `title` | String | Job title |
| `organisation` | String | Hiring organisation |
| `location` | String | Work location |
| `salary_range` | String | Salary if mentioned |
| `contract_type` | String | Permanent/Interim/Fixed-term |
| `seniority_level` | String | Junior/Senior/Head/Director |
| `sector` | String | Industry sector |
| `responsibilities` | Array | Key responsibilities |
| `essential_requirements` | Array | Must-have criteria |
| `desirable_requirements` | Array | Nice-to-have criteria |
| `skills_technical` | Array | Hard skills and tools |
| `skills_soft` | Array | Soft skills |
| `qualifications` | Array | Degree/cert requirements |
| `raw_text` | Text | Full document text |
| `embedding_text` | Text | Focused text for AI embedding |

---

## Candidate CVs

### Privacy & GDPR

All CVs have been **anonymised** in compliance with UK GDPR:
- Full names → `[NAME]`
- Email addresses → `[EMAIL]`
- Phone numbers → `[PHONE]`
- Home addresses → `[ADDRESS]`
- Social media URLs → `[URL]`
- Postcodes → `[POSTCODE]`

The PII mapping file (`pii_mapping.json`) is stored separately,
access-restricted, and excluded from version control.

Each candidate is referred to by an anonymous reference (e.g. `CAND-001`).

### Statistics

| Metric | Value |
|--------|-------|
| Total CVs | {len(cvs)} |
| CVs with years of experience | {cv_with_exp} / {len(cvs)} |
| CVs with technical skills | {cv_with_skills} / {len(cvs)} |
| CVs with UK right-to-work stated | {cv_with_rtw} / {len(cvs)} |
| Total validation warnings | {cv_warnings} |

### Fields in Anonymised Dataset

| Field | Type | Description |
|-------|------|-------------|
| `cv_id` | UUID | Unique identifier |
| `anon_ref` | String | Anonymous reference (CAND-001, etc.) |
| `current_title` | String | Most recent job title |
| `years_experience` | Integer | Estimated years of experience |
| `skills_technical` | Array | Hard skills and tools |
| `skills_soft` | Array | Soft skills |
| `education` | Array | Degrees and institutions |
| `work_history` | Array | Past roles and descriptions |
| `certifications` | Array | Professional certifications |
| `languages` | Array | Spoken languages |
| `right_to_work_uk` | Boolean | UK work authorisation |
| `sector_experience` | Array | Industry sectors worked in |
| `raw_text_anon` | Text | Anonymised full CV text |
| `embedding_text` | Text | Focused text for AI embedding |

---

## Data Quality Notes

### Known Limitations

1. **Small dataset size**: {len(jds)} JDs and {len(cvs)} CVs is a small sample.
   AI matching quality metrics will be indicative, not statistically robust.
   
2. **AI extraction accuracy**: Fields were extracted by Gemini (LLM). 
   Accuracy is high for well-structured documents but may miss nuance in
   free-form or unusually formatted documents.

3. **Salary data**: Many JDs ({len(jds) - jd_with_salary}/{len(jds)}) do not include salary information.
   This limits salary-based filtering in the matching system.

4. **Right-to-work**: Most CVs do not explicitly state UK work authorisation.
   `null` means "not mentioned", not "no right to work".

### Improvement Suggestions (for Week 4)

- Expand to 50+ JDs and 100+ CVs for statistically meaningful evaluation
- Add a human review step to validate AI extraction accuracy
- Create a structured intake form for new CVs to ensure consistent data quality

---

## How to Reproduce This Dataset

```bash
# 1. Place JD .docx files in data/raw/jds/
# 2. Place CV .docx/.pdf files in data/raw/cvs/
# 3. Run pipeline:
python scripts/01_parse_jds.py
python scripts/02_parse_cvs.py
python scripts/03_anonymise_cvs.py
python scripts/04_build_dataset.py
```

---

## Files

| File | Description | Sensitive? |
|------|-------------|------------|
| `data/processed/jds.json` | Structured JD dataset | No |
| `data/processed/cvs_anonymised.json` | Anonymised CV dataset | No |
| `data/processed/cvs_raw.json` | Raw CV dataset with PII | **YES** |
| `data/processed/pii_mapping.json` | PII mapping table | **YES** |
"""

    return doc


# ============================================================
# STEP 5: Main
# ============================================================

def main():
    logger.info("=" * 60)
    logger.info("Week 2 — Task 4: Building PostgreSQL Dataset")
    logger.info("=" * 60)

    # Load JSON files
    if not JDS_FILE.exists():
        logger.error(f"JDs file not found: {JDS_FILE}. Run 01_parse_jds.py first.")
        sys.exit(1)
    if not CVS_FILE.exists():
        logger.error(f"CVs file not found: {CVS_FILE}. Run 02 and 03 scripts first.")
        sys.exit(1)

    with open(JDS_FILE, "r", encoding="utf-8") as f:
        jds = json.load(f)
    logger.info(f"Loaded {len(jds)} JDs")

    with open(CVS_FILE, "r", encoding="utf-8") as f:
        cvs = json.load(f)
    logger.info(f"Loaded {len(cvs)} anonymised CVs")

    # Connect to DB and insert
    conn = get_connection()

    try:
        logger.info("\nInserting JDs into PostgreSQL...")
        jds = insert_jds(conn, jds)

        logger.info("Inserting Candidates into PostgreSQL...")
        cvs = insert_candidates(conn, cvs)

    finally:
        conn.close()

    # Generate documentation
    logger.info("\nGenerating dataset documentation...")
    doc_content = generate_documentation(jds, cvs)
    with open(DOC_OUTPUT, "w", encoding="utf-8") as f:
        f.write(doc_content)
    logger.info(f"✓ Documentation saved to {DOC_OUTPUT}")

    # Save summary JSON
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "jd_count": len(jds),
        "cv_count": len(cvs),
        "total_pairs": len(jds) * len(cvs),
        "jd_sectors": {},
        "jd_ids": [jd["jd_id"] for jd in jds],
        "cv_ids": [cv["cv_id"] for cv in cvs],
    }
    for jd in jds:
        sector = jd.get("sector") or "Unknown"
        summary["jd_sectors"][sector] = summary["jd_sectors"].get(sector, 0) + 1

    with open(SUMMARY_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info(f"\n{'=' * 60}")
    logger.info("✅ WEEK 2 COMPLETE!")
    logger.info(f"{'=' * 60}")
    logger.info(f"  JDs in database:      {len(jds)}")
    logger.info(f"  Candidates in DB:     {len(cvs)}")
    logger.info(f"  Possible match pairs: {len(jds) * len(cvs)}")
    logger.info(f"\n  Documentation:  {DOC_OUTPUT}")
    logger.info(f"  Dataset summary: {SUMMARY_OUTPUT}")
    logger.info("\nNext step: Run scripts/05_embed_and_store.py (Week 3 begins!)")


if __name__ == "__main__":
    main()
