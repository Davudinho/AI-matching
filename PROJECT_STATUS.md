# Project Status & Handover Documentation

**Last Updated:** 2026-09-15  
**Repository:** [Davudinho/AI-matching](https://github.com/Davudinho/AI-matching)  
**Current Branch:** `main`

---

## 📌 Executive Summary

The project is an AI-powered, diversity-promoting candidate matching system (**Dyversifying / AI-matching**). It evaluates candidate CVs against Job Descriptions (JDs) using a 3-stage matching pipeline:
1. **Stage 1 (Pre-filter / Hard Gate):** Hard criteria and field of work verification.
2. **Stage 2 (Semantic Matching):** Vector embedding similarity (`text-embedding-004`).
3. **Stage 3 (Deep AI Evaluation):** Gemini LLM assessment producing Match Scores, Critical Gaps, Strengths, and Recommendation.

---

## ✅ Recently Completed Work (as of 11.09.2026 – 15.09.2026)

1. **Universal Document Parser (`backend/app/services/document_parser.py`):**
   - Implemented unified parsing for `.pdf`, `.docx`, `.doc`, and `.txt`.
   - **Hybrid PDF Extraction:** Native text extraction via PyMuPDF first; if extracted text < 100 characters, falls back automatically to **Gemini Vision OCR** (rendering pages to images and extracting text without needing external Tesseract binary).
   - **Word 97-2003 (.doc) Support:** Windows COM automation via `pywin32` converts `.doc` to `.docx` dynamically.
   - Added `pywin32` dependency to `requirements.txt`.

2. **Parser Script Integration:**
   - [scripts/01_parse_jds.py](file:///c:/Users/User/projects/dyversifying/scripts/01_parse_jds.py): Multi-format support for Job Descriptions.
   - [scripts/02_parse_cvs.py](file:///c:/Users/User/projects/dyversifying/scripts/02_parse_cvs.py): Supports `.pdf`, `.docx`, `.doc`, and `.txt`.
   - Processed two new `.doc` candidate CVs (`Ranil Perera` -> **CAND-021**, `Jaisal Patel` -> **CAND-022**).

3. **Complete English Localization:**
   - [scripts/08_ai_match.py](file:///c:/Users/User/projects/dyversifying/scripts/08_ai_match.py): Entirely migrated to English (prompts, output schema, logs, reasoning).
   - Executed 3-stage matching pipeline for all **176 candidate-job pairs** (22 candidates × 8 JDs).
   - Both CAND-021 and CAND-022 were properly filtered by the profession hard gate (unrelated fields).

4. **English Evaluation Export ([scripts/11_export_results_en.py](file:///c:/Users/User/projects/dyversifying/scripts/11_export_results_en.py)):**
   - Automated script translating residual legacy German database entries into English.
   - Generated final Excel file:  
     📄 [docs/evaluation_results_EN.xlsx](file:///c:/Users/User/projects/dyversifying/docs/evaluation_results_EN.xlsx) (8 tabs for 8 JDs, 176 pairs, 100% in English).

---

## 📋 Open Tasks & Next Steps

1. **Run OCR for the 32 Scanned Image-PDFs:**
   - 32 CVs in the raw dataset (e.g., CAND-002, CAND-005, CAND-009, CAND-012) originally yielded 0 characters because they were scanned images before OCR was integrated.
   - *Action needed:* Clear empty cache entries in `data/processed/cvs_raw.json` and re-run `scripts/02_parse_cvs.py` to populate them via Gemini Vision OCR, then cascade through anonymisation and matching.
2. **Recruiter Decision Ground Truth:**
   - Open [docs/evaluation_results_EN.xlsx](file:///c:/Users/User/projects/dyversifying/docs/evaluation_results_EN.xlsx) and review candidate pairings.
   - Fill in the `Recruiter Decision` column (`0 = No`, `1 = Possible`, `2 = Good`).
3. **Review Remaining Scripts for Language Consistency:**
   - Ensure [scripts/06_match_evaluate.py](file:///c:/Users/User/projects/dyversifying/scripts/06_match_evaluate.py) and any evaluation helpers match the English formatting standard.

---

## 🗂️ Key File Map

| Path | Description |
|---|---|
| `backend/app/services/document_parser.py` | Central multi-format parser (.pdf with OCR fallback, .docx, .doc, .txt) |
| `scripts/01_parse_jds.py` | Job description ingestion |
| `scripts/02_parse_cvs.py` | CV ingestion & text extraction |
| `scripts/03_anonymise_cvs.py` | PII removal & candidate anonymisation |
| `scripts/04_build_dataset.py` | Dataset assembly & pairing |
| `scripts/05_embed_and_store.py` | Vector embedding generation & Chroma/DB storage |
| `scripts/08_ai_match.py` | 3-stage matching pipeline (English) |
| `scripts/11_export_results_en.py` | Export pipeline to [docs/evaluation_results_EN.xlsx](file:///c:/Users/User/projects/dyversifying/docs/evaluation_results_EN.xlsx) |
| `docs/evaluation_results_EN.xlsx` | Latest English evaluation results (176 pairs) |
