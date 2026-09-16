"""
scripts/11_export_results_en.py — English Excel Export from DB (no API calls)

Reads all results from ai_match_results + candidates + job_descriptions
and writes docs/evaluation_results_EN.xlsx with all content in English.

HOW TO RUN:
    python scripts/11_export_results_en.py

OUTPUT:
    docs/evaluation_results_EN.xlsx
"""

import json
import logging
import sys
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from backend.app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

EXCEL_OUTPUT = PROJECT_ROOT / "docs" / "evaluation_results_EN.xlsx"


# ============================================================
# Column definitions
# ============================================================

COL_KEYS = [
    "rank", "final_score", "is_top_match", "ml_confidence",
    "job_title", "organisation",
    "candidate_ref", "candidate_title", "years_experience",
    "profession_domain", "right_to_work_uk", "career_summary",
    "stage1_passed", "stage1_score", "stage1_reason",
    "stage2_score", "requirements_met", "requirements_detail", "critical_gaps",
    "stage3_verdict", "stage3_report",
    "recruiter_decision", "recruiter_notes",
]

COL_HEADERS = {
    "rank":                "Rank",
    "final_score":         "Final Score",
    "is_top_match":        "Top Match?",
    "ml_confidence":       "ML Confidence",
    "job_title":           "Job Title",
    "organisation":        "Organisation",
    "candidate_ref":       "Candidate Ref",
    "candidate_title":     "Candidate Title / Current Role",
    "years_experience":    "Years Exp.",
    "profession_domain":   "Professional Domain",
    "right_to_work_uk":    "UK Right to Work",
    "career_summary":      "Career Summary",
    "stage1_passed":       "Stage 1: Passed?",
    "stage1_score":        "Stage 1: Score (0-10)",
    "stage1_reason":       "Stage 1: Reason",
    "stage2_score":        "Stage 2: Score (0-10)",
    "requirements_met":    "Requirements Met",
    "requirements_detail": "Requirements Detail",
    "critical_gaps":       "Critical Gaps",
    "stage3_verdict":      "Stage 3: Verdict",
    "stage3_report":       "Stage 3: Full Report",
    "recruiter_decision":  "Recruiter Decision (0/1/2)",
    "recruiter_notes":     "Recruiter Notes",
}

COL_WIDTHS = {
    "rank":                6,
    "final_score":         11,
    "is_top_match":        12,
    "ml_confidence":       14,
    "job_title":           28,
    "organisation":        22,
    "candidate_ref":       14,
    "candidate_title":     28,
    "years_experience":    10,
    "profession_domain":   18,
    "right_to_work_uk":    15,
    "career_summary":      45,
    "stage1_passed":       14,
    "stage1_score":        14,
    "stage1_reason":       42,
    "stage2_score":        14,
    "requirements_met":    16,
    "requirements_detail": 60,
    "critical_gaps":       42,
    "stage3_verdict":      24,
    "stage3_report":       70,
    "recruiter_decision":  20,
    "recruiter_notes":     36,
}


# ============================================================
# Database
# ============================================================

def get_connection():
    db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    return psycopg2.connect(db_url)


def fetch_results(conn) -> list[dict]:
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("""
        SELECT
            r.stage1_passed, r.stage1_score, r.stage1_reason,
            r.stage2_score, r.stage2_met_count, r.stage2_total_count,
            r.stage2_breakdown, r.stage2_critical_gaps,
            r.stage3_explanation, r.stage3_verdict,
            r.final_score, r.final_rank,
            r.is_top_match, r.ml_confidence, r.recruiter_label,
            j.title AS jd_title, j.organisation AS jd_organisation,
            c.anon_ref, c.current_title, c.years_experience,
            c.profession_domain, c.career_summary, c.right_to_work_uk
        FROM ai_match_results r
        JOIN job_descriptions j ON r.jd_id = j.jd_id
        JOIN candidates       c ON r.cv_id = c.cv_id
        ORDER BY j.title, r.final_score DESC NULLS LAST
    """)
    rows = cursor.fetchall()
    cursor.close()
    return [dict(row) for row in rows]


# ============================================================
# Translation (existing DB data may be in German)
# ============================================================

def _translate_strings_via_gemini(texts: list[str]) -> dict[str, str]:
    """
    Batch-translate a list of German strings to English via Gemini.
    Returns a dict mapping original -> translated.
    Only non-empty, non-English strings are sent.
    """
    if not texts:
        return {}

    try:
        from google import genai
        from google.genai import types as genai_types
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
    except Exception as e:
        logger.warning(f"Translation skipped — Gemini unavailable: {e}")
        return {}

    # Deduplicate and filter empty strings
    unique = list({t for t in texts if t and t.strip()})
    if not unique:
        return {}

    logger.info(f"  Translating {len(unique)} unique strings to English via Gemini...")

    # Send as numbered list so Gemini can map them back
    numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(unique))
    prompt = (
        "Translate the following numbered items from German to English. "
        "If an item is already in English, return it unchanged. "
        "Return ONLY a JSON object mapping each number (as string key) to its English translation. "
        "Do not add explanations.\n\n"
        f"{numbered}\n\n"
        "Respond with: {\"1\": \"translation...\", \"2\": \"translation...\", ...}"
    )

    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )
        raw = response.text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        mapping_by_num = json.loads(raw)
        result = {}
        for i, original in enumerate(unique):
            translated = mapping_by_num.get(str(i + 1), original)
            result[original] = translated
        logger.info(f"  Translation complete: {len(result)} strings translated")
        return result
    except Exception as e:
        logger.warning(f"  Translation failed: {e} — using original text")
        return {}


def translate_results(results: list[dict]) -> list[dict]:
    """
    Translate German text fields in DB results to English.
    Fields affected: stage2_critical_gaps items, stage2_breakdown evidence strings.
    stage1_reason and stage3_explanation are already in English (per prompt design).
    """
    # Collect all strings that need translation
    to_translate = set()

    for r in results:
        # critical_gaps
        gaps = _parse_json_field(r.get("stage2_critical_gaps"))
        for g in gaps:
            if isinstance(g, str) and g:
                to_translate.add(g)

        # stage2_breakdown evidence
        breakdown = _parse_json_field(r.get("stage2_breakdown"))
        for item in breakdown:
            if isinstance(item, dict):
                ev = item.get("evidence", "")
                if ev and isinstance(ev, str):
                    to_translate.add(ev)

    if not to_translate:
        logger.info("  No translation needed — all text appears to be in English already")
        return results

    translation_map = _translate_strings_via_gemini(list(to_translate))

    if not translation_map:
        return results  # translation failed, use originals

    # Apply translations
    for r in results:
        gaps = _parse_json_field(r.get("stage2_critical_gaps"))
        r["stage2_critical_gaps"] = [
            translation_map.get(g, g) if isinstance(g, str) else g
            for g in gaps
        ]

        breakdown = _parse_json_field(r.get("stage2_breakdown"))
        for item in breakdown:
            if isinstance(item, dict) and isinstance(item.get("evidence"), str):
                item["evidence"] = translation_map.get(item["evidence"], item["evidence"])
        r["stage2_breakdown"] = breakdown

    return results


# ============================================================
# Row builder
# ============================================================

def _parse_json_field(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return []
    return []


def build_row(rank: int, m: dict) -> dict:
    stage1_passed = bool(m.get("stage1_passed"))

    # Stage 2 breakdown
    s2_reqs = _parse_json_field(m.get("stage2_breakdown"))
    s2_gaps = _parse_json_field(m.get("stage2_critical_gaps"))

    # Requirements detail (full text, no truncation)
    s2_detail = "\n".join(
        f"[{r.get('score', 0)}/10] {r.get('requirement', '')}: "
        f"{r.get('evidence', 'No evidence found')}"
        for r in s2_reqs if isinstance(r, dict)
    ) if s2_reqs else ""

    # Stage 2 labels
    s2_score = m.get("stage2_score")
    if not stage1_passed:
        s2_score_label  = "n/a — Stage 1 not passed"
        reqs_met_label  = "n/a — Stage 1 not passed"
        gaps_label      = "n/a — Stage 1 not passed"
    elif s2_score is not None:
        s2_score_label  = round(float(s2_score), 1)
        met   = m.get("stage2_met_count", 0)
        total = m.get("stage2_total_count", 0)
        reqs_met_label  = f"{met} of {total}"
        gaps_label      = "; ".join(s2_gaps) if s2_gaps else "none identified"
    else:
        s2_score_label  = "not evaluated"
        reqs_met_label  = "not evaluated"
        gaps_label      = "not evaluated"

    # Stage 3 labels
    s3_verdict = m.get("stage3_verdict")
    s3_report  = m.get("stage3_explanation")
    if not stage1_passed:
        s3_verdict_label = "n/a — Stage 1 not passed"
        s3_report_label  = "n/a — Stage 1 not passed"
    elif s3_verdict is None:
        s3_verdict_label = "not analysed — not in Top 3"
        s3_report_label  = "not analysed — not in Top 3"
    else:
        s3_verdict_label = s3_verdict
        s3_report_label  = s3_report or ""

    # Candidate title — mark unreadable CVs clearly
    cv_title = m.get("current_title") or "[CV not readable — scanned image PDF]"

    return {
        "rank":                rank,
        "final_score":         round(m.get("final_score") or 0, 2),
        "is_top_match":        "YES" if m.get("is_top_match") else "NO",
        "ml_confidence":       round(m.get("ml_confidence"), 3) if m.get("ml_confidence") is not None else "",
        "job_title":           m.get("jd_title", ""),
        "organisation":        m.get("jd_organisation", ""),
        "candidate_ref":       m.get("anon_ref", ""),
        "candidate_title":     cv_title,
        "years_experience":    m.get("years_experience", ""),
        "profession_domain":   m.get("profession_domain", ""),
        "right_to_work_uk":    "Yes" if m.get("right_to_work_uk") else "Not stated",
        "career_summary":      m.get("career_summary") or "",
        "stage1_passed":       "YES" if stage1_passed else "NO",
        "stage1_score":        m.get("stage1_score", 0),
        "stage1_reason":       m.get("stage1_reason", ""),
        "stage2_score":        s2_score_label,
        "requirements_met":    reqs_met_label,
        "requirements_detail": s2_detail,
        "critical_gaps":       gaps_label,
        "stage3_verdict":      s3_verdict_label,
        "stage3_report":       s3_report_label,
        "recruiter_decision":  m.get("recruiter_label", "") if m.get("recruiter_label") is not None else "",
        "recruiter_notes":     "",
    }


# ============================================================
# Styling
# ============================================================

C_HDR_BG  = "1A1A2E"
C_HDR_FG  = "FFFFFF"
C_YES_BG  = "D4EFDF"
C_YES_FG  = "1E8449"
C_NO_BG   = "FADBD8"
C_NO_FG   = "922B21"
C_STRONG  = "D5F5E3"
C_POSSIBL = "FEF9E7"
C_WEAK    = "FADBD8"
C_ALT     = "F8F9FA"
C_REC     = "EBF5FB"

THIN = Border(
    left=Side(style="thin", color="CCCCCC"),
    right=Side(style="thin", color="CCCCCC"),
    top=Side(style="thin", color="CCCCCC"),
    bottom=Side(style="thin", color="CCCCCC"),
)


def apply_styles(ws, col_keys: list[str]):
    # Header row
    hdr_fill = PatternFill("solid", fgColor=C_HDR_BG)
    hdr_font = Font(bold=True, color=C_HDR_FG, name="Calibri", size=10)
    for cell in ws[1]:
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN
    ws.row_dimensions[1].height = 32

    # Column index lookup
    top_col = col_keys.index("is_top_match") + 1 if "is_top_match" in col_keys else None
    s1_col  = col_keys.index("stage1_passed") + 1  if "stage1_passed"  in col_keys else None
    s3_col  = col_keys.index("stage3_verdict") + 1 if "stage3_verdict" in col_keys else None
    rec_cols = {
        col_keys.index("recruiter_decision") + 1 if "recruiter_decision" in col_keys else -1,
        col_keys.index("recruiter_notes") + 1     if "recruiter_notes"    in col_keys else -1,
    }

    base_font = Font(name="Calibri", size=9)
    bold_font = Font(name="Calibri", size=9, bold=True)

    for row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
        alt = row_idx % 2 == 0
        for cell in row:
            c = cell.column
            cell.border = THIN
            cell.font = base_font
            cell.alignment = Alignment(vertical="top", wrap_text=True)

            # Background
            if c in rec_cols:
                cell.fill = PatternFill("solid", fgColor=C_REC)
            elif alt:
                cell.fill = PatternFill("solid", fgColor=C_ALT)

            # Top Match colour
            if c == top_col and cell.value:
                v = str(cell.value).upper()
                if "YES" in v:
                    cell.fill = PatternFill("solid", fgColor=C_STRONG)
                    cell.font = Font(name="Calibri", size=9, bold=True, color=C_YES_FG)

            # Stage 1 colour
            if c == s1_col and cell.value:
                v = str(cell.value).upper()
                if "YES" in v:
                    cell.fill = PatternFill("solid", fgColor=C_YES_BG)
                    cell.font = Font(name="Calibri", size=9, bold=True, color=C_YES_FG)
                elif "NO" in v:
                    cell.fill = PatternFill("solid", fgColor=C_NO_BG)
                    cell.font = Font(name="Calibri", size=9, bold=True, color=C_NO_FG)

            # Stage 3 colour
            if c == s3_col and cell.value:
                v = str(cell.value)
                if "Strong" in v:
                    cell.fill = PatternFill("solid", fgColor=C_STRONG)
                    cell.font = bold_font
                elif "Possible" in v:
                    cell.fill = PatternFill("solid", fgColor=C_POSSIBL)
                elif "Weak" in v:
                    cell.fill = PatternFill("solid", fgColor=C_WEAK)

        ws.row_dimensions[row_idx].height = 75

    # Column widths
    for i, key in enumerate(col_keys, start=1):
        ws.column_dimensions[get_column_letter(i)].width = COL_WIDTHS.get(key, 15)

    # Freeze panes & filter
    ws.freeze_panes = "E2"
    ws.auto_filter.ref = ws.dimensions


# ============================================================
# Guide sheet
# ============================================================

GUIDE_ROWS = [
    ("rank",
     "Overall rank per job (1 = best candidate for that role)."),
    ("final_score (0–10)",
     "Weighted composite: 30% Stage 1 + 55% Stage 2 + 15% Stage 3. "
     "If Stage 3 not run: 35% Stage 1 + 65% Stage 2."),
    ("Top Match?",
     "YES = Final score meets or exceeds the role-specific calibrated threshold. "
     "NO = Below threshold for this specific role category."),
    ("ML Confidence",
     "Calibrated probability (0.00 to 1.00) from the machine learning model, "
     "estimating likelihood of being a top interview match based on historical feedback."),
    ("Stage 1: Passed?",
     "YES = Candidate's professional background fits this role. "
     "NO = Wrong profession — Stages 2 & 3 were not run (cost saving)."),
    ("Stage 1: Score (0–10)",
     "0 = completely wrong profession. 10 = perfect professional match."),
    ("Stage 2: Score (0–10)",
     "How well the candidate meets the essential requirements. "
     "MOST IMPORTANT SCORE. "
     "0–3: little evidence. 4–6: partial. 7–9: strong. 10: perfect."),
    ("Requirements Met",
     "e.g. '3 of 5' = 3 out of 5 essential requirements scored >= 7/10."),
    ("Requirements Detail",
     "Per-requirement breakdown: [score/10] requirement text: evidence found in CV."),
    ("Critical Gaps",
     "Key qualifications or experience that are missing for this specific role."),
    ("Stage 3: Verdict",
     "Strong Match / Possible Match / Weak Match — "
     "only for the Top 3 candidates per role (expensive step). "
     "'not analysed — not in Top 3' = candidate did not reach this stage."),
    ("Stage 3: Full Report",
     "AI-written match report: Strengths (with evidence from CV), Gaps, Recommendation."),
    ("Recruiter Decision (0/1/2)",
     "TO BE FILLED IN: 0 = No match  |  1 = Possible  |  2 = Good match"),
    ("UK Right to Work",
     "'Yes' = explicitly stated in CV. 'Not stated' = not mentioned — verify with candidate."),
    ("[CV not readable]",
     "This candidate's CV was a scanned image PDF — no text could be extracted. "
     "No AI analysis was possible. Request a text-based PDF or Word document from the applicant."),
    ("Scoring system",
     "The 3-stage funnel filters candidates efficiently: "
     "Stage 1 (profession gate) → Stage 2 (requirements scoring) → "
     "Stage 3 (deep report, Top 3 only). "
     "Most candidates stop at Stage 1 to save cost and time."),
]


def write_guide_sheet(writer):
    df = pd.DataFrame(GUIDE_ROWS, columns=["Column / Field", "Description"])
    df.to_excel(writer, sheet_name="Guide", index=False)

    ws = writer.sheets["Guide"]
    hdr_fill = PatternFill("solid", fgColor="2C3E50")
    hdr_font = Font(bold=True, color="FFFFFF", name="Calibri", size=10)
    for cell in ws[1]:
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN
    ws.row_dimensions[1].height = 28

    row_font = Font(name="Calibri", size=9)
    for row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
        for cell in row:
            cell.font = row_font
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = THIN
        ws.row_dimensions[row_idx].height = 50

    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 85
    ws.freeze_panes = "A2"


# ============================================================
# Main export
# ============================================================

def export_to_excel(results: list[dict]):
    if not results:
        logger.error("No results found in the database.")
        return

    logger.info(f"  {len(results)} results loaded — building Excel...")

    # Group by JD
    jds: dict[str, list] = {}
    for r in results:
        jds.setdefault(r.get("jd_title", "Unknown"), []).append(r)

    with pd.ExcelWriter(EXCEL_OUTPUT, engine="openpyxl") as writer:

        all_rows = []

        for jd_title, matches in jds.items():
            # Sort: Stage 1 passed first, then by final_score descending
            matches_sorted = sorted(
                matches,
                key=lambda x: (not x.get("stage1_passed", False), -(x.get("final_score") or 0)),
            )

            rows = [build_row(rank, m) for rank, m in enumerate(matches_sorted, start=1)]
            all_rows.extend(rows)

            df = pd.DataFrame(rows, columns=COL_KEYS)
            df.rename(columns=COL_HEADERS, inplace=True)

            sheet_name = jd_title[:28] + "..." if len(jd_title) > 31 else jd_title
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            apply_styles(writer.sheets[sheet_name], COL_KEYS)
            logger.info(f"  Sheet '{sheet_name}': {len(rows)} candidates")

        # All Results sheet
        df_all = pd.DataFrame(all_rows, columns=COL_KEYS)
        df_all.rename(columns=COL_HEADERS, inplace=True)
        df_all.to_excel(writer, sheet_name="All Results", index=False)
        apply_styles(writer.sheets["All Results"], COL_KEYS)

        # Guide sheet
        write_guide_sheet(writer)

    logger.info(f"Exported: {EXCEL_OUTPUT}")


def main():
    logger.info("=" * 60)
    logger.info("Export: ai_match_results -> Excel (English, fully styled)")
    logger.info("=" * 60)

    conn = get_connection()
    try:
        results = fetch_results(conn)
        logger.info(f"  {len(results)} candidate-job pairs in DB")

        if not results:
            logger.error("No results. Please run 08_ai_match.py first.")
            sys.exit(1)

        s1       = sum(1 for r in results if r.get("stage1_passed"))
        strong   = sum(1 for r in results if r.get("stage3_verdict") == "Strong Match")
        possible = sum(1 for r in results if r.get("stage3_verdict") == "Possible Match")
        weak     = sum(1 for r in results if r.get("stage3_verdict") == "Weak Match")
        no_text  = sum(1 for r in results if not r.get("current_title") and not r.get("career_summary"))

        logger.info(f"  Stage 1 passed:       {s1}/{len(results)}")
        logger.info(f"  Strong Match:         {strong}")
        logger.info(f"  Possible Match:       {possible}")
        logger.info(f"  Weak Match:           {weak}")
        logger.info(f"  CVs not parseable:    {no_text} (scanned PDFs without text)")
        logger.info("")

        # Translate any German text from existing DB data to English
        logger.info("Translating DB text fields to English...")
        results = translate_results(results)

        export_to_excel(results)

        logger.info("\nNEXT STEPS:")
        logger.info(f"  1. Open {EXCEL_OUTPUT}")
        logger.info("  2. Review each job sheet (Stage 1 YES candidates first)")
        logger.info("  3. Fill in 'Recruiter Decision' column (0 = No / 1 = Possible / 2 = Good)")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
