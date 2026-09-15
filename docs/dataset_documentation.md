# Diversifying.io — Dataset Documentation

**Generated:** 2026-09-14 16:19  
**Week:** 2 (Data Preparation)  
**Status:** Complete

---

## Overview

This dataset was created as part of the Week 2 data preparation phase of the
Diversifying.io AI Recruitment Tool internship project. It contains structured,
anonymised job descriptions and candidate CVs for use in the Week 3 AI matching
experiments.

---

## Dataset Summary

| Metric | Value |
|--------|-------|
| Job Descriptions | 8 |
| Candidate CVs (anonymised) | 22 |
| Possible JD × CV pairs | 176 |

---

## Job Descriptions

### Sources
JDs were collected from UNICEF UK and similar UK-based organisations.
All JDs are in the public domain (advertised roles).

### Statistics

| Metric | Value |
|--------|-------|
| Total JDs | 8 |
| JDs with salary info | 8 / 8 |
| JDs with technical skills | 8 / 8 |
| Total validation warnings | 1 |

### Sector Breakdown

| Sector | Count |
|--------|-------|
| Charity | 7 |
| Government | 1 |

### Fields Extracted

| Field | Type | Description |
|-------|------|-------------|
| `jd_id` | UUID | Unique identifier |
| `filename` | String | Source filename |
| `title` | String | Job title |
| `organisation` | String | Hiring organisation |
| `location` | String | Work location |
| `salary_range` | String | Salary if mentioned |
| `contract_type` | String | Permanent/Interim/Fixed-term |
| `seniority_level` | String | Junior/Senior/Head/Director |
| `sector` | String | Industry sector |
| `responsibilities` | Array | Key responsibilities |
| `essential_requirements` | Array | Must-have criteria |
| `desirable_requirements` | Array | Nice-to-have criteria |
| `skills_technical` | Array | Hard skills and tools |
| `skills_soft` | Array | Soft skills |
| `qualifications` | Array | Degree/cert requirements |
| `raw_text` | Text | Full document text |
| `embedding_text` | Text | Focused text for AI embedding |

---

## Candidate CVs

### Privacy & GDPR

All CVs have been **anonymised** in compliance with UK GDPR:
- Full names → `[NAME]`
- Email addresses → `[EMAIL]`
- Phone numbers → `[PHONE]`
- Home addresses → `[ADDRESS]`
- Social media URLs → `[URL]`
- Postcodes → `[POSTCODE]`

The PII mapping file (`pii_mapping.json`) is stored separately,
access-restricted, and excluded from version control.

Each candidate is referred to by an anonymous reference (e.g. `CAND-001`).

### Statistics

| Metric | Value |
|--------|-------|
| Total CVs | 22 |
| CVs with years of experience | 17 / 22 |
| CVs with technical skills | 18 / 22 |
| CVs with UK right-to-work stated | 2 / 22 |
| Total validation warnings | 21 |

### Fields in Anonymised Dataset

| Field | Type | Description |
|-------|------|-------------|
| `cv_id` | UUID | Unique identifier |
| `anon_ref` | String | Anonymous reference (CAND-001, etc.) |
| `current_title` | String | Most recent job title |
| `years_experience` | Integer | Estimated years of experience |
| `skills_technical` | Array | Hard skills and tools |
| `skills_soft` | Array | Soft skills |
| `education` | Array | Degrees and institutions |
| `work_history` | Array | Past roles and descriptions |
| `certifications` | Array | Professional certifications |
| `languages` | Array | Spoken languages |
| `right_to_work_uk` | Boolean | UK work authorisation |
| `sector_experience` | Array | Industry sectors worked in |
| `raw_text_anon` | Text | Anonymised full CV text |
| `embedding_text` | Text | Focused text for AI embedding |

---

## Data Quality Notes

### Known Limitations

1. **Small dataset size**: 8 JDs and 22 CVs is a small sample.
   AI matching quality metrics will be indicative, not statistically robust.
   
2. **AI extraction accuracy**: Fields were extracted by Gemini (LLM). 
   Accuracy is high for well-structured documents but may miss nuance in
   free-form or unusually formatted documents.

3. **Salary data**: Many JDs (0/8) do not include salary information.
   This limits salary-based filtering in the matching system.

4. **Right-to-work**: Most CVs do not explicitly state UK work authorisation.
   `null` means "not mentioned", not "no right to work".

### Improvement Suggestions (for Week 4)

- Expand to 50+ JDs and 100+ CVs for statistically meaningful evaluation
- Add a human review step to validate AI extraction accuracy
- Create a structured intake form for new CVs to ensure consistent data quality

---

## How to Reproduce This Dataset

```bash
# 1. Place JD .docx files in data/raw/jds/
# 2. Place CV .docx/.pdf files in data/raw/cvs/
# 3. Run pipeline:
python scripts/01_parse_jds.py
python scripts/02_parse_cvs.py
python scripts/03_anonymise_cvs.py
python scripts/04_build_dataset.py
```

---

## Files

| File | Description | Sensitive? |
|------|-------------|------------|
| `data/processed/jds.json` | Structured JD dataset | No |
| `data/processed/cvs_anonymised.json` | Anonymised CV dataset | No |
| `data/processed/cvs_raw.json` | Raw CV dataset with PII | **YES** |
| `data/processed/pii_mapping.json` | PII mapping table | **YES** |
