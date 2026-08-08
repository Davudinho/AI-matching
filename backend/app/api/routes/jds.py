"""backend/app/api/routes/jds.py — Job Descriptions API Endpoints

Endpoints:
  GET    /api/v1/jds           → List all JDs (with pagination)
  GET    /api/v1/jds/{jd_id}  → Get a specific JD
  POST   /api/v1/jds/upload    → Upload a DOCX file and parse it
  DELETE /api/v1/jds/{jd_id}  → Delete a JD
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.services.gemini_service import gemini

router = APIRouter()


@router.get("/")
async def list_jds(
    skip: int = 0,
    limit: int = 20,
    sector: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    List all job descriptions.
    
    Query parameters:
    - skip: Number of records to skip (for pagination)
    - limit: Maximum records to return (max 100)
    - sector: Filter by sector (e.g. 'Finance', 'Charity')
    """
    limit = min(limit, 100)  # Prevent huge responses

    where = "WHERE sector = :sector" if sector else ""
    query = text(f"""
        SELECT jd_id, title, organisation, location, sector,
               seniority_level, contract_type, salary_range,
               skills_technical, created_at
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

    return {
        "total": len(rows),
        "skip": skip,
        "limit": limit,
        "items": [dict(r) for r in rows],
    }


@router.get("/{jd_id}")
async def get_jd(jd_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific job description by ID."""
    result = await db.execute(
        text("SELECT * FROM job_descriptions WHERE jd_id = :jd_id"),
        {"jd_id": jd_id}
    )
    row = result.mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail=f"JD {jd_id} not found")

    return dict(row)


@router.post("/upload")
async def upload_jd(
    file: UploadFile = File(..., description="DOCX file containing the job description"),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a DOCX file, extract structured fields with Gemini, and save to DB.
    
    This endpoint does the same thing as script 01_parse_jds.py,
    but integrated into the FastAPI backend for use by the frontend.
    """
    if not file.filename.endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files are supported")

    # Save file to upload directory
    upload_dir = Path(settings.UPLOAD_DIR) / "jds"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / file.filename

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Parse DOCX text
    try:
        import docx as python_docx
        doc = python_docx.Document(str(file_path))
        raw_text = "\n".join(
            para.text.strip() for para in doc.paragraphs if para.text.strip()
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse DOCX: {e}")

    # Extract fields with Gemini
    from scripts.parse_helpers import extract_jd_fields_for_api  # type: ignore
    # For now, inline the extraction:
    prompt = f"""Extract structured fields from this job description. Return JSON only.
    
{raw_text[:12000]}

Return: {{"title": "...", "organisation": "...", "location": "...", "salary_range": null,
"contract_type": "...", "seniority_level": "...", "sector": "...",
"responsibilities": [], "essential_requirements": [], "desirable_requirements": [],
"skills_technical": [], "skills_soft": [], "qualifications": [],
"missing_fields": [], "quality_flags": []}}"""

    fields = gemini.generate_json(prompt, temperature=0.0)
    if not fields:
        raise HTTPException(status_code=502, detail="AI extraction failed")

    jd_id = str(uuid.uuid4())
    embedding_parts = [
        f"Title: {fields.get('title', '')}",
        f"Skills: {', '.join(fields.get('skills_technical', [])[:15])}",
        f"Requirements: {'; '.join(fields.get('essential_requirements', [])[:8])}",
    ]
    embedding_text = "\n".join(p for p in embedding_parts if p)

    await db.execute(text("""
        INSERT INTO job_descriptions (
            jd_id, filename, title, organisation, location,
            salary_range, contract_type, seniority_level, sector,
            responsibilities, essential_requirements, desirable_requirements,
            skills_technical, skills_soft, qualifications,
            raw_text, embedding_text, missing_fields, quality_flags
        ) VALUES (
            :jd_id, :filename, :title, :organisation, :location,
            :salary_range, :contract_type, :seniority_level, :sector,
            :responsibilities::jsonb, :essential_requirements::jsonb, :desirable_requirements::jsonb,
            :skills_technical::jsonb, :skills_soft::jsonb, :qualifications::jsonb,
            :raw_text, :embedding_text, :missing_fields::jsonb, :quality_flags::jsonb
        )
    """), {
        "jd_id": jd_id,
        "filename": file.filename,
        "title": fields.get("title"),
        "organisation": fields.get("organisation"),
        "location": fields.get("location"),
        "salary_range": fields.get("salary_range"),
        "contract_type": fields.get("contract_type"),
        "seniority_level": fields.get("seniority_level"),
        "sector": fields.get("sector"),
        "responsibilities": json.dumps(fields.get("responsibilities", [])),
        "essential_requirements": json.dumps(fields.get("essential_requirements", [])),
        "desirable_requirements": json.dumps(fields.get("desirable_requirements", [])),
        "skills_technical": json.dumps(fields.get("skills_technical", [])),
        "skills_soft": json.dumps(fields.get("skills_soft", [])),
        "qualifications": json.dumps(fields.get("qualifications", [])),
        "raw_text": raw_text,
        "embedding_text": embedding_text,
        "missing_fields": json.dumps(fields.get("missing_fields", [])),
        "quality_flags": json.dumps(fields.get("quality_flags", [])),
    })

    return {
        "jd_id": jd_id,
        "filename": file.filename,
        "title": fields.get("title"),
        "organisation": fields.get("organisation"),
        "status": "created",
        "message": "JD uploaded and processed. Run embedding script to enable matching.",
    }


@router.delete("/{jd_id}")
async def delete_jd(jd_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a JD and its associated embeddings and match results."""
    result = await db.execute(
        text("DELETE FROM job_descriptions WHERE jd_id = :jd_id RETURNING jd_id"),
        {"jd_id": jd_id}
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail=f"JD {jd_id} not found")

    return {"deleted": jd_id}
