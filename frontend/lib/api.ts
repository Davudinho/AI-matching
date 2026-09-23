/**
 * frontend/lib/api.ts — Typed API client for the Dyversifying backend
 *
 * Usage:
 *   import { api } from "@/lib/api"
 *   const jobs = await api.jobs.list()
 *   const result = await api.candidates.apply(jobId, file)
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

// ---- Auth token helpers (client-side only) ----

export const tokenStorage = {
  get: (): string | null => {
    if (typeof window === "undefined") return null
    return localStorage.getItem("dyversifying_token")
  },
  set: (token: string) => {
    if (typeof window === "undefined") return
    localStorage.setItem("dyversifying_token", token)
  },
  clear: () => {
    if (typeof window === "undefined") return
    localStorage.removeItem("dyversifying_token")
  },
}

// ---- Base fetch wrapper ----

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  auth = false
): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  }

  // Don't set Content-Type for FormData (browser sets it with boundary)
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json"
  }

  if (auth) {
    const token = tokenStorage.get()
    if (token) headers["Authorization"] = `Bearer ${token}`
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({ detail: res.statusText }))
    throw new ApiError(res.status, errorBody.detail || "Request failed")
  }

  return res.json() as Promise<T>
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = "ApiError"
  }
}

// ---- Types ----

export interface Job {
  jd_id: string
  title: string
  organisation: string
  location: string
  sector: string
  seniority_level: string
  contract_type: string
  salary_range: string | null
  essential_requirements: string[]
  skills_technical: string[]
  created_at: string
}

export interface JobDetail extends Job {
  responsibilities: string[]
  desirable_requirements: string[]
  skills_soft: string[]
  qualifications: string[]
  profession_domain: string
  raw_text: string
}

export interface Candidate {
  cv_id: string
  anon_ref: string
  current_title: string
  years_experience: number | null
  skills_technical: string[]
  sector_experience: string[]
  right_to_work_uk: boolean | null
  created_at: string
}

export interface MatchResult {
  match_id: number
  final_rank: number
  final_score: number
  is_top_match: boolean
  ml_confidence: number | null
  recruiter_label: number | null
  stage1_passed: boolean
  stage1_score: number
  stage1_reason: string
  stage2_score: number
  stage2_met_count: number
  stage2_total_count: number
  stage2_breakdown: Array<{ requirement: string; score: number; evidence: string }>
  stage2_critical_gaps: string[]
  stage3_verdict: string | null
  stage3_explanation: string | null
  cv_id: string
  anon_ref: string
  current_title: string
  years_experience: number | null
  right_to_work_uk: boolean | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface RecruiterProfile {
  user_id: string
  email: string
  full_name: string | null
  role: string
  is_active: boolean
  created_at: string
}

// ---- API namespaces ----

export const api = {
  // Public: job listings
  jobs: {
    list: (params?: { skip?: number; limit?: number; sector?: string }) => {
      const qs = new URLSearchParams()
      if (params?.skip) qs.set("skip", String(params.skip))
      if (params?.limit) qs.set("limit", String(params.limit))
      if (params?.sector) qs.set("sector", params.sector)
      const query = qs.toString() ? `?${qs}` : ""
      return apiFetch<{ total: number; items: Job[] }>(`/api/v1/jds/${query}`)
    },
    get: (jdId: string) => apiFetch<JobDetail>(`/api/v1/jds/${jdId}`),

    // Recruiter-only
    createFromText: (payload: { title?: string; organisation?: string; raw_text: string }) =>
      apiFetch<{ jd_id: string; title: string; status: string }>(
        "/api/v1/jds/create-from-text",
        { method: "POST", body: JSON.stringify(payload) },
        true
      ),
    upload: (file: File) => {
      const form = new FormData()
      form.append("file", file)
      return apiFetch<{ jd_id: string; title: string; status: string }>(
        "/api/v1/jds/upload",
        { method: "POST", body: form },
        true
      )
    },
    delete: (jdId: string) =>
      apiFetch<{ deleted: string }>(`/api/v1/jds/${jdId}`, { method: "DELETE" }, true),
  },

  // Public: apply to a job
  candidates: {
    apply: (jdId: string, file: File) => {
      const form = new FormData()
      form.append("jd_id", jdId)
      form.append("file", file)
      return apiFetch<{ status: string; message: string; application_ref: string }>(
        "/api/v1/candidates/apply",
        { method: "POST", body: form }
      )
    },
  },

  // Recruiter-only: match results + feedback
  matching: {
    getResults: (jdId: string, params?: { top_n?: number; top_match_only?: boolean }) => {
      const qs = new URLSearchParams()
      if (params?.top_n) qs.set("top_n", String(params.top_n))
      if (params?.top_match_only) qs.set("top_match_only", "true")
      const query = qs.toString() ? `?${qs}` : ""
      return apiFetch<{ jd_id: string; count: number; results: MatchResult[] }>(
        `/api/v1/matching/${jdId}/ai-results${query}`,
        {},
        true
      )
    },
    sendFeedback: (matchId: number, action: "shortlist" | "interview" | "dismiss") =>
      apiFetch<{ status: string }>(
        `/api/v1/matching/feedback?match_id=${matchId}&action=${action}`,
        { method: "POST" },
        true
      ),
  },

  // Auth
  auth: {
    register: (email: string, password: string, fullName?: string) =>
      apiFetch<TokenResponse>("/api/v1/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password, full_name: fullName }),
      }),

    login: (email: string, password: string) => {
      const form = new URLSearchParams()
      form.set("username", email) // OAuth2 form field name
      form.set("password", password)
      return apiFetch<TokenResponse>("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: form.toString(),
      })
    },

    me: () => apiFetch<RecruiterProfile>("/api/v1/auth/me", {}, true),
  },

  // Health
  health: {
    check: () => apiFetch<{ status: string }>("/api/v1/health"),
  },
}
