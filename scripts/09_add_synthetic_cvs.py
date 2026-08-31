"""
scripts/09_add_synthetic_cvs.py — Synthetische CVs für Pipeline-Tests

WARUM SYNTHETISCHE CVs?
    Unser reales Dataset enthält nur Graphic/Digital Designer CVs.
    Die 8 JDs decken aber 7 verschiedene Berufsfelder ab (Finance,
    Legal, Risk, Healthcare, Procurement, Technology, Creative & Media).

    Synthetische CVs erlauben uns:
    1. Die vollständige 3-stufige Pipeline zu testen
    2. Echte "Strong Match" und "Possible Match" Ergebnisse zu erzeugen
    3. Den Unterschied zwischen guten und schlechten Matches zu demonstrieren

DESIGN DER SYNTHETISCHEN CVs:
    - SYNTH-001: Senior Creative Producer (Film)    → passt zu JD "Senior Creative Producer"
    - SYNTH-002: Digital Delivery Manager           → passt zu JD "Delivery Manager"
    - SYNTH-003: Finance Business Partner           → passt zu JD "Finance" JDs
    - SYNTH-004: Internal Audit Manager             → passt zu JD "Head of Risk and Internal Audit"
    - SYNTH-005: Commercial Solicitor               → passt zu JD "General Counsel"
    - SYNTH-006: Senior Procurement Manager         → passt zu JD "Procurement Lead"

    Alle CVs sind realistisch aber vollständig fiktiv (kein echter Kandidat).
    Alle haben UK Right to Work = True.

VERWENDETE ANON_REF: SYNTH-001 bis SYNTH-006
    Unterscheiden sich von realen CVs (CAND-001 bis CAND-009) an dem SYNTH-Prefix.
"""

import json
import logging
import sys
import uuid
from pathlib import Path

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


# ============================================================
# SYNTHETISCHE CV-DATEN
# ============================================================
#
# Jeder CV enthält alle Felder die in der candidates-Tabelle erwartet werden.
# Die Daten sind realistisch aber vollständig fiktiv.
# Wir benutzen typische UK-Charity/NGO/Government-Erfahrungen.

SYNTHETIC_CVS = [

    # ─────────────────────────────────────────────────────────
    # SYNTH-001: Senior Creative Producer (Film & Photography)
    # Ziel-JD: "Senior Creative Producer (Film & Photography)"
    # Erwartetes Ergebnis: Strong Match (Stufe 1: ~9/10)
    # ─────────────────────────────────────────────────────────
    {
        "anon_ref":         "SYNTH-001",
        "filename":         "synthetic_cv_creative_producer.pdf",
        "current_title":    "Senior Creative Producer (Film & Photography)",
        "years_experience": 9,
        "profession_domain": "Creative & Media",
        "career_summary": (
            "Award-winning Senior Creative Producer with 9 years specialising in documentary "
            "film, charity campaigns, and editorial photography for international NGOs. "
            "Proven track record managing end-to-end productions from concept to broadcast, "
            "leading cross-functional creative teams and delivering compelling visual storytelling."
        ),
        "skills_technical": [
            "Film Production", "Photography Direction", "Video Editing", "Adobe Premiere Pro",
            "Final Cut Pro", "Lightroom", "Storyboarding", "Scriptwriting",
            "Post-Production Management", "Budget Management", "Shoot Direction",
            "Motion Graphics", "Drone Cinematography",
        ],
        "skills_soft": [
            "Creative Leadership", "Stakeholder Management", "Team Direction",
            "Project Management", "Communication", "Problem Solving",
        ],
        "education": [
            {
                "degree":      "BA Film Studies & Photography",
                "institution": "University of the Arts London",
                "year":        "2015",
            }
        ],
        "certifications": [
            "APA (Advertising Producers Association) Member",
            "BAFTA Crew Alumni",
        ],
        "languages": ["English (Native)", "French (Conversational)"],
        "right_to_work_uk": True,
        "sector_experience": ["Charity / NGO", "Media", "Advertising", "Public Sector"],
        "work_history": [
            {
                "title":        "Senior Creative Producer",
                "organisation": "Save the Children UK",
                "start_date":   "2020",
                "end_date":     "Present",
                "description": (
                    "Lead creative producer for all film and photography campaigns. "
                    "Managed annual production budget of £1.2m. Directed 40+ documentary "
                    "shorts across Africa and Middle East. Won 3 Charity Film Awards."
                ),
            },
            {
                "title":        "Creative Producer",
                "organisation": "Comic Relief",
                "start_date":   "2017",
                "end_date":     "2020",
                "description": (
                    "Produced Red Nose Day and Sport Relief broadcast content. "
                    "Managed freelance film crews across 12 countries. "
                    "Delivered 60+ hours of broadcast-quality footage annually."
                ),
            },
            {
                "title":        "Junior Producer / Photographer",
                "organisation": "Stills Photography Agency",
                "start_date":   "2015",
                "end_date":     "2017",
                "description": (
                    "Editorial photography and short-form video production for "
                    "NGO clients including Oxfam and Médecins Sans Frontières."
                ),
            },
        ],
        "missing_fields":     [],
        "extraction_status":  "synthetic",
    },

    # ─────────────────────────────────────────────────────────
    # SYNTH-002: Digital Delivery Manager
    # Ziel-JD: "Delivery Manager (Online Products)"
    # Erwartetes Ergebnis: Strong Match (Stufe 1: ~9/10)
    # ─────────────────────────────────────────────────────────
    {
        "anon_ref":         "SYNTH-002",
        "filename":         "synthetic_cv_delivery_manager.pdf",
        "current_title":    "Digital Delivery Manager",
        "years_experience": 7,
        "profession_domain": "Technology",
        "career_summary": (
            "Results-driven Digital Delivery Manager with 7 years delivering agile digital "
            "products and online platforms for charity and public sector organisations. "
            "Experienced in Scrum, Kanban and SAFe frameworks, managing cross-functional "
            "teams of 15+ to deliver user-centred services on time and within budget."
        ),
        "skills_technical": [
            "Agile Delivery", "Scrum Master", "Kanban", "JIRA", "Confluence",
            "Product Roadmapping", "Sprint Planning", "Stakeholder Management",
            "Risk Management", "Digital Product Management", "User Research",
            "GDS (Government Digital Service)", "API Integration", "Data Analytics",
        ],
        "skills_soft": [
            "Leadership", "Communication", "Problem Solving", "Team Building",
            "Conflict Resolution", "Strategic Thinking",
        ],
        "education": [
            {
                "degree":      "MSc Digital Innovation Management",
                "institution": "King's College London",
                "year":        "2017",
            },
            {
                "degree":      "BSc Computer Science",
                "institution": "University of Manchester",
                "year":        "2016",
            },
        ],
        "certifications": [
            "Certified Scrum Master (CSM)",
            "PRINCE2 Practitioner",
            "SAFe 5 Agilist",
            "AWS Cloud Practitioner",
        ],
        "languages": ["English (Native)", "German (Basic)"],
        "right_to_work_uk": True,
        "sector_experience": ["Charity / NGO", "Public Sector", "Technology", "Education"],
        "work_history": [
            {
                "title":        "Digital Delivery Manager",
                "organisation": "UNICEF UK",
                "start_date":   "2021",
                "end_date":     "Present",
                "description": (
                    "Led delivery of UNICEF UK's digital fundraising platform overhaul. "
                    "Managed 4 agile squads (18 people). Increased online donations by 34% "
                    "in year 1. Introduced OKRs and quarterly delivery roadmaps."
                ),
            },
            {
                "title":        "Product Delivery Lead",
                "organisation": "NSPCC",
                "start_date":   "2019",
                "end_date":     "2021",
                "description": (
                    "Delivered digital safeguarding tools and public-facing online platforms. "
                    "Managed 3 concurrent product workstreams. Introduced automated testing "
                    "and CI/CD pipelines reducing release cycles from 6 weeks to 1 week."
                ),
            },
            {
                "title":        "Agile Delivery Consultant",
                "organisation": "Cabinet Office (GDS)",
                "start_date":   "2017",
                "end_date":     "2019",
                "description": (
                    "Supported GOV.UK service delivery teams with agile transformation. "
                    "Coached 5 product teams on GDS Service Standard and discovery phases."
                ),
            },
        ],
        "missing_fields":     [],
        "extraction_status":  "synthetic",
    },

    # ─────────────────────────────────────────────────────────
    # SYNTH-003: Finance Business Partner
    # Ziel-JDs: "Interim Head of Finance Business Partnering" & "Senior Finance Officer"
    # Erwartetes Ergebnis: Strong Match
    # ─────────────────────────────────────────────────────────
    {
        "anon_ref":         "SYNTH-003",
        "filename":         "synthetic_cv_finance_business_partner.pdf",
        "current_title":    "Head of Finance Business Partnering",
        "years_experience": 12,
        "profession_domain": "Finance",
        "career_summary": (
            "CIMA-qualified Head of Finance Business Partnering with 12 years in charity "
            "and public sector finance. Expert in management accounting, financial planning "
            "& analysis, and strategic finance partnering with senior leadership teams. "
            "Experienced in leading finance transformation projects and implementing ERP systems."
        ),
        "skills_technical": [
            "Financial Reporting", "Management Accounts", "Budget Management",
            "Financial Planning & Analysis (FP&A)", "ERP Systems (SAP, Oracle)",
            "Xero", "Sage", "Month-End Close", "Variance Analysis",
            "Cash Flow Forecasting", "Grant Reporting", "Statutory Accounts",
            "VAT Returns", "Payroll Oversight",
        ],
        "skills_soft": [
            "Business Partnering", "Strategic Thinking", "Stakeholder Influence",
            "Team Leadership", "Communication", "Problem Solving",
        ],
        "education": [
            {
                "degree":      "CIMA Qualified (Chartered Management Accountant)",
                "institution": "CIMA",
                "year":        "2014",
            },
            {
                "degree":      "BSc Economics",
                "institution": "London School of Economics",
                "year":        "2012",
            },
        ],
        "certifications": [
            "CIMA (Chartered Institute of Management Accountants)",
            "Charity Finance Group (CFG) Member",
        ],
        "languages": ["English (Native)"],
        "right_to_work_uk": True,
        "sector_experience": [
            "Charity / NGO", "Government / Public Sector", "Housing Association"
        ],
        "work_history": [
            {
                "title":        "Head of Finance Business Partnering",
                "organisation": "British Red Cross",
                "start_date":   "2019",
                "end_date":     "Present",
                "description": (
                    "Led a team of 6 finance business partners supporting 12 directorates. "
                    "Delivered £2m cost savings through zero-based budgeting. "
                    "Implemented Adaptive Insights planning tool reducing budget cycle by 40%."
                ),
            },
            {
                "title":        "Senior Finance Business Partner",
                "organisation": "London Borough of Southwark",
                "start_date":   "2016",
                "end_date":     "2019",
                "description": (
                    "Business partner to Director of Housing and Director of Children's Services. "
                    "Managed £85m combined budget. Prepared quarterly financial forecasts "
                    "and monthly management accounts for Corporate Leadership Team."
                ),
            },
            {
                "title":        "Management Accountant",
                "organisation": "Shelter",
                "start_date":   "2012",
                "end_date":     "2016",
                "description": (
                    "Produced monthly management accounts for 8 service areas. "
                    "Supported year-end statutory audit. Led the migration to Sage 200."
                ),
            },
        ],
        "missing_fields":     [],
        "extraction_status":  "synthetic",
    },

    # ─────────────────────────────────────────────────────────
    # SYNTH-004: Internal Audit & Risk Manager
    # Ziel-JD: "Head of Risk and Internal Audit"
    # Erwartetes Ergebnis: Strong Match
    # ─────────────────────────────────────────────────────────
    {
        "anon_ref":         "SYNTH-004",
        "filename":         "synthetic_cv_risk_audit_manager.pdf",
        "current_title":    "Head of Internal Audit & Risk",
        "years_experience": 11,
        "profession_domain": "Risk & Audit",
        "career_summary": (
            "CIIA-qualified Head of Internal Audit and Risk with 11 years in the charity "
            "and financial services sectors. Specialist in enterprise risk management (ERM), "
            "internal audit delivery, and governance frameworks. Experienced in audit committee "
            "reporting, fraud prevention, and regulatory compliance."
        ),
        "skills_technical": [
            "Internal Audit", "Risk Assessment", "Enterprise Risk Management (ERM)",
            "Governance & Compliance", "Audit Committee Reporting", "Control Framework Design",
            "ISO 31000", "IRM (Institute of Risk Management)", "Data Analytics for Audit",
            "Anti-Money Laundering (AML)", "Fraud Prevention",
            "Policy Development", "IT Audit", "GDPR Compliance",
        ],
        "skills_soft": [
            "Strategic Leadership", "Board Communication", "Independence & Objectivity",
            "Critical Thinking", "Stakeholder Influence", "Integrity",
        ],
        "education": [
            {
                "degree":      "Chartered Internal Auditor (CIIA)",
                "institution": "Chartered Institute of Internal Auditors",
                "year":        "2015",
            },
            {
                "degree":      "BA Accounting & Finance",
                "institution": "University of Birmingham",
                "year":        "2013",
            },
        ],
        "certifications": [
            "CIIA (Chartered Internal Auditor)",
            "IRM Certificate in Risk Management",
            "CISA (Certified Information Systems Auditor)",
        ],
        "languages": ["English (Native)", "Mandarin (Intermediate)"],
        "right_to_work_uk": True,
        "sector_experience": [
            "Charity / NGO", "Financial Services", "NHS / Healthcare", "Housing"
        ],
        "work_history": [
            {
                "title":        "Head of Internal Audit & Risk",
                "organisation": "Macmillan Cancer Support",
                "start_date":   "2020",
                "end_date":     "Present",
                "description": (
                    "Responsible for the charity's entire internal audit programme and "
                    "enterprise risk management framework. Reports to Audit & Risk Committee. "
                    "Led cyber security audit resulting in 40% reduction in critical vulnerabilities. "
                    "Introduced risk appetite framework adopted at Board level."
                ),
            },
            {
                "title":        "Senior Internal Auditor",
                "organisation": "Lloyds Banking Group",
                "start_date":   "2017",
                "end_date":     "2020",
                "description": (
                    "Delivered complex financial and operational audits across retail banking. "
                    "Managed audit teams of 4-6 on individual assignments. "
                    "Identified £3.2m of control weaknesses in mortgage book."
                ),
            },
            {
                "title":        "Internal Auditor",
                "organisation": "NHS England",
                "start_date":   "2013",
                "end_date":     "2017",
                "description": (
                    "Conducted VFM (Value for Money) and compliance audits across NHS trusts. "
                    "Reported findings to Trust Audit Committees and CFOs."
                ),
            },
        ],
        "missing_fields":     [],
        "extraction_status":  "synthetic",
    },

    # ─────────────────────────────────────────────────────────
    # SYNTH-005: Commercial Solicitor / General Counsel
    # Ziel-JD: "General Counsel"
    # Erwartetes Ergebnis: Strong Match
    # ─────────────────────────────────────────────────────────
    {
        "anon_ref":         "SYNTH-005",
        "filename":         "synthetic_cv_general_counsel.pdf",
        "current_title":    "Deputy General Counsel",
        "years_experience": 14,
        "profession_domain": "Legal",
        "career_summary": (
            "Qualified solicitor and Deputy General Counsel with 14 years of in-house and "
            "private practice experience in the charity, media, and technology sectors. "
            "Expert in commercial contracts, employment law, GDPR/data protection, "
            "charity governance, and IP/brand protection. Experienced advising Boards and Trustees."
        ),
        "skills_technical": [
            "Commercial Contract Drafting", "Employment Law", "GDPR / Data Protection",
            "Charity Law", "Intellectual Property", "Litigation Management",
            "Corporate Governance", "Board Secretariat", "Company Law",
            "Regulatory Compliance", "Legal Project Management",
            "Risk Management", "Fundraising Regulations",
        ],
        "skills_soft": [
            "Board-Level Communication", "Strategic Legal Advice", "Influencing",
            "Leadership", "Commercial Awareness", "Integrity",
        ],
        "education": [
            {
                "degree":      "LPC (Legal Practice Course) — Distinction",
                "institution": "BPP University Law School",
                "year":        "2010",
            },
            {
                "degree":      "LLB Law (First Class Honours)",
                "institution": "University of Cambridge",
                "year":        "2009",
            },
        ],
        "certifications": [
            "Solicitor of the Senior Courts of England and Wales",
            "GDPR Practitioner Certificate",
            "Company Secretary Diploma (ICSA)",
        ],
        "languages": ["English (Native)", "Spanish (Professional Working Proficiency)"],
        "right_to_work_uk": True,
        "sector_experience": ["Charity / NGO", "Media", "Technology", "Financial Services"],
        "work_history": [
            {
                "title":        "Deputy General Counsel",
                "organisation": "WWF-UK",
                "start_date":   "2019",
                "end_date":     "Present",
                "description": (
                    "Second-in-command to the General Counsel. Manages a team of 4 lawyers "
                    "and 2 paralegals. Leads on all commercial contracts, partnership agreements, "
                    "and international licensing. Advises Board of Trustees on governance matters. "
                    "Led GDPR implementation programme across the organisation."
                ),
            },
            {
                "title":        "Senior Legal Counsel",
                "organisation": "Channel 4",
                "start_date":   "2015",
                "end_date":     "2019",
                "description": (
                    "In-house counsel for commissioning, rights and production divisions. "
                    "Negotiated £50m+ of commissioning contracts annually. "
                    "Managed IP disputes and talent agreements."
                ),
            },
            {
                "title":        "Solicitor — Corporate & Commercial",
                "organisation": "Clifford Chance LLP",
                "start_date":   "2010",
                "end_date":     "2015",
                "description": (
                    "Associate in corporate and commercial team. "
                    "Advised FTSE 100 clients on M&A, JVs and major commercial transactions. "
                    "Qualified solicitor in 2012 after training contract."
                ),
            },
        ],
        "missing_fields":     [],
        "extraction_status":  "synthetic",
    },

    # ─────────────────────────────────────────────────────────
    # SYNTH-006: Senior Procurement Manager
    # Ziel-JD: "Procurement Lead"
    # Erwartetes Ergebnis: Strong Match
    # ─────────────────────────────────────────────────────────
    {
        "anon_ref":         "SYNTH-006",
        "filename":         "synthetic_cv_procurement_manager.pdf",
        "current_title":    "Senior Procurement Manager",
        "years_experience": 8,
        "profession_domain": "Procurement",
        "career_summary": (
            "CIPS-qualified Senior Procurement Manager with 8 years leading procurement "
            "functions in charity and public sector organisations. Expert in strategic "
            "sourcing, supplier relationship management, and contract management. "
            "Delivered £4.5m of savings over 5 years through category management and "
            "competitive tendering. Experienced in EU procurement regulations and PCR 2015."
        ),
        "skills_technical": [
            "Strategic Sourcing", "Category Management", "Supplier Relationship Management",
            "Contract Management", "Competitive Tendering", "PCR 2015 (Public Contracts Regulations)",
            "EU Procurement", "Spend Analysis", "P2P (Procure-to-Pay)",
            "SAP Ariba", "Oracle Fusion", "Purchase Order Management",
            "Supplier Due Diligence", "ESG / Ethical Procurement",
        ],
        "skills_soft": [
            "Negotiation", "Stakeholder Management", "Analytical Thinking",
            "Supplier Relationship Building", "Leadership", "Communication",
        ],
        "education": [
            {
                "degree":      "MCIPS (Member of Chartered Institute of Procurement & Supply)",
                "institution": "CIPS",
                "year":        "2018",
            },
            {
                "degree":      "BSc Business Management",
                "institution": "University of Leeds",
                "year":        "2016",
            },
        ],
        "certifications": [
            "MCIPS (Chartered Institute of Procurement & Supply)",
            "IACCM Contract Management Certificate",
        ],
        "languages": ["English (Native)", "Arabic (Conversational)"],
        "right_to_work_uk": True,
        "sector_experience": [
            "Charity / NGO", "Local Government", "NHS / Healthcare", "Higher Education"
        ],
        "work_history": [
            {
                "title":        "Senior Procurement Manager",
                "organisation": "Action Aid UK",
                "start_date":   "2020",
                "end_date":     "Present",
                "description": (
                    "Lead procurement function for £18m annual spend portfolio. "
                    "Manages team of 3 procurement officers. Introduced category management "
                    "framework saving £1.2m in year 1. Oversees international supplier "
                    "onboarding and ethical procurement compliance."
                ),
            },
            {
                "title":        "Procurement Manager",
                "organisation": "London Borough of Hackney",
                "start_date":   "2017",
                "end_date":     "2020",
                "description": (
                    "Managed procurement for IT, facilities and professional services categories. "
                    "Delivered 12 OJEU/PCR compliant tendering exercises. "
                    "Achieved £800k savings vs. prior year through framework agreements."
                ),
            },
            {
                "title":        "Procurement Officer",
                "organisation": "University College London (UCL)",
                "start_date":   "2016",
                "end_date":     "2017",
                "description": (
                    "Supported procurement of research equipment, lab consumables and "
                    "professional services contracts. Managed supplier catalogue and P2P process."
                ),
            },
        ],
        "missing_fields":     [],
        "extraction_status":  "synthetic",
    },
]


# ============================================================
# Embedding-Text generieren
# ============================================================

def build_embedding_text(cv: dict) -> str:
    """
    Baut den Embedding-Text für einen synthetischen CV.
    Format ist identisch zu 02_parse_cvs.py damit die Vektoren vergleichbar sind.

    LERNPUNKT: Warum domain und career_summary an erster Stelle?
    Weil Embedding-Modelle Tokens am Anfang stärker gewichten.
    Indem wir das Berufsfeld zuerst nennen, verankern wir den Vektor
    domänenspezifisch — ein Finance-CV landet im Finance-Bereich des
    Vektorraums, nicht in einem allgemeinen "Business"-Bereich.
    """
    parts = []

    # Domain zuerst (stärkstes Signal)
    if cv.get("profession_domain"):
        parts.append(f"Profession domain: {cv['profession_domain']}")

    if cv.get("career_summary"):
        parts.append(f"Career summary: {cv['career_summary']}")

    if cv.get("current_title"):
        parts.append(f"Current role: {cv['current_title']}")

    years = cv.get("years_experience")
    if years:
        parts.append(f"Years of experience: {years}")

    skills_tech = cv.get("skills_technical") or []
    if skills_tech:
        parts.append(f"Technical skills: {', '.join(skills_tech[:15])}")

    skills_soft = cv.get("skills_soft") or []
    if skills_soft:
        parts.append(f"Soft skills: {', '.join(skills_soft[:8])}")

    certs = cv.get("certifications") or []
    if certs:
        parts.append(f"Certifications: {', '.join(certs)}")

    sectors = cv.get("sector_experience") or []
    if sectors:
        parts.append(f"Sector experience: {', '.join(sectors)}")

    work = cv.get("work_history") or []
    for role in work[:3]:
        if isinstance(role, dict):
            title = role.get("title", "")
            org   = role.get("organisation", "")
            desc  = (role.get("description") or "")[:200]
            parts.append(f"Role: {title} at {org}. {desc}")

    edu = cv.get("education") or []
    for e in edu[:2]:
        if isinstance(e, dict):
            parts.append(f"Education: {e.get('degree', '')} at {e.get('institution', '')}")

    return "\n".join(parts)


# ============================================================
# Datenbankfunktionen
# ============================================================

def get_connection():
    db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    return conn


def insert_synthetic_cv(conn, cv: dict) -> str:
    """
    Fügt einen synthetischen CV in die candidates-Tabelle ein.
    Gibt die generierte cv_id zurück.
    Überspringt den Eintrag wenn anon_ref bereits existiert.
    """
    cursor = conn.cursor()

    # Prüfen ob bereits vorhanden
    cursor.execute("SELECT cv_id FROM candidates WHERE anon_ref = %s", (cv["anon_ref"],))
    existing = cursor.fetchone()
    if existing:
        logger.info(f"  ⏭  {cv['anon_ref']} bereits vorhanden — wird übersprungen")
        cursor.close()
        return str(existing[0])

    cv_id = str(uuid.uuid4())
    embedding_text = build_embedding_text(cv)

    cursor.execute("""
        INSERT INTO candidates (
            cv_id, anon_ref, filename, current_title, years_experience,
            skills_technical, skills_soft, education, work_history,
            certifications, languages, right_to_work_uk, sector_experience,
            missing_fields, raw_text_anon, embedding_text,
            profession_domain, career_summary
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s
        )
    """, (
        cv_id,
        cv["anon_ref"],
        cv.get("filename") or f"synthetic_{cv['anon_ref'].lower()}.pdf",
        cv.get("current_title"),
        cv.get("years_experience"),
        json.dumps(cv.get("skills_technical") or []),
        json.dumps(cv.get("skills_soft") or []),
        json.dumps(cv.get("education") or []),
        json.dumps(cv.get("work_history") or []),
        json.dumps(cv.get("certifications") or []),
        json.dumps(cv.get("languages") or []),
        cv.get("right_to_work_uk"),
        json.dumps(cv.get("sector_experience") or []),
        json.dumps(cv.get("missing_fields") or []),
        "",  # raw_text_anon — leer für synthetische CVs
        embedding_text,
        cv.get("profession_domain"),
        cv.get("career_summary"),
    ))

    conn.commit()
    cursor.close()
    logger.info(f"  ✓ {cv['anon_ref']} ({cv.get('current_title')}) eingefügt")
    return cv_id


def generate_and_store_embedding(conn, cv_id: str, embedding_text: str, anon_ref: str):
    """
    Generiert ein Embedding für einen CV und speichert es in cv_embeddings.
    """
    if not embedding_text or not embedding_text.strip():
        logger.warning(f"  ⚠ {anon_ref}: Leerer Embedding-Text — übersprungen")
        return False

    # Prüfen ob bereits vorhanden
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM cv_embeddings WHERE cv_id = %s AND model = %s",
        (cv_id, "gemini-embedding-001"),
    )
    if cursor.fetchone():
        logger.info(f"  ⏭  {anon_ref}: Embedding bereits vorhanden")
        cursor.close()
        return True
    cursor.close()

    try:
        vectors = gemini.embed_texts([embedding_text])
        if not vectors or vectors[0] is None:
            logger.error(f"  ✗ {anon_ref}: Kein Embedding erhalten")
            return False

        vector_str = "[" + ",".join(str(v) for v in vectors[0]) + "]"

        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cv_embeddings (cv_id, model, embedding)
            VALUES (%s, %s, %s::vector)
            ON CONFLICT (cv_id, model) DO UPDATE SET
                embedding = EXCLUDED.embedding,
                created_at = NOW()
        """, (cv_id, "gemini-embedding-001", vector_str))
        conn.commit()
        cursor.close()

        dim = len(vectors[0])
        logger.info(f"  ✓ {anon_ref}: Embedding gespeichert ({dim} Dimensionen)")
        return True

    except Exception as e:
        logger.error(f"  ✗ {anon_ref}: Embedding fehlgeschlagen — {e}")
        conn.rollback()
        return False


# ============================================================
# Main
# ============================================================

def main():
    logger.info("=" * 60)
    logger.info("Synthetische CVs — Diversifying.io Pipeline-Test")
    logger.info("=" * 60)
    logger.info(f"  {len(SYNTHETIC_CVS)} synthetische CVs werden hinzugefügt")

    conn = get_connection()
    try:
        inserted = 0
        embedded = 0

        for cv in SYNTHETIC_CVS:
            logger.info(f"\n── {cv['anon_ref']}: {cv.get('current_title')} ──")

            # 1. CV in DB einfügen
            cv_id = insert_synthetic_cv(conn, cv)
            inserted += 1

            # 2. Embedding generieren + speichern
            embedding_text = build_embedding_text(cv)
            ok = generate_and_store_embedding(conn, cv_id, embedding_text, cv["anon_ref"])
            if ok:
                embedded += 1

        # Zusammenfassung
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM candidates")
        total_cvs = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM cv_embeddings")
        total_emb = cursor.fetchone()[0]
        cursor.close()

        logger.info(f"\n{'=' * 60}")
        logger.info("FERTIG")
        logger.info(f"{'=' * 60}")
        logger.info(f"  Synthetische CVs verarbeitet: {inserted}")
        logger.info(f"  Embeddings generiert:         {embedded}")
        logger.info(f"  Gesamte CVs in DB:            {total_cvs}")
        logger.info(f"  Gesamte Embeddings in DB:     {total_emb}")
        logger.info(f"\nNÄCHSTER SCHRITT:")
        logger.info("  python scripts/08_ai_match.py")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
