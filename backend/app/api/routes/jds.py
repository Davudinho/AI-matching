"""backend/app/api/routes/jds.py — Job Descriptions API Endpoints

Endpoints:
  GET    /api/v1/jds/                  → List all JDs (with pagination)
  GET    /api/v1/jds/{jd_id}           → Get a specific JD
  POST   /api/v1/jds/upload            → Upload PDF/DOCX → Gemini parses → DB  [Auth required]
  POST   /api/v1/jds/create-from-text  → Free-text input → Gemini parses → DB  [Auth required]
  DELETE /api/v1/jds/{jd_id}           → Delete a JD                            [Auth required]
"""

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.services.document_parser import extract_text, SUPPORTED_EXTENSIONS
from backend.app.services.gemini_service import gemini
from backend.app.api.routes.auth import require_recruiter

router = APIRouter()

# ---- Shared helpers ----

_JD_EXTRACT_PROMPT = """Extract structured fields from this job description. Return JSON only.

JD TEXT:
{text}

Return exactly this JSON structure (use null for missing fields, [] for missing arrays):
{{
  "title": "job title",
  "organisation": "company name",
  "location": "city or remote",
  "salary_range": "e.g. £40,000 - £50,000 or null",
  "contract_type": "Permanent | Interim | Fixed-term | Freelance",
  "seniority_level": "Junior | Mid | Senior | Head | Director | Executive",
  "sector": "Charity | Finance | Digital | Health | Legal | Education | HR | Operations | Other",
  "responsibilities": ["responsibility 1", "responsibility 2"],
  "essential_requirements": ["requirement 1", "requirement 2"],
  "desirable_requirements": ["desirable 1"],
  "skills_technical": ["Python", "SQL"],
  "skills_soft": ["leadership", "communication"],
  "qualifications": ["degree or certification"],
  "profession_domain": "Creative & Media | Finance | Legal | Digital & Tech | Health & Social Care | Education | HR & People | Operations & Admin | Other",
  "min_years_experience": <integer or null>,
  "missing_fields": ["field names not found"],
  "quality_flags": ["e.g. vague requirements"]
}}"""


def _build_jd_embedding_text(fields: dict) -> str:
    parts = [
        f"Title: {fields.get('title', '')}",
        f"Organisation: {fields.get('organisation', '')}",
        f"Sector: {fields.get('sector', '')}",
        f"Technical skills: {', '.join((fields.get('skills_technical') or [])[:15])}",
        f"Requirements: {'; '.join((fields.get('essential_requirements') or [])[:8])}",
        f"Responsibilities: {'; '.join((fields.get('responsibilities') or [])[:5])}",
    ]
    return "\n".join(p for p in parts if p.split(": ", 1)[-1].strip())


async def _insert_jd(db: AsyncSession, fields: dict, raw_text: str, filename: str) -> str:
    """Insert a parsed JD into the database. Returns the new jd_id."""
    jd_id = str(uuid.uuid4())
    embedding_text = _build_jd_embedding_text(fields)

    await db.execute(text("""
        INSERT INTO job_descriptions (
            jd_id, filename, title, organisation, location,
            salary_range, contract_type, seniority_level, sector,
            responsibilities, essential_requirements, desirable_requirements,
            skills_technical, skills_soft, qualifications,
            profession_domain, profession_keywords, min_years_experience,
            raw_text, embedding_text, missing_fields, quality_flags
        ) VALUES (
            :jd_id, :filename, :title, :organisation, :location,
            :salary_range, :contract_type, :seniority_level, :sector,
            :responsibilities::jsonb, :essential_requirements::jsonb, :desirable_requirements::jsonb,
            :skills_technical::jsonb, :skills_soft::jsonb, :qualifications::jsonb,
            :profession_domain, '[]'::jsonb, :min_years_experience,
            :raw_text, :embedding_text, :missing_fields::jsonb, :quality_flags::jsonb
        )
    """), {
        "jd_id": jd_id,
        "filename": filename,
        "title": fields.get("title"),
        "organisation": fields.get("organisation"),
        "location": fields.get("location"),
        "salary_range": fields.get("salary_range"),
        "contract_type": fields.get("contract_type"),
        "seniority_level": fields.get("seniority_level"),
        "sector": fields.get("sector"),
        "responsibilities": json.dumps(fields.get("responsibilities") or []),
        "essential_requirements": json.dumps(fields.get("essential_requirements") or []),
        "desirable_requirements": json.dumps(fields.get("desirable_requirements") or []),
        "skills_technical": json.dumps(fields.get("skills_technical") or []),
        "skills_soft": json.dumps(fields.get("skills_soft") or []),
        "qualifications": json.dumps(fields.get("qualifications") or []),
        "profession_domain": fields.get("profession_domain"),
        "min_years_experience": fields.get("min_years_experience"),
        "raw_text": raw_text,
        "embedding_text": embedding_text,
        "missing_fields": json.dumps(fields.get("missing_fields") or []),
        "quality_flags": json.dumps(fields.get("quality_flags") or []),
    })
    await db.commit()

    # Generate and store embedding
    embedding_vec = gemini.embed_text(embedding_text, task_type="RETRIEVAL_DOCUMENT")
    if embedding_vec:
        vec_str = "[" + ",".join(str(v) for v in embedding_vec) + "]"
        await db.execute(text("""
            INSERT INTO jd_embeddings (jd_id, model, embedding)
            VALUES (:jd_id, :model, :embedding::vector)
            ON CONFLICT (jd_id, model) DO UPDATE SET embedding = EXCLUDED.embedding
        """), {
            "jd_id": jd_id,
            "model": "gemini-embedding-001",
            "embedding": vec_str,
        })
        await db.commit()

    return jd_id


# ---- Endpoints ----

@router.get("/")
async def list_jds(
    skip: int = 0,
    limit: int = 20,
    sector: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    List all job descriptions (public — candidates browse these).

    Query parameters:
    - skip: Pagination offset
    - limit: Max records (max 100)
    - sector: Filter by sector
    """
    limit = min(limit, 100)
    where = "WHERE sector = :sector" if sector else ""
    query = text(f"""
        SELECT jd_id, title, organisation, location, sector,
               seniority_level, contract_type, salary_range,
               essential_requirements, skills_technical, created_at
        FROM job_descriptions
        {where}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :skip
    """)
    params = {"limit": limit, "skip": skip}
    if sector:
        params["sector"] = sector

    result = await db.execute(query, params)
    rows = result.mappings().all()
    return {"total": len(rows), "skip": skip, "limit": limit, "items": [dict(r) for r in rows]}


@router.get("/{jd_id}")
async def get_jd(jd_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific job description by ID (public)."""
    result = await db.execute(
        text("SELECT * FROM job_descriptions WHERE jd_id = :jd_id"),
        {"jd_id": jd_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Job {jd_id} not found")
    return dict(row)


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_jd(
    file: UploadFile = File(..., description="PDF or DOCX file containing the job description"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_recruiter),
):
    """
    Recruiter uploads a JD file (PDF or DOCX).
    Gemini extracts all structured fields automatically.
    Embedding is generated and stored immediately for matching.
    Requires: Recruiter JWT.
    """
    import sys
    suffix = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""

    allowed = {".pdf", ".docx"}
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Only PDF and DOCX files are supported for JD upload. Got: '{suffix}'",
        )

    if suffix == ".doc" and sys.platform != "win32":
        raise HTTPException(
            status_code=400,
            detail="Old .doc files not supported. Please convert to .docx or .pdf.",
        )

    import tempfile, os
    file_bytes = await file.read()
    if len(file_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Maximum: 20 MB")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        from pathlib import Path
        raw_text = extract_text(Path(tmp_path))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not extract text: {e}")
    finally:
        os.unlink(tmp_path)

    if len(raw_text.strip()) < 100:
        raise HTTPException(
            status_code=422,
            detail="Could not extract enough text from the file. Is this a scanned image-only PDF?",
        )

    fields = gemini.generate_json(
        _JD_EXTRACT_PROMPT.format(text=raw_text[:15000]),
        temperature=0.0,
    )
    if not fields:
        raise HTTPException(status_code=502, detail="AI field extraction failed. Try again.")

    jd_id = await _insert_jd(db, fields, raw_text, file.filename)

    return {
        "jd_id": jd_id,
        "title": fields.get("title"),
        "organisation": fields.get("organisation"),
        "status": "created",
        "embedding": "generated",
        "message": "Job description uploaded, parsed, and ready for candidate matching.",
    }


class JDTextRequest(BaseModel):
    """Request body for creating a JD from free-text."""
    title: Optional[str] = None          # Optional pre-filled title (shown in UI form)
    organisation: Optional[str] = None   # Optional pre-filled org name
    raw_text: str                         # The full JD text entered by the recruiter


@router.post("/create-from-text", status_code=status.HTTP_201_CREATED)
async def create_jd_from_text(
    payload: JDTextRequest,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_recruiter),
):
    """
    Recruiter types or pastes a job description as free text.
    Gemini extracts all structured fields automatically.
    Embedding is generated and stored for matching.
    Requires: Recruiter JWT.
    """
    if len(payload.raw_text.strip()) < 100:
        raise HTTPException(
            status_code=422,
            detail="Job description text is too short. Please provide at least 100 characters.",
        )

    # Prepend optional pre-filled fields to help Gemini
    context_prefix = ""
    if payload.title:
        context_prefix += f"Job Title: {payload.title}\n"
    if payload.organisation:
        context_prefix += f"Organisation: {payload.organisation}\n"
    full_text = context_prefix + payload.raw_text

    fields = gemini.generate_json(
        _JD_EXTRACT_PROMPT.format(text=full_text[:15000]),
        temperature=0.0,
    )
    if not fields:
        raise HTTPException(status_code=502, detail="AI field extraction failed. Try again.")

    # Override with user-provided values if they exist
    if payload.title:
        fields["title"] = payload.title
    if payload.organisation:
        fields["organisation"] = payload.organisation

    filename = f"text-{uuid.uuid4().hex[:8]}.txt"
    jd_id = await _insert_jd(db, fields, payload.raw_text, filename)

    return {
        "jd_id": jd_id,
        "title": fields.get("title"),
        "organisation": fields.get("organisation"),
        "sector": fields.get("sector"),
        "seniority_level": fields.get("seniority_level"),
        "essential_requirements_count": len(fields.get("essential_requirements") or []),
        "status": "created",
        "embedding": "generated",
        "message": "Job description created, parsed, and ready for candidate matching.",
    }


@router.delete("/{jd_id}", status_code=status.HTTP_200_OK)
async def delete_jd(
    jd_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_recruiter),
):
    """Delete a JD and all its match results. Requires Recruiter JWT."""
    result = await db.execute(
        text("DELETE FROM job_descriptions WHERE jd_id = :jd_id RETURNING jd_id"),
        {"jd_id": jd_id},
    )
    await db.commit()
    if not result.fetchone():
        raise HTTPException(status_code=404, detail=f"Job {jd_id} not found")
    return {"deleted": jd_id, "status": "ok"}
