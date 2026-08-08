# Diversifying.io — AI Recruitment Tool

An AI-powered candidate matching system built during an 8-week internship.  
Recruiters upload Job Descriptions and CVs. The system uses Gemini embeddings and semantic search to surface the best candidates with human-readable explanations.

---

## Architecture

```
data/raw/jds/     →  01_parse_jds.py   →  data/processed/jds.json
data/raw/cvs/     →  02_parse_cvs.py   →  data/processed/cvs_raw.json
                  →  03_anonymise.py   →  data/processed/cvs_anonymised.json
                  →  04_build_dataset  →  PostgreSQL (job_descriptions, candidates)
                  →  05_embed_store.py →  PostgreSQL (jd_embeddings, cv_embeddings)
                  →  06_match_eval.py  →  docs/evaluation_results.xlsx
```

**Stack:** FastAPI + PostgreSQL + pgvector + Gemini + (Next.js frontend in Weeks 4–8)

---

## Quick Start (Step by Step)

### Step 1 — Get a Gemini API Key (FREE)

1. Go to **https://aistudio.google.com/app/apikey**
2. Sign in with your Google account
3. Click **"Create API Key"** → select or create a project → copy the key
4. The free tier gives you **1,500 API requests/day** — more than enough

### Step 2 — Configure Your Environment

```powershell
# Edit the .env file and add your Gemini API key:
notepad .env
```

Change this line:
```
GEMINI_API_KEY=your-gemini-api-key-here
```
To your actual key:
```
GEMINI_API_KEY=AIzaSy...your-actual-key...
```

### Step 3 — Start PostgreSQL via Docker

> ⚠️ Make sure **Docker Desktop** is running before this step.
> Open Docker Desktop from the Start menu, wait for it to show "Engine running".

```powershell
docker compose up -d
```

This starts PostgreSQL with the pgvector extension. The database schema
is automatically created from `db/schema.sql` on first run.

Verify it's running:
```powershell
docker compose ps
# Should show: dyversifying_postgres   Up
```

### Step 4 — Install Python Dependencies

```powershell
# Activate the virtual environment
.\venv\Scripts\Activate.ps1

# Install all packages
pip install -r requirements.txt
```

### Step 5 — Add Your JD Files

Copy your `.docx` Job Description files into:
```
data\raw\jds\
```

Example:
```
data\raw\jds\6177-Delivery-Manager.docx
data\raw\jds\6133-Senior-Professional-Officer-Baby-Friendly-Team.docx
data\raw\jds\6152-Interim-Head-of-Finance-Business-Partnering.docx
```

### Step 6 — Add Your CV Files

Copy your CV files (`.docx` or `.pdf`) into:
```
data\raw\cvs\
```

---

## Week 2 — Data Preparation

Run these scripts **in order**:

```powershell
# Activate venv first
.\venv\Scripts\Activate.ps1

# Task 1: Parse JDs → structured JSON
python scripts/01_parse_jds.py

# Task 2: Parse CVs → structured JSON (with PII)
python scripts/02_parse_cvs.py

# Task 3: Anonymise CVs → GDPR compliant
python scripts/03_anonymise_cvs.py

# Task 4: Import to PostgreSQL + generate documentation
python scripts/04_build_dataset.py
```

**After Week 2 you'll have:**
- `data/processed/jds.json` — structured JD dataset
- `data/processed/cvs_anonymised.json` — anonymised CVs
- PostgreSQL tables populated
- `docs/dataset_documentation.md` — Week 2 deliverable

---

## Week 3 — AI Matching

```powershell
# Task 1: Generate Gemini embeddings (run after Week 2)
python scripts/05_embed_and_store.py

# Task 2: Run matching + export evaluation spreadsheet
python scripts/06_match_evaluate.py --top-n 10 --explain
```

Then:
1. Open `docs/evaluation_results.xlsx`
2. Fill in `recruiter_label` column: `0`=No, `1`=Maybe, `2`=Yes
3. Compute metrics:

```powershell
python scripts/06_match_evaluate.py --metrics-only
```

---

## Running the FastAPI Backend

```powershell
.\venv\Scripts\Activate.ps1
uvicorn backend.app.main:app --reload --port 8000
```

Then open:
- **http://localhost:8000/docs** — Interactive API documentation (Swagger UI)
- **http://localhost:8000/api/v1/health** — Health check

---

## Project Structure

```
dyversifying/
├── .env                    ← Your config (NEVER commit this)
├── .env.example            ← Template (safe to commit)
├── .gitignore
├── docker-compose.yml      ← PostgreSQL + pgvector
├── requirements.txt
├── README.md
│
├── data/
│   ├── raw/
│   │   ├── jds/            ← Put your JD .docx files here
│   │   └── cvs/            ← Put your CV files here
│   └── processed/          ← Script outputs (auto-generated)
│
├── scripts/
│   ├── 01_parse_jds.py     ← Week 2: Parse JDs
│   ├── 02_parse_cvs.py     ← Week 2: Parse CVs
│   ├── 03_anonymise_cvs.py ← Week 2: GDPR anonymisation
│   ├── 04_build_dataset.py ← Week 2: PostgreSQL import
│   ├── 05_embed_and_store.py ← Week 3: Generate embeddings
│   └── 06_match_evaluate.py  ← Week 3: Matching + evaluation
│
├── db/
│   └── schema.sql          ← PostgreSQL schema (auto-loaded by Docker)
│
├── backend/
│   └── app/
│       ├── main.py             ← FastAPI app entry point
│       ├── core/
│       │   ├── config.py       ← Settings from .env
│       │   └── database.py     ← DB connection pool
│       ├── services/
│       │   └── gemini_service.py ← Gemini AI wrapper
│       └── api/routes/
│           ├── health.py       ← GET /api/v1/health
│           ├── jds.py          ← JD endpoints
│           ├── candidates.py   ← Candidate endpoints
│           └── matching.py     ← Matching endpoint
│
└── docs/
    ├── dataset_documentation.md  ← Week 2 deliverable
    └── evaluation_results.xlsx   ← Week 3 deliverable
```

---

## GDPR Compliance

- CVs are anonymised before entering the AI pipeline (script 03)
- PII (names, emails, phones) stored only in `pii_mapping.json` (access-restricted)
- Both `cvs_raw.json` and `pii_mapping.json` are in `.gitignore`
- Never commit or share files in `data/processed/` that contain PII

---

## API Cost Estimate (Gemini)

| Task | Approximate Cost |
|------|-----------------|
| Parsing 10 JDs | ~$0.01 |
| Parsing 10 CVs | ~$0.02 |
| Embedding 100 documents | ~$0.02 |
| 20 AI explanations/day | ~$0.003/day |
| **Monthly total (moderate usage)** | **~$1–5/month** |

Free tier (1,500 requests/day) covers initial development completely.
