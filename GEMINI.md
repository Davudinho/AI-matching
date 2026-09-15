# Workspace Guidelines & Project Context

## Project: Dyversifying (AI-matching)
This repository implements an AI-matching pipeline for diversity-oriented candidate evaluation against Job Descriptions.

### Current Status & Progress Tracking
- A detailed record of recent progress, pipeline stages, and pending tasks is documented in [PROJECT_STATUS.md](file:///c:/Users/User/projects/dyversifying/PROJECT_STATUS.md).
- Always consult [PROJECT_STATUS.md](file:///c:/Users/User/projects/dyversifying/PROJECT_STATUS.md) upon starting a session to resume work immediately.

### Key Working Principles
- **Language Standard:** All prompts, logs, data schemas, and exported evaluation files must remain in **English**.
- **Universal Parsing:** Document extraction uses `backend/app/services/document_parser.py` supporting PDF (with Gemini Vision OCR fallback), DOCX, DOC, and TXT.
- **Evaluation Export:** The primary reference evaluation workbook is `docs/evaluation_results_EN.xlsx`.
