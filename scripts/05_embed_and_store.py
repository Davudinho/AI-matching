"""
scripts/05_embed_and_store.py — Week 3, Task 1: Generate & Store Embeddings

PURPOSE:
    Reads all JDs and CVs from PostgreSQL, generates Gemini embedding vectors
    for each one, and stores the vectors back in the database.

    After this script, every JD and CV has a 3072-dimensional vector stored in
    jd_embeddings and cv_embeddings tables. These vectors are used in
    06_match_evaluate.py to find semantically similar JD-CV pairs.

WHAT IS AN EMBEDDING?
    An embedding is a mathematical representation of text meaning.
    Imagine each document as a point in 3072-dimensional space.
    Documents with similar meaning are close together; different ones are far apart.
    
    Example:
    - "Software Engineer with Python skills" ←→ "Python Developer, Django expert"
      → cosine similarity ≈ 0.92 (very close)
    - "Software Engineer" ←→ "Finance Manager, CPA qualified"
      → cosine similarity ≈ 0.31 (very far)

HOW TO RUN:
    python scripts/05_embed_and_store.py

COST NOTE:
    Embeddings are cached in the database — we NEVER re-embed a document
    that already has an embedding. This means after the first run, this
    script costs nothing (no API calls) unless new JDs/CVs are added.
"""

import json
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

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

EMBEDDING_MODEL = settings.GEMINI_EMBEDDING_MODEL


# ============================================================
# Database helpers
# ============================================================

def get_connection():
    """Get a psycopg2 PostgreSQL connection."""
    db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    return conn


def fetch_jds_needing_embeddings(conn) -> list[dict]:
    """
    Fetch JDs that don't yet have embeddings stored.
    
    The LEFT JOIN checks if an embedding exists. If cv_embeddings.jd_id
    is NULL after the join, no embedding exists yet for that JD.
    """
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("""
        SELECT jd.jd_id, jd.embedding_text, jd.title
        FROM job_descriptions jd
        LEFT JOIN jd_embeddings je ON jd.jd_id = je.jd_id AND je.model = %s
        WHERE je.jd_id IS NULL
          AND jd.embedding_text IS NOT NULL
          AND LENGTH(jd.embedding_text) > 10
        ORDER BY jd.created_at
    """, (EMBEDDING_MODEL,))
    rows = cursor.fetchall()
    cursor.close()
    return [dict(r) for r in rows]


def fetch_cvs_needing_embeddings(conn) -> list[dict]:
    """Fetch CVs that don't yet have embeddings stored."""
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("""
        SELECT c.cv_id, c.embedding_text, c.anon_ref, c.current_title
        FROM candidates c
        LEFT JOIN cv_embeddings ce ON c.cv_id = ce.cv_id AND ce.model = %s
        WHERE ce.cv_id IS NULL
          AND c.embedding_text IS NOT NULL
          AND LENGTH(c.embedding_text) > 10
        ORDER BY c.created_at
    """, (EMBEDDING_MODEL,))
    rows = cursor.fetchall()
    cursor.close()
    return [dict(r) for r in rows]


def store_jd_embeddings(conn, jd_embeddings: list[tuple]):
    """
    Store JD embedding vectors in the jd_embeddings table.
    
    Args:
        jd_embeddings: List of (jd_id, embedding_list) tuples
    
    We use pgvector's vector type — the embedding is stored as a string
    like '[0.1, 0.2, ...]' and PostgreSQL casts it to the vector type.
    """
    cursor = conn.cursor()
    for jd_id, embedding in jd_embeddings:
        if not embedding:
            continue
        # Convert list of floats to pgvector format string: '[0.1, -0.2, ...]'
        vector_str = "[" + ",".join(str(x) for x in embedding) + "]"
        cursor.execute("""
            INSERT INTO jd_embeddings (jd_id, model, embedding)
            VALUES (%s, %s, %s::vector)
            ON CONFLICT (jd_id, model) DO UPDATE SET
                embedding = EXCLUDED.embedding,
                created_at = NOW()
        """, (jd_id, EMBEDDING_MODEL, vector_str))
    conn.commit()
    cursor.close()


def store_cv_embeddings(conn, cv_embeddings: list[tuple]):
    """Store CV embedding vectors in the cv_embeddings table."""
    cursor = conn.cursor()
    for cv_id, embedding in cv_embeddings:
        if not embedding:
            continue
        vector_str = "[" + ",".join(str(x) for x in embedding) + "]"
        cursor.execute("""
            INSERT INTO cv_embeddings (cv_id, model, embedding)
            VALUES (%s, %s, %s::vector)
            ON CONFLICT (cv_id, model) DO UPDATE SET
                embedding = EXCLUDED.embedding,
                created_at = NOW()
        """, (cv_id, EMBEDDING_MODEL, vector_str))
    conn.commit()
    cursor.close()


# ============================================================
# Main embedding pipeline
# ============================================================

def embed_records(records: list[dict], id_field: str, label: str) -> list[tuple]:
    """
    Generate embeddings for a list of records.
    
    Args:
        records: List of dicts with 'id_field' and 'embedding_text'
        id_field: The field name for the ID (e.g. 'jd_id' or 'cv_id')
        label: Human-readable name for logging ('JD' or 'CV')
    
    Returns:
        List of (id, embedding_vector) tuples
    
    We process in batches of 20 to balance:
    - Speed (batching is faster than one-by-one)
    - Memory (don't hold all embeddings in RAM at once)
    - Rate limiting (pause between batches)
    """
    if not records:
        logger.info(f"No {label}s need embedding")
        return []

    logger.info(f"Generating embeddings for {len(records)} {label}s...")
    results = []
    BATCH_SIZE = 20

    total_batches = (len(records) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(total_batches):
        batch_start = batch_idx * BATCH_SIZE
        batch = records[batch_start: batch_start + BATCH_SIZE]

        # Extract just the texts for the embedding API
        texts = [r["embedding_text"] for r in batch]
        ids = [r[id_field] for r in batch]

        logger.info(
            f"  Batch {batch_idx + 1}/{total_batches}: "
            f"embedding {len(texts)} {label}s..."
        )

        # Call Gemini embedding API
        # task_type="RETRIEVAL_DOCUMENT" tells Gemini this text is being indexed
        # (vs RETRIEVAL_QUERY which is for search queries)
        embeddings = gemini.embed_texts_batch(
            texts,
            task_type="RETRIEVAL_DOCUMENT",
            batch_size=BATCH_SIZE,
        )

        # Pair IDs with their embeddings
        for record_id, embedding in zip(ids, embeddings):
            if embedding:
                results.append((record_id, embedding))
            else:
                logger.warning(f"  ⚠ Empty embedding for {label} {record_id}")

        # Pause between batches to avoid hitting rate limits
        if batch_idx < total_batches - 1:
            time.sleep(1)

    logger.info(f"✓ Generated {len(results)}/{len(records)} {label} embeddings")
    return results


def main():
    logger.info("=" * 60)
    logger.info("Week 3 — Task 1: Generating Gemini Embeddings")
    logger.info("=" * 60)
    logger.info(f"Embedding model: {EMBEDDING_MODEL}")

    conn = get_connection()

    try:
        # ---- JDs ----
        jds = fetch_jds_needing_embeddings(conn)
        logger.info(f"\nJDs without embeddings: {len(jds)}")

        if jds:
            jd_embeddings = embed_records(jds, "jd_id", "JD")
            if jd_embeddings:
                store_jd_embeddings(conn, jd_embeddings)
                logger.info(f"✓ Stored {len(jd_embeddings)} JD embeddings in DB")
        else:
            logger.info("All JDs already have embeddings — no API calls needed ✓")

        # ---- CVs ----
        cvs = fetch_cvs_needing_embeddings(conn)
        logger.info(f"\nCVs without embeddings: {len(cvs)}")

        if cvs:
            cv_embeddings = embed_records(cvs, "cv_id", "CV")
            if cv_embeddings:
                store_cv_embeddings(conn, cv_embeddings)
                logger.info(f"✓ Stored {len(cv_embeddings)} CV embeddings in DB")
        else:
            logger.info("All CVs already have embeddings — no API calls needed ✓")

        # ---- Final count ----
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM jd_embeddings")
        total_jd = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM cv_embeddings")
        total_cv = cursor.fetchone()[0]
        cursor.close()

        logger.info(f"\n{'=' * 60}")
        logger.info("SUMMARY")
        logger.info(f"{'=' * 60}")
        logger.info(f"Total JD embeddings in DB:  {total_jd}")
        logger.info(f"Total CV embeddings in DB:  {total_cv}")
        logger.info(f"Possible match pairs: {total_jd * total_cv}")
        logger.info("\nNext step: Run scripts/06_match_evaluate.py")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
