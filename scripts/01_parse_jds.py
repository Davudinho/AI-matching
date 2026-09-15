"""
scripts/01_parse_jds.py — Week 2, Task 1: Parse Job Descriptions

PURPOSE:
    Reads every .docx file from data/raw/jds/, extracts plain text,
    then asks Gemini to extract structured fields (title, organisation,
    skills, requirements, etc.) and saves the result as data/processed/jds.json.

HOW TO RUN:
    1. Copy your .docx JD files into:  data/raw/jds/
    2. Make sure GEMINI_API_KEY is set in your .env file
    3. From the project root, run:
       python scripts/01_parse_jds.py

OUTPUT:
    data/processed/jds.json         ← Structured dataset (one entry per JD)
    data/processed/jds_parse_log.txt ← Log of what succeeded/failed

WHAT YOU'LL LEARN:
    - How to read Word documents with python-docx
    - How to write structured prompts for AI extraction
    - How to handle JSON responses from Gemini
    - How to build a dataset from raw documents
"""

import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---- Path setup ----
# We add the project root to sys.path so we can import from backend/app/
# This is only needed for standalone scripts — FastAPI handles this automatically.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# ---- Now import our project modules ----
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")  # Load .env BEFORE importing settings

from backend.app.services.gemini_service import gemini
from backend.app.core.config import settings
from backend.app.services.document_parser import extract_text

# ---- Standard library imports ----
import docx  # python-docx: reads .docx files (still used for embedding text builder)

# ---- Logging setup ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# STEP 1: Define paths
# ============================================================

JDS_INPUT_DIR = PROJECT_ROOT / "data" / "raw" / "jds"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_FILE = PROCESSED_DIR / "jds.json"
LOG_FILE = PROCESSED_DIR / "jds_parse_log.txt"

# Create output directory if it doesn't exist
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# STEP 2: Document text extraction
# ============================================================

def extract_text_from_docx(filepath: Path) -> str:
    """
    Read a .docx file and return all its text as a single string.
    
    python-docx represents a Word document as a series of paragraphs.
    We join them with newlines to preserve the structure.
    
    Args:
        filepath: Path to the .docx file
    
    Returns:
        Plain text string (all paragraphs joined)
    
    Example:
        text = extract_text_from_docx(Path("data/raw/jds/6177-Delivery-Manager.docx"))
        print(text[:200])  # First 200 chars of the JD
    """
    doc = docx.Document(str(filepath))

    paragraphs = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:  # Skip empty paragraphs
            paragraphs.append(text)

    # Also extract text from tables (some JDs have tables for requirements)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if text and text not in paragraphs:  # Avoid duplicates
                    paragraphs.append(text)

    return "\n".join(paragraphs)


# ============================================================
# STEP 3: AI-powered field extraction
# ============================================================

# This is the prompt we send to Gemini.
# Notice how specific it is: we tell Gemini exactly what fields we want,
# what format to use, and how to handle missing data.
# A well-designed prompt is the key to getting reliable, structured output.

# Allowed profession domains — MUST use exactly one of these values.
# This standardised vocabulary enables the domain-gate in matching:
# a Creative candidate will never be shown for a Finance role.
PROFESSION_DOMAINS = [
    "Finance",
    "Legal",
    "Procurement",
    "Risk & Audit",
    "Creative & Media",
    "Technology",
    "Healthcare",
    "HR & People",
    "General Management",
    "Other",
]

SYSTEM_INSTRUCTION = """You are an expert HR analyst specialising in job description analysis.
Your task is to extract structured information from job descriptions.
Always return valid JSON. If a field is not mentioned in the JD, use null for strings
and [] for arrays — never invent information that is not in the document.
Be precise and comprehensive — include all skills, requirements, and responsibilities mentioned."""

EXTRACTION_PROMPT_TEMPLATE = """Analyse this job description and extract the following fields.
Return ONLY a valid JSON object with these exact keys.

JOB DESCRIPTION:
---
{jd_text}
---

Extract these fields:
{{
  "title": "exact job title from the JD",
  "organisation": "hiring organisation name",
  "location": "work location (city, region, remote, hybrid etc.)",
  "salary_range": "salary range or band if mentioned, else null",
  "contract_type": "one of: Permanent, Interim, Fixed-term, Freelance, Volunteer, null",
  "seniority_level": "one of: Junior, Mid-level, Senior, Lead, Head, Director, Executive, null",
  "sector": "primary sector: Charity, Finance, Digital, Health, Legal, Education, Government, Tech, Other",

  "profession_domain": "MUST be exactly one of: Finance | Legal | Procurement | Risk & Audit | Creative & Media | Technology | Healthcare | HR & People | General Management | Other. Choose the PRIMARY professional domain this role belongs to. Examples: Senior Finance Officer → Finance. General Counsel → Legal. Delivery Manager (Online Products) → Technology. Creative Producer → Creative & Media. Head of Risk and Internal Audit → Risk & Audit. Procurement Manager → Procurement.",
  "profession_keywords": ["3-5 domain-specific keywords that define what expertise is needed, e.g. for Finance: ['financial reporting', 'budget management', 'P&L responsibility']"],
  "min_years_experience": "<integer: minimum years of professional experience required. Infer from seniority language: 'Junior/Graduate'=1, 'Officer/Manager'=4, 'Senior'=6, 'Head of/Director'=9. Return as integer, not string.>",

  "responsibilities": ["list", "of", "key", "responsibilities"],
  "essential_requirements": ["must-have", "criteria", "from", "the", "JD"],
  "desirable_requirements": ["nice-to-have", "criteria"],
  "skills_technical": ["specific", "technical", "skills", "tools", "software"],
  "skills_soft": ["communication", "leadership", "teamwork", "etc."],
  "qualifications": ["degree requirements", "professional certifications"],
  "missing_fields": ["list any fields above that you could not determine from the text"],
  "quality_flags": ["flag any issues: e.g. 'no salary mentioned', 'vague requirements', 'very long requirements list'"]
}}"""


def extract_jd_fields(raw_text: str, filename: str) -> dict:
    """
    Send JD text to Gemini and return extracted structured fields.
    
    Args:
        raw_text: The plain text of the JD document
        filename: Source filename (used for error messages)
    
    Returns:
        Dict with all extracted fields, plus metadata.
        If extraction fails, returns a dict with error information.
    """
    logger.info(f"  Extracting fields from {filename} ({len(raw_text)} chars)...")

    # Format the prompt with the actual JD text
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        jd_text=raw_text[:12000]  # Limit to ~12,000 chars to stay within token limits
    )

    # Call Gemini — this is where the AI magic happens
    result = gemini.generate_json(
        prompt=prompt,
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0.0,  # 0 = deterministic: same JD → same extraction every time
    )

    if result is None:
        logger.error(f"  ✗ Gemini returned None for {filename}")
        return {
            "extraction_status": "failed",
            "error": "Gemini returned no response",
        }

    # Add metadata fields that are not in the AI response
    result["extraction_status"] = "success"
    result["raw_text"] = raw_text

    # Build the "embedding_text" — a focused representation used for vector search.
    # We don't embed the whole raw text; we embed the most semantically important parts.
    result["embedding_text"] = _build_jd_embedding_text(result)

    logger.info(f"  ✓ Extracted: title='{result.get('title')}' | sector='{result.get('sector')}'")
    return result


def _build_jd_embedding_text(fields: dict) -> str:
    """
    Build a focused text representation of a JD for embedding.

    WEEK 4 UPDATE: profession_domain and profession_keywords are now
    placed at the TOP of the embedding text. This makes the embedding
    more domain-specific — a Finance JD embedding will be semantically
    farther from a Creative CV embedding than it was before.

    Why not embed the entire raw text?
    - Raw text contains boilerplate (application instructions, etc.)
    - A focused representation makes similarity search more accurate
    """
    parts = []

    # Domain fields FIRST — they anchor the semantic space of this JD
    if fields.get("profession_domain"):
        parts.append(f"Professional Domain: {fields['profession_domain']}")
    if fields.get("profession_keywords"):
        kws = fields["profession_keywords"]
        if isinstance(kws, list):
            parts.append(f"Domain Keywords: {', '.join(kws[:5])}")

    if fields.get("title"):
        parts.append(f"Job Title: {fields['title']}")
    if fields.get("organisation"):
        parts.append(f"Organisation: {fields['organisation']}")
    if fields.get("seniority_level"):
        parts.append(f"Seniority: {fields['seniority_level']}")
    if fields.get("sector"):
        parts.append(f"Sector: {fields['sector']}")
    if fields.get("responsibilities"):
        responsibilities = fields["responsibilities"]
        if isinstance(responsibilities, list):
            parts.append("Responsibilities: " + "; ".join(responsibilities[:10]))
    if fields.get("essential_requirements"):
        reqs = fields["essential_requirements"]
        if isinstance(reqs, list):
            parts.append("Essential Requirements: " + "; ".join(reqs[:10]))
    if fields.get("skills_technical"):
        skills = fields["skills_technical"]
        if isinstance(skills, list):
            parts.append("Technical Skills: " + ", ".join(skills[:15]))
    if fields.get("qualifications"):
        quals = fields["qualifications"]
        if isinstance(quals, list):
            parts.append("Qualifications: " + "; ".join(quals[:5]))

    return "\n".join(parts)


# ============================================================
# STEP 4: Main processing loop
# ============================================================

def main():
    """
    Main function: processes all supported JD files in data/raw/jds/
    (formats: .docx, .pdf, .doc, .txt) and saves structured output
    to data/processed/jds.json
    """
    logger.info("=" * 60)
    logger.info("Week 2 — Task 1: Parsing Job Descriptions")
    logger.info("=" * 60)

    # Find all supported JD files in the input directory
    jd_files = sorted(
        f
        for pattern in ["*.docx", "*.pdf", "*.doc", "*.txt"]
        for f in JDS_INPUT_DIR.glob(pattern)
    )

    if not jd_files:
        logger.error(
            f"No supported JD files found in {JDS_INPUT_DIR}\n"
            f"Supported formats: .docx, .pdf, .doc, .txt\n"
            f"Please copy your JD files there and run again."
        )
        sys.exit(1)

    logger.info(f"Found {len(jd_files)} JD file(s) to process:")
    for f in jd_files:
        logger.info(f"  • {f.name}")

    # Check if output file already exists (to allow resuming interrupted runs)
    existing_jds = []
    processed_filenames = set()
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing_jds = json.load(f)
        processed_filenames = {jd["filename"] for jd in existing_jds}
        logger.info(f"Resuming: {len(existing_jds)} JDs already processed")

    # Process each JD file
    results = existing_jds.copy()
    log_lines = []

    for jd_file in jd_files:
        filename = jd_file.name

        # Skip already-processed files (allows safe resumption)
        if filename in processed_filenames:
            logger.info(f"⏭  Skipping {filename} (already processed)")
            continue

        logger.info(f"\n{'─' * 50}")
        logger.info(f"Processing: {filename}")

        try:
            # Step A: Extract plain text from the document
            raw_text = extract_text(jd_file)

            if len(raw_text) < 100:
                logger.warning(f"  ⚠ Very short document ({len(raw_text)} chars) — may be empty or corrupted")

            # Step B: Ask Gemini to extract structured fields
            fields = extract_jd_fields(raw_text, filename)

            # Step C: Add our own metadata (not from Gemini)
            jd_record = {
                "jd_id": str(uuid.uuid4()),   # Unique identifier for this JD
                "filename": filename,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                **fields,                       # Merge all AI-extracted fields
            }

            results.append(jd_record)

            # Save after each file (incremental saves prevent data loss if script crashes)
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)

            log_lines.append(f"✓ {filename} → title: {fields.get('title', 'unknown')}")
            logger.info(f"  ✓ Saved to {OUTPUT_FILE}")

        except Exception as e:
            logger.error(f"  ✗ Failed to process {filename}: {e}")
            log_lines.append(f"✗ {filename} → ERROR: {e}")

    # ============================================================
    # STEP 5: Print summary
    # ============================================================

    logger.info(f"\n{'=' * 60}")
    logger.info("SUMMARY")
    logger.info(f"{'=' * 60}")
    logger.info(f"Total JDs processed: {len(results)}")

    # Count quality issues across all JDs
    total_missing = sum(len(jd.get("missing_fields") or []) for jd in results)
    total_flags = sum(len(jd.get("quality_flags") or []) for jd in results)
    logger.info(f"Missing fields across all JDs: {total_missing}")
    logger.info(f"Quality flags across all JDs: {total_flags}")

    # Show sector breakdown
    sectors = {}
    for jd in results:
        sector = jd.get("sector") or "Unknown"
        sectors[sector] = sectors.get(sector, 0) + 1
    logger.info("\nSectors found:")
    for sector, count in sorted(sectors.items(), key=lambda x: -x[1]):
        logger.info(f"  {sector}: {count} JD(s)")

    # Save log file
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"JD Parse Log — {datetime.now().isoformat()}\n")
        f.write("=" * 60 + "\n")
        f.write("\n".join(log_lines))

    logger.info(f"\n✅ Output saved to: {OUTPUT_FILE}")
    logger.info(f"📋 Log saved to: {LOG_FILE}")
    logger.info("\nNext step: Run scripts/02_parse_cvs.py")


if __name__ == "__main__":
    main()
