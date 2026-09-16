# Diversifying.io — System Architecture, RAG Setup & Matching Logic

Dieses Dokument bietet eine vollständige, strukturierte und technisch präzise Übersicht über das gesamte System, die Datenmodelle, das RAG-Setup, die Scoring-Formeln und die Prompts. Es dient als Übergabe- und Bewertungsgrundlage für HR- und Tech-Analysen.

---

## 1. Projekt-Überblick & Value Proposition

**Projekt:** Dyversifying (Diversifying.io AI Matching Tool)  
**Ziel:** Ein KI-gestütztes HR-SaaS für vorurteilsfreies, diversitätsorientiertes Kandidaten-Matching (Diversity-First Hiring).  
**Kernansatz:** Vollständige PII-Anonymisierung (Name, Geschlecht, Alter, Herkunft, Fotos, Kontaktdaten und Schulnamen werden vor dem Matching gestrippt) gepaart mit einem transparenten, evidenzbasierten 3-Stufen-Scoring ("Explainable AI Recruiter").

---

## 2. Architektur & Datenfluss

```
[ Dokumente (PDF, DOCX, DOC, TXT) ]
                │
                ▼
┌────────────────────────────────────────────────────────┐
│ 1. Universal Document Parser                           │
│    - PyMuPDF (Native Text)                             │
│    - Fallback: Gemini Vision OCR (< 100 Zeichen)       │
│    - Word COM (pywin32) für .doc                       │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ 2. Information Extraction & PII-Anonymisation          │
│    - LLM-basierte Extraktion strukturierter HR-Felder  │
│    - Stripping aller PII -> Zuweisung CAND-XXX         │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ 3. Storage & Vektordatenbank (PostgreSQL + pgvector)   │
│    - Tabellen: job_descriptions, candidates,           │
│      jd_embeddings, cv_embeddings, ai_match_results    │
│    - Embeddings: 3072 Dimensionen                      │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ 4. 3-Stage Matching Pipeline (Funnel)                  │
│    Stage 1: Profession Gate (Binary + Score 0-10)      │
│    Stage 2: Requirements Scoring (0-10 je Kriterium)   │
│    Stage 3: Deep Match Report (Top 3-5 Kandidaten)     │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ 5. Auswertung & Export                                 │
│    - REST-API (FastAPI: /api/v1/matching)              │
│    - Excel-Export (evaluation_results_EN.xlsx)         │
│      mit Recruiter-Labels (0 / 1 / 2)                  │
└────────────────────────────────────────────────────────┘
```

---

## 3. Datenmodell für das Matching

### Aus Job Descriptions (JDs) extrahierte Features:
* `title`: Rollenbezeichnung (z. B. "Senior Finance Officer", "Delivery Manager")
* `organisation`: Einstellende Organisation
* `sector`: Branche (z. B. Charity, Public Sector, NGO, Tech)
* `seniority_level`: Senioritätsstufe (z. B. Mid-Level, Senior, Lead, Executive)
* `essential_requirements`: Array von 5–8 zwingenden Muss-Kriterien
* `desirable_requirements`: Array von Kann-Kriterien
* `responsibilities`: Hauptaufgaben
* `skills_technical`: Liste technischer Hard Skills
* `skills_soft`: Liste sozialer/methodischer Soft Skills
* `profession_domain`: Fachbereich (z. B. Finance, Procurement, Digital Delivery)
* `min_years_experience`: Mindestberufserfahrung in Jahren

### Aus Kandidaten-CVs extrahierte Features:
* `anon_ref`: Anonyme Kennung (z. B. `CAND-001`, `CAND-010`)
* `current_title`: Aktuelle bzw. letzte Position
* `years_experience`: Gesamte Berufserfahrung (Jahre)
* `career_summary`: Fachliche Zusammenfassung ohne PII
* `skills_technical`: Extrahierte Hard Skills
* `skills_soft`: Extrahierte Soft Skills
* `work_history`: Array von Rollen (Titel, Organisation, Zeitraum, Aufgabenbeschreibung)
* `education`: Ausbildung & Abschlüsse (anonymisiert)
* `certifications`: Relevante Zertifikate (z. B. ACCA, Scrum Master, Prince2)
* `sector_experience`: Branchenerfahrung
* `right_to_work_uk`: Boolean (Arbeitserlaubnis)
* `embedding_text`: Bereinigter Volltext für das Embedding

---

## 4. RAG- & Vektor-Setup im Detail

* **Embedding-Modell:** Google Gemini Embeddings (`gemini-embedding-001`), Vektorlänge: **3072 Dimensionen**.
* **Vektordatenbank:** **PostgreSQL mit pgvector-Erweiterung**.
* **Index & Distanzmaß:** IVFFlat / HNSW mit **Kosinus-Distanz** (`<=>` Operator in pgvector).
* **Vektorsuche (API-Level):**
  ```sql
  SELECT c.cv_id, c.anon_ref, c.current_title,
         1 - (ce.embedding <=> :query_vec::vector) AS semantic_score
  FROM candidates c
  JOIN cv_embeddings ce ON c.cv_id = ce.cv_id
  ORDER BY ce.embedding <=> :query_vec::vector
  LIMIT :top_n;
  ```
* **Warum reines Vektor-Retrieval nicht ausreicht:**
  In frühen Tests zeigte sich: Ein "Lead Digital Designer" und ein "Digital Delivery Manager" hatten wegen Wörtern wie *"digital"*, *"teams"*, *"delivering"* eine Kosinus-Ähnlichkeit von > 0.82, obwohl die Profile beruflich inkompatibel sind. Daher wurde der **3-Stufen AI-Agenten-Trichter** entwickelt.

---

## 5. 3-Stufen Matching-Logik (Funnel)

Statt alle Kandidaten blind durch teure LLM-Prompts zu schleusen, arbeitet das System als hierarchischer Trichter:

### Stage 1: Profession Gate (Kompakt & Streng)
* **Ziel:** Schließt berufsfremde Bewerber sofort aus (z. B. Grafikdesigner auf CFO-Stelle).
* **Eingabe:** Job-Titel, Branche, Kernanforderungen vs. aktueller Titel des Kandidaten, Erfahrung, Summary.
* **Output:** `relevant` (Boolean), `score` (0–10), `reason` (1 Satz Begründung).
* **Filter:** Nur Kandidaten mit `relevant = True` dürfen in Stage 2.

### Stage 2: Requirements Scoring (Evidenzbasiert)
* **Ziel:** Prüft jedes einzelne "Essential Requirement" der JD gegen das CV.
* **Output pro Kriterium:** Score (0–10) + konkreter Evidenz-Auszug aus dem CV (kein Erfinden!).
* **Aggregierter Output:**
  * `overall_score`: Gewichteter Schnitt (0–10)
  * `met_count` / `total_count`: Anzahl Kriterien mit Score ≥ 7
  * `critical_gaps`: Liste fehlender Kernqualifikationen

### Stage 3: Deep AI Analysis (Nur Top 3–5 Kandidaten)
* **Ziel:** Tiefenbericht für den Hiring Manager.
* **Output:**
  * `strengths`: 2–3 belegte Kernstärken
  * `gaps`: Konkrete Lücken für die Zielrolle
  * `verdict`: Genau eines von `["Strong Match", "Possible Match", "Weak Match"]`
  * `recommendation`: 1–2 Sätze Handlungsempfehlung

### Hard Filters (Regelbasiert):
* `right_to_work_uk`: Zwingendes Ausschlusskriterium (wenn gefordert).
* `min_years_experience`: Mindesterfahrung (wenn gefordert).

---

## 6. Scoring-Formel & Ranking-Berechnung

### Berechnung des `final_score` (Skala 0–10):

Wenn Stage 3 ausgeführt wurde (Top-Kandidaten):
$$\text{final\_score} = 0.30 \times \text{Stage 1 Score} + 0.55 \times \text{Stage 2 Score} + 0.15 \times \text{Stage 3 Wert}$$

*Mapping für Stage 3 Verdict:*
* `"Strong Match"` $\rightarrow 10.0$
* `"Possible Match"` $\rightarrow 6.0$
* `"Weak Match"` $\rightarrow 2.0$

Wenn Stage 3 nicht ausgeführt wurde:
$$\text{final\_score} = 0.35 \times \text{Stage 1 Score} + 0.65 \times \text{Stage 2 Score}$$

*Begründung der Gewichtung:* Stage 2 (55%) trägt das größte Gewicht, weil das Erfüllen der konkreten Muss-Kriterien die Kernvoraussetzung ist.

### Sortierung für `final_rank`:
1. Kandidaten mit `stage1_passed = True` stehen **immer** vor Kandidaten mit `stage1_passed = False`.
2. Innerhalb beider Gruppen wird strikt nach `final_score` absteigend sortiert.

---

## 7. Verwendete Prompts (LLM as Judge)

### Stage 1: Profession Gate Prompt
```text
SYSTEM:
You are an experienced UK recruiter with 15 years of expertise.
You assess whether a candidate is fundamentally suitable for a role.
Respond ONLY with valid JSON.

USER PROMPT:
Assess whether this candidate would be a plausible applicant for this role.

ROLE:
- Job title: {jd_title}
- Organisation: {jd_organisation}
- Sector: {jd_sector}
- Key requirements: {jd_requirements_preview}

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

Format:
{
  "relevant": true or false,
  "score": <integer 0-10>,
  "reason": "<max. 1 precise sentence in English>"
}
```

### Stage 2: Requirements Scoring Prompt
```text
SYSTEM:
You are an experienced UK recruiter.
Assess precisely and honestly how well a candidate meets the job requirements.
Use ONLY evidence from the candidate profile. Do not invent qualifications.
Respond ONLY with valid JSON. All text fields must be in English.

USER PROMPT:
Score EACH essential requirement from 0 to 10:
  0-3: No evidence in CV
  4-6: Partially met — some evidence, but gaps remain
  7-9: Well met — strong evidence in CV
  10: Fully met — perfect match

Format:
{
  "requirements": [
    {
      "requirement": "<exact requirement text>",
      "score": <0-10>,
      "evidence": "<specific evidence from CV, or 'No evidence found'>"
    }
  ],
  "overall_score": <weighted average 0-10>,
  "met_count": <number of requirements with score >= 7>,
  "total_count": <total number of requirements>,
  "critical_gaps": ["<key missing qualification 1>"]
}
```

---

## 8. Ground-Truth-Daten & Validierungs-Setup

* **Datensatz:** 8 Job Descriptions (u. a. UNICEF UK: Finance, Procurement, Delivery, Risk, Creative) × 22 CVs = **176 Match-Paare**.
* **Referenz-Datei:** `docs/evaluation_results_EN.xlsx` (bzw. `evaluation_results_III.xlsx`).
* **HR-Ground-Truth-Labels (Spalte `Recruiter Decision`):**
  * `0` = No / Rejected (nicht geeignet)
  * `1` = Possible Match (in der engeren Auswahl)
  * `2` = Good / Strong Match (Top-Kandidat für Interview)
* **Ziel der externen Analyse:**
  1. Erstellung einer **Confusion Matrix** (Modell-Ranking / Final Score vs. Recruiter-Label 0/1/2).
  2. Berechnung von **Precision, Recall und F1-Score** für Top-Kandidaten (Label 2).
  3. Analyse von **False Positives** (z. B. hohe semantische Ähnlichkeit, aber fehlende Seniorität) und **False Negatives**.
  4. Optimierung von Cutoff-Schwellenwerten pro Rollen-Kategorie.

---

## 9. Technischer Stack & Constraints

* **Backend:** Python 3.12+, FastAPI (asynchron mit `uvicorn`).
* **Datenbank:** PostgreSQL 16 mit `pgvector`, SQLAlchemy (asyncpg) + Psycopg2 für Batch-Scripts.
* **LLM & Embeddings:** Google Gemini (`gemini-3.6-flash`, `gemini-embedding-001`).
* **Deployment:** Docker & Docker Compose (`docker-compose.yml`).
* **Latenz & Kosten:**
  * Durch den 3-Stufen-Trichter werden bei 176 Paaren nur ~15–20 Paare in Stage 2 und nur ~24 Paare (Top 3 pro Rolle) in Stage 3 geschickt.
  * API-Calls sind mit Exponential Backoff (5s, 15s, 30s) und 2s Mindestpause abgesichert.
* **Datenschutz & Diversity:** DSGVO-konform durch clientseitige Anonymisierung vor dem Senden an LLMs; kein Speichern von Klarnamen in den Vector-Embeddings.
