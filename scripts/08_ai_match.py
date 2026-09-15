"""
scripts/08_ai_match.py — 3-Stage AI-Powered Matching

WHY THIS SCRIPT?
    The old embedding-based matching (07_week4_match.py) has a fundamental
    problem: embeddings measure text similarity, but not whether a candidate
    is actually suitable for a role.

    A 'Lead Digital Designer' and a 'Delivery Manager' role share similar words
    ('digital', 'teams', 'delivering') — but a Designer is not a Delivery Manager.

    This script uses Gemini as an intelligent recruiter agent that has real
    understanding of professional roles.

THE 3-STAGE SYSTEM:

    STAGE 1: PROFESSION GATE (cheap, fast, binary)
    ───────────────────────────────────────────────
    Question: 'Is this candidate fundamentally suitable for this role?'
    Gemini checks whether the candidate's profession and career path fit.
    Output: YES/NO + Score 0-10 + 1-sentence reason

    STAGE 2: REQUIREMENTS SCORING (medium, detailed)
    ─────────────────────────────────────────────────
    Question: 'How well does the candidate meet each specific requirement?'
    Gemini scores each essential requirement from the JD individually.
    Output: Score 0-10 per requirement + evidence + gaps

    STAGE 3: DEEP AI ANALYSIS (expensive, top candidates only)
    ───────────────────────────────────────────────────────────
    Question: 'What is the full strengths/weaknesses analysis?'
    Gemini writes a structured match report with recommendation.
    Output: Report + Verdict (Strong / Possible / Weak Match)

FUNNEL EFFECT:
    160 pairs -> Stage 1 -> ~15-20 -> Stage 2 -> Top 3-5 -> Stage 3 -> Final

HOW TO RUN:
    # Standard: all JDs + CVs, all 3 stages, Top 3 for Stage 3
    python scripts/08_ai_match.py

    # Stage 1 + 2 only (skip expensive Stage 3):
    python scripts/08_ai_match.py --max-stage 2

    # Test with a single JD:
    python scripts/08_ai_match.py --jd-title "Senior Creative Producer"

    # With recruiter filters:
    python scripts/08_ai_match.py --require-rtw --min-years 4

    # Top N for Stage 3 (default: 3):
    python scripts/08_ai_match.py --top-n 5

OUTPUT:
    docs/evaluation_results_III.xlsx  — complete matching results
    PostgreSQL: ai_match_results table
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd
import concurrent.futures
import psycopg2
import psycopg2.extras

API_TIMEOUT_SECONDS = 90   # Max seconds to wait for a single Gemini API call
API_MIN_PAUSE      = 2.0  # Minimum pause between all API calls (rate limiting)
API_MAX_RETRIES    = 3    # How many times to retry a failed call
API_RETRY_DELAYS   = [5, 15, 30]  # Seconds to wait before each retry attempt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from backend.app.services.gemini_service import gemini
from backend.app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DOCS_DIR = PROJECT_ROOT / "docs"
DOCS_DIR.mkdir(parents=True, exist_ok=True)
EXCEL_OUTPUT = DOCS_DIR / "evaluation_results_III.xlsx"


# ============================================================
# ROBUST API CALL WITH RETRY + EXPONENTIAL BACKOFF
# ============================================================
#
# NOTE: What is Exponential Backoff?
# When an API call fails, we wait before retrying.
# Each attempt waits longer: 5s -> 15s -> 30s.
# Why? Because an overloaded server needs time to recover.
# If all clients retry immediately, the server gets even more overloaded.
# With backoff we give the server time to breathe.
#
# Why 90s timeout instead of 45s?
# The Gemini API can take 60-80 seconds under high load.
# 45s was too tight. 90s gives enough headroom.
#
# Why 2s pause between calls?
# Gemini Flash: ~60 requests/minute in the free tier.
# 60s / 60 requests = 1s/request minimum.
# We use 2s as a safe buffer.

def call_gemini_with_retry(
    prompt: str,
    system_instruction: str,
    temperature: float = 0.0,
    context: str = "",
) -> dict | None:
    """
    Calls gemini.generate_json() with automatic retry + exponential backoff.

    Args:
        prompt:             The prompt for the AI
        system_instruction: The system role instruction
        temperature:        Creativity level (0.0 = deterministic)
        context:            Description for log output

    Returns:
        Dict with the AI response, or None if all attempts fail
    """
    last_error = None

    for attempt in range(API_MAX_RETRIES):
        if attempt > 0:
            wait = API_RETRY_DELAYS[attempt - 1]
            logger.info(f"      ↺ Retry {attempt}/{API_MAX_RETRIES - 1} after {wait}s pause ({context})")
            time.sleep(wait)

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    gemini.generate_json,
                    prompt=prompt,
                    system_instruction=system_instruction,
                    temperature=temperature,
                )
                result = future.result(timeout=API_TIMEOUT_SECONDS)

            # Minimum pause after each successful call (rate limiting)
            time.sleep(API_MIN_PAUSE)
            return result

        except concurrent.futures.TimeoutError:
            last_error = f"Timeout after {API_TIMEOUT_SECONDS}s"
            logger.warning(f"      ⚠ {context}: {last_error} (attempt {attempt + 1})")

        except Exception as exc:
            last_error = str(exc)
            logger.warning(f"      ⚠ {context}: API error (attempt {attempt + 1}): {exc}")

    logger.error(f"      ✗ {context}: All {API_MAX_RETRIES} attempts failed. Last error: {last_error}")
    return None



# ============================================================
# STAGE 1: Profession Gate
# ============================================================
#
# NOTE: Why binary and not just a score?
# To save API costs. Stage 2 costs 3-5x more than Stage 1.
# If a candidate is clearly unsuitable (score < 5),
# it would be wasteful to analyse them further.
#
# Why both a score AND a boolean?
# The score (0-10) allows finer analysis later.
# The boolean is the hard gate value for the funnel.

STAGE1_SYSTEM = """You are an experienced UK recruiter with 15 years of expertise.
You assess whether a candidate is fundamentally suitable for a role.
Respond ONLY with valid JSON. No additional explanations outside the JSON."""

STAGE1_PROMPT = """Assess whether this candidate would be a plausible applicant for this role.

ROLE:
- Job title: {jd_title}
- Organisation: {jd_organisation}
- Sector: {jd_sector}
- Key requirements (preview): {jd_requirements_preview}

CANDIDATE:
- Current / most recent role: {cv_title}
- Years of experience: {years_experience}
- Professional profile: {career_summary}
- Sectors: {sector_experience}

QUESTION: Is this candidate's professional background relevant to this role?

Consider:
✓ Does the candidate's job title match the target profile?
✓ Is the career path logically consistent with this role?
✓ Would a recruiter even consider this CV?

IMPORTANT: Be strict. A Designer is not a Finance Officer.
A Delivery Manager leads product teams — that is not a creative role.
Only mark relevant=true if it genuinely makes sense.

Respond ONLY with this JSON format:
{{
  "relevant": true or false,
  "score": <integer 0-10: 0=completely wrong, 10=perfect fit>,
  "reason": "<max. 1 precise sentence in English>"
}}"""


def run_stage1(jd: dict, cv: dict) -> dict:
    """
    STAGE 1: Checks whether the candidate's career path fits the role.

    Args:
        jd: JD data from the DB
        cv: CV data from the DB

    Returns:
        Dict with: relevant (bool), score (int), reason (str), error (str|None)

    NOTE: Why not use embeddings here?
    Because embeddings don't understand the MEANING of professional roles.
    'Digital Designer' and 'Digital Delivery Manager' have similar embeddings
    (both 'digital', both in teams) — but completely different professions.
    Gemini understands the difference.
    """
    jd_requirements = jd.get("essential_requirements") or []
    req_preview = "; ".join(jd_requirements[:3]) if jd_requirements else "No requirements specified"

    sector_exp = cv.get("sector_experience") or []
    sector_str = ", ".join(sector_exp[:4]) if sector_exp else "not stated"

    prompt = STAGE1_PROMPT.format(
        jd_title=jd.get("title", ""),
        jd_organisation=jd.get("organisation", ""),
        jd_sector=jd.get("sector", ""),
        jd_requirements_preview=req_preview,
        cv_title=cv.get("current_title") or "Unknown",
        years_experience=cv.get("years_experience") or "unknown",
        career_summary=cv.get("career_summary") or "No profile available",
        sector_experience=sector_str,
    )

    result = call_gemini_with_retry(
        prompt=prompt,
        system_instruction=STAGE1_SYSTEM,
        temperature=0.0,
        context=f"Stage1 {cv.get('anon_ref')} -> {jd.get('title', '')[:30]}",
    )

    if result is None:
        logger.warning(f"    Stage 1 failed for {cv.get('anon_ref')} -> {jd.get('title')}")
        return {"relevant": False, "score": 0, "reason": "API error", "error": "No response"}

    return {
        "relevant": bool(result.get("relevant", False)),
        "score": int(result.get("score", 0)),
        "reason": str(result.get("reason", "")),
        "error": None,
    }


# ============================================================
# STAGE 2: Requirements Scoring
# ============================================================
#
# NOTE: Why score each requirement individually?
# Because an overall score hides important details.
# 'Score: 6/10' tells you nothing. But:
#   'Requirement 1: Agile — 8/10 (Scrum certificate)'
#   'Requirement 2: Film Production — 2/10 (photography only)'
# This shows the recruiter exactly where the strengths and weaknesses are.

STAGE2_SYSTEM = """You are an experienced UK recruiter.
Assess precisely and honestly how well a candidate meets the job requirements.
Use ONLY evidence from the candidate profile. Do not invent qualifications.
Respond ONLY with valid JSON. All text fields must be in English."""

STAGE2_PROMPT = """Assess how well this candidate meets the essential job requirements.

ROLE: {jd_title} at {jd_organisation}

ESSENTIAL REQUIREMENTS:
{requirements_numbered}

CANDIDATE PROFILE:
- Job title: {cv_title}
- Years of experience: {years_experience}
- Technical skills: {skills_technical}
- Soft skills: {skills_soft}
- Work history: {work_history_summary}
- Certifications: {certifications}
- Sector experience: {sector_experience}

Score EACH requirement from 0 to 10:
  0-3: No evidence in CV
  4-6: Partially met — some evidence, but gaps remain
  7-9: Well met — strong evidence in CV
  10: Fully met — perfect match

Respond ONLY with this JSON (all text in English):
{{
  "requirements": [
    {{
      "requirement": "<exact requirement text>",
      "score": <0-10>,
      "evidence": "<specific evidence from the CV, or 'No evidence found'>"
    }}
  ],
  "overall_score": <weighted average 0-10>,
  "met_count": <number of requirements with score >= 7>,
  "total_count": <total number of requirements>,
  "critical_gaps": ["<key missing qualification 1>", "<...>"]
}}"""


def run_stage2(jd: dict, cv: dict) -> dict:
    """
    STAGE 2: Scores each essential requirement individually.

    Only runs if stage1.relevant = True.

    Returns:
        Dict with: overall_score, met_count, total_count,
                   requirements (list), critical_gaps (list), error
    """
    requirements = jd.get("essential_requirements") or []

    if not requirements:
        # No requirements defined — use responsibilities as fallback
        requirements = (jd.get("responsibilities") or [])[:5]

    if not requirements:
        return {
            "overall_score": 0,
            "met_count": 0,
            "total_count": 0,
            "requirements": [],
            "critical_gaps": ["No requirements defined in this job description"],
            "error": "No requirements",
        }

    requirements_numbered = "\n".join(
        f"{i+1}. {req}" for i, req in enumerate(requirements[:8])  # max 8
    )

    skills_tech = cv.get("skills_technical") or []
    skills_soft = cv.get("skills_soft") or []
    certs = cv.get("certifications") or []
    sectors = cv.get("sector_experience") or []

    # Work history as short summary
    work_hist = cv.get("work_history") or []
    work_summary_parts = []
    for role in work_hist[:4]:
        if isinstance(role, dict):
            title = role.get("title", "")
            org = role.get("organisation", "")
            desc = str(role.get("description", ""))[:120]
            work_summary_parts.append(f"{title} @ {org}: {desc}")
    work_summary = " | ".join(work_summary_parts) if work_summary_parts else "No work history available"

    prompt = STAGE2_PROMPT.format(
        jd_title=jd.get("title", ""),
        jd_organisation=jd.get("organisation", ""),
        requirements_numbered=requirements_numbered,
        cv_title=cv.get("current_title") or "Unknown",
        years_experience=cv.get("years_experience") or "unknown",
        skills_technical=", ".join(skills_tech[:15]) if skills_tech else "none stated",
        skills_soft=", ".join(skills_soft[:8]) if skills_soft else "none stated",
        work_history_summary=work_summary,
        certifications=", ".join(certs[:5]) if certs else "none stated",
        sector_experience=", ".join(sectors[:5]) if sectors else "not stated",
    )

    result = call_gemini_with_retry(
        prompt=prompt,
        system_instruction=STAGE2_SYSTEM,
        temperature=0.0,
        context=f"Stage2 {cv.get('anon_ref')} -> {jd.get('title', '')[:30]}",
    )

    if result is None:
        return {
            "overall_score": 0,
            "met_count": 0,
            "total_count": len(requirements),
            "requirements": [],
            "critical_gaps": [],
            "error": "API error or timeout after retries",
        }

    return {
        "overall_score": float(result.get("overall_score", 0)),
        "met_count": int(result.get("met_count", 0)),
        "total_count": int(result.get("total_count", len(requirements))),
        "requirements": result.get("requirements", []),
        "critical_gaps": result.get("critical_gaps", []),
        "error": None,
    }


# ============================================================
# STAGE 3: Deep AI Analysis
# ============================================================
#
# NOTE: Why use the full text only now?
# Because Stage 3 is the most expensive (~1500 tokens per pair).
# Running it for all 160 pairs would be 160 x 1500 = 240,000 tokens
# — expensive and slow.
# Through the funnel, only 3-5 candidates per role reach this stage.
# This keeps costs low AND the explanations are higher quality,
# because Gemini focuses on genuinely suitable candidates.

STAGE3_SYSTEM = """You are a senior UK recruiter writing a match report for a hiring manager.
Be specific, evidence-based and honest.
No empty phrases. No inventions. Only what is stated in the CV."""

STAGE3_PROMPT = """Write a structured match report for the hiring manager.

═══ ROLE ═══
Job title: {jd_title}
Organisation: {jd_organisation} ({jd_sector})
Seniority level: {seniority_level}
Essential requirements:
{essential_requirements}
Key responsibilities:
{responsibilities}

═══ CANDIDATE ═══
Job title: {cv_title}
Years of experience: {years_experience}
Profile: {career_summary}
Skills: {all_skills}
Sectors: {sector_experience}
Work history:
{work_history}
Education: {education}

═══ STAGE 2 ANALYSIS ═══
Requirements score: {stage2_score}/10
Requirements met: {met_count}/{total_count}
Critical gaps: {critical_gaps}
Details:
{requirements_detail}

Write a professional match report in English (max. 150 words):

**Strengths** (cite specific evidence from CV):
[2-3 concrete strengths with evidence]

**Gaps** (what is missing for this specific role):
[1-3 specific gaps]

**Recommendation**:
Verdict: [Strong Match / Possible Match / Weak Match]
[1-2 sentences explaining the verdict]"""


def run_stage3(jd: dict, cv: dict, stage2_result: dict) -> dict:
    """
    STAGE 3: Full evidence-based match analysis.

    Only runs for top candidates (sorted by stage2_score).

    Returns:
        Dict with: explanation (str), verdict (str), error (str|None)
    """
    skills_tech = cv.get("skills_technical") or []
    skills_soft = cv.get("skills_soft") or []
    all_skills = (skills_tech[:12] + skills_soft[:6])

    work_hist = cv.get("work_history") or []
    work_lines = []
    for role in work_hist[:4]:
        if isinstance(role, dict):
            title = role.get("title", "")
            org = role.get("organisation", "")
            dates = f"{role.get('start_date', '')}-{role.get('end_date', '')}"
            desc = str(role.get("description", ""))[:200]
            work_lines.append(f"  * {title} @ {org} ({dates}): {desc}")
    work_str = "\n".join(work_lines) if work_lines else "  No work history available"

    edu = cv.get("education") or []
    edu_parts = []
    for e in edu[:3]:
        if isinstance(e, dict):
            edu_parts.append(f"{e.get('degree', '')} ({e.get('institution', '')})")
    edu_str = "; ".join(edu_parts) if edu_parts else "Not stated"

    req_detail_lines = []
    for r in (stage2_result.get("requirements") or [])[:8]:
        if isinstance(r, dict):
            req_detail_lines.append(
                f"  [{r.get('score', 0)}/10] {r.get('requirement', '')[:60]}: {r.get('evidence', '')[:80]}"
            )
    req_detail = "\n".join(req_detail_lines) if req_detail_lines else "  No details available"

    essential_reqs = "\n".join(
        f"  {i+1}. {r}" for i, r in enumerate((jd.get("essential_requirements") or [])[:6])
    )
    responsibilities = "\n".join(
        f"  * {r}" for r in (jd.get("responsibilities") or [])[:5]
    )
    critical_gaps = ", ".join(stage2_result.get("critical_gaps") or []) or "No critical gaps identified"

    prompt = STAGE3_PROMPT.format(
        jd_title=jd.get("title", ""),
        jd_organisation=jd.get("organisation", ""),
        jd_sector=jd.get("sector", ""),
        seniority_level=jd.get("seniority_level", "not stated"),
        essential_requirements=essential_reqs or "  None defined",
        responsibilities=responsibilities or "  None defined",
        cv_title=cv.get("current_title") or "Unknown",
        years_experience=cv.get("years_experience") or "unknown",
        career_summary=cv.get("career_summary") or "No profile available",
        all_skills=", ".join(all_skills) if all_skills else "none stated",
        sector_experience=", ".join(cv.get("sector_experience") or []) or "not stated",
        work_history=work_str,
        education=edu_str,
        stage2_score=stage2_result.get("overall_score", 0),
        met_count=stage2_result.get("met_count", 0),
        total_count=stage2_result.get("total_count", 0),
        critical_gaps=critical_gaps,
        requirements_detail=req_detail,
    )

    # Stage 3 uses generate_json with JSON schema for structured responses
    stage3_system = (
        "You are a senior UK recruiter writing a match report for a hiring manager. "
        "Be specific, evidence-based and concise. Only use information from the candidate profile. "
        "Respond ONLY with valid JSON."
    )
    stage3_json_prompt = prompt + """

Respond with ONLY this JSON (no extra text):
{
  "strengths": "<2-3 concrete strengths with evidence from CV>",
  "gaps": "<1-3 specific gaps for this role>",
  "verdict": "<exactly one of: Strong Match, Possible Match, Weak Match>",
  "recommendation": "<1-2 sentences explaining the verdict>"
}"""

    result = call_gemini_with_retry(
        prompt=stage3_json_prompt,
        system_instruction=stage3_system,
        temperature=0.1,
        context=f"Stage3 {cv.get('anon_ref', '?')} -> {jd.get('title', '')[:30]}",
    )

    if result is None:
        return {"explanation": "(API error after retries)", "verdict": "Unknown", "error": "No response"}

    verdict = result.get("verdict", "Possible Match")
    verdict_lower = verdict.lower()
    if "strong" in verdict_lower:
        verdict = "Strong Match"
    elif "weak" in verdict_lower:
        verdict = "Weak Match"
    else:
        verdict = "Possible Match"

    explanation = (
        f"**Strengths**: {result.get('strengths', '')}\n\n"
        f"**Gaps**: {result.get('gaps', '')}\n\n"
        f"**Recommendation**: {result.get('recommendation', '')}"
    )

    return {"explanation": explanation, "verdict": verdict, "error": None}


# ============================================================
# Database functions
# ============================================================

def get_connection():
    db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    return conn


def fetch_all_jds(conn, title_filter: str = None) -> list:
    """Load JDs — optionally filter by title keyword."""
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if title_filter:
        cursor.execute("""
            SELECT jd_id, title, organisation, sector, seniority_level,
                   essential_requirements, desirable_requirements,
                   responsibilities, skills_technical, skills_soft,
                   profession_domain, min_years_experience
            FROM job_descriptions
            WHERE LOWER(title) LIKE %s
            ORDER BY title
        """, (f"%{title_filter.lower()}%",))
    else:
        cursor.execute("""
            SELECT jd_id, title, organisation, sector, seniority_level,
                   essential_requirements, desirable_requirements,
                   responsibilities, skills_technical, skills_soft,
                   profession_domain, min_years_experience
            FROM job_descriptions
            ORDER BY title
        """)

    rows = cursor.fetchall()
    cursor.close()
    return [dict(r) for r in rows]


def fetch_all_cvs(conn, skip_empty: bool = True) -> list:
    """Load CVs — optionally skip empty CVs (scanned image PDFs)."""
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("""
        SELECT cv_id, anon_ref, current_title, years_experience,
               skills_technical, skills_soft, education,
               work_history, certifications, languages,
               right_to_work_uk, sector_experience,
               profession_domain, career_summary,
               raw_text_anon, embedding_text
        FROM candidates
        ORDER BY anon_ref
    """)
    rows = cursor.fetchall()
    cursor.close()

    result = []
    for row in rows:
        cv = dict(row)
        # Skip empty CVs (scanned PDFs without text)
        if skip_empty:
            has_data = (
                cv.get("current_title") or
                cv.get("career_summary") or
                cv.get("embedding_text") or
                (cv.get("skills_technical") and len(cv["skills_technical"]) > 0)
            )
            if not has_data:
                logger.info(f"  ⏭ {cv.get('anon_ref')} skipped (empty CV — scanned PDF)")
                continue
        result.append(cv)
    return result


def save_ai_match(conn, match: dict):
    """Save a match result to ai_match_results (upsert)."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ai_match_results (
            jd_id, cv_id,
            stage1_passed, stage1_score, stage1_reason,
            stage2_score, stage2_met_count, stage2_total_count,
            stage2_breakdown, stage2_critical_gaps,
            stage3_explanation, stage3_verdict,
            final_score, final_rank
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (jd_id, cv_id) DO UPDATE SET
            stage1_passed    = EXCLUDED.stage1_passed,
            stage1_score     = EXCLUDED.stage1_score,
            stage1_reason    = EXCLUDED.stage1_reason,
            stage2_score     = EXCLUDED.stage2_score,
            stage2_met_count = EXCLUDED.stage2_met_count,
            stage2_total_count = EXCLUDED.stage2_total_count,
            stage2_breakdown = EXCLUDED.stage2_breakdown,
            stage2_critical_gaps = EXCLUDED.stage2_critical_gaps,
            stage3_explanation = EXCLUDED.stage3_explanation,
            stage3_verdict   = EXCLUDED.stage3_verdict,
            final_score      = EXCLUDED.final_score,
            final_rank       = EXCLUDED.final_rank,
            created_at       = NOW()
    """, (
        match["jd_id"], match["cv_id"],
        match.get("stage1_passed"), match.get("stage1_score"), match.get("stage1_reason"),
        match.get("stage2_score"), match.get("stage2_met_count"), match.get("stage2_total_count"),
        json.dumps(match.get("stage2_breakdown") or []),
        json.dumps(match.get("stage2_critical_gaps") or []),
        match.get("stage3_explanation"), match.get("stage3_verdict"),
        match.get("final_score"), match.get("final_rank"),
    ))
    conn.commit()
    cursor.close()


# ============================================================
# Final score calculation
# ============================================================

def compute_final_score(s1_score: float, s2_score: float, s3_verdict: str = None) -> float:
    """
    Weighted composite score from all 3 stages.

    Weights:
      30% Stage 1 — basic professional relevance (important, but coarse)
      55% Stage 2 — requirements fulfilment (most important factor!)
      15% Stage 3 — deep analysis / verdict

    Stage 3 is optional (top candidates only).
    If not available: weights are 35/65 (Stage 1/2).

    NOTE: Why 55% for Stage 2?
    Because the requirements are THE most important factor. A candidate
    can have the right profession (Stage 1 high) but lack the specific
    qualifications (Stage 2 low) — in that case they are not suitable.
    """
    s3_map = {"Strong Match": 10.0, "Possible Match": 6.0, "Weak Match": 2.0}

    if s3_verdict and s3_verdict in s3_map:
        s3_val = s3_map[s3_verdict]
        return round(0.30 * s1_score + 0.55 * s2_score + 0.15 * s3_val, 3)
    else:
        # Nur Stage 1 + 2
        return round(0.35 * s1_score + 0.65 * s2_score, 3)


# ============================================================
# Hard filters (in addition to the 3 AI stages)
# ============================================================

def apply_hard_filter(cv: dict, require_rtw: bool, min_years: int) -> tuple:
    """
    Binary hard filters ADDITIONAL to AI matching.
    These are not AI-based — they are simple rules.

    Returns (passed: bool, reason: str).
    """
    # Right to Work filter
    if require_rtw and cv.get("right_to_work_uk") is False:
        return False, "No UK Right to Work"

    # Minimum experience
    if min_years and min_years > 0:
        cv_years = cv.get("years_experience")
        if cv_years is not None and int(cv_years) < min_years:
            return False, f"Insufficient experience: {cv_years} years (minimum: {min_years})"

    return True, ""


# ============================================================
# Excel export (legacy — used when running 08 directly)
# ============================================================

def export_to_excel(all_results: list):
    """
    Exports all results to docs/evaluation_results_III.xlsx.

    Structure:
    - One sheet per JD (candidates sorted by final_rank)
    - An 'All Results' overview sheet
    - A 'Guide' sheet

    NOTE: For the fully-styled English export, use 11_export_results_en.py instead.
    """
    if not all_results:
        logger.warning("No results to export")
        return

    with pd.ExcelWriter(EXCEL_OUTPUT, engine="openpyxl") as writer:

        all_rows = []

        # Group by JD
        jds_seen = {}
        for m in all_results:
            jt = m.get("jd_title", "Unknown")
            if jt not in jds_seen:
                jds_seen[jt] = []
            jds_seen[jt].append(m)

        for jd_title, matches in jds_seen.items():
            # Sort: Stage 1 passed first, then by final_score descending
            matches_sorted = sorted(
                matches,
                key=lambda x: (
                    not x.get("stage1_passed", False),
                    -(x.get("final_score") or 0),
                ),
            )

            rows = []
            for rank, m in enumerate(matches_sorted, start=1):
                s2_reqs = m.get("stage2_breakdown") or []
                s2_detail = "\n".join(
                    f"[{r.get('score',0)}/10] {r.get('requirement','')[:50]}: {r.get('evidence','')[:60]}"
                    for r in s2_reqs[:5] if isinstance(r, dict)
                ) if s2_reqs else ""

                row = {
                    # -- Rank & Score --
                    "final_rank":         rank,
                    "final_score":        m.get("final_score"),

                    # -- Job --
                    "jd_title":           m.get("jd_title"),
                    "jd_organisation":    m.get("jd_organisation"),

                    # -- Candidate --
                    "anon_ref":           m.get("anon_ref"),
                    "cv_title":           m.get("cv_title"),
                    "career_summary":     m.get("career_summary"),
                    "years_experience":   m.get("years_experience"),
                    "right_to_work_uk":   m.get("right_to_work_uk"),

                    # -- Stage 1: Profession Gate --
                    "stage1_passed":      "YES" if m.get("stage1_passed") else "NO",
                    "stage1_score":       m.get("stage1_score"),
                    "stage1_reason":      m.get("stage1_reason"),

                    # -- Stage 2: Requirements --
                    "stage2_score":       m.get("stage2_score"),
                    "stage2_met":         f"{m.get('stage2_met_count', 0)}/{m.get('stage2_total_count', 0)} requirements",
                    "stage2_gaps":        ", ".join(m.get("stage2_critical_gaps") or []),
                    "stage2_details":     s2_detail,

                    # -- Stage 3: Deep Analysis --
                    "stage3_verdict":     m.get("stage3_verdict") or "not analysed — not in Top 3",
                    "stage3_report":      m.get("stage3_explanation") or "not analysed",

                    # -- Recruiter to fill in --
                    "recruiter_decision": None,   # 0=No | 1=Possible | 2=Good match
                    "recruiter_notes":    None,
                }
                rows.append(row)
                all_rows.append(row)

            # Sheet name: max 31 chars (Excel limit)
            sheet_name = jd_title[:28] + "..." if len(jd_title) > 31 else jd_title
            df = pd.DataFrame(rows)
            df.to_excel(writer, index=False, sheet_name=sheet_name)

            # Column widths
            ws = writer.sheets[sheet_name]
            col_widths = {
                "A": 8, "B": 10, "C": 30, "D": 20, "E": 10, "F": 25,
                "G": 50, "H": 8, "I": 10, "J": 8, "K": 8, "L": 50,
                "M": 8, "N": 20, "O": 40, "P": 60, "Q": 15, "R": 80, "S": 12, "T": 30,
            }
            for col_letter, width in col_widths.items():
                ws.column_dimensions[col_letter].width = width

        # All Results overview sheet
        if all_rows:
            df_all = pd.DataFrame(all_rows)
            df_all = df_all.sort_values(["jd_title", "final_rank"])
            df_all.to_excel(writer, index=False, sheet_name="All Results")

        # Guide sheet
        pd.DataFrame({
            "Column": [
                "final_rank", "final_score",
                "stage1_passed", "stage1_score",
                "stage2_score", "stage2_met", "stage2_gaps",
                "stage3_verdict", "stage3_report",
                "recruiter_decision",
            ],
            "Description": [
                "Overall rank (1 = best candidate for this role)",
                "Weighted score: 35% profession relevance + 65% requirements (0-10)",
                "YES = profession fits | NO = wrong profession",
                "0-10: How well does the career path fit? (0=wrong, 10=perfect)",
                "0-10: How many requirements met? (Most important value!)",
                "e.g. '3/5 requirements' met (score >= 7)",
                "Missing key qualifications",
                "Strong Match / Possible Match / Weak Match (top candidates only)",
                "Full AI match report (top candidates only)",
                "0=No match | 1=Possible | 2=Good match — TO BE FILLED IN BY RECRUITER",
            ],
        }).to_excel(writer, index=False, sheet_name="Guide")

    logger.info(f"Exported to: {EXCEL_OUTPUT}")


# ============================================================
# Main matching function
# ============================================================

def match_jd_to_cvs(
    jd: dict,
    cvs: list,
    max_stage: int = 3,
    top_n_stage3: int = 3,
    require_rtw: bool = False,
    min_years: int = None,
) -> list:
    """
    Runs the 3-stage matching for one JD against all CVs.

    Args:
        jd:           JD dict from the DB
        cvs:          List of all CV dicts
        max_stage:    Up to which stage to analyse (1, 2 or 3)
        top_n_stage3: How many top candidates to analyse in Stage 3
        require_rtw:  Only candidates with UK Right to Work
        min_years:    Minimum years of experience (recruiter filter)

    Returns:
        List of match dicts, sorted by final_score (descending)
    """
    jd_title = jd.get("title", "?")
    jd_id    = jd["jd_id"]
    logger.info(f"\n{'─' * 55}")
    logger.info(f"JD: '{jd_title}' | {len(cvs)} candidates")

    results = []

    # -- Stage 1 for all CVs --
    logger.info(f"  STAGE 1: Profession Gate...")
    stage1_passed = []

    for cv in cvs:
        anon = cv.get("anon_ref", "?")

        # Hard filter first (no API cost)
        hard_ok, hard_reason = apply_hard_filter(cv, require_rtw, min_years)

        s1 = run_stage1(jd, cv)
        time.sleep(0.3)   # Rate limiting

        match = {
            "jd_id":           jd_id,
            "cv_id":           cv["cv_id"],
            "jd_title":        jd_title,
            "jd_organisation": jd.get("organisation"),
            "anon_ref":        anon,
            "cv_title":        cv.get("current_title"),
            "career_summary":  cv.get("career_summary"),
            "years_experience": cv.get("years_experience"),
            "right_to_work_uk": cv.get("right_to_work_uk"),
            "hard_filter_passed": hard_ok,
            "hard_filter_reason": hard_reason,
            # Stage 1
            "stage1_passed":   s1["relevant"] and hard_ok,
            "stage1_score":    s1["score"],
            "stage1_reason":   s1["reason"],
            # Stage 2+3 not yet filled
            "stage2_score":    None,
            "stage2_met_count": None,
            "stage2_total_count": None,
            "stage2_breakdown": [],
            "stage2_critical_gaps": [],
            "stage3_explanation": None,
            "stage3_verdict":  None,
            "final_score":     s1["score"] / 10 * 3.5,  # Preliminary Stage 1 only
            "final_rank":      None,
        }

        icon = "✓" if s1["relevant"] else "✗"
        rtw_note = " [Hard-Filter ✗]" if not hard_ok else ""
        title_short = (cv.get("current_title") or "?")[:30]
        reason_short = (s1.get("reason") or "")[:80]
        logger.info(
            f"    {icon} {anon} ({title_short})"
            f"  score={s1['score']}/10{rtw_note}"
        )
        logger.info(f"      -> {reason_short}")

        results.append(match)

        if s1["relevant"] and hard_ok:
            stage1_passed.append((match, cv))

    logger.info(f"  Stage 1: {len(stage1_passed)}/{len(cvs)} passed")

    if max_stage < 2 or not stage1_passed:
        return results

    # -- Stage 2 for all Stage 1 passers --
    logger.info(f"  STAGE 2: Requirements Scoring ({len(stage1_passed)} candidates)...")

    for match, cv in stage1_passed:
        s2 = run_stage2(jd, cv)
        time.sleep(0.4)

        match["stage2_score"]         = s2["overall_score"]
        match["stage2_met_count"]     = s2["met_count"]
        match["stage2_total_count"]   = s2["total_count"]
        match["stage2_breakdown"]     = s2["requirements"]
        match["stage2_critical_gaps"] = s2["critical_gaps"]

        # Preliminary final_score (without Stage 3)
        match["final_score"] = compute_final_score(
            s1_score=match["stage1_score"],
            s2_score=s2["overall_score"],
        )

        logger.info(
            f"    {match['anon_ref']}: "
            f"score={s2['overall_score']:.1f}/10  "
            f"met={s2['met_count']}/{s2['total_count']}  "
            f"-> final={match['final_score']:.2f}"
        )

    if max_stage < 3:
        return results

    # -- Stage 3: Top N by Stage 2 score --
    stage2_sorted = sorted(
        [(m, cv) for (m, cv) in stage1_passed if m["stage2_score"] is not None],
        key=lambda x: x[0]["stage2_score"],
        reverse=True,
    )
    top_candidates = stage2_sorted[:top_n_stage3]

    logger.info(f"  STAGE 3: Deep Analysis for Top {len(top_candidates)} candidates...")

    for match, cv in top_candidates:
        s2_result = {
            "overall_score": match["stage2_score"],
            "met_count":     match["stage2_met_count"],
            "total_count":   match["stage2_total_count"],
            "requirements":  match["stage2_breakdown"],
            "critical_gaps": match["stage2_critical_gaps"],
        }
        s3 = run_stage3(jd, cv, s2_result)
        time.sleep(0.5)

        match["stage3_explanation"] = s3["explanation"]
        match["stage3_verdict"]     = s3["verdict"]

        # Finaler Score mit Stage 3
        match["final_score"] = compute_final_score(
            s1_score=match["stage1_score"],
            s2_score=match["stage2_score"],
            s3_verdict=s3["verdict"],
        )

        logger.info(
            f"    {match['anon_ref']}: "
            f"Verdict={s3['verdict']}  "
            f"-> final={match['final_score']:.2f}"
        )

    # -- Calculate final ranking --
    results_sorted = sorted(results, key=lambda x: (
        not x.get("stage1_passed", False),
        -(x.get("final_score") or 0),
    ))
    for rank, m in enumerate(results_sorted, start=1):
        m["final_rank"] = rank

    top_final = [m for m in results_sorted if m.get("stage1_passed")]
    if top_final:
        logger.info(
            f"\n  TOP MATCH: {top_final[0]['anon_ref']} "
            f"({top_final[0].get('cv_title', '?')}) "
            f"| Score: {top_final[0]['final_score']:.2f} "
            f"| Verdict: {top_final[0].get('stage3_verdict', 'n/a')}"
        )

    return results


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="08_ai_match.py — 3-stage AI-powered candidate matching"
    )
    parser.add_argument("--max-stage",    type=int, default=3, choices=[1, 2, 3],
                        help="Maximum stage to run (default: 3)")
    parser.add_argument("--top-n",        type=int, default=3,
                        help="Top N candidates for Stage 3 deep analysis (default: 3)")
    parser.add_argument("--jd-title",     type=str, default=None,
                        help="Only process JDs whose title contains this keyword")
    parser.add_argument("--require-rtw",  action="store_true", default=False,
                        help="Only candidates with UK Right to Work")
    parser.add_argument("--min-years",    type=int, default=None,
                        help="Minimum years of experience")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("3-Stage AI Matching — Diversifying.io")
    logger.info("=" * 60)
    logger.info(f"  Max stage:       {args.max_stage}")
    logger.info(f"  Top N (Stage 3): {args.top_n}")
    if args.jd_title:
        logger.info(f"  JD filter:       title contains '{args.jd_title}'")
    if args.require_rtw:
        logger.info(f"  Filter:          UK Right to Work only")
    if args.min_years:
        logger.info(f"  Filter:          Min. {args.min_years} years experience")

    conn = get_connection()
    try:
        jds = fetch_all_jds(conn, title_filter=args.jd_title)
        cvs = fetch_all_cvs(conn, skip_empty=True)

        logger.info(f"\nLoaded: {len(jds)} JD(s) | {len(cvs)} CV(s) (empty skipped)")

        if not jds or not cvs:
            logger.error("No data found. Please run scripts 01-05 first.")
            sys.exit(1)

        all_results = []

        for jd in jds:
            jd_results = match_jd_to_cvs(
                jd=jd,
                cvs=cvs,
                max_stage=args.max_stage,
                top_n_stage3=args.top_n,
                require_rtw=args.require_rtw,
                min_years=args.min_years,
            )

            # Save to DB
            for m in jd_results:
                save_ai_match(conn, m)

            all_results.extend(jd_results)

        # Export to Excel
        logger.info(f"\n{'=' * 60}")
        logger.info("Exporting...")
        export_to_excel(all_results)

        # Summary
        total_pairs  = len(all_results)
        s1_passed    = sum(1 for m in all_results if m.get("stage1_passed"))
        s3_done      = sum(1 for m in all_results if m.get("stage3_verdict"))
        strong       = sum(1 for m in all_results if m.get("stage3_verdict") == "Strong Match")
        possible     = sum(1 for m in all_results if m.get("stage3_verdict") == "Possible Match")

        logger.info(f"{'=' * 60}")
        logger.info("SUMMARY")
        logger.info(f"{'=' * 60}")
        logger.info(f"  Total pairs analysed:  {total_pairs}")
        logger.info(f"  Stage 1 passed:        {s1_passed}/{total_pairs} pairs")
        logger.info(f"  Stage 3 (Deep):        {s3_done} candidates")
        logger.info(f"  -> Strong Match:       {strong}")
        logger.info(f"  -> Possible Match:     {possible}")
        logger.info(f"\n  Output: {EXCEL_OUTPUT}")
        logger.info("\nNEXT STEPS:")
        logger.info("  1. Run: python scripts/11_export_results_en.py")
        logger.info("  2. Open docs/evaluation_results_EN.xlsx")
        logger.info("  3. Fill in 'recruiter_decision' column (0/1/2)")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
