-- ============================================================
-- db/schema.sql — Diversifying.io Database Schema
--
-- This file is automatically run when PostgreSQL first starts
-- via Docker (see docker-compose.yml volume mount).
--
-- To run manually against a running DB:
--   psql -h localhost -U dyversifying_user -d dyversifying_db -f db/schema.sql
-- ============================================================

-- Enable pgvector extension: adds the 'vector' data type which lets us store
-- and compare AI embedding vectors (lists of floating-point numbers).
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable UUID generation function (built into Postgres 13+)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- ============================================================
-- TABLE: job_descriptions
-- Stores one row per Job Description document.
-- JSONB columns store arrays/objects and support rich querying.
-- ============================================================
CREATE TABLE IF NOT EXISTS job_descriptions (
    jd_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename            TEXT NOT NULL,
    title               TEXT,
    organisation        TEXT,
    location            TEXT,
    salary_range        TEXT,
    contract_type       TEXT,           -- 'Permanent', 'Interim', 'Fixed-term', 'Freelance'
    seniority_level     TEXT,           -- 'Junior', 'Mid', 'Senior', 'Head', 'Director', 'Executive'
    sector              TEXT,           -- 'Charity', 'Finance', 'Digital', 'Health', 'Legal', 'Education'
    
    -- These are arrays stored as JSONB — e.g. ["Manage team", "Deliver projects"]
    responsibilities        JSONB DEFAULT '[]',
    essential_requirements  JSONB DEFAULT '[]',
    desirable_requirements  JSONB DEFAULT '[]',
    skills_technical        JSONB DEFAULT '[]',   -- Hard skills: Python, Salesforce, etc.
    skills_soft             JSONB DEFAULT '[]',   -- Soft skills: leadership, communication
    qualifications          JSONB DEFAULT '[]',   -- Degrees, professional certifications
    
    raw_text            TEXT,                     -- Full original doc16ument text
    embedding_text      TEXT,                     -- Focused text used to create embeddings
    
    -- Data quality
    missing_fields      JSONB DEFAULT '[]',       -- Fields AI couldn't find
    quality_flags       JSONB DEFAULT '[]',       -- e.g. ["no salary", "vague requirements"]
    
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Index on organisation and sector for fast filtering
CREATE INDEX IF NOT EXISTS idx_jd_organisation ON job_descriptions (organisation);
CREATE INDEX IF NOT EXISTS idx_jd_sector ON job_descriptions (sector);


-- ============================================================
-- TABLE: candidates
-- Stores one row per CV. All PII has been removed/anonymised.
-- The original PII mapping is stored separately (pii_mapping.json).
-- ============================================================
CREATE TABLE IF NOT EXISTS candidates (
    cv_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename            TEXT NOT NULL,
    anon_ref            TEXT UNIQUE,    -- Human-readable reference: CAND-001, CAND-002, ...
    
    current_title       TEXT,
    years_experience    INT,
    
    -- Arrays stored as JSONB
    skills_technical    JSONB DEFAULT '[]',
    skills_soft         JSONB DEFAULT '[]',
    
    -- Structured arrays of objects
    -- education: [{"degree": "BSc Computer Science", "institution": "UCL", "year": 2019}]
    education           JSONB DEFAULT '[]',
    -- work_history: [{"title": "...", "org": "...", "duration": "2 years", "description": "..."}]
    work_history        JSONB DEFAULT '[]',
    
    certifications      JSONB DEFAULT '[]',
    languages           JSONB DEFAULT '[]',   -- ["English", "French"]
    sector_experience   JSONB DEFAULT '[]',   -- ["Charity", "Tech"]
    
    right_to_work_uk    BOOLEAN,             -- NULL if not mentioned in CV
    
    raw_text_anon       TEXT,               -- Full anonymised CV text (no PII)
    embedding_text      TEXT,               -- Focused text for embeddings
    
    missing_fields      JSONB DEFAULT '[]',
    
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_candidate_anon_ref ON candidates (anon_ref);
CREATE INDEX IF NOT EXISTS idx_candidate_title ON candidates (current_title);


-- ============================================================
-- TABLE: jd_embeddings
-- Stores the AI embedding vector for each JD.
-- vector(3072) = a list of 3072 floating-point numbers representing
-- the semantic "meaning" of the JD in mathematical space.
-- (gemini-embedding-001 produces 3072-dimensional vectors)
-- ============================================================
CREATE TABLE IF NOT EXISTS jd_embeddings (
    jd_id       UUID NOT NULL REFERENCES job_descriptions(jd_id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'gemini-embedding-001',
    embedding   vector(3072),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (jd_id, model)
);

-- HNSW index: makes vector similarity search fast.
-- IVFFlat is limited to 2000 dimensions; HNSW supports up to 16,000.
-- gemini-embedding-001 produces 3072 dimensions, so HNSW is required.
CREATE INDEX IF NOT EXISTS idx_jd_embedding_vector
    ON jd_embeddings USING hnsw (embedding vector_cosine_ops);


-- ============================================================
-- TABLE: cv_embeddings
-- Same concept as jd_embeddings but for CVs.
-- ============================================================
CREATE TABLE IF NOT EXISTS cv_embeddings (
    cv_id       UUID NOT NULL REFERENCES candidates(cv_id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'gemini-embedding-001',
    embedding   vector(3072),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (cv_id, model)
);

CREATE INDEX IF NOT EXISTS idx_cv_embedding_vector
    ON cv_embeddings USING hnsw (embedding vector_cosine_ops);


-- ============================================================
-- TABLE: match_results
-- Stores the computed similarity score for each JD × CV pair.
-- This is the core of the evaluation dataset (Week 3).
-- ============================================================
CREATE TABLE IF NOT EXISTS match_results (
    match_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jd_id           UUID NOT NULL REFERENCES job_descriptions(jd_id) ON DELETE CASCADE,
    cv_id           UUID NOT NULL REFERENCES candidates(cv_id) ON DELETE CASCADE,
    
    -- Computed by AI / algorithms
    semantic_score  FLOAT,      -- Cosine similarity: 0.0 (no match) to 1.0 (identical)
    skill_overlap   FLOAT,      -- Jaccard similarity of skill lists: |A∩B| / |A∪B|
    rank_position   INT,        -- 1 = best match for this JD
    
    -- AI-generated explanation ("Why is this a good match?")
    ai_explanation  TEXT,
    
    -- Manually filled by the recruiter (you!) for evaluation
    -- 0 = No match, 1 = Maybe, 2 = Yes (good match)
    recruiter_label INT CHECK (recruiter_label IN (0, 1, 2)),
    recruiter_notes TEXT,
    
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (jd_id, cv_id)       -- Only one match result per JD-CV pair
);

CREATE INDEX IF NOT EXISTS idx_match_jd ON match_results (jd_id);
CREATE INDEX IF NOT EXISTS idx_match_cv ON match_results (cv_id);


-- ============================================================
-- TABLE: users
-- Recruiter accounts. Used by FastAPI JWT authentication.
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    user_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    full_name       TEXT,
    role            TEXT DEFAULT 'recruiter' CHECK (role IN ('recruiter', 'admin')),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Seed a default admin user (password: 'changeme' — hashed with bcrypt)
-- You will change this via the API after setup.
-- INSERT INTO users (email, hashed_password, full_name, role)
-- VALUES ('admin@diversifying.io', '$2b$12$...', 'Admin', 'admin');


-- ============================================================
-- HELPER: Trigger to auto-update 'updated_at' on row change
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_jd_updated_at
    BEFORE UPDATE ON job_descriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_candidate_updated_at
    BEFORE UPDATE ON candidates
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
