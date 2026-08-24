"""
scripts/07_week4_match.py — Week 4: Intelligentes Matching mit 3-stufiger Pipeline

PROBLEM DAS WIR LÖSEN:
    Woche-3-Matching verwendete nur Embedding-Kosinus-Ähnlichkeit.
    Embeddings enthalten viel allgemeines Berufssprachen-Vokabular
    ("stakeholder management", "delivering projects"), das in JEDEM Beruf
    vorkommt. Deshalb landete ein Lead Designer bei Finance-Stellen auf Rang 1.

LÖSUNG — 3-stufige Pipeline:

    STUFE 1: BERUFSFELD-GATE (NEU — das Wichtigste)
    ─────────────────────────────────────────────────
    Bevor irgendein Score berechnet wird, prüfen wir:
    "Gehört der Kandidat überhaupt zum richtigen Berufsfeld?"

    Jede JD und jeder Kandidat hat jetzt ein "profession_domain" Feld
    (z.B. "Finance", "Legal", "Creative & Media", "Technology").
    Nur Kandidaten deren Domain mit der JD kompatibel ist, kommen weiter.

    → Designer bei Finance-JD: sofort herausgefiltert
    → Finance-Kandidat bei Risk & Audit: erlaubt (verwandte Domänen)

    STUFE 2: HARD FILTER
    ─────────────────────────────────────────────────
    - Right to Work UK (alle JDs sind UK-basiert)
    - Mindest-Erfahrungsjahre (konfigurierbar: --min-years N)
    - Pflicht-Skills (konfigurierbar: --require-skills "skill1,skill2")

    STUFE 3: COMPOSITE SCORE
    ─────────────────────────────────────────────────
    Nur für Kandidaten die Stufe 1+2 bestanden haben:
      score = 0.6 × semantic + 0.3 × skill_overlap + 0.1 × experience_fit

HOW TO RUN:
    # Standard: composite scoring, alle JDs, top 10 pro JD
    python scripts/07_week4_match.py --top-n 10 --explain

    # Nur bestimmte JD (UUID aus DB):
    python scripts/07_week4_match.py --jd-id <UUID> --explain

    # Recruiter-Filter:
    python scripts/07_week4_match.py --min-years 5 --require-rtw --top-n 5

    # A/B Experimente (alle 3 Strategien vergleichen):
    python scripts/07_week4_match.py --compare --no-explain

    # Skills-Filter:
    python scripts/07_week4_match.py --require-skills "financial reporting,stakeholder management"

WEEK 4 DELIVERABLE:
    docs/week4_results.xlsx  — ein Sheet pro Experiment + Comparison-Sheet
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras

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
EXCEL_OUTPUT = DOCS_DIR / "week4_results.xlsx"


# ============================================================
# STUFE 1: Berufsfeld-Kompatibilitäts-Matrix
# ============================================================
#
# Diese Matrix definiert welche Kandidaten-Domänen mit welchen
# JD-Domänen kompatibel sind.
#
# LERNPUNKT: Das ist eine "rule-based" Vorfilterung.
# Sie ist einfach, erklärbar und sehr effektiv.
# Ein ML-Modell könnte das besser, aber wir haben zu wenig Daten.
#
# Struktur: { JD-Domäne: [erlaubte Kandidaten-Domänen] }
#
COMPATIBLE_DOMAINS = {
    "Finance": [
        "Finance",
        "General Management",  # Senior-Manager können in Finance wechseln
    ],
    "Legal": [
        "Legal",
        "General Management",
    ],
    "Procurement": [
        "Procurement",
        "Finance",             # Finance-Kandidaten haben oft Procurement-Erfahrung
        "General Management",
    ],
    "Risk & Audit": [
        "Risk & Audit",
        "Finance",             # Finance und Risk sind eng verwandt
        "Legal",               # Legal hat oft Risk/Compliance-Aspekte
        "General Management",
    ],
    "Creative & Media": [
        "Creative & Media",
        "Technology",          # Digitale Kreative überschneiden sich mit Tech
        "General Management",
    ],
    "Technology": [
        "Technology",
        "Creative & Media",    # z.B. UX-Designer in Tech-Rollen
        "General Management",
    ],
    "Healthcare": [
        "Healthcare",
        "General Management",
    ],
    "HR & People": [
        "HR & People",
        "General Management",
    ],
    "General Management": [
        # General Management JDs akzeptieren jeden mit Senior-Erfahrung
        "Finance", "Legal", "Procurement", "Risk & Audit",
        "Creative & Media", "Technology", "Healthcare",
        "HR & People", "General Management", "Other",
    ],
    "Other": [
        "Other", "General Management",
    ],
}

# Fallback: wenn domain nicht bekannt → zeige eine Warnung, filtere nicht heraus
FALLBACK_BEHAVIOR = "warn"  # "warn" oder "exclude"


def check_domain_compatibility(jd_domain: str, cv_domain: str) -> tuple:
    """
    Prüft ob eine Kandidaten-Domäne mit einer JD-Domäne kompatibel ist.

    STUFE 1 der Matching-Pipeline.

    Args:
        jd_domain: Berufsfeld der Stelle (z.B. "Finance")
        cv_domain: Berufsfeld des Kandidaten (z.B. "Creative & Media")

    Returns:
        (compatible: bool, reason: str)

    Beispiele:
        check_domain_compatibility("Finance", "Finance")
            → (True, "Domain match: Finance")
        check_domain_compatibility("Finance", "Creative & Media")
            → (False, "Domain mismatch: Creative & Media not relevant for Finance")
        check_domain_compatibility("Finance", None)
            → (True, "Domain unknown — included with warning")
    """
    # Wenn eine der Domänen unbekannt → Benefit of the doubt
    if not jd_domain:
        return True, "JD domain unknown — no gate applied"
    if not cv_domain:
        return True, "CV domain unknown — included with warning"

    allowed = COMPATIBLE_DOMAINS.get(jd_domain, [jd_domain])

    if cv_domain in allowed:
        return True, f"Domain match: {cv_domain} ✓ for {jd_domain}"
    else:
        return False, f"Domain mismatch: {cv_domain} not relevant for {jd_domain}"


# ============================================================
# Experiment-Konfigurationen
# ============================================================

EXPERIMENTS = {
    "baseline": {
        "description": "Nur Semantik — wie in Woche 3, aber MIT Domain-Gate",
        "w_sem":   1.0,
        "w_skill": 0.0,
        "w_exp":   0.0,
    },
    "composite": {
        "description": "Ausgewogen: 60% Semantik, 30% Skills, 10% Erfahrung",
        "w_sem":   0.6,
        "w_skill": 0.3,
        "w_exp":   0.1,
    },
    "skills_heavy": {
        "description": "Skill-fokussiert: 40% Semantik, 50% Skills, 10% Erfahrung",
        "w_sem":   0.4,
        "w_skill": 0.5,
        "w_exp":   0.1,
    },
}


# ============================================================
# Seniority-Mapping (Erfahrungsjahre aus JD-Titel ableiten)
# ============================================================

SENIORITY_RULES = [
    (["head of", "director", "general counsel", "chief"],  9),
    (["senior", "interim head", "lead"],                   6),
    (["manager", "officer", "producer", "counsel"],        4),
    (["junior", "graduate", "associate", "trainee"],       0),
]

def infer_min_years(jd_title: str, db_min_years: int = None) -> int:
    """
    Minimale Erfahrungsjahre für eine Stelle.

    Bevorzugt den Wert aus der DB (von Gemini extrahiert),
    fällt auf Titel-basiertes Regelwerk zurück wenn nicht vorhanden.
    """
    # Preferenz: DB-Wert von Gemini (genauer)
    if db_min_years is not None:
        return int(db_min_years)

    # Fallback: Regelbasiert aus Jobtitel
    if not jd_title:
        return 4

    title_lower = jd_title.lower()
    for keywords, min_years in SENIORITY_RULES:
        if any(kw in title_lower for kw in keywords):
            return min_years
    return 4


# ============================================================
# STUFE 2: Hard Filter
# ============================================================

def apply_hard_filters(
    cv: dict,
    jd: dict,
    require_rtw: bool = False,
    min_years_override: int = None,
    required_skills: list = None,
) -> tuple:
    """
    STUFE 2 der Pipeline: Hard Filter auf Kandidaten.

    Filter:
    1. Right to Work UK (nur wenn --require-rtw gesetzt)
    2. Mindest-Erfahrungsjahre (aus DB oder Regelwerk, oder --min-years Override)
    3. Pflicht-Skills (aus --require-skills Parameter)

    Args:
        cv:                 Kandidaten-Dict aus DB
        jd:                 JD-Dict aus DB
        require_rtw:        True = nur UK-RTW-Kandidaten zeigen
        min_years_override: Vom Recruiter gesetztes Minimum (überschreibt JD-Wert)
        required_skills:    Liste von Pflicht-Skills (vom Recruiter gesetzt)

    Returns:
        (passed: bool, reasons: list[str])
        passed=False → noch sichtbar im Excel, aber als gefiltert markiert

    LERNPUNKT:
    "Hard filter" bedeutet: Entweder bestanden oder nicht — kein Grauverlauf.
    "Soft filter" bedeutet: Score wird reduziert aber Kandidat bleibt sichtbar.
    Wir verwenden Hard Filter hier, aber zeigen die Kandidaten trotzdem (für Analyse).
    """
    reasons = []

    # Filter 1: Right to Work UK
    if require_rtw:
        rtw = cv.get("right_to_work_uk")
        if rtw is False:
            reasons.append("No UK right to work")
        # rtw=None → Benefit of the doubt (nicht explizit ausgeschlossen)

    # Filter 2: Mindest-Erfahrungsjahre
    jd_title     = jd.get("title", "")
    db_min_years = jd.get("min_years_experience")
    min_years    = min_years_override if min_years_override is not None else infer_min_years(jd_title, db_min_years)

    if min_years > 0:
        cv_years = cv.get("years_experience")
        if cv_years is not None and int(cv_years) < min_years:
            reasons.append(
                f"Experience too low: {cv_years} yrs (minimum: {min_years} yrs for '{jd_title}')"
            )

    # Filter 3: Pflicht-Skills
    if required_skills:
        cv_skills_all = set(
            s.strip().lower()
            for s in ((cv.get("skills_technical") or []) + (cv.get("skills_soft") or []))
            if isinstance(s, str)
        )
        missing_required = [
            skill for skill in required_skills
            if skill.strip().lower() not in cv_skills_all
        ]
        if missing_required:
            reasons.append(f"Missing required skills: {', '.join(missing_required)}")

    return (len(reasons) == 0), reasons


# ============================================================
# STUFE 3: Scoring-Funktionen
# ============================================================

def cosine_similarity(vec_a: list, vec_b: list) -> float:
    """Kosinus-Ähnlichkeit zwischen zwei Vektoren."""
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def jaccard_skill_overlap(jd_skills: list, cv_skills: list) -> float:
    """Jaccard-Ähnlichkeit auf normalisierten Skill-Mengen."""
    set_a = {s.strip().lower() for s in (jd_skills or []) if isinstance(s, str)}
    set_b = {s.strip().lower() for s in (cv_skills or []) if isinstance(s, str)}
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def compute_experience_fit(cv_years, jd_title: str, db_min_years: int = None) -> float:
    """
    Score (0.0–1.0): Wie gut passt die Erfahrung des Kandidaten zur Stelle?

    - cv_years >= min_years         → 1.0
    - cv_years >= min_years × 0.75  → 0.7
    - cv_years >= min_years × 0.5   → 0.5
    - darunter                      → skaliert bis 0.2
    - unbekannt (None)              → 0.5 (neutral)
    """
    min_years = infer_min_years(jd_title, db_min_years)

    if cv_years is None:
        return 0.5
    cv_years = float(cv_years)
    if min_years == 0:
        return 1.0
    if cv_years >= min_years:
        return 1.0
    elif cv_years >= min_years * 0.75:
        return 0.7
    elif cv_years >= min_years * 0.5:
        return 0.5
    else:
        return round(max(0.2, cv_years / min_years), 3)


def compute_composite_score(semantic, skill_overlap, experience_fit, weights) -> float:
    """Gewichtete Linearkombination der drei Signale."""
    return round(
        weights["w_sem"]   * semantic
        + weights["w_skill"] * skill_overlap
        + weights["w_exp"]   * experience_fit,
        4,
    )


# ============================================================
# Verbesserter Erklärungsprompt (v2)
# ============================================================

def build_explanation_prompt_v2(
    jd_title, jd_domain, jd_skills, jd_requirements,
    cv_title, cv_domain, cv_skills, cv_experience_summary,
    cv_years, semantic_score, skill_overlap_pct, experience_fit,
    filter_passed, filter_reasons, domain_compatible, domain_reason,
) -> str:
    """
    Verbesserter Gemini-Prompt für Match-Erklärungen.

    Neu gegenüber v1:
    - Berufsfeld-Kontext (profession_domain) wird explizit mitgegeben
    - Welche Skills genau matchen und welche fehlen
    - Erfahrungs-Lücke oder -Überschuss wird benannt
    - Klare Anweisung: konkret und evidence-based, kein Blabla
    - Verdict am Ende: Strong / Possible / Weak match

    Warum das besser ist:
    v1-Ergebnisse: "This candidate has relevant skills for this role."
    v2-Ergebnisse: "The candidate brings 8 years of NHS finance experience
                    and matches 3/5 required skills. Missing: budget planning
                    at board level. Verdict: Possible match."
    """
    jd_set  = {s.strip().lower() for s in jd_skills if isinstance(s, str)}
    cv_set  = {s.strip().lower() for s in cv_skills  if isinstance(s, str)}
    matched = sorted(jd_set & cv_set)
    missing = sorted(jd_set - cv_set)

    matched_str    = ", ".join(matched[:5]) if matched else "none explicitly listed"
    missing_str    = ", ".join(missing[:5]) if missing else "none identified"
    filter_note    = f"\n⚠ HARD FILTER FLAG: {', '.join(filter_reasons)}" if not filter_passed else ""
    domain_note    = "" if domain_compatible else f"\n⚠ DOMAIN WARNING: {domain_reason}"

    return f"""You are an expert UK recruiter evaluating a candidate for a specific role.
Write a concise, evidence-based match explanation (2-3 sentences).

JOB DETAILS:
- Role: {jd_title}
- Professional Domain: {jd_domain or 'not specified'}
- Required Skills: {', '.join(jd_skills[:8]) if jd_skills else 'not specified'}
- Key Requirements: {'; '.join((jd_requirements or [])[:3])}

CANDIDATE PROFILE:
- Current Role: {cv_title or 'Not specified'}
- Professional Domain: {cv_domain or 'not specified'}
- Years Experience: {cv_years or '?'}
- Candidate Skills: {', '.join(cv_skills[:8]) if cv_skills else 'not specified'}
- Recent Experience: {cv_experience_summary or 'Not available'}

MATCH SCORES:
- Semantic similarity: {semantic_score:.0%} (overall profile alignment)
- Skill overlap: {skill_overlap_pct:.0f}% of required skills present
- Experience fit: {experience_fit:.0%} (relative to role seniority){filter_note}{domain_note}

MATCHED SKILLS: {matched_str}
MISSING SKILLS: {missing_str}

Write 2-3 sentences:
1. State the strongest evidence FOR or AGAINST this match (cite specific domain expertise or skills)
2. Name the most important gap or strength
3. End with: "Verdict: Strong match / Possible match / Weak match"

Rules: Be specific. Never write "relevant skills" without naming them. Never write "good fit" without evidence."""


# ============================================================
# Datenbank-Helpers
# ============================================================

def get_connection():
    db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    return conn


def fetch_all_jds(conn, jd_id_filter: str = None) -> list:
    """JDs mit Embeddings, Domain-Feldern und allen Skills laden."""
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    where  = "WHERE jd.jd_id = %s" if jd_id_filter else ""
    params = (jd_id_filter,) if jd_id_filter else ()

    cursor.execute(f"""
        SELECT
            jd.jd_id, jd.title, jd.organisation, jd.sector,
            jd.seniority_level, jd.location, jd.contract_type,
            jd.skills_technical, jd.skills_soft,
            jd.essential_requirements, jd.responsibilities,
            jd.profession_domain, jd.profession_keywords, jd.min_years_experience,
            je.embedding
        FROM job_descriptions jd
        JOIN jd_embeddings je ON jd.jd_id = je.jd_id
        {where}
        ORDER BY jd.created_at
    """, params)

    rows = cursor.fetchall()
    cursor.close()

    result = []
    for row in rows:
        d = dict(row)
        if d.get("embedding"):
            d["embedding"] = [float(x) for x in str(d["embedding"]).strip("[]").split(",")]
        result.append(d)
    return result


def fetch_all_cvs(conn) -> list:
    """CVs mit Embeddings, Domain-Feldern und allen Skills laden."""
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("""
        SELECT
            c.cv_id, c.anon_ref, c.current_title, c.years_experience,
            c.skills_technical, c.skills_soft, c.sector_experience,
            c.work_history, c.education, c.right_to_work_uk,
            c.profession_domain, c.career_summary,
            ce.embedding
        FROM candidates c
        JOIN cv_embeddings ce ON c.cv_id = ce.cv_id
        ORDER BY c.created_at
    """)
    rows = cursor.fetchall()
    cursor.close()

    result = []
    for row in rows:
        d = dict(row)
        if d.get("embedding"):
            d["embedding"] = [float(x) for x in str(d["embedding"]).strip("[]").split(",")]
        result.append(d)
    return result


def save_match_results(conn, matches: list, experiment_id: str):
    """Match-Ergebnisse in die DB schreiben (Upsert)."""
    cursor = conn.cursor()
    for m in matches:
        cursor.execute("""
            INSERT INTO match_results (
                jd_id, cv_id,
                semantic_score, skill_overlap, rank_position,
                composite_score, experience_fit,
                filter_passed, experiment_id,
                ai_explanation
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (jd_id, cv_id) DO UPDATE SET
                semantic_score  = EXCLUDED.semantic_score,
                skill_overlap   = EXCLUDED.skill_overlap,
                rank_position   = EXCLUDED.rank_position,
                composite_score = EXCLUDED.composite_score,
                experience_fit  = EXCLUDED.experience_fit,
                filter_passed   = EXCLUDED.filter_passed,
                experiment_id   = EXCLUDED.experiment_id,
                ai_explanation  = EXCLUDED.ai_explanation,
                created_at      = NOW()
        """, (
            m["jd_id"], m["cv_id"],
            m["semantic_score"], m["skill_overlap"], m["rank_position"],
            m.get("composite_score"), m.get("experience_fit"),
            m.get("filter_passed", True), experiment_id,
            m.get("ai_explanation"),
        ))
    conn.commit()
    cursor.close()
    logger.info(f"  ✓ {len(matches)} Ergebnisse gespeichert (experiment: {experiment_id})")


# ============================================================
# Haupt-Matching-Pipeline (alle 3 Stufen)
# ============================================================

def match_jd_to_cvs(
    jd: dict,
    cvs: list,
    weights: dict,
    top_n: int = 10,
    generate_explanations: bool = True,
    require_rtw: bool = False,
    min_years_override: int = None,
    required_skills: list = None,
) -> list:
    """
    Findet die top-N passendsten Kandidaten für eine Stelle.

    STUFE 1 → Domain-Gate: Passt das Berufsfeld?
    STUFE 2 → Hard Filter: RTW, Mindest-Jahre, Pflicht-Skills
    STUFE 3 → Composite Score: Semantik + Skills + Erfahrung

    Kandidaten die Stufe 1 oder 2 nicht bestehen:
    - Bleiben im Output sichtbar (filter_passed=False, domain_match=False)
    - Werden ans Ende des Rankings gesetzt (score - 10 Penalty)
    - Werden im Excel mit roter Markierung kenntlich gemacht

    Warum sichtbar lassen?
    → Damit der Recruiter sieht: "Ohne Filter wäre XY dabei gewesen"
    → Wertvolle Information für die Evaluation
    """
    jd_embedding = jd.get("embedding")
    if not jd_embedding:
        logger.warning(f"JD {jd['jd_id']} hat kein Embedding — übersprungen")
        return []

    jd_title   = jd.get("title", "")
    jd_domain  = jd.get("profession_domain")
    jd_skills  = (jd.get("skills_technical") or []) + (jd.get("skills_soft") or [])
    jd_reqs    = jd.get("essential_requirements") or []
    db_min_yrs = jd.get("min_years_experience")

    scored = []
    domain_blocked = 0

    for cv in cvs:
        cv_embedding = cv.get("embedding")
        if not cv_embedding:
            continue

        cv_domain = cv.get("profession_domain")

        # ── STUFE 1: Domain-Gate ──────────────────────────────────
        domain_ok, domain_reason = check_domain_compatibility(jd_domain, cv_domain)

        # ── STUFE 2: Hard Filter ──────────────────────────────────
        filter_ok, filter_reasons = apply_hard_filters(
            cv, jd,
            require_rtw=require_rtw,
            min_years_override=min_years_override,
            required_skills=required_skills,
        )

        # ── STUFE 3: Scoring ──────────────────────────────────────
        semantic  = cosine_similarity(jd_embedding, cv_embedding)
        cv_skills = (cv.get("skills_technical") or []) + (cv.get("skills_soft") or [])
        skill_jac = jaccard_skill_overlap(jd_skills, cv_skills)
        exp_fit   = compute_experience_fit(cv.get("years_experience"), jd_title, db_min_yrs)
        score     = compute_composite_score(semantic, skill_jac, exp_fit, weights)

        # Penalty für geblockte Kandidaten (sichtbar aber am Ende)
        if not domain_ok:
            sort_key = score - 20  # Starke Penalty → immer ans Ende
            domain_blocked += 1
        elif not filter_ok:
            sort_key = score - 10  # Moderate Penalty → nach domain-validen
        else:
            sort_key = score

        scored.append({
            "cv_id":             cv["cv_id"],
            "anon_ref":          cv.get("anon_ref"),
            "cv_title":          cv.get("current_title"),
            "cv_domain":         cv_domain,
            "years_experience":  cv.get("years_experience"),
            "right_to_work_uk":  cv.get("right_to_work_uk"),
            "career_summary":    cv.get("career_summary"),
            "domain_match":      domain_ok,
            "domain_reason":     domain_reason,
            "filter_passed":     filter_ok,
            "filter_reasons":    filter_reasons,
            "semantic_score":    round(semantic, 4),
            "skill_overlap":     round(skill_jac, 4),
            "skill_overlap_pct": round(skill_jac * 100, 1),
            "experience_fit":    round(exp_fit, 4),
            "composite_score":   score,
            "_sort_key":         sort_key,
            "_cv":               cv,
            "_cv_skills":        cv_skills,
        })

    scored.sort(key=lambda x: x["_sort_key"], reverse=True)
    top_matches = scored[:top_n]

    domain_ok_count  = sum(1 for m in top_matches if m["domain_match"])
    filter_ok_count  = sum(1 for m in top_matches if m["filter_passed"] and m["domain_match"])

    logger.info(
        f"  '{jd_title}' [{jd_domain}] — "
        f"domain-relevant: {domain_ok_count}/{len(top_matches)} | "
        f"filter-passed: {filter_ok_count}/{len(top_matches)} | "
        f"domain-blocked (total): {domain_blocked}"
    )

    # Rang und Erklärungen
    for rank, m in enumerate(top_matches, start=1):
        m["rank_position"]   = rank
        m["jd_id"]           = jd["jd_id"]
        m["jd_title"]        = jd_title
        m["jd_domain"]       = jd_domain
        m["jd_organisation"] = jd.get("organisation")

        cv_data   = m.pop("_cv", {})
        cv_skills = m.pop("_cv_skills", [])
        m.pop("_sort_key", None)

        if generate_explanations:
            cv_work = cv_data.get("work_history") or []
            exp_summary = " | ".join([
                f"{r.get('title','')} at {r.get('organisation','')}: {str(r.get('description',''))[:80]}"
                for r in cv_work[:2] if isinstance(r, dict)
            ])

            prompt = build_explanation_prompt_v2(
                jd_title=jd_title,
                jd_domain=jd_domain,
                jd_skills=jd_skills,
                jd_requirements=jd_reqs,
                cv_title=m.get("cv_title", ""),
                cv_domain=m.get("cv_domain"),
                cv_skills=cv_skills,
                cv_experience_summary=exp_summary,
                cv_years=m.get("years_experience"),
                semantic_score=m["semantic_score"],
                skill_overlap_pct=m["skill_overlap_pct"],
                experience_fit=m["experience_fit"],
                filter_passed=m["filter_passed"],
                filter_reasons=m["filter_reasons"],
                domain_compatible=m["domain_match"],
                domain_reason=m["domain_reason"],
            )
            try:
                m["ai_explanation"] = gemini.client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=prompt,
                ).text.strip()
            except Exception as e:
                logger.warning(f"Erklärung fehlgeschlagen für {m['cv_id']}: {e}")
                m["ai_explanation"] = f"(failed: {e})"
            time.sleep(0.4)
        else:
            m["ai_explanation"] = "(use --explain to generate)"

    return top_matches


# ============================================================
# Excel-Export
# ============================================================

def export_to_excel(results_by_experiment: dict):
    """Exportiert alle Experimente in docs/week4_results.xlsx."""

    with pd.ExcelWriter(EXCEL_OUTPUT, engine="openpyxl") as writer:
        all_dfs = {}

        for exp_name, matches in results_by_experiment.items():
            if not matches:
                continue

            rows = [{
                "jd_title":         m.get("jd_title"),
                "jd_domain":        m.get("jd_domain"),
                "jd_organisation":  m.get("jd_organisation"),
                "anon_ref":         m.get("anon_ref"),
                "cv_title":         m.get("cv_title"),
                "cv_domain":        m.get("cv_domain"),
                "career_summary":   m.get("career_summary"),
                "years_experience": m.get("years_experience"),
                "right_to_work_uk": m.get("right_to_work_uk"),
                # ── Stufe 1: Domain Gate ──
                "domain_match":     m.get("domain_match"),
                "domain_reason":    m.get("domain_reason"),
                # ── Stufe 2: Hard Filter ──
                "filter_passed":    m.get("filter_passed"),
                "filter_reason":    "; ".join(m.get("filter_reasons") or []) or None,
                # ── Stufe 3: Scores ──
                "rank":             m["rank_position"],
                "composite_score":  m.get("composite_score"),
                "semantic_score":   m["semantic_score"],
                "skill_overlap_%":  m.get("skill_overlap_pct"),
                "experience_fit":   m.get("experience_fit"),
                "ai_explanation":   m.get("ai_explanation"),
                # ── Recruiter ausfüllen ──
                "recruiter_label":  None,   # 0=Nein, 1=Vielleicht, 2=Ja
                "notes":            None,
            } for m in matches]

            df = pd.DataFrame(rows)
            all_dfs[exp_name] = df
            sheet = exp_name[:31]
            df.to_excel(writer, index=False, sheet_name=sheet)

            ws = writer.sheets[sheet]
            for col in ws.columns:
                w = min(max(len(str(c.value or "")) for c in col) + 2, 55)
                ws.column_dimensions[col[0].column_letter].width = w

        # Comparison-Sheet
        if len(all_dfs) > 1:
            ref = "composite" if "composite" in all_dfs else list(all_dfs.keys())[0]
            rows = []
            for _, ref_row in all_dfs[ref].iterrows():
                row = {
                    "jd_title":    ref_row["jd_title"],
                    "jd_domain":   ref_row["jd_domain"],
                    "anon_ref":    ref_row["anon_ref"],
                    "cv_title":    ref_row["cv_title"],
                    "cv_domain":   ref_row["cv_domain"],
                    "domain_match": ref_row["domain_match"],
                }
                for exp, df in all_dfs.items():
                    hit = df[
                        (df["jd_title"] == ref_row["jd_title"]) &
                        (df["anon_ref"]  == ref_row["anon_ref"])
                    ]
                    if not hit.empty:
                        row[f"rank_{exp}"]  = hit.iloc[0]["rank"]
                        row[f"score_{exp}"] = hit.iloc[0].get("composite_score") or hit.iloc[0]["semantic_score"]
                rows.append(row)
            pd.DataFrame(rows).to_excel(writer, index=False, sheet_name="Comparison")

        # Anweisungs-Sheet
        pd.DataFrame({
            "Spalte": [
                "recruiter_label", "notes", "domain_match", "filter_passed",
                "composite_score", "career_summary"
            ],
            "Anweisung": [
                "0 = Kein Match  |  1 = Vielleicht / überprüfenswert  |  2 = Guter Match",
                "Freitext: Warum stimmst du zu oder nicht?",
                "TRUE = Berufsfeld passt zur Stelle | FALSE = falsches Berufsfeld (Designer bei Finance)",
                "FALSE = Hard Filter nicht bestanden (z.B. zu wenig Erfahrung, kein UK RTW)",
                "Gewichteter Score: 60% Semantik + 30% Skills + 10% Erfahrung",
                "KI-generierte 2-Satz-Zusammenfassung des Kandidaten-Profils",
            ],
        }).to_excel(writer, index=False, sheet_name="Anleitung")

    logger.info(f"✓ Exportiert nach: {EXCEL_OUTPUT}")


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Week 4 — Intelligentes Matching mit 3-stufiger Pipeline"
    )
    parser.add_argument("--top-n",      type=int,  default=10,
                        help="Top N Kandidaten pro JD (default: 10)")
    parser.add_argument("--explain",    action="store_true", default=True,
                        help="AI-Erklärungen generieren (Gemini API calls)")
    parser.add_argument("--no-explain", dest="explain", action="store_false",
                        help="Erklärungen überspringen (schneller, kein API-Cost)")
    parser.add_argument("--jd-id",      type=str, default=None,
                        help="Nur diese spezifische JD verarbeiten (UUID)")
    parser.add_argument("--experiment", type=str, default="composite",
                        choices=list(EXPERIMENTS.keys()),
                        help="Welches Experiment (default: composite)")
    parser.add_argument("--compare",    action="store_true", default=False,
                        help="Alle 3 Experimente laufen lassen + Comparison-Excel")
    # Recruiter-Filter
    parser.add_argument("--require-rtw", action="store_true", default=False,
                        help="Nur Kandidaten mit UK Right to Work zeigen")
    parser.add_argument("--min-years",   type=int, default=None,
                        help="Mindest-Erfahrungsjahre (überschreibt JD-Wert)")
    parser.add_argument("--require-skills", type=str, default=None,
                        help="Komma-getrennte Pflicht-Skills, z.B. 'Python,SQL'")
    args = parser.parse_args()

    # Pflicht-Skills parsen
    required_skills = None
    if args.require_skills:
        required_skills = [s.strip() for s in args.require_skills.split(",") if s.strip()]

    logger.info("=" * 60)
    logger.info("Week 4 — Intelligentes Matching mit 3-stufiger Pipeline")
    logger.info("=" * 60)
    if args.require_rtw:
        logger.info("  Filter: Nur UK Right to Work Kandidaten")
    if args.min_years:
        logger.info(f"  Filter: Mindest-Erfahrung = {args.min_years} Jahre")
    if required_skills:
        logger.info(f"  Filter: Pflicht-Skills = {required_skills}")

    conn = get_connection()
    try:
        jds = fetch_all_jds(conn, jd_id_filter=args.jd_id)
        cvs = fetch_all_cvs(conn)
        logger.info(f"Geladen: {len(jds)} JD(s)  |  {len(cvs)} CV(s)")

        # Domain-Übersicht loggen
        jd_domains = sorted(set(jd.get("profession_domain") or "unknown" for jd in jds))
        cv_domains = sorted(set(cv.get("profession_domain") or "unknown" for cv in cvs))
        logger.info(f"JD-Domänen:  {jd_domains}")
        logger.info(f"CV-Domänen:  {cv_domains}")

        if not jds or not cvs:
            logger.error("Keine JDs oder CVs gefunden. Zuerst Skripte 01-05 ausführen.")
            sys.exit(1)

        experiments_to_run = list(EXPERIMENTS.keys()) if args.compare else [args.experiment]
        results_by_experiment = {}

        for exp_name in experiments_to_run:
            cfg = EXPERIMENTS[exp_name]
            logger.info(f"\n{'─' * 60}")
            logger.info(f"EXPERIMENT: {exp_name}  —  {cfg['description']}")
            logger.info(f"Gewichte → Semantik:{cfg['w_sem']}  Skills:{cfg['w_skill']}  Erfahrung:{cfg['w_exp']}")
            logger.info(f"{'─' * 60}")

            all_matches = []
            for jd in jds:
                matches = match_jd_to_cvs(
                    jd=jd, cvs=cvs, weights=cfg,
                    top_n=args.top_n,
                    generate_explanations=args.explain,
                    require_rtw=args.require_rtw,
                    min_years_override=args.min_years,
                    required_skills=required_skills,
                )
                save_match_results(conn, matches, experiment_id=exp_name)
                all_matches.extend(matches)

                # Top 3 in der Konsole anzeigen
                relevant = [m for m in matches if m["domain_match"] and m["filter_passed"]]
                logger.info(
                    f"  → {len(relevant)} relevante Kandidaten "
                    f"(von {len(matches)} gesamt)"
                )
                for m in matches[:3]:
                    domain_icon = "✓" if m["domain_match"] else "✗"
                    filter_icon = "✓" if m["filter_passed"] else "⚠"
                    logger.info(
                        f"    #{m['rank_position']:2d}  {m['anon_ref']}  "
                        f"[{m.get('cv_domain','?')}] "
                        f"domain:{domain_icon} filter:{filter_icon}  "
                        f"composite={m.get('composite_score', m['semantic_score']):.3f}  "
                        f"sem={m['semantic_score']:.3f}  "
                        f"skills={m['skill_overlap_pct']}%  "
                        f"exp_fit={m['experience_fit']:.2f}"
                    )

            results_by_experiment[exp_name] = all_matches
            logger.info(f"\n  ✓ {exp_name}: {len(all_matches)} Matches gespeichert")

        export_to_excel(results_by_experiment)

        logger.info(f"\n{'=' * 60}")
        logger.info("WEEK 4 MATCHING ABGESCHLOSSEN")
        logger.info(f"{'=' * 60}")
        logger.info(f"  Experimente: {', '.join(experiments_to_run)}")
        logger.info(f"  Output:      {EXCEL_OUTPUT}")
        logger.info("\nNÄCHSTE SCHRITTE:")
        logger.info("1. docs/week4_results.xlsx öffnen")
        logger.info("2. 'recruiter_label' (0/1/2) in jedem Sheet ausfüllen")
        logger.info("3. Nur Zeilen mit domain_match=TRUE bewerten")
        logger.info("4. Im 'Comparison' Sheet: Rangunterschiede zwischen Experimenten prüfen")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
