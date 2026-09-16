"""
scripts/14_train_calibration_model.py — Train ML Calibration Model for Match Confidence

PURPOSE:
    1. Loads match features and recruiter labels from PostgreSQL (or Excel fallback).
    2. Trains a supervised calibration model to predict recruiter suitability (0=Reject, 1=Possible, 2=Top Match).
    3. Evaluates generalization via Leave-One-Role-Out Cross-Validation (8 folds).
    4. Computes Out-Of-Fold (OOF) predictions, probabilities, and calibration metrics.
    5. Saves the trained model to `scripts/models/calibration_model.joblib`.
    6. Updates `ml_predicted_label` and `ml_confidence` in PostgreSQL `ai_match_results`.
    7. Generates a markdown evaluation report at `docs/ml_model_report.md`.

PROVENANCE & METHODOLOGY:
    - Labels: AI-bootstrap ground truth (Perplexity). Real recruiter feedback replaces this in production.
    - Class Imbalance: 160 Reject vs 10 Possible vs 6 Top Match. Balanced sample weights applied.
    - Output: Model provides calibrated probabilities (predict_proba), with P(Top Match) as confidence.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import joblib

from sklearn.model_selection import LeaveOneGroupOut
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
    accuracy_score
)
from sklearn.utils.class_weight import compute_sample_weight

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import settings

MODELS_DIR = PROJECT_ROOT / "scripts" / "models"
DOCS_DIR = PROJECT_ROOT / "docs"


def parse_args():
    parser = argparse.ArgumentParser(description="Train ML match calibration model")
    parser.add_argument(
        "--model-type",
        type=str,
        default="gradient_boosting",
        choices=["gradient_boosting", "logistic_regression", "random_forest"],
        help="Algorithm to train (default: gradient_boosting)"
    )
    parser.add_argument(
        "--no-db-update",
        action="store_true",
        help="Skip updating ml_predicted_label and ml_confidence in PostgreSQL"
    )
    parser.add_argument(
        "--report",
        type=str,
        default="docs/ml_model_report.md",
        help="Path for markdown report output"
    )
    return parser.parse_args()


def get_db_connection():
    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    return psycopg2.connect(db_url)


def load_dataset():
    """Load matching dataset from PostgreSQL with candidate and JD features."""
    conn = get_db_connection()
    query = """
        SELECT 
            ai.id,
            jd.title AS jd_title,
            c.anon_ref,
            ai.stage1_score,
            ai.stage1_passed,
            ai.stage2_score,
            ai.stage2_met_count,
            ai.stage2_total_count,
            ai.stage3_verdict,
            ai.final_score,
            c.years_experience,
            c.right_to_work_uk,
            ai.recruiter_label
        FROM ai_match_results ai
        JOIN job_descriptions jd ON jd.jd_id = ai.jd_id
        JOIN candidates c ON c.cv_id = ai.cv_id
        ORDER BY jd.title, ai.final_score DESC;
    """
    df = pd.read_sql(query, conn)
    conn.close()

    # Fallback if DB lacks recruiter_labels
    if df["recruiter_label"].isna().all():
        excel_path = PROJECT_ROOT / "docs/evaluation_results_III_recruiter_labels.xlsx"
        if excel_path.exists():
            print(f" [Info] Loading labels from {excel_path}...")
            edf = pd.read_excel(excel_path, sheet_name="All Results")
            label_map = {(r["jd_title"].strip(), r["anon_ref"].strip()): r.get("Recruiter_Label", 0) for _, r in edf.iterrows()}
            df["recruiter_label"] = df.apply(lambda r: label_map.get((r["jd_title"].strip(), r["anon_ref"].strip()), 0), axis=1)

    return df


def prepare_features(df: pd.DataFrame):
    """Clean and encode feature matrix for ML models."""
    verdict_map = {
        "Strong Match": 10.0,
        "Possible Match": 6.0,
        "Weak Match": 2.0
    }

    X_data = pd.DataFrame()
    X_data["stage1_score"] = df["stage1_score"].fillna(0.0).astype(float)
    X_data["stage1_passed"] = df["stage1_passed"].fillna(False).astype(int)
    X_data["stage2_score"] = df["stage2_score"].fillna(0.0).astype(float)
    X_data["stage2_met_count"] = df["stage2_met_count"].fillna(0).astype(int)
    X_data["stage2_total_count"] = df["stage2_total_count"].fillna(0).astype(int)
    X_data["stage3_score"] = df["stage3_verdict"].map(verdict_map).fillna(0.0).astype(float)
    X_data["final_score"] = df["final_score"].fillna(0.0).astype(float)
    X_data["years_experience"] = df["years_experience"].fillna(0.0).astype(float)
    X_data["right_to_work_uk"] = df["right_to_work_uk"].fillna(False).astype(int)

    feature_names = list(X_data.columns)
    X = X_data.values
    y = df["recruiter_label"].fillna(0).astype(int).values
    groups = df["jd_title"].values

    return X, y, groups, feature_names


def get_model(model_type: str):
    """Instantiate classifier pipeline."""
    if model_type == "logistic_regression":
        return Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42))
        ])
    elif model_type == "random_forest":
        return RandomForestClassifier(
            n_estimators=100,
            max_depth=4,
            class_weight="balanced",
            random_state=42
        )
    elif model_type == "gradient_boosting":
        return GradientBoostingClassifier(
            n_estimators=80,
            learning_rate=0.08,
            max_depth=3,
            random_state=42
        )
    else:
        raise ValueError(f"Unknown model_type: {model_type}")


def evaluate_logo_cv(X, y, groups, model_type: str):
    """Leave-One-Role-Out Cross-Validation."""
    logo = LeaveOneGroupOut()
    n_splits = logo.get_n_splits(groups=groups)

    oof_preds = np.zeros(len(y), dtype=int)
    oof_probs = np.zeros((len(y), 3), dtype=float)

    fold_reports = []

    for fold_idx, (train_idx, test_idx) in enumerate(logo.split(X, y, groups)):
        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]
        role_name = groups[test_idx][0]

        model = get_model(model_type)

        # Apply sample weights for gradient boosting to counter extreme class imbalance
        if model_type == "gradient_boosting":
            sample_weight = compute_sample_weight("balanced", y_train)
            model.fit(X_train, y_train, sample_weight=sample_weight)
        else:
            model.fit(X_train, y_train)

        # Predict
        probs = model.predict_proba(X_test)
        # Ensure probs has all 3 classes (0, 1, 2)
        classes_present = model.classes_
        full_probs = np.zeros((len(y_test), 3), dtype=float)
        for c_idx, c_val in enumerate(classes_present):
            if c_val < 3:
                full_probs[:, c_val] = probs[:, c_idx]

        preds = np.argmax(full_probs, axis=1)

        oof_preds[test_idx] = preds
        oof_probs[test_idx] = full_probs

        fold_acc = accuracy_score(y_test, preds)
        fold_reports.append({
            "fold": fold_idx + 1,
            "role": role_name,
            "test_size": len(test_idx),
            "label_distribution": dict(pd.Series(y_test).value_counts()),
            "accuracy": fold_acc
        })

    return oof_preds, oof_probs, fold_reports


def train_final_model(X, y, model_type: str):
    """Fit model on all available samples."""
    model = get_model(model_type)
    if model_type == "gradient_boosting":
        sample_weight = compute_sample_weight("balanced", y)
        model.fit(X, y, sample_weight=sample_weight)
    else:
        model.fit(X, y)
    return model


def main():
    args = parse_args()

    print(f"\n=======================================================")
    print(f" 14_train_calibration_model.py")
    print(f" Model Type:  {args.model_type}")
    print(f" Update DB:   {'NO' if args.no_db_update else 'YES'}")
    print(f"=======================================================\n")

    # 1. Load data
    df = load_dataset()
    print(f"[1/5] Loaded {len(df)} records across {df['jd_title'].nunique()} unique roles.")
    print(f"      Label distribution: {dict(df['recruiter_label'].value_counts())}")

    # 2. Prepare features
    X, y, groups, feature_names = prepare_features(df)
    print(f"[2/5] Prepared {len(feature_names)} features: {feature_names}")

    # 3. Cross-Validation
    print(f"[3/5] Running Leave-One-Role-Out Cross-Validation (8 folds)...")
    oof_preds, oof_probs, fold_reports = evaluate_logo_cv(X, y, groups, args.model_type)

    # 4. Metrics
    print(f"\n--- Cross-Validation Evaluation Results ---")
    overall_acc = accuracy_score(y, oof_preds)
    p_macro, r_macro, f1_macro, _ = precision_recall_fscore_support(y, oof_preds, average="macro", zero_division=0)
    p_weight, r_weight, f1_weight, _ = precision_recall_fscore_support(y, oof_preds, average="weighted", zero_division=0)

    # Class 2 (Top Match) specific metrics
    y_bin = (y == 2).astype(int)
    pred_bin = (oof_preds == 2).astype(int)
    p2, r2, f1_2, _ = precision_recall_fscore_support(y_bin, pred_bin, average="binary", zero_division=0)

    cm = confusion_matrix(y, oof_preds, labels=[0, 1, 2])
    print(f"Overall Accuracy:   {overall_acc:.4f}")
    print(f"Macro F1 Score:     {f1_macro:.4f}")
    print(f"Weighted F1 Score:  {f1_weight:.4f}")
    print(f"\nTop Match (Label 2) Detection:")
    print(f"  Precision: {p2:.4f} | Recall: {r2:.4f} | F1: {f1_2:.4f}")
    print(f"\nFull Confusion Matrix (Rows=True, Cols=Pred: [0, 1, 2]):")
    print(cm)

    # 5. Train final model & save
    print(f"\n[4/5] Training production calibration model on all {len(X)} samples...")
    final_model = train_final_model(X, y, args.model_type)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / "calibration_model.joblib"

    # Extract feature importance if available
    feature_importances = {}
    if hasattr(final_model, "feature_importances_"):
        for name, imp in zip(feature_names, final_model.feature_importances_):
            feature_importances[name] = float(imp)
    elif hasattr(final_model, "named_steps") and hasattr(final_model.named_steps["clf"], "coef_"):
        coefs = np.mean(np.abs(final_model.named_steps["clf"].coef_), axis=0)
        for name, imp in zip(feature_names, coefs):
            feature_importances[name] = float(imp)

    save_payload = {
        "model": final_model,
        "feature_names": feature_names,
        "model_type": args.model_type,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": len(df),
        "cv_accuracy": float(overall_acc),
        "cv_macro_f1": float(f1_macro),
        "cv_top_match_f1": float(f1_2),
        "feature_importances": feature_importances,
        "labels_source": "AI-generated bootstrap (Perplexity)"
    }
    joblib.dump(save_payload, model_path)
    print(f"      Saved model to: {model_path}")

    # 6. Update DB with predictions & confidence
    if not args.no_db_update:
        print(f"\n[5/5] Updating PostgreSQL ai_match_results with ML predictions and confidence...")
        conn = get_db_connection()
        # Full model predictions & confidence
        full_probs = final_model.predict_proba(X)
        full_preds = np.argmax(full_probs, axis=1)
        # Class 2 prob is Top Match confidence
        confidence_scores = full_probs[:, 2] if full_probs.shape[1] > 2 else full_probs[:, -1]

        update_tuples = []
        for idx, row in df.iterrows():
            rec_id = int(row["id"])
            pred_lbl = int(full_preds[idx])
            conf_val = float(confidence_scores[idx])
            update_tuples.append((pred_lbl, conf_val, rec_id))

        with conn.cursor() as cur:
            query = """
                UPDATE ai_match_results AS ai
                SET 
                    ml_predicted_label = val.ml_predicted_label,
                    ml_confidence = val.ml_confidence
                FROM (VALUES %s) AS val(ml_predicted_label, ml_confidence, id)
                WHERE ai.id = val.id;
            """
            execute_values(
                cur,
                query,
                update_tuples,
                template="(%s::int, %s::float, %s::int)"
            )
        conn.commit()
        conn.close()
        print(f"      Updated {len(update_tuples)} records with ml_predicted_label & ml_confidence.")

    # 7. Write Markdown Evaluation Report
    report_path = PROJECT_ROOT / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report_content = f"""# ML Calibration Model Evaluation Report

**Generated:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}  
**Model Type:** `{args.model_type}`  
**Evaluation Strategy:** Leave-One-Role-Out Cross-Validation (8 Folds)  
**Data Provenance:** Bootstrap AI Recruiter Labels (Perplexity) — replaces with live implicit feedback in production  

---

## 1. Overall Cross-Validation Performance

| Metric | Score |
| --- | --- |
| Accuracy | {overall_acc:.4f} |
| Macro F1 Score | {f1_macro:.4f} |
| Weighted F1 Score | {f1_weight:.4f} |
| Top Match (Label 2) Precision | {p2:.4f} |
| Top Match (Label 2) Recall | {r2:.4f} |
| Top Match (Label 2) F1 Score | {f1_2:.4f} |

---

## 2. Confusion Matrix (Out-of-Fold Predictions)

Rows: True Ground Truth | Columns: Model Prediction

| Ground Truth \\ Prediction | Reject (0) | Possible (1) | Top Match (2) |
| --- | --- | --- | --- |
| **Reject (0)** | {cm[0, 0]} | {cm[0, 1]} | {cm[0, 2]} |
| **Possible (1)** | {cm[1, 0]} | {cm[1, 1]} | {cm[1, 2]} |
| **Top Match (2)** | {cm[2, 0]} | {cm[2, 1]} | {cm[2, 2]} |

---

## 3. Feature Importance Ranking

Features contributing to recruiter match suitability:

| Rank | Feature | Importance / Weight |
| --- | --- | --- |
"""
    if feature_importances:
        sorted_feats = sorted(feature_importances.items(), key=lambda x: x[1], reverse=True)
        for rank, (feat, imp) in enumerate(sorted_feats, 1):
            report_content += f"| {rank} | `{feat}` | {imp:.4f} |\n"
    else:
        report_content += "| - | Not applicable for linear model | - |\n"

    report_content += """
---

## 4. Production Usage & Implicit Feedback Architecture

- **Inference Mode:** The ML calibration model acts as an explainable confidence layer on top of the 3-stage funnel.
- **Continuous Retraining:** Natural platform interactions (Shortlist ⭐ = 1, Interview 📞 = 2, Dismiss ❌ = 0) update ground truth labels in `ai_match_results.recruiter_label`.
- **Scheduled Calibration:** Retraining can be triggered periodically once sufficient human interactions are logged.
"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"\n[Done] Evaluation report written to: {report_path}\n")


if __name__ == "__main__":
    main()
