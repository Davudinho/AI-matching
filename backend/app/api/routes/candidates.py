"""backend/app/api/routes/candidates.py — Candidate (CV) API Endpoints"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional

from backend.app.core.database import get_db

router = APIRouter()


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
