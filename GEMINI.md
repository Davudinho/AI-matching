# Workspace Guidelines & Project Context

## Project: Dyversifying (AI-matching)
This repository implements an AI-matching pipeline for diversity-oriented candidate evaluation against Job Descriptions.

### Current Status & Progress Tracking
- A detailed record of recent progress, pipeline stages, and pending tasks is documented in [PROJECT_STATUS.md](file:///c:/Users/User/projects/dyversifying/PROJECT_STATUS.md).
- Always consult [PROJECT_STATUS.md](file:///c:/Users/User/projects/dyversifying/PROJECT_STATUS.md) upon starting a session to resume work immediately.
- **⚠️ Daily Rule:** At the end of every working session, update `PROJECT_STATUS.md`:
  - Move completed tasks to the ✅ section.
  - Add a dated entry describing what was done, what broke, and what is next.
  - This file is the single source of truth — keep it current!

### Key Working Principles
- **Language Standard:** All prompts, logs, data schemas, and exported evaluation files must remain in **English**.
- **Universal Parsing:** Document extraction uses `backend/app/services/document_parser.py` supporting PDF (with Gemini Vision OCR fallback), DOCX, DOC, and TXT.
- **Evaluation Export:** The primary reference evaluation workbook is `docs/evaluation_results_EN.xlsx`.
