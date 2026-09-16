"""
scripts/12_evaluate_model.py — Offline Evaluation & Threshold Generation

PURPOSE:
    Standalone OFFLINE evaluation script that:
    1. Loads labelled evaluation data (Excel with Recruiter_Label)
    2. Computes confusion matrices and Precision/Recall/F1 per role
    3. Finds optimal final_score thresholds per role (maximising F1)
    4. Generates scripts/config/match_thresholds.json for online use
    5. Optionally evaluates the ML calibration model (if trained)

    This script is NOT called during online serving.
    It is used for evaluation, regression testing, and threshold updates.

HOW TO RUN:
    python scripts/12_evaluate_model.py

    # With a specific Excel file:
    python scripts/12_evaluate_model.py --input docs/evaluation_results_III_recruiter_labels.xlsx

    # Skip ML model evaluation:
    python scripts/12_evaluate_model.py --no-ml

OUTPUT:
    - Console report (human-readable)
    - docs/evaluation_report.md (Markdown report)
    - scripts/config/match_thresholds.json (role-specific thresholds)

IMPORTANT — GROUND TRUTH LABELS:
    The current Recruiter_Label values are AI-GENERATED (bootstrap labels
    from Perplexity). They serve as a prototype starting point.
    In production, these MUST be replaced by real recruiter decisions
    collected implicitly through platform actions (shortlist, interview, dismiss).
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DOCS_DIR = PROJECT_ROOT / "docs"
CONFIG_DIR = Path(__file__).resolve().parent / "config"
DEFAULT_INPUT = DOCS_DIR / "evaluation_results_III_recruiter_labels.xlsx"
THRESHOLDS_OUTPUT = CONFIG_DIR / "match_thresholds.json"
REPORT_OUTPUT = DOCS_DIR / "evaluation_report.md"


# ============================================================
# Metrics computation
# ============================================================

def compute_binary_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """
    Compute TP, FP, FN, TN, Precision, Recall, F1 for binary classification.

    Args:
        y_true: Ground truth binary labels (0 or 1)
        y_pred: Predicted binary labels (0 or 1)

    Returns:
        Dict with tp, fp, fn, tn, precision, recall, f1
    """
    tp = int(np.sum((y_pred == 1) & (y_true == 1)))
    fp = int(np.sum((y_pred == 1) & (y_true == 0)))
    fn = int(np.sum((y_pred == 0) & (y_true == 1)))
    tn = int(np.sum((y_pred == 0) & (y_true == 0)))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def find_optimal_threshold(
    final_scores: np.ndarray,
    y_true_top: np.ndarray,
    thresholds: np.ndarray = None,
) -> tuple:
    """
    Find the threshold on final_score that maximises F1 for Top Match.

    Args:
        final_scores: Array of final_score values
        y_true_top: Binary array (1 if Recruiter_Label == 2, else 0)
        thresholds: Array of thresholds to try (default: 0.0 to 10.0 in 0.25 steps)

    Returns:
        Tuple of (best_threshold, best_f1, all_results)
    """
    if thresholds is None:
        thresholds = np.arange(0.0, 10.25, 0.25)

    best_f1 = -1.0
    best_threshold = 6.5  # sensible default
    all_results = []

    for t in thresholds:
        y_pred = (final_scores >= t).astype(int)
        metrics = compute_binary_metrics(y_true_top, y_pred)
        metrics["threshold"] = round(float(t), 2)
        all_results.append(metrics)

        if metrics["f1"] > best_f1:
            best_f1 = metrics["f1"]
            best_threshold = round(float(t), 2)

    return best_threshold, best_f1, all_results


# ============================================================
# Per-role evaluation
# ============================================================

def evaluate_per_role(df: pd.DataFrame) -> dict:
    """
    Evaluate threshold-based classification per role.

    Returns:
        Dict mapping jd_title -> {
            best_threshold, best_f1, n_total, n_top, n_possible,
            metrics_at_best, confusion_matrix
        }
    """
    results = {}

    for jd_title in sorted(df["jd_title"].unique()):
        role_df = df[df["jd_title"] == jd_title].copy()
        n_total = len(role_df)

        # Count labels
        label_counts = role_df["Recruiter_Label"].value_counts()
        n_top = int(label_counts.get(2, 0))
        n_possible = int(label_counts.get(1, 0))
        n_reject = int(label_counts.get(0, 0))

        # Binary: Top Match (2) vs. Rest (0, 1)
        y_true_top = (role_df["Recruiter_Label"] == 2).astype(int).values
        final_scores = role_df["final_score"].fillna(0).values

        if n_top == 0:
            # No top matches for this role — cannot compute meaningful F1
            results[jd_title] = {
                "best_threshold": None,
                "best_f1": None,
                "n_total": n_total,
                "n_top": 0,
                "n_possible": n_possible,
                "n_reject": n_reject,
                "note": "No Top Match labels for this role — threshold not computable",
            }
            continue

        best_threshold, best_f1, _ = find_optimal_threshold(final_scores, y_true_top)

        # Compute metrics at best threshold
        y_pred = (final_scores >= best_threshold).astype(int)
        metrics = compute_binary_metrics(y_true_top, y_pred)

        results[jd_title] = {
            "best_threshold": best_threshold,
            "best_f1": best_f1,
            "n_total": n_total,
            "n_top": n_top,
            "n_possible": n_possible,
            "n_reject": n_reject,
            "metrics_at_best": metrics,
        }

    return results


def evaluate_global(df: pd.DataFrame) -> dict:
    """
    Evaluate threshold-based classification across ALL roles combined.
    Used as fallback default threshold.
    """
    y_true_top = (df["Recruiter_Label"] == 2).astype(int).values
    final_scores = df["final_score"].fillna(0).values

    best_threshold, best_f1, all_results = find_optimal_threshold(
        final_scores, y_true_top
    )

    y_pred = (final_scores >= best_threshold).astype(int)
    metrics = compute_binary_metrics(y_true_top, y_pred)

    return {
        "best_threshold": best_threshold,
        "best_f1": best_f1,
        "n_total": len(df),
        "n_top": int((df["Recruiter_Label"] == 2).sum()),
        "n_possible": int((df["Recruiter_Label"] == 1).sum()),
        "n_reject": int((df["Recruiter_Label"] == 0).sum()),
        "metrics_at_best": metrics,
    }


# ============================================================
# ML model evaluation (optional)
# ============================================================

def evaluate_ml_model(df: pd.DataFrame) -> dict | None:
    """
    Evaluate the ML calibration model against the labelled data.
    Returns None if no model is available.
    """
    try:
        from scripts.match_config import load_calibration_model, predict_ml_confidence
    except ImportError:
        sys.path.insert(0, str(PROJECT_ROOT))
        from scripts.match_config import load_calibration_model, predict_ml_confidence

    model, feature_names = load_calibration_model()
    if model is None:
        return None

    predictions = []
    for _, row in df.iterrows():
        result = predict_ml_confidence(
            model=model,
            feature_names=feature_names,
            stage1_score=row.get("stage1_score", 0),
            stage2_score=row.get("stage2_score_num", 0),
            stage3_verdict=row.get("stage3_verdict"),
            years_experience=row.get("years_experience"),
            right_to_work_uk=row.get("right_to_work_uk_bool"),
        )
        predictions.append(result)

    ml_labels = [p["ml_predicted_label"] for p in predictions]
    ml_confidences = [p["ml_confidence"] for p in predictions]

    # Binary metrics for Top Match
    y_true = (df["Recruiter_Label"] == 2).astype(int).values
    y_pred_ml = np.array([1 if label == 2 else 0 for label in ml_labels])
    metrics = compute_binary_metrics(y_true, y_pred_ml)

    return {
        "metrics": metrics,
        "predictions": predictions,
        "ml_confidences": ml_confidences,
    }


# ============================================================
# Threshold config generation
# ============================================================

def generate_thresholds_config(
    global_result: dict,
    role_results: dict,
) -> dict:
    """
    Generate the match_thresholds.json config from evaluation results.
    """
    roles = {}
    for jd_title, result in role_results.items():
        if result.get("best_threshold") is not None:
            roles[jd_title] = result["best_threshold"]
        # Roles without top matches get no entry — they'll use the default

    config = {
        "default": global_result["best_threshold"],
        "roles": roles,
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "scripts/12_evaluate_model.py",
            "labels_source": "AI-generated bootstrap (Perplexity) — replace with real recruiter data in production",
            "global_f1": global_result["best_f1"],
            "n_labelled_pairs": global_result["n_total"],
            "n_top_matches": global_result["n_top"],
            "n_possible_matches": global_result["n_possible"],
        },
    }

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(THRESHOLDS_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    logger.info(f"Thresholds saved to: {THRESHOLDS_OUTPUT}")
    return config


# ============================================================
# Report generation
# ============================================================

def generate_report(
    global_result: dict,
    role_results: dict,
    ml_result: dict | None,
    thresholds_config: dict,
) -> str:
    """
    Generate a Markdown evaluation report.
    """
    lines = []
    lines.append("# Evaluation Report — Diversifying.io AI Matching")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("> [!WARNING]")
    lines.append("> The current Recruiter_Label values are **AI-generated bootstrap labels** (from Perplexity).")
    lines.append("> They serve as a prototype starting point. In production, these MUST be replaced")
    lines.append("> by real recruiter decisions collected implicitly through platform actions.")
    lines.append("")

    # Global summary
    lines.append("## Global Summary")
    lines.append("")
    gm = global_result["metrics_at_best"]
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Total pairs evaluated | {global_result['n_total']} |")
    lines.append(f"| Top Match labels (2) | {global_result['n_top']} |")
    lines.append(f"| Possible labels (1) | {global_result['n_possible']} |")
    lines.append(f"| Reject labels (0) | {global_result['n_reject']} |")
    lines.append(f"| **Global optimal threshold** | **{global_result['best_threshold']}** |")
    lines.append(f"| **Global F1 (Top Match)** | **{global_result['best_f1']}** |")
    lines.append(f"| Precision (Top Match) | {gm['precision']} |")
    lines.append(f"| Recall (Top Match) | {gm['recall']} |")
    lines.append(f"| TP / FP / FN / TN | {gm['tp']} / {gm['fp']} / {gm['fn']} / {gm['tn']} |")
    lines.append("")

    # Per-role results
    lines.append("## Per-Role Results")
    lines.append("")
    lines.append("| Role | Labels (0/1/2) | Threshold | F1 | Precision | Recall |")
    lines.append("|---|---|---|---|---|---|")

    for jd_title in sorted(role_results.keys()):
        r = role_results[jd_title]
        label_dist = f"{r['n_reject']}/{r['n_possible']}/{r['n_top']}"

        if r.get("best_threshold") is not None:
            m = r["metrics_at_best"]
            lines.append(
                f"| {jd_title} | {label_dist} | {r['best_threshold']} | "
                f"{r['best_f1']} | {m['precision']} | {m['recall']} |"
            )
        else:
            lines.append(
                f"| {jd_title} | {label_dist} | n/a | n/a | n/a | n/a |"
            )
            lines.append(f"")
            lines.append(f"> *{r.get('note', 'No Top Match labels')}*")
            lines.append(f"")

    lines.append("")

    # Thresholds config
    lines.append("## Generated Thresholds")
    lines.append("")
    lines.append(f"Default threshold: **{thresholds_config['default']}**")
    lines.append("")
    if thresholds_config["roles"]:
        lines.append("| Role | Threshold |")
        lines.append("|---|---|")
        for role, t in sorted(thresholds_config["roles"].items()):
            lines.append(f"| {role} | {t} |")
    else:
        lines.append("*No role-specific thresholds generated (using global default for all roles).*")
    lines.append("")

    # ML model results
    if ml_result is not None:
        lines.append("## ML Calibration Model")
        lines.append("")
        mm = ml_result["metrics"]
        lines.append(f"| Metric | Value |")
        lines.append(f"|---|---|")
        lines.append(f"| F1 (Top Match) | {mm['f1']} |")
        lines.append(f"| Precision | {mm['precision']} |")
        lines.append(f"| Recall | {mm['recall']} |")
        lines.append(f"| TP / FP / FN / TN | {mm['tp']} / {mm['fp']} / {mm['fn']} / {mm['tn']} |")
    else:
        lines.append("## ML Calibration Model")
        lines.append("")
        lines.append("*No trained model found. Run `python scripts/14_train_calibration_model.py` to train.*")

    lines.append("")

    # Write report
    report = "\n".join(lines)
    with open(REPORT_OUTPUT, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info(f"Report saved to: {REPORT_OUTPUT}")
    return report


# ============================================================
# Data loading and preparation
# ============================================================

def load_evaluation_data(input_path: Path) -> pd.DataFrame:
    """
    Load and prepare evaluation data from Excel.
    """
    logger.info(f"Loading: {input_path}")
    df = pd.read_excel(input_path, sheet_name="All Results")
    logger.info(f"  Loaded {len(df)} rows, {len(df.columns)} columns")

    # Ensure Recruiter_Label exists
    if "Recruiter_Label" not in df.columns:
        logger.error(
            "Column 'Recruiter_Label' not found. Available columns: "
            f"{list(df.columns)}"
        )
        sys.exit(1)

    # Convert stage2_score to numeric (may be "n/a — Stage 1 not passed")
    if "stage2_score" in df.columns:
        df["stage2_score_num"] = pd.to_numeric(df["stage2_score"], errors="coerce").fillna(0)
    else:
        df["stage2_score_num"] = 0

    # Convert right_to_work_uk to boolean
    if "right_to_work_uk" in df.columns:
        df["right_to_work_uk_bool"] = df["right_to_work_uk"].apply(
            lambda x: True if str(x).strip().lower() in ("yes", "true", "1") else False
        )
    else:
        df["right_to_work_uk_bool"] = False

    # Print label distribution
    logger.info("  Label distribution:")
    for label, count in sorted(df["Recruiter_Label"].value_counts().items()):
        label_name = {0: "Reject", 1: "Possible", 2: "Top Match"}.get(label, "?")
        logger.info(f"    Label {label} ({label_name}): {count}")

    return df


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="12_evaluate_model.py — Offline Evaluation & Threshold Generation"
    )
    parser.add_argument(
        "--input", type=str, default=str(DEFAULT_INPUT),
        help=f"Path to labelled Excel file (default: {DEFAULT_INPUT.name})"
    )
    parser.add_argument(
        "--no-ml", action="store_true", default=False,
        help="Skip ML model evaluation"
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Evaluation & Threshold Generation — Diversifying.io")
    logger.info("=" * 60)

    # Load data
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        sys.exit(1)

    df = load_evaluation_data(input_path)

    # Global evaluation
    logger.info("\n--- Global Evaluation ---")
    global_result = evaluate_global(df)
    gm = global_result["metrics_at_best"]
    logger.info(
        f"  Global optimal threshold: {global_result['best_threshold']}  "
        f"F1={global_result['best_f1']}  "
        f"P={gm['precision']}  R={gm['recall']}  "
        f"(TP={gm['tp']} FP={gm['fp']} FN={gm['fn']} TN={gm['tn']})"
    )

    # Per-role evaluation
    logger.info("\n--- Per-Role Evaluation ---")
    role_results = evaluate_per_role(df)
    for jd_title in sorted(role_results.keys()):
        r = role_results[jd_title]
        if r.get("best_threshold") is not None:
            m = r["metrics_at_best"]
            logger.info(
                f"  {jd_title[:45]:45s}  "
                f"T={r['best_threshold']:.2f}  F1={r['best_f1']:.3f}  "
                f"P={m['precision']:.2f}  R={m['recall']:.2f}  "
                f"(top={r['n_top']}  poss={r['n_possible']})"
            )
        else:
            logger.info(
                f"  {jd_title[:45]:45s}  "
                f"NO TOP MATCHES — threshold not computable  "
                f"(poss={r['n_possible']})"
            )

    # Generate thresholds config
    logger.info("\n--- Generating Thresholds Config ---")
    thresholds_config = generate_thresholds_config(global_result, role_results)

    # ML model evaluation (optional)
    ml_result = None
    if not args.no_ml:
        logger.info("\n--- ML Model Evaluation ---")
        ml_result = evaluate_ml_model(df)
        if ml_result:
            mm = ml_result["metrics"]
            logger.info(
                f"  ML Model: F1={mm['f1']}  P={mm['precision']}  R={mm['recall']}  "
                f"(TP={mm['tp']} FP={mm['fp']} FN={mm['fn']} TN={mm['tn']})"
            )
        else:
            logger.info("  No trained ML model found — skipping")

    # Generate report
    logger.info("\n--- Generating Report ---")
    report = generate_report(global_result, role_results, ml_result, thresholds_config)

    # Print summary to console
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"  Pairs evaluated:     {global_result['n_total']}")
    print(f"  Labels:              {global_result['n_reject']} reject / "
          f"{global_result['n_possible']} possible / {global_result['n_top']} top")
    print(f"  Global threshold:    {global_result['best_threshold']}")
    print(f"  Global F1:           {global_result['best_f1']}")
    print(f"  Roles with threshold:{len(thresholds_config['roles'])}")
    print(f"  Thresholds file:     {THRESHOLDS_OUTPUT}")
    print(f"  Report file:         {REPORT_OUTPUT}")
    if ml_result:
        print(f"  ML Model F1:         {ml_result['metrics']['f1']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
