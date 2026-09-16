# Project Status & Handover Documentation

**Last Updated:** 2026-09-16  
**Repository:** [Davudinho/AI-matching](https://github.com/Davudinho/AI-matching)  
**Current Branch:** `main`

---

## 📌 Executive Summary

The project is an AI-powered, diversity-promoting candidate matching system (**Dyversifying / AI-matching**). It evaluates candidate CVs against Job Descriptions (JDs) using a 3-stage matching pipeline:
1. **Stage 1 (Profession Gate):** Fast binary verification of whether candidate career domain fits the role.
2. **Stage 2 (Requirements Scoring):** Evidence-based evaluation of each essential requirement (0–10).
3. **Stage 3 (Deep Match Report):** Comprehensive qualitative analysis for top shortlist candidates.
4. **ML Calibration Layer:** Post-funnel statistical calibration model generating role-specific `is_top_match` decisions and calibrated `ml_confidence` scores based on recruiter feedback.

---

## ✅ Recently Completed Work (as of 16.09.2026)

### 1. ML Calibration & Evaluation Framework (5/5 Tasks Complete)
- **Role-Specific Thresholds (`scripts/match_config.py` & `scripts/config/match_thresholds.json`):**
  - Replaced rigid static cutoffs with empirically optimized thresholds per role (e.g., Delivery Manager: 1.5, Senior Finance Officer: 6.75, Head of Risk: 6.0, default: 6.0).
- **Feature Logging & Database Expansion (`db/schema.sql`, `scripts/13_import_recruiter_labels.py`):**
  - Added `recruiter_label` (0=Reject, 1=Possible, 2=Top Match), `is_top_match` (boolean), `ml_predicted_label` (int), and `ml_confidence` (float) to `ai_match_results`.
  - Created idempotent migration and import script syncing evaluation data into PostgreSQL for all 176 match pairs.
- **ML Calibration Model (`scripts/14_train_calibration_model.py`):**
  - Supervised model trained on 9 match features with balanced sample weighting.
  - Validated via **Leave-One-Role-Out Cross-Validation (8 folds)**: **94.89% Accuracy**, Weighted F1: **0.9513**, Top Match F1: **0.7273**.
  - Production model serialized to `scripts/models/calibration_model.joblib`.
  - Detailed report generated: [docs/ml_model_report.md](file:///c:/Users/User/projects/dyversifying/docs/ml_model_report.md).
- **Offline Evaluation Module (`scripts/12_evaluate_model.py`):**
  - Standalone script computing confusion matrices, Precision/Recall/F1, and generating [docs/evaluation_report.md](file:///c:/Users/User/projects/dyversifying/docs/evaluation_report.md).
- **Online Matching & API Integration (`scripts/08_ai_match.py`, `scripts/11_export_results_en.py`, `matching.py`):**
  - `08_ai_match.py` automatically performs threshold lookup and ML inference after the funnel.
  - `11_export_results_en.py` exports `Top Match?` and `ML Confidence` with frozen panes and green highlights to [docs/evaluation_results_EN.xlsx](file:///c:/Users/User/projects/dyversifying/docs/evaluation_results_EN.xlsx).
  - FastAPI endpoint `/api/v1/matching/{jd_id}/ai-results` exposes full funnel + ML confidence data.
  - FastAPI endpoint `POST /api/v1/matching/feedback` records implicit recruiter feedback (`shortlist` -> 1, `interview` -> 2, `dismiss` -> 0).

### 2. Universal Document Parser & OCR Fallback
- Unified parsing for `.pdf`, `.docx`, `.doc`, and `.txt`.
- Native text extraction with automatic fallback to **Gemini Vision OCR** for scanned PDFs.
- Added COM automation for legacy Word 97-2003 (`.doc`).

### 3. Documentation & Code Health
- Resolved all Markdown linter warnings across documentation files.
- Documented Implicit Feedback architecture: External platform recruiters do not need explicit rating forms; platform actions naturally train the system in the background.

---

## 📋 Open Tasks & Next Steps

1. **OCR for Scanned Image-PDFs:**
   - Run OCR processing for candidate CVs that originally yielded 0 characters.
2. **Collect Live Recruiter Interactions:**
   - As recruiters use the frontend to shortlist or invite candidates, capture feedback via `/api/v1/matching/feedback` to continuously replace the initial AI-bootstrap labels with real human hiring decisions.
3. **Periodic Model Retraining:**
   - Run `python scripts/14_train_calibration_model.py` periodically when new recruiter decisions are logged.

---

## 🗂️ Key File Map

| Path | Description |
|---|---|
| `backend/app/services/document_parser.py` | Multi-format parser (.pdf with OCR fallback, .docx, .doc, .txt) |
| `backend/app/api/routes/matching.py` | API endpoints: vector search, AI match results, and implicit feedback |
| `scripts/match_config.py` | Central threshold loader and ML calibration inference helper |
| `scripts/config/match_thresholds.json` | Empirically derived role-specific top match thresholds |
| `scripts/models/calibration_model.joblib` | Serialized ML calibration model artifact |
| `scripts/08_ai_match.py` | 3-stage matching pipeline with online ML scoring |
| `scripts/11_export_results_en.py` | Excel export to `docs/evaluation_results_EN.xlsx` |
| `scripts/12_evaluate_model.py` | Standalone offline evaluation & threshold generator |
| `scripts/13_import_recruiter_labels.py` | DB schema expansion & recruiter label importer |
| `scripts/14_train_calibration_model.py` | ML calibration model training with Leave-One-Role-Out CV |
| `docs/evaluation_results_EN.xlsx` | Latest English evaluation results (176 pairs, with ML confidence) |
| `docs/ml_model_report.md` | ML Cross-Validation & feature importance report |
| `docs/evaluation_report.md` | Confusion matrices & role-level evaluation report |
