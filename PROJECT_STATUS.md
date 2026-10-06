# Project Status & Handover Documentation

**Last Updated:** 2026-10-05
**Repository:** [Davudinho/AI-matching](https://github.com/Davudinho/AI-matching)
**Current Branch:** `main`

> ⚠️ **Daily Habit:** Update this file at the end of every working session.
> Describe what was done, what broke, what was fixed, and what is next.
> A stale status file costs hours of re-orientation!

---

## 📌 Executive Summary

The project is an AI-powered, diversity-promoting candidate matching system (**Dyversifying / AI-matching**). It evaluates candidate CVs against Job Descriptions (JDs) using a 3-stage matching pipeline:
1. **Stage 1 (Profession Gate):** Fast binary verification of whether candidate career domain fits the role.
2. **Stage 2 (Requirements Scoring):** Evidence-based evaluation of each essential requirement (0–10).
3. **Stage 3 (Deep Match Report):** Comprehensive qualitative analysis for top shortlist candidates.
4. **ML Calibration Layer:** Post-funnel statistical calibration model generating role-specific `is_top_match` decisions and calibrated `ml_confidence` scores based on recruiter feedback.

**Current State:** Full-stack **prototype** is deployed (Render / Vercel / Supabase), but **not yet MVP-ready**. Recruiter registration and JD creation work. Live applications are NOT scored by the 3-stage pipeline yet, and there are open security, privacy and stability issues (see 2026-10-05 log entry).

---

## 🗓️ Daily Log

### 2026-10-05 — Manual live test + code review
**Works:** Recruiter registration, login, JD creation (text + PDF/DOCX upload).

**Broken / missing (found in live test):**
- `.doc` not accepted (CV + JD) — parser relies on Windows-only `win32com`.
- `/dashboard/jobs` → 404 — page exists only locally (untracked `frontend/app/dashboard/jobs/page.tsx`), never deployed.
- Delete button not visible for recruiter (code exists on overview, limited to 6 newest jobs; deployment to be verified).
- Large/scanned CVs (e.g. Fred Wang, 4.3 MB) fail; Render crashes — synchronous 300-DPI OCR in request, blocking Gemini calls, 512 MB free tier.
- Duplicate CV uploads possible; no dedupe.
- Logged-in recruiter can register again, apply to jobs and upload CVs via public form.
- No list views for Shortlist / Interview / Dismiss.
- "View public job page" link broken; purpose unclear.
- Recruiter cannot contact candidates (no contact data stored, no reveal mechanism); reference number has no use for candidates.

**Additional findings (code review):**
- 3-stage AI matching is never executed for live applications (only placeholder row inserted).
- Regex anonymisation does not remove names.
- Public endpoints without auth: `GET /candidates/{id}`, `GET /matching/{jd_id}/ai-results`, `POST /matching/feedback`.
- No multi-tenancy: JDs have no `recruiter_id`; any recruiter can see/delete all JDs.
- Untracked secret files in `docs/` not covered by `.gitignore`; no `.dockerignore`.
- No rate limiting on public upload; prompt-injection risk; no AI disclosure/consent on apply form (confirmed by Perplexity review).

**Decisions (2026-10-05, evening — after Perplexity comparison):**
- Stay on free tier (Render Free + Supabase Free + Vercel Hobby). Keep-alive ping + "server starting" UI state.
- Gemini must move to a **company-owned, paid-tier** account (free tier allows Google to use CV data → not GDPR-compliant). Est. $1–5/month.
- AI matching moves **into the backend**: Postgres-backed job queue (`processing_jobs`, `FOR UPDATE SKIP LOCKED`) + in-process async worker; 202 Accepted + status polling. arq/Redis deferred until budget exists.
- Candidates: no account in MVP; mandatory email + magic status link. Blind until shortlist, then contact reveal (`candidate_contacts`, audited).
- Job visibility: public / link-only (default) / internal. Recruiter CV upload as separate dashboard feature.
- Compliance baseline: AI disclosure + consent, "AI never rejects", audit log, retention policy. EU AI Act high-risk obligations postponed to 2027-12-02 (Digital Omnibus, Reg. (EU) 2026/1744); GDPR applies now.

**Done:**
- Extended `.gitignore` for secret files in `docs/` (verified with `git check-ignore`).
- Added `.dockerignore` (excludes `data/`, `docs/`, `frontend/`, `venv/`, secrets).

**Next:** P0 — user moves secret files out of `docs/` and rotates keys; then multi-tenancy, auth on recruiter endpoints, rate limiting, queue + worker with live 3-stage matching, lightweight OCR. Open question: target market UK vs EU.

### 2026-10-02 — Status review
- Reconstructed work from git history (22 deployment bugfix commits, 23.09–30.09). Note: deployment was marked "live" based on commit messages only — not verified end-to-end.

---

## ✅ Completed Work

### Phase 1: Backend API (FastAPI) — ✅ Done
- `auth.py`: JWT-based registration and login endpoints.
- `candidates.py`: Refactored `/apply` to securely handle uploads, strip PII, and generate embeddings.
- `jds.py`: Endpoints for JD text creation, file uploads, and **deletion**.
- `document_parser.py`: Linux-compatibility fix for `.doc` files (Render/Docker friendly).
- Fully Dockerized API with a `render.yaml` blueprint.
- Created `scripts/02b_reprocess_ocr_cvs.py` — targeted re-processing script for CVs with < 100 chars extracted.
- Successfully processed 4 scanned image-PDFs via Gemini Vision OCR.
- Full downstream pipeline re-run: `03_anonymise_cvs.py` → `04_build_dataset.py` → `05_embed_and_store.py` → `08_ai_match.py` → `11_export_results_en.py`.

### Phase 2: Frontend (Next.js 14) — ✅ Done
- Design system: Tailwind CSS + `shadcn/ui` + Framer Motion.
- Landing page, Job browsing (`/jobs`, `/jobs/[id]`), Candidate application (`/apply/[id]`).
- Recruiter Auth (`/auth/login`, `/auth/register`).
- Recruiter Dashboard (`/dashboard`) with active jobs overview + **delete button for JD cards**.
- JD Creation (`/dashboard/jobs/new`) — free-text and file upload (PDF/DOCX) modes.
- Candidate Ranking (`/dashboard/jobs/[id]`) with ML scores, explainability, Shortlist/Interview/Dismiss feedback buttons.

### Phase 3: Production Deployment — 🟡 Deployed, not production-ready (2026-09-23 → 2026-09-30)
All three platforms are deployed. **22 bugfix commits** were required to get the stack running (see open issues in Daily Log):

| Date | Commit | Fix |
|---|---|---|
| 2026-09-23 | `dc982b5` | Removed HNSW index (pgvector limit: HNSW max 2000 dims, vectors are 3072) |
| 2026-09-23 | `2aeecda` | Added `email-validator` for Pydantic `EmailStr` |
| 2026-09-23 | `689beec` | Removed broken `vercel.json` forcing a secret reference |
| 2026-09-24 | `1ad32a2` | Secured `.gitignore`, fixed model name, unified token expiry |
| 2026-09-24 | `216844e` | Added minimal `vercel.json` for correct Next.js detection |
| 2026-09-24 | `f7a1a84` | CORS: allow all `*.vercel.app` origins via regex |
| 2026-09-24 | `54ecca5` | SSL: switched from `sslmode` URL param → `connect_args` + custom `SSLContext(CERT_NONE)` for Supabase pooler on slim Docker |
| 2026-09-24 | `27c5c07` | Added `statement_cache_size=0` for Supabase Session Pooler compatibility |
| 2026-09-24 | `1bfb2e4` | Custom `SSLContext` (CERT_NONE) for Supabase pooler on slim Docker |
| 2026-09-24 | `8364ffd` | Replaced `passlib` with raw `bcrypt` to fix 500 crashes (`bcrypt >= 4.1.0` incompatibility) |
| 2026-09-24 | `8f258d0` | Cast `user_id` UUID → `str` during JWT generation to fix JSON serialization error |
| 2026-09-24 | `792552c` | Fixed `[object Object]` errors: parse array responses correctly, don't overwrite Content-Type headers |
| 2026-09-24 | `e6456db` | Fixed `SELECT created_at` in `get_current_user` to satisfy `RecruiterProfile` schema |
| 2026-09-29 | `0e5138e` | Explicitly convert asyncpg UUID → `str` in `get_current_user` to fix `/me` 500 error |
| 2026-09-29 | `034f684` | Added global exception handler to expose actual error messages in 500 responses |
| 2026-09-29 | `d6a76b1` | Updated Gemini model: deprecated `gemini-2.0-flash` → `gemini-3.8-flash` |
| 2026-09-29 | `b932353` | Replaced all `::jsonb` raw casts with `CAST(... AS JSONB)` to fix SQLAlchemy `PostgresSyntaxError` |
| 2026-09-29 | `eb71f03` | Replaced all `::vector` raw casts with `CAST(... AS vector)` |
| 2026-09-29 | `5ca763b` | Removed broken `/dashboard/jobs` sidebar link |
| 2026-09-29 | `ec285f7` | Added delete button to JD cards; removed broken `/dashboard/jobs` link |
| 2026-09-30 | `9adcf8f` | Patched remaining `::jsonb` casts in `candidates.py`; fixed pagination count; fixed broken `/dashboard/jobs` link in rankings page |

---

## 📋 Open Tasks & Next Steps

### P0 — Blockers (before any real user)
1. Remove secret files from `docs/`, extend `.gitignore`, add `.dockerignore`, rotate keys.
2. Multi-tenancy: `recruiter_id` on JDs + ownership checks.
3. Auth on all recruiter endpoints (`ai-results`, `feedback`, `candidates`).
4. Async application processing + run 3-stage matching live.
5. Lightweight OCR (send PDF directly to Gemini), non-blocking Gemini calls.

### P1 — Core UX (pending product decisions)
6. Candidate identity model: email, dedupe, reveal-on-shortlist, LLM name anonymisation.
7. Pipeline view (New / Shortlist / Interview / Dismissed).
8. `/dashboard/jobs` page with delete + visibility settings.
9. Role-aware navigation; block `/apply` for recruiters.
10. `.doc` support via `antiword` (CV + JD).

### Future Maintenance
1. **Collect Live Recruiter Interactions:**
   - As recruiters shortlist/invite/dismiss candidates, feedback is captured via `/api/v1/matching/feedback` and replaces AI-bootstrap labels with real human decisions.
2. **Periodic Model Retraining:**
   - Run `python scripts/14_train_calibration_model.py` periodically when new recruiter decisions accumulate.
3. **Vector Index:** Consider adding an IVFFlat index (not HNSW — pgvector limits HNSW to ≤2000 dims) once the candidate count grows significantly.

---

## 🗂️ Key File Map

| Path | Description |
|---|---|
| `backend/app/services/document_parser.py` | Multi-format parser (.pdf with OCR fallback, .docx, .doc, .txt) |
| `backend/app/api/routes/auth.py` | JWT registration & login |
| `backend/app/api/routes/candidates.py` | CV upload → anonymise → embed → store → match |
| `backend/app/api/routes/jds.py` | JD creation (text + file), listing, deletion |
| `backend/app/api/routes/matching.py` | API endpoints: vector search, AI match results, implicit feedback |
| `frontend/app/dashboard/jobs/[id]/page.tsx` | Candidate ranking page with feedback buttons |
| `frontend/lib/api.ts` | Frontend API client (all backend calls) |
| `render.yaml` | Render deployment blueprint (Docker backend, Frankfurt region) |
| `scripts/match_config.py` | Central threshold loader and ML calibration inference helper |
| `scripts/config/match_thresholds.json` | Empirically derived role-specific top match thresholds |
| `scripts/models/calibration_model.joblib` | Serialized ML calibration model artifact |
| `scripts/08_ai_match.py` | 3-stage matching pipeline with online ML scoring |
| `scripts/11_export_results_en.py` | Excel export to `docs/evaluation_results_EN.xlsx` |
| `scripts/12_evaluate_model.py` | Standalone offline evaluation & threshold generator |
| `scripts/13_import_recruiter_labels.py` | DB schema expansion & recruiter label importer |
| `scripts/14_train_calibration_model.py` | ML calibration model training with Leave-One-Role-Out CV |
| `docs/evaluation_results_EN.xlsx` | Latest English evaluation results (176 pairs, with ML confidence) |
| `docs/SYSTEM_ARCHITECTURE_AND_EVALUATION.md` | Full system architecture, RAG setup, prompts & scoring formula |
| `docs/ml_model_report.md` | ML Cross-Validation & feature importance report |
| `docs/evaluation_report.md` | Confusion matrices & role-level evaluation report |

---

## 🔐 Deployment Platforms

| Platform | Service | Status |
|---|---|---|
| **Supabase** | PostgreSQL + pgvector (3072-dim) | ✅ Running |
| **Render** | FastAPI (Docker, Frankfurt, free tier) | 🟡 Running, unstable (OOM/timeouts on large CVs) |
| **Vercel** | Next.js 14 frontend | 🟡 Running, deployed state lags local code |

**Key env vars (set in Render dashboard):**
- `GEMINI_API_KEY`, `DATABASE_URL`, `SECRET_KEY`, `FRONTEND_URL`
- `GEMINI_MODEL=gemini-3.8-flash`, `GEMINI_EMBEDDING_MODEL=gemini-embedding-001`
