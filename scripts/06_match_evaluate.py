"""
scripts/06_match_evaluate.py — Week 3, Task 2: Matching & Evaluation

PURPOSE:
    For each JD in the database, finds the top-N matching candidate CVs
    using semantic (embedding) similarity, computes additional metrics,
    generates AI explanations, and exports an evaluation spreadsheet.

    THIS IS YOUR MAIN WEEK 3 DELIVERABLE.

    After running this script:
    1. Open docs/evaluation_results.xlsx
    2. Fill in the 'recruiter_label' column for each row:
       - 0 = Not a match
       - 1 = Maybe / worth reviewing
       - 2 = Good match
    3. Run the metrics section at the bottom to compute Precision@K, NDCG@K

HOW IT WORKS:
    1. Fetch all JD and CV embeddings from the database
    2. For each JD, compute cosine similarity against ALL CV embeddings
    3. Rank CVs by similarity score — top-N are the predicted matches
    4. Compute skill overlap (Jaccard similarity) for additional signal
    5. Ask Gemini to generate a 2-3 sentence explanation
    6. Save to match_results table + export to Excel

HOW TO RUN:
    python scripts/06_match_evaluate.py --top-n 10 --explain

    Options:
    --top-n N       Number of top candidates to retrieve per JD (default: 10)
    --explain       Generate AI explanations (costs Gemini API calls)
    --no-explain    Skip explanations (faster, no cost)
    --jd-id UUID    Process only a specific JD (useful for testing)
"""

import argparse
import json
import logging
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras
from backend.app.services.gemini_service import gemini
from backend.app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


DOCS_DIR = PROJECT_ROOT / "docs"
DOCS_DIR.mkdir(parents=True, exist_ok=True)
EXCEL_OUTPUT = DOCS_DIR / "evaluation_results.xlsx"


# ============================================================
# Database helpers
# ============================================================

def get_connection():
    db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    return conn


def fetch_all_jds(conn, jd_id_filter: str = None) -> list[dict]:
    """Fetch all JDs with their stored embeddings."""
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    where_clause = "WHERE jd.jd_id = %s" if jd_id_filter else ""
    params = (jd_id_filter,) if jd_id_filter else ()

    cursor.execute(f"""
        SELECT
            jd.jd_id, jd.title, jd.organisation, jd.sector,
            jd.seniority_level, jd.location, jd.contract_type,
            jd.skills_technical, jd.skills_soft,
            jd.essential_requirements, jd.responsibilities,
            je.embedding
        FROM job_descriptions jd
        JOIN jd_embeddings je ON jd.jd_id = je.jd_id
        {where_clause}
        ORDER BY jd.created_at
    """, params)

    rows = cursor.fetchall()
    cursor.close()

    result = []
    for row in rows:
        d = dict(row)
        # embedding is returned as a string like '[0.1, 0.2, ...]' — parse it
        if d.get("embedding"):
            embedding_str = str(d["embedding"])
            # Remove brackets and split by comma
            d["embedding"] = [float(x) for x in embedding_str.strip("[]").split(",")]
        result.append(d)

    return result


def fetch_all_cvs(conn) -> list[dict]:
    """Fetch all CVs with their stored embeddings."""
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("""
        SELECT
            c.cv_id, c.anon_ref, c.current_title, c.years_experience,
            c.skills_technical, c.skills_soft, c.sector_experience,
            c.work_history, c.education, c.right_to_work_uk,
            ce.embedding
        FROM candidates c
        JOIN cv_embeddings ce ON c.cv_id = ce.cv_id
        ORDER BY c.created_at
    """)
    rows = cursor.fetchall()
    cursor.close()

    result = []
    for row in rows:
        d = dict(row)
        if d.get("embedding"):
            embedding_str = str(d["embedding"])
            d["embedding"] = [float(x) for x in embedding_str.strip("[]").split(",")]
        result.append(d)

    return result


# ============================================================
# Similarity computations
# ============================================================

def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Compute cosine similarity between two vectors.
    
    Cosine similarity measures the angle between two vectors:
    - 1.0 = identical direction (perfect match)
    - 0.0 = perpendicular (no similarity)
    - -1.0 = opposite directions (impossible for positive embeddings)
    
    Formula: (A · B) / (|A| × |B|)
    
    Why cosine (not Euclidean distance)?
    Cosine ignores the magnitude of vectors — it only cares about direction.
    This makes it more robust for comparing text of different lengths.
    """
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)

    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(np.dot(a, b) / (norm_a * norm_b))


def jaccard_skill_overlap(jd_skills: list[str], cv_skills: list[str]) -> float:
    """
    Compute Jaccard similarity between two skill lists.
    
    Jaccard = |A ∩ B| / |A ∪ B|
    
    Example:
      JD skills:  ["Python", "SQL", "AWS", "Communication"]
      CV skills:  ["Python", "Django", "SQL", "Teamwork"]
      Intersection: {"Python", "SQL"} = 2 items
      Union: {"Python", "SQL", "AWS", "Communication", "Django", "Teamwork"} = 6 items
      Jaccard = 2/6 = 0.333 (33.3% overlap)
    
    Note: We normalise to lowercase for comparison to avoid "Python" ≠ "python"
    """
    if not jd_skills or not cv_skills:
        return 0.0

    # Normalise to lowercase and strip whitespace
    set_a = {s.strip().lower() for s in jd_skills if isinstance(s, str)}
    set_b = {s.strip().lower() for s in cv_skills if isinstance(s, str)}

    if not set_a or not set_b:
        return 0.0

    intersection = set_a & set_b
    union = set_a | set_b

    return len(intersection) / len(union)


# ============================================================
# Matching pipeline
# ============================================================

def match_jd_to_cvs(
    jd: dict,
    cvs: list[dict],
    top_n: int = 10,
    generate_explanations: bool = True,
) -> list[dict]:
    """
    Find the top-N matching CVs for a given JD.
    
    Algorithm:
    1. Compute cosine similarity between JD embedding and each CV embedding
    2. Sort by similarity (highest first)
    3. Take top-N results
    4. For each result, also compute skill overlap (Jaccard)
    5. Optionally generate an AI explanation
    
    Args:
        jd: JD dict with embedding and skill fields
        cvs: All CV dicts with embeddings
        top_n: How many top candidates to return
        generate_explanations: Whether to call Gemini for explanations
    
    Returns:
        List of match dicts, sorted by semantic_score descending
    """
    jd_embedding = jd.get("embedding")
    if not jd_embedding:
        logger.warning(f"JD {jd['jd_id']} has no embedding — skipping")
        return []

    # ---- Compute similarities ----
    scores = []
    for cv in cvs:
        cv_embedding = cv.get("embedding")
        if not cv_embedding:
            continue

        semantic_score = cosine_similarity(jd_embedding, cv_embedding)

        # Combine technical + soft skills for Jaccard
        jd_skills = (jd.get("skills_technical") or []) + (jd.get("skills_soft") or [])
        cv_skills = (cv.get("skills_technical") or []) + (cv.get("skills_soft") or [])

        skill_overlap = jaccard_skill_overlap(jd_skills, cv_skills)

        scores.append({
            "cv_id": cv["cv_id"],
            "anon_ref": cv.get("anon_ref"),
            "cv_title": cv.get("current_title"),
            "years_experience": cv.get("years_experience"),
            "semantic_score": round(semantic_score, 4),
            "skill_overlap": round(skill_overlap, 4),
            "skill_overlap_pct": round(skill_overlap * 100, 1),
            "cv": cv,  # Keep full CV for explanation generation
        })

    # Sort by semantic score, highest first
    scores.sort(key=lambda x: x["semantic_score"], reverse=True)

    # Take top-N
    top_matches = scores[:top_n]

    # ---- Add rank and explanations ----
    jd_skills_list = jd.get("skills_technical") or []
    jd_reqs_list = jd.get("essential_requirements") or []

    for rank, match in enumerate(top_matches, start=1):
        match["rank_position"] = rank
        match["jd_id"] = jd["jd_id"]
        match["jd_title"] = jd.get("title")
        match["jd_organisation"] = jd.get("organisation")

        if generate_explanations:
            cv_data = match.pop("cv", {})  # Remove the full CV dict
            cv_skills = cv_data.get("skills_technical") or []
            cv_history = cv_data.get("work_history") or []

            # Build a brief experience summary from work history
            exp_summary = " | ".join([
                f"{r.get('title', '')} at {r.get('organisation', '')}: {r.get('description', '')[:100]}"
                for r in cv_history[:2] if isinstance(r, dict)
            ])

            match["ai_explanation"] = gemini.generate_match_explanation(
                jd_title=jd.get("title", ""),
                jd_skills=jd_skills_list,
                jd_requirements=jd_reqs_list,
                cv_title=match.get("cv_title", ""),
                cv_skills=cv_skills,
                cv_experience=exp_summary,
                semantic_score=match["semantic_score"],
            )
            time.sleep(0.5)  # Small pause between explanation calls
        else:
            match.pop("cv", None)
            match["ai_explanation"] = "(explanations not generated — use --explain flag)"

    return top_matches


def save_match_results(conn, matches: list[dict]):
    """Save match results to the match_results table."""
    cursor = conn.cursor()

    for m in matches:
        cursor.execute("""
            INSERT INTO match_results (
                jd_id, cv_id, semantic_score, skill_overlap,
                rank_position, ai_explanation
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (jd_id, cv_id) DO UPDATE SET
                semantic_score = EXCLUDED.semantic_score,
                skill_overlap = EXCLUDED.skill_overlap,
                rank_position = EXCLUDED.rank_position,
                ai_explanation = EXCLUDED.ai_explanation,
                created_at = NOW()
        """, (
            m["jd_id"], m["cv_id"],
            m["semantic_score"], m["skill_overlap"],
            m["rank_position"], m.get("ai_explanation"),
        ))

    conn.commit()
    cursor.close()


# ============================================================
# Evaluation metrics (for after you fill in recruiter_label)
# ============================================================

def compute_metrics(df: pd.DataFrame, k_values: list[int] = [3, 5, 10]) -> dict:
    """
    Compute evaluation metrics from the filled-in evaluation spreadsheet.
    
    You must fill in the 'recruiter_label' column first!
    (0=No, 1=Maybe, 2=Yes)
    
    Metrics computed:
    
    PRECISION@K:
        Of the top K results, what fraction are relevant (label >= 1)?
        Range: 0.0 to 1.0. Higher = better.
        
    RECALL@K:
        Of ALL relevant candidates for this JD, what fraction appear in top K?
        Range: 0.0 to 1.0. Higher = better.
        
    NDCG@K (Normalised Discounted Cumulative Gain):
        Rewards finding relevant results AND finding them earlier (higher rank).
        A perfect ranking where all relevant results are at rank 1,2,3 gives NDCG=1.0.
        Range: 0.0 to 1.0. Higher = better.
        
    MRR (Mean Reciprocal Rank):
        For each JD, what is 1/rank of the FIRST relevant result?
        If first relevant is at rank 3: MRR contribution = 1/3 = 0.33
        Range: 0.0 to 1.0. Higher = better.
    """
    if "recruiter_label" not in df.columns:
        logger.error("No 'recruiter_label' column found. Please fill in labels first.")
        return {}

    # Only include rows with labels filled in
    labelled = df.dropna(subset=["recruiter_label"])
    if len(labelled) == 0:
        logger.error("No labelled rows found — please fill in recruiter_label column first")
        return {}

    metrics = {}
    jd_ids = labelled["jd_id"].unique()

    for k in k_values:
        precision_scores = []
        recall_scores = []
        ndcg_scores = []
        reciprocal_ranks = []

        for jd_id in jd_ids:
            jd_rows = labelled[labelled["jd_id"] == jd_id].sort_values("rank")

            # Relevant = label >= 1 (Maybe or Yes)
            all_relevant = (jd_rows["recruiter_label"] >= 1).sum()
            top_k = jd_rows.head(k)
            top_k_relevant = (top_k["recruiter_label"] >= 1).sum()

            # Precision@K
            precision_scores.append(top_k_relevant / k)

            # Recall@K
            if all_relevant > 0:
                recall_scores.append(top_k_relevant / all_relevant)
            else:
                recall_scores.append(0.0)

            # NDCG@K
            # DCG = sum of (2^relevance - 1) / log2(rank + 1)
            dcg = 0.0
            for pos, (_, row) in enumerate(top_k.iterrows(), start=1):
                rel = row["recruiter_label"]
                if rel >= 1:
                    dcg += (2**rel - 1) / math.log2(pos + 1)

            # Ideal DCG: if all top-k results were perfect (label=2)
            ideal_ranks = sorted(
                [row["recruiter_label"] for _, row in jd_rows.iterrows()],
                reverse=True
            )[:k]
            idcg = sum(
                (2**rel - 1) / math.log2(pos + 1)
                for pos, rel in enumerate(ideal_ranks, start=1)
                if rel > 0
            )
            ndcg_scores.append(dcg / idcg if idcg > 0 else 0.0)

            # MRR: reciprocal rank of first relevant result
            first_relevant_rank = None
            for _, row in jd_rows.head(k).iterrows():
                if row["recruiter_label"] >= 1:
                    first_relevant_rank = row["rank"]
                    break
            reciprocal_ranks.append(1.0 / first_relevant_rank if first_relevant_rank else 0.0)

        metrics[f"Precision@{k}"] = round(sum(precision_scores) / len(precision_scores), 4)
        metrics[f"Recall@{k}"] = round(sum(recall_scores) / len(recall_scores), 4)
        metrics[f"NDCG@{k}"] = round(sum(ndcg_scores) / len(ndcg_scores), 4)

    metrics["MRR"] = round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4) if reciprocal_ranks else 0.0

    return metrics


# ============================================================
# Excel export
# ============================================================

def export_to_excel(all_matches: list[dict]) -> pd.DataFrame:
    """
    Export all match results to an Excel spreadsheet.
    
    The spreadsheet has these columns:
    - Auto-populated by the script (semantic scores, explanations)
    - 'recruiter_label' and 'notes' — to be filled in by YOU manually
    
    This is the core evaluation artefact for Week 3.
    """
    rows = []
    for m in all_matches:
        rows.append({
            "jd_id": m["jd_id"],
            "jd_title": m.get("jd_title"),
            "jd_organisation": m.get("jd_organisation"),
            "cv_id": m["cv_id"],
            "anon_ref": m.get("anon_ref"),
            "cv_title": m.get("cv_title"),
            "years_experience": m.get("years_experience"),
            "rank": m["rank_position"],
            "semantic_score": m["semantic_score"],
            "skill_overlap_pct": m.get("skill_overlap_pct"),
            "ai_explanation": m.get("ai_explanation"),
            "recruiter_label": None,   # ← YOU FILL THIS IN: 0=No, 1=Maybe, 2=Yes
            "notes": None,             # ← YOUR OBSERVATIONS
        })

    df = pd.DataFrame(rows)

    # Excel export with formatting
    with pd.ExcelWriter(EXCEL_OUTPUT, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Match Results")

        # Auto-size columns
        ws = writer.sheets["Match Results"]
        for column in ws.columns:
            max_length = max(len(str(cell.value or "")) for cell in column)
            col_letter = column[0].column_letter
            ws.column_dimensions[col_letter].width = min(max_length + 2, 60)

        # Add a second sheet with instructions
        instructions_df = pd.DataFrame({
            "Column": ["recruiter_label", "notes"],
            "Instructions": [
                "0 = Not a match | 1 = Maybe/review | 2 = Good match",
                "Free text: observations, why you agree/disagree with AI",
            ]
        })
        instructions_df.to_excel(writer, index=False, sheet_name="Instructions")

    logger.info(f"✓ Evaluation spreadsheet exported to: {EXCEL_OUTPUT}")
    return df


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Week 3 Matching & Evaluation")
    parser.add_argument("--top-n", type=int, default=10, help="Top N candidates per JD")
    parser.add_argument("--explain", action="store_true", default=True, help="Generate AI explanations")
    parser.add_argument("--no-explain", dest="explain", action="store_false")
    parser.add_argument("--jd-id", type=str, default=None, help="Process only this JD UUID")
    parser.add_argument("--metrics-only", action="store_true",
                        help="Only compute metrics from filled-in spreadsheet")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Week 3 — Task 2: Semantic Matching & Evaluation")
    logger.info("=" * 60)

    # ---- Metrics-only mode ----
    if args.metrics_only:
        if not EXCEL_OUTPUT.exists():
            logger.error(f"Spreadsheet not found: {EXCEL_OUTPUT}")
            sys.exit(1)
        df = pd.read_excel(EXCEL_OUTPUT, sheet_name="Match Results")
        metrics = compute_metrics(df)
        logger.info("\nEvaluation Metrics:")
        for metric, value in metrics.items():
            logger.info(f"  {metric}: {value:.4f}")
        return

    # ---- Full matching pipeline ----
    conn = get_connection()

    try:
        logger.info("Loading JDs and CVs from database...")
        jds = fetch_all_jds(conn, jd_id_filter=args.jd_id)
        cvs = fetch_all_cvs(conn)

        logger.info(f"Loaded {len(jds)} JD(s) with embeddings")
        logger.info(f"Loaded {len(cvs)} CV(s) with embeddings")

        if not jds or not cvs:
            logger.error("No JDs or CVs found. Run scripts 01–05 first.")
            sys.exit(1)

        all_matches = []

        for jd in jds:
            logger.info(f"\nMatching JD: '{jd.get('title')}' ({jd.get('organisation')})")

            matches = match_jd_to_cvs(
                jd=jd,
                cvs=cvs,
                top_n=args.top_n,
                generate_explanations=args.explain,
            )

            # Save to database
            save_match_results(conn, matches)
            all_matches.extend(matches)

            logger.info(f"  Top {len(matches)} matches found:")
            for m in matches[:3]:  # Show top 3 in console
                logger.info(
                    f"    #{m['rank_position']} {m['anon_ref']} ({m['cv_title']}) "
                    f"— score: {m['semantic_score']:.3f} "
                    f"| skill overlap: {m['skill_overlap_pct']}%"
                )

        # Export to Excel
        df = export_to_excel(all_matches)

        logger.info(f"\n{'=' * 60}")
        logger.info("✅ MATCHING COMPLETE")
        logger.info(f"{'=' * 60}")
        logger.info(f"  JDs processed:   {len(jds)}")
        logger.info(f"  Matches stored:  {len(all_matches)}")
        logger.info(f"  Spreadsheet:     {EXCEL_OUTPUT}")
        logger.info(f"\n{'─' * 60}")
        logger.info("YOUR NEXT STEPS:")
        logger.info("1. Open docs/evaluation_results.xlsx")
        logger.info("2. Fill in 'recruiter_label' for each row:")
        logger.info("   0 = Not a match  |  1 = Maybe  |  2 = Good match")
        logger.info("3. Add notes in the 'notes' column")
        logger.info("4. Re-run with --metrics-only to compute Precision@K, NDCG@K:")
        logger.info("   python scripts/06_match_evaluate.py --metrics-only")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
