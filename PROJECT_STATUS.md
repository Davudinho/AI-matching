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

## ✅ Recently Completed Work (as of 22.09.2026)

### Phase 2: Frontend Implementation (Next.js 14+)
- Scaffolding of a new Next.js 14 App Router project (`frontend/`).
- Design system built with Tailwind CSS, `shadcn/ui`, and Framer Motion.
- **Completed Pages:**
  - Landing Page (`/`) with features and sector links.
  - Job Browsing (`/jobs` and `/jobs/[id]`) with pagination and sector filtering.
  - Candidate Application (`/apply/[id]`) with file dropzone and anonymisation privacy notice.
  - Recruiter Auth (`/auth/login` and `/auth/register`).
  - Recruiter Dashboard (`/dashboard`) with active jobs overview.
  - JD Creation (`/dashboard/jobs/new`) with free-text and file upload (PDF/DOCX) modes. Both leverage Gemini for data extraction and embedding.
  - Candidate Ranking (`/dashboard/jobs/[id]`) with ML scores, explainability, and quick feedback actions (Shortlist/Interview/Dismiss).

### Phase 1: Backend API & Deployment Prep (FastAPI)
- `auth.py`: JWT-based registration and login endpoints.
- `candidates.py`: Refactored `/apply` to securely handle uploads, strip PII, and generate embeddings.
- `jds.py`: Endpoints for JD text creation and file uploads.
- `document_parser.py`: Linux-compatibility fix for `.doc` files (Render/Docker friendly).
- Fully Dockerized API with a `render.yaml` blueprint.
- Created `scripts/02b_reprocess_ocr_cvs.py` — targeted re-processing script for CVs with < 100 chars extracted.
- Successfully processed 4 scanned image-PDFs via Gemini Vision OCR:
  - `resume-dan-holt-1784553981.pdf` → Creative & Media
  - `resume-rachel-young-1784454920.pdf` → Senior Photo Producer, Creative & Media
  - `resume-tristan-mcshepherd-1784550112.pdf` → Filmmaker, Creative & Media
  - `resume-fred-wang-1777976053.pdf` → Partner, Legal
- Full downstream pipeline re-run: `03_anonymise_cvs.py` → `04_build_dataset.py` → `05_embed_and_store.py` → `08_ai_match.py` → `11_export_results_en.py`.
- Embeddings regenerated using real OCR text (1400–1900 chars each, replacing previous empty vectors).

---

## 📋 Open Tasks & Next Steps

### Phase 3: Production Deployment
The application is fully coded and ready for production deployment on free-tier platforms:
1. **Supabase (Database):** Create project, run `db/schema.sql`, and configure `pgvector`.
2. **Render (Backend API):** Deploy the Dockerized FastAPI service using the provided `render.yaml` blueprint.
3. **Vercel (Frontend):** Deploy the Next.js app, configure CORS, and link `NEXT_PUBLIC_API_URL`.

### Future Maintenance
1. **Collect Live Recruiter Interactions:**
   - As recruiters use the frontend to shortlist or invite candidates, capture feedback via `/api/v1/matching/feedback` to continuously replace the initial AI-bootstrap labels with real human hiring decisions.
2. **Periodic Model Retraining:**
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
