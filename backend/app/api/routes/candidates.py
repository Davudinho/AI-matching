"""
backend/app/api/routes/candidates.py — Candidate (CV) API Endpoints

Endpoints:
  GET  /api/v1/candidates/          → List all anonymised candidates
  GET  /api/v1/candidates/{cv_id}   → Get a specific candidate
  POST /api/v1/candidates/apply     → PUBLIC: upload CV + apply to a JD
                                       Parses → anonymises → embeds → matches (background)
"""

import io
import json
import re
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from backend.app.core.database import get_db
from backend.app.services.document_parser import extract_text, SUPPORTED_EXTENSIONS
from backend.app.services.gemini_service import gemini

router = APIRouter()

# ---- Anonymisation helpers ----

_PII_PATTERNS = [
    # Email
    (re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"), "[EMAIL]"),
    # UK mobile
    (re.compile(r"(\+44|0)[\s\-]?7\d{3}[\s\-]?\d{3}[\s\-]?\d{3}"), "[PHONE]"),
    # Generic phone
    (re.compile(r"\b(\+?\d[\d\s\-().]{7,}\d)\b"), "[PHONE]"),
    # LinkedIn / Twitter / GitHub URLs with usernames
    (re.compile(r"(linkedin\.com/in/|twitter\.com/|github\.com/)[\w\-]+", re.I), r"\1[USER]"),
    # Postcodes (UK)
    (re.compile(r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}\b"), "[POSTCODE]"),
]


def _anonymise_text(text: str) -> str:
    """Remove PII from extracted CV text."""
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ---- CV Field Extraction via Gemini ----

_CV_EXTRACT_PROMPT = """Extract structured fields from this anonymised CV text. Return JSON only.

CV TEXT:
{text}

Return exactly this JSON structure (use null for missing fields, empty arrays [] for missing lists):
{{
  "current_title": "most recent job title",
  "years_experience": <integer or null>,
  "career_summary": "2-sentence professional summary (no PII)",
  "skills_technical": ["skill1", "skill2"],
  "skills_soft": ["skill1", "skill2"],
  "education": [{{"degree": "...", "institution": "...", "year": null}}],
  "work_history": [{{"title": "...", "org": "...", "duration": "...", "description": "..."}}],
  "certifications": ["cert1"],
  "languages": ["English", "French"],
  "sector_experience": ["Charity", "Finance"],
  "right_to_work_uk": <true/false/null>,
  "profession_domain": "one of: Creative & Media | Finance | Legal | Digital & Tech | Health & Social Care | Education | HR & People | Operations & Admin | Other"
}}"""


async def _parse_and_store_candidate(
    raw_text: str,
    filename: str,
    jd_id: str,
    db: AsyncSession,
) -> Optional[str]:
    """
    Full pipeline for a single candidate:
    1. Anonymise text
    2. Extract fields via Gemini
    3. Generate embedding
    4. Store candidate + embedding in DB
    5. Run 3-stage matching against specified JD
    Returns the new cv_id or None on failure.
    """
    anon_text = _anonymise_text(raw_text)

    # Extract structured fields
    fields = gemini.generate_json(
        _CV_EXTRACT_PROMPT.format(text=anon_text[:15000]),
        temperature=0.0,
    )
    if not fields:
        return None

    # Build embedding text (focused, anonymised)
    embedding_parts = [
        f"Title: {fields.get('current_title', '')}",
        f"Skills: {', '.join((fields.get('skills_technical') or [])[:15])}",
        f"Sector experience: {', '.join((fields.get('sector_experience') or [])[:5])}",
        f"Summary: {fields.get('career_summary', '')}",
    ]
    embedding_text = "\n".join(p for p in embedding_parts if p)

    cv_id = str(uuid.uuid4())

    # Generate a sequential anon_ref (CAND-NNN)
    count_res = await db.execute(text("SELECT COUNT(*) FROM candidates"))
    count = count_res.scalar() or 0
    anon_ref = f"CAND-{count + 1:03d}"

    # Store candidate
    await db.execute(text("""
        INSERT INTO candidates (
            cv_id, filename, anon_ref,
            current_title, years_experience, career_summary,
            skills_technical, skills_soft,
            education, work_history, certifications, languages,
            sector_experience, right_to_work_uk,
            profession_domain,
            raw_text_anon, embedding_text, missing_fields
        ) VALUES (
            :cv_id, :filename, :anon_ref,
            :current_title, :years_experience, :career_summary,
            :skills_technical::jsonb, :skills_soft::jsonb,
            :education::jsonb, :work_history::jsonb, :certifications::jsonb, :languages::jsonb,
            :sector_experience::jsonb, :right_to_work_uk,
            :profession_domain,
            :raw_text_anon, :embedding_text, '[]'::jsonb
        )
    """), {
        "cv_id": cv_id,
        "filename": filename,
        "anon_ref": anon_ref,
        "current_title": fields.get("current_title"),
        "years_experience": fields.get("years_experience"),
        "career_summary": fields.get("career_summary"),
        "skills_technical": json.dumps(fields.get("skills_technical") or []),
        "skills_soft": json.dumps(fields.get("skills_soft") or []),
        "education": json.dumps(fields.get("education") or []),
        "work_history": json.dumps(fields.get("work_history") or []),
        "certifications": json.dumps(fields.get("certifications") or []),
        "languages": json.dumps(fields.get("languages") or []),
        "sector_experience": json.dumps(fields.get("sector_experience") or []),
        "right_to_work_uk": fields.get("right_to_work_uk"),
        "profession_domain": fields.get("profession_domain"),
        "raw_text_anon": anon_text[:50000],
        "embedding_text": embedding_text,
    })

    await db.commit()

    # Generate and store embedding
    embedding_vec = gemini.embed_text(embedding_text, task_type="RETRIEVAL_DOCUMENT")
    if embedding_vec:
        vec_str = "[" + ",".join(str(v) for v in embedding_vec) + "]"
        await db.execute(text("""
            INSERT INTO cv_embeddings (cv_id, model, embedding)
            VALUES (:cv_id, :model, :embedding::vector)
            ON CONFLICT (cv_id, model) DO UPDATE SET embedding = EXCLUDED.embedding
        """), {
            "cv_id": cv_id,
            "model": "gemini-embedding-001",
            "embedding": vec_str,
        })
        await db.commit()

    # Insert a placeholder match result so the recruiter sees this candidate
    await db.execute(text("""
        INSERT INTO ai_match_results (jd_id, cv_id)
        VALUES (:jd_id, :cv_id)
        ON CONFLICT (jd_id, cv_id) DO NOTHING
    """), {"jd_id": jd_id, "cv_id": cv_id})
    await db.commit()

    return cv_id


# ---- Endpoints ----

@router.get("/")
async def list_candidates(
    skip: int = 0,
    limit: int = 20,
    sector: Optional[str] = None,
    min_years_exp: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all anonymised candidates with optional filtering."""
    limit = min(limit, 100)

    conditions = []
    params = {"limit": limit, "skip": skip}

    if sector:
        conditions.append("sector_experience @> :sector::jsonb")
        params["sector"] = f'["{sector}"]'
    if min_years_exp is not None:
        conditions.append("years_experience >= :min_years_exp")
        params["min_years_exp"] = min_years_exp

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    result = await db.execute(text(f"""
        SELECT cv_id, anon_ref, current_title, years_experience,
               skills_technical, sector_experience, right_to_work_uk, created_at
        FROM candidates
        {where}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :skip
    """), params)

    rows = result.mappings().all()
    return {"total": len(rows), "skip": skip, "limit": limit, "items": [dict(r) for r in rows]}


@router.get("/{cv_id}")
async def get_candidate(cv_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific candidate by ID."""
    result = await db.execute(
        text("SELECT * FROM candidates WHERE cv_id = :cv_id"),
        {"cv_id": cv_id}
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Candidate {cv_id} not found")
    return dict(row)


@router.post("/apply", status_code=status.HTTP_202_ACCEPTED)
async def apply_to_job(
    background_tasks: BackgroundTasks,
    jd_id: str = Form(..., description="Job Description ID to apply to"),
    file: UploadFile = File(..., description="CV file (PDF, DOCX, or TXT)"),
    db: AsyncSession = Depends(get_db),
):
    """
    PUBLIC endpoint — Candidate applies to a job by uploading their CV.

    Pipeline (runs synchronously for now, moved to background for large files):
    1. Validate file format
    2. Extract text (PDF/DOCX/TXT)
    3. Anonymise PII
    4. Extract structured fields with Gemini
    5. Generate embedding
    6. Store candidate in DB
    7. Create placeholder match result (recruiter will see this candidate)

    Note: The full 3-stage AI matching score is computed separately.
    The candidate appears immediately in the recruiter's dashboard.
    """
    # Validate JD exists
    jd_check = await db.execute(
        text("SELECT jd_id, title FROM job_descriptions WHERE jd_id = :jd_id"),
        {"jd_id": jd_id},
    )
    jd = jd_check.mappings().first()
    if not jd:
        raise HTTPException(status_code=404, detail=f"Job {jd_id} not found")

    # Validate file extension
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    # Reject old .doc on Linux-based deployments (pywin32 not available)
    import sys
    if suffix == ".doc" and sys.platform != "win32":
        raise HTTPException(
            status_code=400,
            detail="Old .doc files are not supported on this server. Please convert to .pdf or .docx.",
        )

    # Read file bytes and parse to text
    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=413, detail="File too large. Maximum size: 10 MB")

    try:
        # Write to a temp file so document_parser can open it
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)

        raw_text = extract_text(tmp_path)
        os.unlink(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not extract text from file: {e}")

    if len(raw_text.strip()) < 50:
        raise HTTPException(
            status_code=422,
            detail="Could not extract enough text from the file. Please try a different format.",
        )

    # Run full pipeline (parse → store → embed) — this takes ~5-10 seconds
    cv_id = await _parse_and_store_candidate(
        raw_text=raw_text,
        filename=file.filename,
        jd_id=jd_id,
        db=db,
    )

    if not cv_id:
        raise HTTPException(
            status_code=502,
            detail="AI processing failed. Please try again in a moment.",
        )

    return {
        "status": "received",
        "message": (
            f"Your application for '{jd['title']}' has been received. "
            "Our team will review it shortly."
        ),
        "application_ref": cv_id[:8].upper(),  # Short ref for the candidate to quote
    }
