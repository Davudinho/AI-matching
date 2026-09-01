"""
scripts/08_ai_match.py — 3-stufiges KI-gestütztes Matching

WARUM DIESES SKRIPT?
    Das alte Embedding-basierte Matching (07_week4_match.py) hat ein
    fundamentales Problem: Embeddings messen Textähnlichkeit, aber nicht
    ob ein Kandidat für eine Stelle geeignet ist.

    Ein "Lead Digital Designer" und eine "Delivery Manager"-Stelle haben
    ähnliche Wörter ("digital", "teams", "delivering") — aber ein Designer
    ist kein Delivery Manager.

    Dieses Skript verwendet Gemini als intelligenten Recruiter-Agenten,
    der echtes Verständnis von Berufsrollen hat.

DAS 3-STUFIGE SYSTEM:

    STUFE 1: BERUFS-GATE (billig, schnell, binär)
    ─────────────────────────────────────────────
    Frage: "Ist dieser Kandidat grundsätzlich für diese Stelle geeignet?"
    Gemini prüft ob Berufsbild und Karriereweg zur Stelle passen.
    Output: JA/NEIN + Score 0-10 + 1-Satz-Begründung

    STUFE 2: ANFORDERUNGS-SCORING (mittel, detailliert)
    ────────────────────────────────────────────────────
    Frage: "Wie gut erfüllt der Kandidat jede konkrete Anforderung?"
    Gemini bewertet jede essentielle Anforderung aus dem JD einzeln.
    Output: Score 0-10 pro Anforderung + Belege + Lücken

    STUFE 3: TIEFE KI-ANALYSE (teuer, nur für Top-Kandidaten)
    ──────────────────────────────────────────────────────────
    Frage: "Was ist die vollständige Stärken/Schwächen-Analyse?"
    Gemini schreibt einen strukturierten Match-Report mit Empfehlung.
    Output: Report + Verdict (Strong / Possible / Weak Match)

FUNNEL-EFFEKT:
    72 Paare → Stufe 1 → ~15-20 → Stufe 2 → Top 5 → Stufe 3 → Final

HOW TO RUN:
    # Standard: alle JDs + CVs, alle 3 Stufen, Top 3 für Stufe 3
    python scripts/08_ai_match.py

    # Nur Stufe 1 + 2 (kein teures Stufe-3):
    python scripts/08_ai_match.py --max-stage 2

    # Test mit einer einzigen JD:
    python scripts/08_ai_match.py --jd-title "Senior Creative Producer"

    # Mit Recruiter-Filtern:
    python scripts/08_ai_match.py --require-rtw --min-years 4

    # Top N für Stufe 3 (default: 3):
    python scripts/08_ai_match.py --top-n 5

OUTPUT:
    docs/evaluation_results_III.xlsx  — vollständiges Matching-Ergebnis
    PostgreSQL: ai_match_results Tabelle
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
# ROBUSTER API-AUFRUF MIT RETRY + EXPONENTIAL BACKOFF
# ============================================================
#
# LERNPUNKT: Was ist Exponential Backoff?
# Bei einem API-Fehler warten wir, bevor wir es erneut versuchen.
# Jeder Versuch wartet länger: 5s → 15s → 30s.
# Warum? Weil ein überlasteter Server Zeit braucht um sich zu erholen.
# Wenn alle Clients sofort wiederholen, wird der Server noch überlasteter.
# Mit Backoff geben wir dem Server Zeit zu atmen.
#
# Warum 90s Timeout statt 45s?
# Die Gemini API kann bei hoher Last 60-80 Sekunden brauchen.
# 45s war zu knapp. 90s gibt genügend Spielraum.
#
# Warum 2s Pause zwischen Calls?
# Gemini Flash: ~60 Requests/Minute im Free Tier.
# 60s / 60 Requests = 1s/Request als Minimum.
# Wir nutzen 2s als sicheren Puffer.

def call_gemini_with_retry(
    prompt: str,
    system_instruction: str,
    temperature: float = 0.0,
    context: str = "",
) -> dict | None:
    """
    Ruft gemini.generate_json() mit automatischem Retry + Backoff auf.

    Args:
        prompt:             Der Prompt für die KI
        system_instruction: Die Systemrolle
        temperature:        Kreativität (0.0 = deterministisch)
        context:            Beschreibung für Log-Ausgaben

    Returns:
        Dict mit der KI-Antwort, oder None wenn alle Versuche scheitern
    """
    last_error = None

    for attempt in range(API_MAX_RETRIES):
        if attempt > 0:
            wait = API_RETRY_DELAYS[attempt - 1]
            logger.info(f"      ↺ Retry {attempt}/{API_MAX_RETRIES - 1} nach {wait}s Pause ({context})")
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

            # Mindestpause nach jedem erfolgreichen Call (Rate Limiting)
            time.sleep(API_MIN_PAUSE)
            return result

        except concurrent.futures.TimeoutError:
            last_error = f"Timeout nach {API_TIMEOUT_SECONDS}s"
            logger.warning(f"      ⚠ {context}: {last_error} (Versuch {attempt + 1})")

        except Exception as exc:
            last_error = str(exc)
            logger.warning(f"      ⚠ {context}: API-Fehler (Versuch {attempt + 1}): {exc}")

    logger.error(f"      ✗ {context}: Alle {API_MAX_RETRIES} Versuche fehlgeschlagen. Letzter Fehler: {last_error}")
    return None



# ============================================================
# STUFE 1: Berufs-Gate
# ============================================================
#
# LERNPUNKT: Warum binär und nicht nur ein Score?
# Weil wir API-Kosten sparen wollen. Stufe 2 kostet 3-5× mehr
# als Stufe 1. Wenn ein Kandidat klar ungeeignet ist (Score < 5),
# wäre es Geldverschwendung ihn weiter zu analysieren.
#
# Warum Score UND boolean?
# Der Score (0-10) erlaubt uns später feinere Analysen.
# Der boolean ist der harte Gate-Wert für den Funnel.

STAGE1_SYSTEM = """Du bist ein erfahrener UK-Recruiter mit 15 Jahren Erfahrung.
Du bewertest ob ein Kandidat grundsätzlich für eine Stelle geeignet ist.
Antworte NUR mit validem JSON. Keine zusätzlichen Erklärungen außerhalb des JSON."""

STAGE1_PROMPT = """Beurteile ob dieser Kandidat ein plausibler Bewerber für diese Stelle wäre.

STELLE:
- Jobtitel: {jd_title}
- Organisation: {jd_organisation}
- Bereich: {jd_sector}
- Kurzbeschreibung (erste Anforderungen): {jd_requirements_preview}

KANDIDAT:
- Aktuelle/Letzte Stelle: {cv_title}
- Berufserfahrung: {years_experience} Jahre
- Berufliches Profil: {career_summary}
- Sektoren: {sector_experience}

FRAGE: Ist der Berufsweg dieses Kandidaten relevant für diese Stelle?

Berücksichtige:
✓ Passt der Berufstitel des Kandidaten zum gesuchten Profil?
✓ Ist der Karriereweg zur Stelle logisch und plausibel?
✓ Würde ein Recruiter diesen CV auch nur in Betracht ziehen?

WICHTIG: Sei streng. Ein Designer ist kein Finance Officer. 
Ein Delivery Manager leitet Produktteams — das ist kein kreativer Beruf.
Nur wenn es wirklich Sinn ergibt: relevant=true.

Antworte NUR mit diesem JSON-Format:
{{
  "relevant": true oder false,
  "score": <Ganzzahl 0-10: 0=völlig falsch, 10=perfekt passend>,
  "reason": "<max. 1 präziser Satz auf Englisch>"
}}"""


def run_stage1(jd: dict, cv: dict) -> dict:
    """
    STUFE 1: Prüft ob der Berufsweg des Kandidaten zur Stelle passt.

    Args:
        jd: JD-Daten aus der DB
        cv: CV-Daten aus der DB

    Returns:
        Dict mit: relevant (bool), score (int), reason (str), error (str|None)

    LERNPUNKT: Warum kein Embedding hier?
    Weil Embeddings den SINN von Berufsrollen nicht verstehen.
    "Digital Designer" und "Digital Delivery Manager" haben ähnliche
    Embeddings (beide "digital", beide in Teams) — aber völlig verschiedene
    Berufe. Gemini versteht den Unterschied.
    """
    jd_requirements = jd.get("essential_requirements") or []
    req_preview = "; ".join(jd_requirements[:3]) if jd_requirements else "Keine spezifizierten Anforderungen"

    sector_exp = cv.get("sector_experience") or []
    sector_str = ", ".join(sector_exp[:4]) if sector_exp else "nicht angegeben"

    prompt = STAGE1_PROMPT.format(
        jd_title=jd.get("title", ""),
        jd_organisation=jd.get("organisation", ""),
        jd_sector=jd.get("sector", ""),
        jd_requirements_preview=req_preview,
        cv_title=cv.get("current_title") or "Unbekannt",
        years_experience=cv.get("years_experience") or "unbekannt",
        career_summary=cv.get("career_summary") or "Kein Profil verfügbar",
        sector_experience=sector_str,
    )

    result = call_gemini_with_retry(
        prompt=prompt,
        system_instruction=STAGE1_SYSTEM,
        temperature=0.0,
        context=f"Stufe1 {cv.get('anon_ref')} → {jd.get('title', '')[:30]}",
    )

    if result is None:
        logger.warning(f"    Stufe 1 fehlgeschlagen für {cv.get('anon_ref')} → {jd.get('title')}")
        return {"relevant": False, "score": 0, "reason": "API error", "error": "No response"}

    return {
        "relevant": bool(result.get("relevant", False)),
        "score": int(result.get("score", 0)),
        "reason": str(result.get("reason", "")),
        "error": None,
    }


# ============================================================
# STUFE 2: Anforderungs-Scoring
# ============================================================
#
# LERNPUNKT: Warum jede Anforderung einzeln bewerten?
# Weil ein Gesamt-Score wichtige Details versteckt.
# "Score: 6/10" sagt nichts aus. Aber:
#   "Anforderung 1: Agile — 8/10 (Scrum-Zertifikat)"
#   "Anforderung 2: Film Production — 2/10 (nur Foto)"
# Das zeigt dem Recruiter genau wo die Stärken und Schwächen liegen.

STAGE2_SYSTEM = """Du bist ein erfahrener UK-Recruiter.
Bewerte präzise und ehrlich wie gut ein Kandidat die Stellenanforderungen erfüllt.
Nutze NUR Belege aus dem Kandidatenprofil. Erfinde keine Qualifikationen.
Antworte NUR mit validem JSON."""

STAGE2_PROMPT = """Bewerte wie gut dieser Kandidat die essentiellen Stellenanforderungen erfüllt.

STELLE: {jd_title} bei {jd_organisation}

ESSENTIELLE ANFORDERUNGEN:
{requirements_numbered}

KANDIDATENPROFIL:
- Jobtitel: {cv_title}
- Berufsjahre: {years_experience}
- Skills (technisch): {skills_technical}
- Skills (soft): {skills_soft}
- Berufsverlauf: {work_history_summary}
- Zertifikate: {certifications}
- Sektor-Erfahrung: {sector_experience}

Bewerte JEDE Anforderung mit einem Score 0-10:
  0-3: Kein Beleg im CV vorhanden
  4-6: Teilweise erfüllt — Belege vorhanden, aber Lücken
  7-9: Gut erfüllt — starke Belege im CV
  10: Vollständig erfüllt — perfekte Übereinstimmung

Antworte NUR mit diesem JSON:
{{
  "requirements": [
    {{
      "requirement": "<exakter Anforderungstext>",
      "score": <0-10>,
      "evidence": "<konkreter Beleg aus dem CV, oder 'Kein Beleg gefunden'>"
    }}
  ],
  "overall_score": <gewichteter Durchschnitt 0-10>,
  "met_count": <Anzahl Anforderungen mit Score >= 7>,
  "total_count": <Gesamtzahl der Anforderungen>,
  "critical_gaps": ["<wichtige fehlende Qualifikation 1>", "<...>"]
}}"""


def run_stage2(jd: dict, cv: dict) -> dict:
    """
    STUFE 2: Bewertet jede essentielle Anforderung einzeln.

    Läuft nur wenn stage1.relevant = True.

    Returns:
        Dict mit: overall_score, met_count, total_count,
                  requirements (list), critical_gaps (list), error
    """
    requirements = jd.get("essential_requirements") or []

    if not requirements:
        # Keine Anforderungen definiert — nutze Responsibilities als Fallback
        requirements = (jd.get("responsibilities") or [])[:5]

    if not requirements:
        return {
            "overall_score": 0,
            "met_count": 0,
            "total_count": 0,
            "requirements": [],
            "critical_gaps": ["Keine Anforderungen in der Stelle definiert"],
            "error": "No requirements",
        }

    requirements_numbered = "\n".join(
        f"{i+1}. {req}" for i, req in enumerate(requirements[:8])  # max 8
    )

    skills_tech = cv.get("skills_technical") or []
    skills_soft = cv.get("skills_soft") or []
    certs = cv.get("certifications") or []
    sectors = cv.get("sector_experience") or []

    # Berufsverlauf als kurze Zusammenfassung
    work_hist = cv.get("work_history") or []
    work_summary_parts = []
    for role in work_hist[:4]:
        if isinstance(role, dict):
            title = role.get("title", "")
            org = role.get("organisation", "")
            desc = str(role.get("description", ""))[:120]
            work_summary_parts.append(f"{title} @ {org}: {desc}")
    work_summary = " | ".join(work_summary_parts) if work_summary_parts else "Kein Berufsverlauf"

    prompt = STAGE2_PROMPT.format(
        jd_title=jd.get("title", ""),
        jd_organisation=jd.get("organisation", ""),
        requirements_numbered=requirements_numbered,
        cv_title=cv.get("current_title") or "Unbekannt",
        years_experience=cv.get("years_experience") or "unbekannt",
        skills_technical=", ".join(skills_tech[:15]) if skills_tech else "keine angegeben",
        skills_soft=", ".join(skills_soft[:8]) if skills_soft else "keine angegeben",
        work_history_summary=work_summary,
        certifications=", ".join(certs[:5]) if certs else "keine angegeben",
        sector_experience=", ".join(sectors[:5]) if sectors else "nicht angegeben",
    )

    result = call_gemini_with_retry(
        prompt=prompt,
        system_instruction=STAGE2_SYSTEM,
        temperature=0.0,
        context=f"Stufe2 {cv.get('anon_ref')} → {jd.get('title', '')[:30]}",
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
# STUFE 3: Tiefe KI-Analyse
# ============================================================
#
# LERNPUNKT: Warum erst jetzt den vollen Text verwenden?
# Weil Stufe 3 die teuerste ist (~1500 Tokens pro Paar).
# Wenn wir sie für alle 72 Paare laufen lassen würden, wäre das
# 72 × 1500 = 108.000 Tokens — teuer und langsam.
# Durch den Funnel laufen hier nur noch 3-5 Kandidaten pro Stelle.
# Das macht es kostengünstig UND die Erklärungen sind hochwertiger,
# weil Gemini sich auf echte Kandidaten konzentriert.

STAGE3_SYSTEM = """Du bist ein erfahrener UK-Recruiter der einen Match-Report
für den Hiring Manager erstellt. Sei konkret, evidenz-basiert und ehrlich.
Keine leeren Phrasen. Keine Erfindungen. Nur was im CV steht."""

STAGE3_PROMPT = """Erstelle einen strukturierten Match-Report für den Hiring Manager.

═══ STELLE ═══
Jobtitel: {jd_title}
Organisation: {jd_organisation} ({jd_sector})
Senioritätslevel: {seniority_level}
Essentiell:
{essential_requirements}
Aufgaben:
{responsibilities}

═══ KANDIDAT ═══
Jobtitel: {cv_title}
Berufsjahre: {years_experience}
Profil: {career_summary}
Skills: {all_skills}
Sektoren: {sector_experience}
Berufsverlauf:
{work_history}
Ausbildung: {education}

═══ STUFE-2-ANALYSE ═══
Anforderungs-Score: {stage2_score}/10
Erfüllte Anforderungen: {met_count}/{total_count}
Kritische Lücken: {critical_gaps}
Details:
{requirements_detail}

Schreibe einen professionellen Match-Report auf Englisch (max. 150 Wörter):

**Strengths** (cite specific evidence from CV):
[2-3 concrete strengths with evidence]

**Gaps** (what is missing for this specific role):
[1-3 specific gaps]

**Recommendation**:
Verdict: [Strong Match / Possible Match / Weak Match]
[1-2 sentences explaining the verdict]"""


def run_stage3(jd: dict, cv: dict, stage2_result: dict) -> dict:
    """
    STUFE 3: Vollständige evidenz-basierte Match-Analyse.

    Läuft nur für Top-Kandidaten (nach stage2_score sortiert).

    Returns:
        Dict mit: explanation (str), verdict (str), error (str|None)
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
            dates = f"{role.get('start_date', '')}–{role.get('end_date', '')}"
            desc = str(role.get("description", ""))[:200]
            work_lines.append(f"  • {title} @ {org} ({dates}): {desc}")
    work_str = "\n".join(work_lines) if work_lines else "  Kein Berufsverlauf verfügbar"

    edu = cv.get("education") or []
    edu_parts = []
    for e in edu[:3]:
        if isinstance(e, dict):
            edu_parts.append(f"{e.get('degree', '')} ({e.get('institution', '')})")
    edu_str = "; ".join(edu_parts) if edu_parts else "Nicht angegeben"

    req_detail_lines = []
    for r in (stage2_result.get("requirements") or [])[:8]:
        if isinstance(r, dict):
            req_detail_lines.append(
                f"  [{r.get('score', 0)}/10] {r.get('requirement', '')[:60]}: {r.get('evidence', '')[:80]}"
            )
    req_detail = "\n".join(req_detail_lines) if req_detail_lines else "  Keine Details"

    essential_reqs = "\n".join(
        f"  {i+1}. {r}" for i, r in enumerate((jd.get("essential_requirements") or [])[:6])
    )
    responsibilities = "\n".join(
        f"  • {r}" for r in (jd.get("responsibilities") or [])[:5]
    )
    critical_gaps = ", ".join(stage2_result.get("critical_gaps") or []) or "Keine kritischen Lücken identifiziert"

    prompt = STAGE3_PROMPT.format(
        jd_title=jd.get("title", ""),
        jd_organisation=jd.get("organisation", ""),
        jd_sector=jd.get("sector", ""),
        seniority_level=jd.get("seniority_level", "nicht angegeben"),
        essential_requirements=essential_reqs or "  Keine definiert",
        responsibilities=responsibilities or "  Keine definiert",
        cv_title=cv.get("current_title") or "Unbekannt",
        years_experience=cv.get("years_experience") or "unbekannt",
        career_summary=cv.get("career_summary") or "Kein Profil",
        all_skills=", ".join(all_skills) if all_skills else "keine angegeben",
        sector_experience=", ".join(cv.get("sector_experience") or []) or "nicht angegeben",
        work_history=work_str,
        education=edu_str,
        stage2_score=stage2_result.get("overall_score", 0),
        met_count=stage2_result.get("met_count", 0),
        total_count=stage2_result.get("total_count", 0),
        critical_gaps=critical_gaps,
        requirements_detail=req_detail,
    )

    # Stufe 3 nutzt generate_json mit JSON-Schema für strukturierte Antworten
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
        context=f"Stufe3 {cv.get('anon_ref', '?')} → {jd.get('title', '')[:30]}",
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
# Datenbankfunktionen
# ============================================================

def get_connection():
    db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    return conn


def fetch_all_jds(conn, title_filter: str = None) -> list:
    """JDs laden — optional nach Titel-Keyword filtern."""
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
    """CVs laden — leere CVs optional überspringen."""
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
        # Leere CVs überspringen (gescannte PDFs ohne Text)
        if skip_empty:
            has_data = (
                cv.get("current_title") or
                cv.get("career_summary") or
                cv.get("embedding_text") or
                (cv.get("skills_technical") and len(cv["skills_technical"]) > 0)
            )
            if not has_data:
                logger.info(f"  ⏭ {cv.get('anon_ref')} übersprungen (leeres CV)")
                continue
        result.append(cv)
    return result


def save_ai_match(conn, match: dict):
    """Ein Match-Ergebnis in ai_match_results speichern (Upsert)."""
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
# Finaler Score berechnen
# ============================================================

def compute_final_score(s1_score: float, s2_score: float, s3_verdict: str = None) -> float:
    """
    Gewichteter Gesamtscore aus allen 3 Stufen.

    Gewichtung:
      30% Stage 1 — grundlegende Berufsrelevanz (wichtig, aber grob)
      55% Stage 2 — Anforderungserfüllung (wichtigster Faktor!)
      15% Stage 3 — Tiefe Analyse / Verdict

    Stage 3 ist optional (nur für Top-Kandidaten).
    Wenn nicht vorhanden: Gewichtung 30/70 (Stage 1/2).

    LERNPUNKT: Warum 55% für Stage 2?
    Weil die Anforderungen DAS Wichtigste sind. Ein Kandidat
    kann beruflich passen (Stage 1 hoch) aber keine der konkreten
    Qualifikationen haben (Stage 2 niedrig) — dann ist er nicht geeignet.
    """
    s3_map = {"Strong Match": 10.0, "Possible Match": 6.0, "Weak Match": 2.0}

    if s3_verdict and s3_verdict in s3_map:
        s3_val = s3_map[s3_verdict]
        return round(0.30 * s1_score + 0.55 * s2_score + 0.15 * s3_val, 3)
    else:
        # Nur Stage 1 + 2
        return round(0.35 * s1_score + 0.65 * s2_score, 3)


# ============================================================
# Hard Filter (zusätzlich zu den 3 KI-Stufen)
# ============================================================

def apply_hard_filter(cv: dict, require_rtw: bool, min_years: int) -> tuple:
    """
    Binäre harte Filter ZUSÄTZLICH zum KI-Matching.
    Diese sind nicht KI-basiert — sie sind einfache Regeln.

    Gibt (passed: bool, reason: str) zurück.
    """
    # RTW-Filter
    if require_rtw and cv.get("right_to_work_uk") is False:
        return False, "Kein UK Right to Work"

    # Mindest-Erfahrung
    if min_years and min_years > 0:
        cv_years = cv.get("years_experience")
        if cv_years is not None and int(cv_years) < min_years:
            return False, f"Zu wenig Erfahrung: {cv_years} Jahre (min. {min_years})"

    return True, ""


# ============================================================
# Excel-Export
# ============================================================

def export_to_excel(all_results: list):
    """
    Exportiert alle Ergebnisse in docs/evaluation_results_III.xlsx.

    Struktur:
    - Ein Sheet pro JD (mit Kandidaten sortiert nach final_rank)
    - Ein 'Alle Ergebnisse' Übersichts-Sheet
    - Ein 'Anleitung' Sheet
    """
    if not all_results:
        logger.warning("Keine Ergebnisse zum Exportieren")
        return

    with pd.ExcelWriter(EXCEL_OUTPUT, engine="openpyxl") as writer:

        # Alle Ergebnisse für Übersichts-Sheet
        all_rows = []

        # Gruppiere nach JD
        jds_seen = {}
        for m in all_results:
            jt = m.get("jd_title", "Unbekannt")
            if jt not in jds_seen:
                jds_seen[jt] = []
            jds_seen[jt].append(m)

        for jd_title, matches in jds_seen.items():
            # Sortiere: zuerst nach stage1_passed, dann nach final_score
            matches_sorted = sorted(
                matches,
                key=lambda x: (
                    not x.get("stage1_passed", False),  # Stage1=True zuerst
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
                    # ── Rang & Ergebnis ──
                    "final_rank":       rank,
                    "final_score":      m.get("final_score"),

                    # ── Stelle ──
                    "jd_title":         m.get("jd_title"),
                    "jd_organisation":  m.get("jd_organisation"),

                    # ── Kandidat ──
                    "anon_ref":         m.get("anon_ref"),
                    "cv_title":         m.get("cv_title"),
                    "career_summary":   m.get("career_summary"),
                    "years_experience": m.get("years_experience"),
                    "right_to_work_uk": m.get("right_to_work_uk"),

                    # ── Stufe 1: Berufs-Gate ──
                    "stufe1_relevant":  "✓ JA" if m.get("stage1_passed") else "✗ NEIN",
                    "stufe1_score":     m.get("stage1_score"),
                    "stufe1_begruendung": m.get("stage1_reason"),

                    # ── Stufe 2: Anforderungen ──
                    "stufe2_score":     m.get("stage2_score"),
                    "stufe2_erfuellt":  f"{m.get('stage2_met_count', 0)}/{m.get('stage2_total_count', 0)} Anforderungen",
                    "stufe2_luecken":   ", ".join(m.get("stage2_critical_gaps") or []),
                    "stufe2_details":   s2_detail,

                    # ── Stufe 3: Tiefe Analyse ──
                    "stufe3_verdict":   m.get("stage3_verdict") or "(nicht analysiert — nicht in Top 5)",
                    "stufe3_report":    m.get("stage3_explanation") or "(nicht analysiert)",

                    # ── Recruiter ausfüllen ──
                    "recruiter_label":  None,   # 0=Nein, 1=Vielleicht, 2=Ja
                    "notes":            None,
                }
                rows.append(row)
                all_rows.append(row)

            # Sheet-Name: max 31 Zeichen
            sheet_name = jd_title[:28] + "..." if len(jd_title) > 31 else jd_title
            df = pd.DataFrame(rows)
            df.to_excel(writer, index=False, sheet_name=sheet_name)

            # Spaltenbreiten
            ws = writer.sheets[sheet_name]
            col_widths = {
                "A": 8, "B": 10, "C": 30, "D": 20, "E": 10, "F": 25,
                "G": 50, "H": 8, "I": 10, "J": 8, "K": 8, "L": 50,
                "M": 8, "N": 20, "O": 40, "P": 60, "Q": 15, "R": 80, "S": 12, "T": 30,
            }
            for col_letter, width in col_widths.items():
                ws.column_dimensions[col_letter].width = width

        # Übersichts-Sheet (alle Stellen)
        if all_rows:
            df_all = pd.DataFrame(all_rows)
            df_all = df_all.sort_values(["jd_title", "final_rank"])
            df_all.to_excel(writer, index=False, sheet_name="Alle Ergebnisse")

        # Anleitung-Sheet
        pd.DataFrame({
            "Spalte": [
                "final_rank", "final_score",
                "stufe1_relevant", "stufe1_score",
                "stufe2_score", "stufe2_erfuellt", "stufe2_luecken",
                "stufe3_verdict", "stufe3_report",
                "recruiter_label",
            ],
            "Bedeutung": [
                "Gesamtrang (1 = bester Kandidat pro Stelle)",
                "Gewichteter Score: 35% Berufsrelevanz + 65% Anforderungen (0-10)",
                "✓ JA = Beruf passt grundsätzlich | ✗ NEIN = falscher Beruf",
                "0-10: Wie gut passt der Berufsweg? (0=falsch, 10=perfekt)",
                "0-10: Wie viele Anforderungen erfüllt? (Wichtigster Wert!)",
                "z.B. '3/5 Anforderungen' erfüllt (Score >= 7)",
                "Fehlende Schlüsselqualifikationen",
                "Strong Match / Possible Match / Weak Match (nur Top-Kandidaten)",
                "Vollständiger Match-Report von der KI (nur Top-Kandidaten)",
                "0=Kein Match | 1=Vielleicht | 2=Guter Match — VON DIR AUSFÜLLEN",
            ],
        }).to_excel(writer, index=False, sheet_name="Anleitung")

    logger.info(f"✓ Exportiert nach: {EXCEL_OUTPUT}")


# ============================================================
# Haupt-Matching-Funktion
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
    Führt das 3-stufige Matching für eine JD gegen alle CVs durch.

    Args:
        jd:           JD-Dict aus der DB
        cvs:          Liste aller CV-Dicts
        max_stage:    Bis zu welcher Stufe analysieren (1, 2 oder 3)
        top_n_stage3: Wie viele Top-Kandidaten in Stufe 3 analysieren
        require_rtw:  Nur UK-RTW-Kandidaten
        min_years:    Mindest-Erfahrungsjahre (Recruiter-Filter)

    Returns:
        Liste von Match-Dicts, sortiert nach final_score (absteigend)
    """
    jd_title = jd.get("title", "?")
    jd_id    = jd["jd_id"]
    logger.info(f"\n{'─' * 55}")
    logger.info(f"JD: '{jd_title}' | {len(cvs)} Kandidaten")

    results = []

    # ── Stufe 1 für alle CVs ──────────────────────────────────
    logger.info(f"  STUFE 1: Berufs-Gate...")
    stage1_passed = []

    for cv in cvs:
        anon = cv.get("anon_ref", "?")

        # Hard Filter zuerst (keine API-Kosten)
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
            # Stufe 1
            "stage1_passed":   s1["relevant"] and hard_ok,
            "stage1_score":    s1["score"],
            "stage1_reason":   s1["reason"],
            # Stufe 2+3 noch leer
            "stage2_score":    None,
            "stage2_met_count": None,
            "stage2_total_count": None,
            "stage2_breakdown": [],
            "stage2_critical_gaps": [],
            "stage3_explanation": None,
            "stage3_verdict":  None,
            "final_score":     s1["score"] / 10 * 3.5,  # Vorläufig nur Stage 1
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
        logger.info(f"      → {reason_short}")

        results.append(match)

        if s1["relevant"] and hard_ok:
            stage1_passed.append((match, cv))

    logger.info(f"  Stufe 1: {len(stage1_passed)}/{len(cvs)} bestanden")

    if max_stage < 2 or not stage1_passed:
        return results

    # ── Stufe 2 für alle Stage-1-Bestehenden ─────────────────
    logger.info(f"  STUFE 2: Anforderungs-Scoring ({len(stage1_passed)} Kandidaten)...")

    for match, cv in stage1_passed:
        s2 = run_stage2(jd, cv)
        time.sleep(0.4)

        match["stage2_score"]         = s2["overall_score"]
        match["stage2_met_count"]     = s2["met_count"]
        match["stage2_total_count"]   = s2["total_count"]
        match["stage2_breakdown"]     = s2["requirements"]
        match["stage2_critical_gaps"] = s2["critical_gaps"]

        # Vorläufiger final_score (ohne Stage 3)
        match["final_score"] = compute_final_score(
            s1_score=match["stage1_score"],
            s2_score=s2["overall_score"],
        )

        logger.info(
            f"    {match['anon_ref']}: "
            f"score={s2['overall_score']:.1f}/10  "
            f"erfüllt={s2['met_count']}/{s2['total_count']}  "
            f"→ final={match['final_score']:.2f}"
        )

    if max_stage < 3:
        return results

    # ── Stufe 3: Nur Top-N nach Stage 2 ──────────────────────
    stage2_sorted = sorted(
        [(m, cv) for (m, cv) in stage1_passed if m["stage2_score"] is not None],
        key=lambda x: x[0]["stage2_score"],
        reverse=True,
    )
    top_candidates = stage2_sorted[:top_n_stage3]

    logger.info(f"  STUFE 3: Tiefe Analyse für Top {len(top_candidates)} Kandidaten...")

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
            f"→ final={match['final_score']:.2f}"
        )

    # ── Ranking berechnen ─────────────────────────────────────
    results_sorted = sorted(results, key=lambda x: (
        not x.get("stage1_passed", False),
        -(x.get("final_score") or 0),
    ))
    for rank, m in enumerate(results_sorted, start=1):
        m["final_rank"] = rank

    top_final = [m for m in results_sorted if m.get("stage1_passed")]
    if top_final:
        logger.info(
            f"\n  🏆 TOP MATCH: {top_final[0]['anon_ref']} "
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
        description="08_ai_match.py — 3-stufiges KI-Matching"
    )
    parser.add_argument("--max-stage",    type=int, default=3, choices=[1, 2, 3],
                        help="Bis zu welcher Stufe analysieren (default: 3)")
    parser.add_argument("--top-n",        type=int, default=3,
                        help="Top N Kandidaten für Stufe 3 (default: 3)")
    parser.add_argument("--jd-title",     type=str, default=None,
                        help="Nur JDs mit diesem Keyword im Titel verarbeiten")
    parser.add_argument("--require-rtw",  action="store_true", default=False,
                        help="Nur Kandidaten mit UK Right to Work")
    parser.add_argument("--min-years",    type=int, default=None,
                        help="Mindest-Erfahrungsjahre")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("3-stufiges KI-Matching — Diversifying.io")
    logger.info("=" * 60)
    logger.info(f"  Max. Stufe:    {args.max_stage}")
    logger.info(f"  Top N (Stufe 3): {args.top_n}")
    if args.jd_title:
        logger.info(f"  JD-Filter:     Titel enthält '{args.jd_title}'")
    if args.require_rtw:
        logger.info(f"  Filter:        Nur UK Right to Work")
    if args.min_years:
        logger.info(f"  Filter:        Min. {args.min_years} Jahre Erfahrung")

    conn = get_connection()
    try:
        jds = fetch_all_jds(conn, title_filter=args.jd_title)
        cvs = fetch_all_cvs(conn, skip_empty=True)

        logger.info(f"\nGeladen: {len(jds)} JD(s) | {len(cvs)} CV(s) (leere übersprungen)")

        if not jds or not cvs:
            logger.error("Keine Daten. Zuerst Skripte 01-05 ausführen.")
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

            # In DB speichern
            for m in jd_results:
                save_ai_match(conn, m)

            all_results.extend(jd_results)

        # Excel exportieren
        logger.info(f"\n{'=' * 60}")
        logger.info("Export...")
        export_to_excel(all_results)

        # Zusammenfassung
        total_pairs  = len(all_results)
        s1_passed    = sum(1 for m in all_results if m.get("stage1_passed"))
        s3_done      = sum(1 for m in all_results if m.get("stage3_verdict"))
        strong       = sum(1 for m in all_results if m.get("stage3_verdict") == "Strong Match")
        possible     = sum(1 for m in all_results if m.get("stage3_verdict") == "Possible Match")

        logger.info(f"{'=' * 60}")
        logger.info("ZUSAMMENFASSUNG")
        logger.info(f"{'=' * 60}")
        logger.info(f"  Gesamte Paare analysiert: {total_pairs}")
        logger.info(f"  Stufe 1 bestanden:        {s1_passed}/{total_pairs} Paare")
        logger.info(f"  Stufe 3 (Deep Analysis):  {s3_done} Kandidaten")
        logger.info(f"  → Strong Match:           {strong}")
        logger.info(f"  → Possible Match:         {possible}")
        logger.info(f"\n  📊 Output: {EXCEL_OUTPUT}")
        logger.info("\nNÄCHSTE SCHRITTE:")
        logger.info("  1. docs/evaluation_results_III.xlsx öffnen")
        logger.info("  2. Zeilen mit stufe1_relevant=✓ prüfen")
        logger.info("  3. recruiter_label (0/1/2) ausfüllen")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
