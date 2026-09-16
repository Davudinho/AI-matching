"""
scripts/match_config.py — Threshold & ML Model Configuration Loader

PURPOSE:
    Central configuration module for the matching system.
    Loads role-specific thresholds and ML calibration models.

    Used by:
    - 08_ai_match.py (online: threshold lookup + ML inference)
    - 12_evaluate_model.py (offline: threshold generation)
    - API endpoints (online: threshold lookup)

DESIGN DECISION — Implicit Feedback Architecture:
    This system is designed for a platform where EXTERNAL recruiters
    use the service. Feedback is collected IMPLICITLY through natural
    recruiter actions (shortlist, interview request, dismiss) — never
    through explicit "please rate this match" forms.

    The recruiter_label field maps to:
        0 = Recruiter dismissed / skipped candidate
        1 = Recruiter shortlisted candidate
        2 = Recruiter requested interview / hired

    In the current prototype, labels are AI-generated (bootstrap).
    In production, they will be derived from recruiter platform actions.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = Path(__file__).resolve().parent / "config"
MODELS_DIR = Path(__file__).resolve().parent / "models"

THRESHOLDS_FILE = CONFIG_DIR / "match_thresholds.json"
MODEL_FILE = MODELS_DIR / "calibration_model.joblib"

# Global default threshold if no role-specific one exists
DEFAULT_TOP_MATCH_THRESHOLD = 6.5


def load_thresholds() -> dict:
    """
    Load role-specific top-match thresholds from JSON config.

    Returns:
        Dict with structure:
        {
            "default": 6.5,
            "roles": {
                "Senior Finance Officer": 6.8,
                "Delivery Manager (Online Products)": 7.0,
                ...
            },
            "metadata": {
                "generated_at": "2026-09-16T...",
                "source": "12_evaluate_model.py",
                "labels_source": "AI-generated (bootstrap)"
            }
        }
    """
    if not THRESHOLDS_FILE.exists():
        logger.warning(
            f"No thresholds file found at {THRESHOLDS_FILE}. "
            f"Using default threshold {DEFAULT_TOP_MATCH_THRESHOLD} for all roles. "
            f"Run 'python scripts/12_evaluate_model.py' to generate thresholds."
        )
        return {"default": DEFAULT_TOP_MATCH_THRESHOLD, "roles": {}, "metadata": {}}

    with open(THRESHOLDS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    logger.info(
        f"Loaded thresholds for {len(data.get('roles', {}))} roles "
        f"(default={data.get('default', DEFAULT_TOP_MATCH_THRESHOLD)})"
    )
    return data


def get_top_match_threshold(jd_title: str, thresholds: dict = None) -> float:
    """
    Get the top-match threshold for a specific role.

    Args:
        jd_title: The job title to look up
        thresholds: Pre-loaded thresholds dict (optional, loads from file if None)

    Returns:
        Float threshold value. Candidates with final_score >= threshold
        are flagged as potential top matches.
    """
    if thresholds is None:
        thresholds = load_thresholds()

    role_thresholds = thresholds.get("roles", {})
    default = thresholds.get("default", DEFAULT_TOP_MATCH_THRESHOLD)

    threshold = role_thresholds.get(jd_title, default)
    return float(threshold)


def load_calibration_model():
    """
    Load the trained ML calibration model.

    Returns:
        Tuple of (model, feature_names) or (None, None) if no model exists.

    NOTE:
        The ML model does NOT replace the 3-stage LLM funnel.
        It adds a calibrated confidence score based on historical
        recruiter decisions (or AI-bootstrap labels in prototype).
    """
    if not MODEL_FILE.exists():
        logger.info(
            f"No calibration model found at {MODEL_FILE}. "
            f"ML confidence scores will not be available. "
            f"Run 'python scripts/14_train_calibration_model.py' to train."
        )
        return None, None

    try:
        import joblib
        model_data = joblib.load(MODEL_FILE)
        model = model_data["model"]
        feature_names = model_data["feature_names"]
        logger.info(
            f"Loaded calibration model "
            f"(trained: {model_data.get('trained_at', 'unknown')}, "
            f"features: {len(feature_names)})"
        )
        return model, feature_names
    except Exception as e:
        logger.warning(f"Failed to load calibration model: {e}")
        return None, None


def predict_ml_confidence(
    model,
    feature_names: list,
    stage1_score: float,
    stage2_score: float,
    stage3_verdict: str = None,
    years_experience: int = None,
    right_to_work_uk: bool = None,
) -> dict:
    """
    Get ML-calibrated confidence scores for a candidate-JD pair.

    Args:
        model: Trained sklearn model
        feature_names: List of feature names the model expects
        stage1_score: Score from Stage 1 (0-10)
        stage2_score: Score from Stage 2 (0-10)
        stage3_verdict: Verdict string or None
        years_experience: Candidate years of experience
        right_to_work_uk: Whether candidate has UK right to work

    Returns:
        Dict with:
            ml_predicted_label: int (0, 1, or 2)
            ml_confidence: float (probability of being label 2 = top match)
            ml_probabilities: dict {0: p0, 1: p1, 2: p2}
    """
    import numpy as np

    # Convert stage3 verdict to numeric
    s3_map = {"Strong Match": 10.0, "Possible Match": 6.0, "Weak Match": 2.0}
    stage3_value = s3_map.get(stage3_verdict, 0.0) if stage3_verdict else 0.0

    # Build feature vector in the order the model expects
    feature_map = {
        "stage1_score": float(stage1_score or 0),
        "stage2_score": float(stage2_score or 0),
        "stage3_value": stage3_value,
        "years_experience": float(years_experience or 0),
        "right_to_work_uk": 1.0 if right_to_work_uk else 0.0,
    }

    features = np.array([[feature_map.get(f, 0.0) for f in feature_names]])

    try:
        predicted_label = int(model.predict(features)[0])
        probabilities = model.predict_proba(features)[0]

        # Map probabilities to class labels
        classes = list(model.classes_)
        prob_dict = {int(cls): float(prob) for cls, prob in zip(classes, probabilities)}

        return {
            "ml_predicted_label": predicted_label,
            "ml_confidence": prob_dict.get(2, 0.0),  # P(top match)
            "ml_probabilities": prob_dict,
        }
    except Exception as e:
        logger.warning(f"ML prediction failed: {e}")
        return {
            "ml_predicted_label": None,
            "ml_confidence": None,
            "ml_probabilities": None,
        }
