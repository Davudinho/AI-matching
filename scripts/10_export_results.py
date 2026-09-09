"""
scripts/10_export_results.py — Excel-Export aus DB (ohne API-Calls)

Benutze dieses Skript wenn:
- Das Matching (08_ai_match.py) erfolgreich war
- Der Excel-Export fehlgeschlagen ist (z.B. Datei war geöffnet)
- Du die Ergebnisse erneut exportieren willst ohne neue API-Calls

Liest alle Ergebnisse aus ai_match_results + candidates + job_descriptions
und schreibt docs/evaluation_results_III.xlsx neu.
"""

import json
import logging
import sys
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras

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

EXCEL_OUTPUT = PROJECT_ROOT / "docs" / "evaluation_results_III.xlsx"


def get_connection():
    db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    return psycopg2.connect(db_url)


def fetch_results(conn) -> list[dict]:
    """Alle Ergebnisse aus ai_match_results mit JD- und CV-Details."""
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("""
        SELECT
            r.id,
            r.jd_id,
            r.cv_id,
            r.stage1_passed,
            r.stage1_score,
            r.stage1_reason,
            r.stage2_score,
            r.stage2_met_count,
            r.stage2_total_count,
            r.stage2_breakdown,
            r.stage2_critical_gaps,
            r.stage3_explanation,
            r.stage3_verdict,
            r.final_score,
            r.final_rank,
            r.created_at,

            -- JD fields
            j.title          AS jd_title,
            j.organisation   AS jd_organisation,

            -- CV fields
            c.anon_ref,
            c.current_title,
            c.years_experience,
            c.profession_domain,
            c.career_summary,
            c.right_to_work_uk

        FROM ai_match_results r
        JOIN job_descriptions j ON r.jd_id = j.jd_id
        JOIN candidates       c ON r.cv_id = c.cv_id
        ORDER BY j.title, r.final_score DESC NULLS LAST
    """)
    rows = cursor.fetchall()
    cursor.close()
    return [dict(row) for row in rows]


def export_to_excel(results: list[dict]):
    if not results:
        logger.error("Keine Ergebnisse in der Datenbank gefunden.")
        return

    logger.info(f"  {len(results)} Ergebnisse geladen → exportiere nach Excel...")

    with pd.ExcelWriter(EXCEL_OUTPUT, engine="openpyxl") as writer:

        all_rows = []
        jds_seen: dict[str, list] = {}

        for r in results:
            jt = r.get("jd_title", "Unbekannt")
            jds_seen.setdefault(jt, []).append(r)

        for jd_title, matches in jds_seen.items():
            rows = []
            for rank, m in enumerate(matches, start=1):

                s2_reqs = m.get("stage2_breakdown") or []
                if isinstance(s2_reqs, str):
                    try:
                        s2_reqs = json.loads(s2_reqs)
                    except Exception:
                        s2_reqs = []

                s2_detail = "\n".join(
                    f"[{r2.get('score',0)}/10] {str(r2.get('requirement',''))[:50]}: "
                    f"{str(r2.get('evidence',''))[:60]}"
                    for r2 in s2_reqs[:5] if isinstance(r2, dict)
                ) if s2_reqs else ""

                s2_gaps = m.get("stage2_critical_gaps") or []
                if isinstance(s2_gaps, str):
                    try:
                        s2_gaps = json.loads(s2_gaps)
                    except Exception:
                        s2_gaps = []

                row = {
                    # Rang & Ergebnis
                    "rang":             rank,
                    "anon_ref":         m.get("anon_ref", ""),
                    "kandidat_titel":   m.get("current_title", ""),
                    "jd_titel":         jd_title,
                    "organisation":     m.get("jd_organisation", ""),

                    # Stufe 1
                    "stufe1_relevant":  "✓ JA" if m.get("stage1_passed") else "✗ NEIN",
                    "stufe1_score":     m.get("stage1_score", 0),
                    "stufe1_begruendung": m.get("stage1_reason", ""),

                    # Stufe 2
                    "stufe2_score":         m.get("stage2_score") or "",
                    "anforderungen_erfuellt": (
                        f"{m.get('stage2_met_count',0)}/{m.get('stage2_total_count',0)}"
                        if m.get("stage1_passed") else ""
                    ),
                    "anforderungen_detail": s2_detail,
                    "kritische_luecken":    "; ".join(s2_gaps[:3]) if s2_gaps else "",

                    # Stufe 3
                    "stufe3_verdict":   m.get("stage3_verdict", ""),
                    "stufe3_report":    m.get("stage3_explanation", ""),

                    # Final
                    "final_score":      round(m.get("final_score") or 0, 2),

                    # Für Recruiter
                    "recruiter_label":  "",   # 0=Nein, 1=Vielleicht, 2=Ja
                    "recruiter_notizen": "",

                    # Kandidaten-Info
                    "erfahrung_jahre":  m.get("years_experience", ""),
                    "profession_domain": m.get("profession_domain", ""),
                    "right_to_work_uk": "✓" if m.get("right_to_work_uk") else "?",
                    "karriere_summary": (m.get("career_summary") or "")[:200],
                }
                rows.append(row)
                all_rows.append(row)

            df = pd.DataFrame(rows)

            # Sheet-Name: max 31 Zeichen (Excel-Limit)
            sheet_name = jd_title[:28] + "..." if len(jd_title) > 31 else jd_title
            df.to_excel(writer, sheet_name=sheet_name, index=False)

            # Spaltenbreiten anpassen
            ws = writer.sheets[sheet_name]
            for col in ws.columns:
                max_len = max(
                    (len(str(cell.value)) if cell.value else 0 for cell in col),
                    default=10
                )
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 60)

        # Übersichts-Sheet
        df_all = pd.DataFrame(all_rows)
        df_all.to_excel(writer, sheet_name="Alle Ergebnisse", index=False)

        # Anleitung-Sheet
        anleitung = pd.DataFrame([
            {"Spalte": "recruiter_label",
             "Bedeutung": "0 = Kein Match  |  1 = Möglicher Match  |  2 = Guter Match"},
            {"Spalte": "stufe1_relevant",
             "Bedeutung": "✓ JA = Kandidat hat Stufe 1 (Berufs-Gate) bestanden"},
            {"Spalte": "stufe2_score",
             "Bedeutung": "0-10: Wie gut erfüllt der Kandidat die Anforderungen?"},
            {"Spalte": "stufe3_verdict",
             "Bedeutung": "Strong Match / Possible Match / Weak Match"},
            {"Spalte": "final_score",
             "Bedeutung": "Gesamtscore: 35% Stufe1 + 65% Stufe2 (+ Stufe3 Bonus)"},
            {"Spalte": "recruiter_notizen",
             "Bedeutung": "Deine optionalen Kommentare für jede Zeile"},
        ])
        anleitung.to_excel(writer, sheet_name="Anleitung", index=False)

    logger.info(f"✓ Exportiert nach: {EXCEL_OUTPUT}")


def main():
    logger.info("=" * 60)
    logger.info("Export: ai_match_results → Excel")
    logger.info("=" * 60)

    conn = get_connection()
    try:
        results = fetch_results(conn)
        logger.info(f"  {len(results)} Paare in DB gefunden")

        if not results:
            logger.error("Keine Ergebnisse. Bitte zuerst 08_ai_match.py ausführen.")
            sys.exit(1)

        # Zusammenfassung
        s1 = sum(1 for r in results if r.get("stage1_passed"))
        strong   = sum(1 for r in results if r.get("stage3_verdict") == "Strong Match")
        possible = sum(1 for r in results if r.get("stage3_verdict") == "Possible Match")
        logger.info(f"  Stufe 1 bestanden:  {s1}/{len(results)}")
        logger.info(f"  Strong Match:       {strong}")
        logger.info(f"  Possible Match:     {possible}")
        logger.info("")

        export_to_excel(results)

        logger.info("\nNÄCHSTER SCHRITT:")
        logger.info(f"  {EXCEL_OUTPUT} öffnen und recruiter_label (0/1/2) ausfüllen")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
