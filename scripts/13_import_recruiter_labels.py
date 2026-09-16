"""
scripts/13_import_recruiter_labels.py — Import Recruiter Labels & Set Role-Based Top Match Flags

PURPOSE:
    1. Ensures DB schema in `ai_match_results` contains the required columns:
       - recruiter_label (INT: 0=Reject, 1=Possible/Shortlist, 2=Top Match/Interview)
       - is_top_match (BOOLEAN: whether candidate meets role-specific threshold)
       - ml_predicted_label (INT: calibrated prediction from ML model)
       - ml_confidence (FLOAT: predicted probability/confidence)
    2. Imports ground-truth / bootstrap recruiter labels from evaluation Excel.
    3. Computes and sets `is_top_match` based on role-specific thresholds from `match_config.py`.
    4. Provides detailed reporting on data alignment, label distribution, and confusion matrix.

NOTE ON DATA PROVENANCE:
    Current labels originate from Perplexity AI bootstrap distillation (evaluation_results_III_recruiter_labels.xlsx).
    In production, this table receives implicit feedback directly from platform interactions:
      - Bookmark / Shortlist candidate -> Label 1
      - Request interview / Contact   -> Label 2
      - Dismiss / Skip candidate      -> Label 0
"""

import os
import sys
import argparse
from pathlib import Path
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import settings
from scripts.match_config import get_top_match_threshold, get_all_thresholds


def parse_args():
    parser = argparse.ArgumentParser(description="Import recruiter labels and update top-match flags in database")
    parser.add_argument(
        "--file",
        type=str,
        default="docs/evaluation_results_III_recruiter_labels.xlsx",
        help="Path to evaluation Excel workbook containing recruiter labels"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the import and display metrics without writing to database"
    )
    return parser.parse_args()


def get_db_connection():
    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    return psycopg2.connect(db_url)


def ensure_schema_columns(conn):
    """Ensure that ai_match_results has the required columns for ML & recruiter feedback."""
    alter_statements = [
        """
        ALTER TABLE ai_match_results 
        ADD COLUMN IF NOT EXISTS recruiter_label INT CHECK (recruiter_label IN (0, 1, 2));
        """,
        """
        ALTER TABLE ai_match_results 
        ADD COLUMN IF NOT EXISTS is_top_match BOOLEAN DEFAULT FALSE;
        """,
        """
        ALTER TABLE ai_match_results 
        ADD COLUMN IF NOT EXISTS ml_predicted_label INT;
        """,
        """
        ALTER TABLE ai_match_results 
        ADD COLUMN IF NOT EXISTS ml_confidence FLOAT;
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_ai_match_recruiter_label ON ai_match_results (recruiter_label);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_ai_match_is_top_match ON ai_match_results (is_top_match);
        """
    ]
    with conn.cursor() as cur:
        for stmt in alter_statements:
            cur.execute(stmt)
    conn.commit()
    print(" [Schema] Checked/updated ai_match_results table columns.")


def main():
    args = parse_args()
    excel_path = PROJECT_ROOT / args.file
    if not excel_path.exists():
        fallback_path = PROJECT_ROOT / "docs/evaluation_results_EN.xlsx"
        if fallback_path.exists():
            print(f" [Warning] File '{excel_path}' not found. Falling back to '{fallback_path}'.")
            excel_path = fallback_path
        else:
            raise FileNotFoundError(f"Neither '{excel_path}' nor '{fallback_path}' exists.")

    print(f"\n=======================================================")
    print(f" 13_import_recruiter_labels.py")
    print(f" Source: {excel_path}")
    print(f" Mode:   {'DRY-RUN (no changes saved)' if args.dry_run else 'LIVE COMMIT'}")
    print(f"=======================================================\n")

    # 1. Load Excel
    df = pd.read_excel(excel_path, sheet_name="All Results")
    print(f"[1/4] Loaded {len(df)} candidate-JD pairs from sheet 'All Results'.")

    # Verify column existence
    label_col = "Recruiter_Label"
    if label_col not in df.columns:
        if "recruiter_decision" in df.columns:
            label_col = "recruiter_decision"
        else:
            raise KeyError(f"Neither 'Recruiter_Label' nor 'recruiter_decision' found in columns: {list(df.columns)}")

    print(f"      Using label column: '{label_col}'")

    # Connect to DB
    conn = get_db_connection()

    try:
        # 2. Schema check
        if not args.dry_run:
            ensure_schema_columns(conn)

        # 3. Load DB mapping (jd.title + c.anon_ref -> ai.id, ai.final_score, ai.stage1_passed)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    ai.id,
                    jd.title AS jd_title,
                    c.anon_ref,
                    ai.final_score,
                    ai.stage1_passed
                FROM ai_match_results ai
                JOIN job_descriptions jd ON jd.jd_id = ai.jd_id
                JOIN candidates c ON c.cv_id = ai.cv_id;
            """)
            db_rows = cur.fetchall()

        db_map = {}
        for row in db_rows:
            ai_id, jd_title, anon_ref, final_score, stage1_passed = row
            key = (jd_title.strip(), anon_ref.strip())
            db_map[key] = {
                "id": ai_id,
                "final_score": final_score or 0.0,
                "stage1_passed": bool(stage1_passed)
            }

        print(f"[2/4] Retrieved {len(db_map)} existing matches from PostgreSQL.")

        # 4. Prepare updates
        thresholds_cfg = get_all_thresholds()
        update_data = []
        unmatched = 0

        label_counts = {0: 0, 1: 0, 2: 0, "unknown": 0}
        top_match_count = 0

        for _, row in df.iterrows():
            jd_title = str(row.get("jd_title", "")).strip()
            anon_ref = str(row.get("anon_ref", "")).strip()
            raw_label = row.get(label_col)

            # Clean label
            if pd.isna(raw_label):
                clean_label = None
                label_counts["unknown"] += 1
            else:
                try:
                    clean_label = int(raw_label)
                    label_counts[clean_label] = label_counts.get(clean_label, 0) + 1
                except (ValueError, TypeError):
                    clean_label = None
                    label_counts["unknown"] += 1

            key = (jd_title, anon_ref)
            if key in db_map:
                match_info = db_map[key]
                ai_id = match_info["id"]
                final_score = match_info["final_score"]
                stage1_passed = match_info["stage1_passed"]

                # Threshold decision
                thresh = get_top_match_threshold(jd_title)
                is_top = bool(stage1_passed and final_score >= thresh)
                if is_top:
                    top_match_count += 1

                update_data.append((clean_label, is_top, ai_id))
            else:
                unmatched += 1

        print(f"[3/4] Prepared updates for {len(update_data)} records (Unmatched: {unmatched}).")

        # 5. Execute DB Update
        if not args.dry_run and update_data:
            with conn.cursor() as cur:
                # Update in batch using execute_values
                query = """
                    UPDATE ai_match_results AS ai
                    SET 
                        recruiter_label = val.recruiter_label,
                        is_top_match = val.is_top_match
                    FROM (VALUES %s) AS val(recruiter_label, is_top_match, id)
                    WHERE ai.id = val.id;
                """
                # Prepare typed tuples: (int/None, bool, int)
                execute_values(
                    cur,
                    query,
                    update_data,
                    template="(%s::int, %s::boolean, %s::int)"
                )
            conn.commit()
            print(f"[4/4] Successfully committed updates for {len(update_data)} records into PostgreSQL.")
        elif args.dry_run:
            print(f"[4/4] [DRY-RUN] No updates committed to database.")

        # 6. Summary Statistics & Cross-Tabulation
        print("\n" + "=" * 55)
        print(" SUMMARY REPORT: Labels & Top-Match Distribution")
        print("=" * 55)
        print(f"Total evaluated pairs: {len(update_data)}")
        print(f"  Reject (0):          {label_counts.get(0, 0)}")
        print(f"  Possible (1):        {label_counts.get(1, 0)}")
        print(f"  Top Match (2):       {label_counts.get(2, 0)}")
        print(f"  Unlabeled:           {label_counts.get('unknown', 0)}")
        print(f"  is_top_match = TRUE: {top_match_count} / {len(update_data)}")

        # Calculate alignment between is_top_match and Recruiter_Label
        # We define a match as positive if recruiter_label == 2 (or optionally 1)
        tp = sum(1 for l, top, _ in update_data if l == 2 and top)
        fp = sum(1 for l, top, _ in update_data if l != 2 and top)
        fn = sum(1 for l, top, _ in update_data if l == 2 and not top)
        tn = sum(1 for l, top, _ in update_data if l != 2 and not top)

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

        print("\n Alignment Matrix (Target: Top Match Label 2):")
        print(f"  True Positives  (Label 2 & Top Match):     {tp}")
        print(f"  False Positives (Label <2 & Top Match):    {fp}")
        print(f"  False Negatives (Label 2 & NOT Top Match): {fn}")
        print(f"  True Negatives  (Label <2 & NOT Top Match):{tn}")
        print(f"  Precision: {prec:.4f} | Recall: {rec:.4f} | F1: {f1:.4f}")
        print("=" * 55 + "\n")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
