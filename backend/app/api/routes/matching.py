"""backend/app/api/routes/matching.py — Matching API Endpoints

The core of the product: given a JD, find the top matching candidates.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import numpy as np

from backend.app.core.database import get_db
from backend.app.services.gemini_service import gemini
from backend.app.core.config import settings

router = APIRouter()


@router.get("/{jd_id}/top-candidates")
async def get_top_candidates(
    jd_id: str,
    top_n: int = Query(default=10, ge=1, le=50, description="Number of top candidates to return"),
    generate_explanation: bool = Query(default=False, description="Generate AI explanation (costs API tokens)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Find the top-N candidates for a given JD using semantic similarity.
    
    This is the main matching endpoint used by the recruiter dashboard.
    
    How it works:
    1. Fetch the JD's embedding vector from the database
    2. Use pgvector's <=> operator (cosine distance) to find similar CV embeddings
    3. Return the top-N results with scores and optional AI explanations
    
    The <=> operator in pgvector computes cosine DISTANCE (1 - similarity).
    So lower <=> score = higher similarity. We convert to similarity in the response.
    """
    # Fetch JD and its embedding
    jd_result = await db.execute(
        text("""
            SELECT jd.*, je.embedding
            FROM job_descriptions jd
            JOIN jd_embeddings je ON jd.jd_id = je.jd_id
            WHERE jd.jd_id = :jd_id
        """),
        {"jd_id": jd_id}
    )
    jd_row = jd_result.mappings().first()

    if not jd_row:
        raise HTTPException(
            status_code=404,
            detail=f"JD {jd_id} not found or has no embedding. Run 05_embed_and_store.py first."
        )

    jd_data = dict(jd_row)
    embedding_str = str(jd_data.get("embedding", ""))

    # Use pgvector's cosine distance operator <=> for semantic search
    # This is much faster than computing similarity in Python (the IVFFlat index is used)
    matches_result = await db.execute(text("""
        SELECT
            c.cv_id, c.anon_ref, c.current_title, c.years_experience,
            c.skills_technical, c.skills_soft, c.sector_experience,
            c.right_to_work_uk,
            1 - (ce.embedding <=> :query_vec::vector) AS semantic_score
        FROM candidates c
        JOIN cv_embeddings ce ON c.cv_id = ce.cv_id
        ORDER BY ce.embedding <=> :query_vec::vector  -- closest first
        LIMIT :top_n
    """), {"query_vec": embedding_str, "top_n": top_n})

    matches = [dict(r) for r in matches_result.mappings().all()]

    # Compute skill overlap for each match
    jd_skills = set(
        s.strip().lower()
        for s in (jd_data.get("skills_technical") or [])
    )

    results = []
    for rank, match in enumerate(matches, start=1):
        cv_skills = set(
            s.strip().lower()
            for s in (match.get("skills_technical") or [])
        )
        # Jaccard similarity
        if jd_skills or cv_skills:
            overlap = len(jd_skills & cv_skills) / len(jd_skills | cv_skills) if (jd_skills | cv_skills) else 0.0
        else:
            overlap = 0.0

        result_item = {
            "rank": rank,
            "cv_id": match["cv_id"],
            "anon_ref": match["anon_ref"],
            "current_title": match["current_title"],
            "years_experience": match["years_experience"],
            "semantic_score": round(float(match["semantic_score"]), 4),
            "skill_overlap_pct": round(overlap * 100, 1),
            "skills_technical": match["skills_technical"],
            "sector_experience": match["sector_experience"],
            "right_to_work_uk": match["right_to_work_uk"],
            "ai_explanation": None,
        }

        if generate_explanation:
            result_item["ai_explanation"] = gemini.generate_match_explanation(
                jd_title=jd_data.get("title", ""),
                jd_skills=list(jd_skills),
                jd_requirements=jd_data.get("essential_requirements") or [],
                cv_title=match.get("current_title", ""),
                cv_skills=list(match.get("skills_technical") or []),
                cv_experience="",
                semantic_score=result_item["semantic_score"],
            )

        results.append(result_item)

    return {
        "jd_id": jd_id,
        "jd_title": jd_data.get("title"),
        "jd_organisation": jd_data.get("organisation"),
        "top_n": top_n,
        "candidates": results,
    }


@router.get("/{jd_id}/ai-results")
async def get_ai_match_results(
    jd_id: str,
    top_n: int = Query(default=20, ge=1, le=100, description="Max candidates to return"),
    top_match_only: bool = Query(default=False, description="Filter to top matches only"),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve 3-stage AI funnel matching results with ML calibration confidence and top match flags.
    """
    query_str = """
        SELECT
            r.id AS match_id,
            r.final_rank,
            r.final_score,
            r.is_top_match,
            r.ml_confidence,
            r.ml_predicted_label,
            r.recruiter_label,
            r.stage1_passed,
            r.stage1_score,
            r.stage1_reason,
            r.stage2_score,
            r.stage2_met_count,
            r.stage2_total_count,
            r.stage2_breakdown,
            r.stage2_critical_gaps,
            r.stage3_verdict,
            r.stage3_explanation,
            c.cv_id,
            c.anon_ref,
            c.current_title,
            c.years_experience,
            c.right_to_work_uk
        FROM ai_match_results r
        JOIN candidates c ON r.cv_id = c.cv_id
        WHERE r.jd_id = :jd_id
    """
    if top_match_only:
        query_str += " AND r.is_top_match = TRUE"
    query_str += " ORDER BY r.final_rank ASC NULLS LAST LIMIT :top_n"

    res = await db.execute(text(query_str), {"jd_id": jd_id, "top_n": top_n})
    rows = [dict(r) for r in res.mappings().all()]

    return {
        "jd_id": jd_id,
        "count": len(rows),
        "results": rows,
    }


@router.post("/feedback")
async def record_recruiter_feedback(
    match_id: int,
    action: str = Query(..., pattern="^(shortlist|interview|dismiss)$", description="Implicit recruiter action"),
    db: AsyncSession = Depends(get_db),
):
    """
    Record implicit feedback from natural recruiter actions without adding labeling workload:
      - 'shortlist' -> recruiter_label = 1
      - 'interview' -> recruiter_label = 2
      - 'dismiss'   -> recruiter_label = 0
    """
    action_map = {"dismiss": 0, "shortlist": 1, "interview": 2}
    label = action_map[action]

    await db.execute(
        text("UPDATE ai_match_results SET recruiter_label = :label WHERE id = :id"),
        {"label": label, "id": match_id}
    )
    await db.commit()
    return {
        "status": "success",
        "match_id": match_id,
        "action": action,
        "assigned_label": label
    }

