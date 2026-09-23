"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { api, type MatchResult } from "@/lib/api"

type FeedbackAction = "shortlist" | "interview" | "dismiss"

const VERDICT_COLORS: Record<string, string> = {
  "Strong Match": "badge-success",
  "Possible Match": "badge-warning",
  "Weak Match": "badge-danger",
}

export default function JobCandidatesPage() {
  const params = useParams()
  const jdId = params.id as string

  const [results, setResults] = useState<MatchResult[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [feedbackMap, setFeedbackMap] = useState<Record<number, FeedbackAction>>({})
  const [feedbackLoading, setFeedbackLoading] = useState<Record<number, boolean>>({})

  useEffect(() => {
    api.matching.getResults(jdId, { top_n: 30 })
      .then((r) => setResults(r.results))
      .catch(() => setError("Could not load candidates. Make sure this JD has been matched."))
      .finally(() => setLoading(false))
  }, [jdId])

  const sendFeedback = async (matchId: number, action: FeedbackAction) => {
    setFeedbackLoading((prev) => ({ ...prev, [matchId]: true }))
    try {
      await api.matching.sendFeedback(matchId, action)
      setFeedbackMap((prev) => ({ ...prev, [matchId]: action }))
    } catch {
      // silently ignore — feedback is best-effort
    } finally {
      setFeedbackLoading((prev) => ({ ...prev, [matchId]: false }))
    }
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "2rem", gap: "1rem", flexWrap: "wrap" }}>
        <div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 800, margin: "0 0 0.25rem", letterSpacing: "-0.02em" }}>
            Candidate Rankings
          </h1>
          <p style={{ color: "var(--text-secondary)", margin: 0, fontSize: "0.9rem" }}>
            {results.length} candidates evaluated · AI-anonymised profiles · Evidence-based scoring
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <a href="/dashboard/jobs" className="btn btn-secondary" style={{ fontSize: "0.8rem" }}>
            ← All Jobs
          </a>
        </div>
      </div>

      {/* Legend */}
      <div
        style={{
          display: "flex",
          gap: "1rem",
          padding: "0.875rem 1rem",
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-md)",
          marginBottom: "1.5rem",
          flexWrap: "wrap",
          fontSize: "0.8rem",
          color: "var(--text-muted)",
        }}
      >
        <span>🟢 <strong style={{ color: "var(--text-primary)" }}>Shortlist</strong> — worth reviewing</span>
        <span>⭐ <strong style={{ color: "var(--text-primary)" }}>Interview</strong> — top match, invite</span>
        <span>❌ <strong style={{ color: "var(--text-primary)" }}>Dismiss</strong> — not a fit</span>
        <span style={{ marginLeft: "auto" }}>Actions are saved to improve AI calibration</span>
      </div>

      {/* Loading / Error */}
      {loading && <div style={{ color: "var(--text-muted)", padding: "3rem 0", textAlign: "center" }}>Loading candidates…</div>}
      {error && (
        <div style={{ padding: "1.5rem", background: "hsla(0, 70%, 55%, 0.1)", border: "1px solid hsla(0, 70%, 55%, 0.3)", borderRadius: "var(--radius-md)", color: "var(--danger)" }}>
          {error}
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && results.length === 0 && (
        <div className="card" style={{ textAlign: "center", padding: "4rem" }}>
          <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>👥</div>
          <p style={{ color: "var(--text-muted)", margin: 0 }}>
            No candidates yet. Share the job posting so candidates can apply!
          </p>
          <a
            href={`/jobs/${jdId}`}
            className="btn btn-primary"
            style={{ marginTop: "1.5rem", display: "inline-flex" }}
          >
            View public job page →
          </a>
        </div>
      )}

      {/* Candidate cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        {results.map((result) => {
          const feedback = feedbackMap[result.match_id] ?? (
            result.recruiter_label === 2 ? "interview" :
            result.recruiter_label === 1 ? "shortlist" :
            result.recruiter_label === 0 ? "dismiss" : null
          )
          const scoreColor =
            result.final_score >= 7 ? "var(--success)" :
            result.final_score >= 4 ? "var(--warning)" : "var(--danger)"

          return (
            <article
              key={result.match_id}
              className="card"
              style={{
                borderColor: result.is_top_match ? "hsla(267, 65%, 55%, 0.4)" : undefined,
                boxShadow: result.is_top_match ? "0 0 20px hsla(267, 65%, 55%, 0.1)" : undefined,
              }}
            >
              <div style={{ display: "grid", gridTemplateColumns: "auto 1fr auto", gap: "1.25rem", alignItems: "start" }}>
                {/* Rank badge */}
                <div
                  style={{
                    width: "48px",
                    height: "48px",
                    borderRadius: "50%",
                    background: result.final_rank <= 3 ? "var(--gradient-brand)" : "var(--bg-hover)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: 800,
                    fontSize: "1rem",
                    color: result.final_rank <= 3 ? "white" : "var(--text-secondary)",
                    flexShrink: 0,
                  }}
                >
                  #{result.final_rank || "–"}
                </div>

                {/* Info */}
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.4rem" }}>
                    <span style={{ fontWeight: 700, fontSize: "1rem" }}>
                      {result.current_title || "Candidate"}
                    </span>
                    <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>
                      · {result.anon_ref}
                    </span>
                    {result.is_top_match && (
                      <span className="badge badge-purple">⭐ Top Match</span>
                    )}
                    {result.stage3_verdict && (
                      <span className={`badge ${VERDICT_COLORS[result.stage3_verdict] || "badge-purple"}`}>
                        {result.stage3_verdict}
                      </span>
                    )}
                  </div>

                  {/* Score row */}
                  <div style={{ display: "flex", gap: "1.25rem", flexWrap: "wrap", fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
                    <span>
                      Overall: <strong style={{ color: scoreColor, fontSize: "0.9rem" }}>
                        {result.final_score?.toFixed(1) ?? "–"}/10
                      </strong>
                    </span>
                    <span>
                      Stage 1: <strong style={{ color: result.stage1_passed ? "var(--success)" : "var(--danger)" }}>
                        {result.stage1_passed ? "✓ Pass" : "✗ Fail"}
                      </strong>
                    </span>
                    <span>
                      Stage 2: <strong style={{ color: "var(--text-primary)" }}>
                        {result.stage2_met_count ?? "–"}/{result.stage2_total_count ?? "–"} met
                      </strong>
                    </span>
                    {result.ml_confidence != null && (
                      <span>
                        ML Confidence: <strong style={{ color: "var(--brand-purple-400)" }}>
                          {(result.ml_confidence * 100).toFixed(0)}%
                        </strong>
                      </span>
                    )}
                    {result.years_experience != null && (
                      <span>{result.years_experience} yrs exp</span>
                    )}
                  </div>

                  {/* Stage 3 explanation */}
                  {result.stage3_explanation && (
                    <p
                      style={{
                        margin: "0 0 0.75rem",
                        fontSize: "0.85rem",
                        color: "var(--text-secondary)",
                        lineHeight: 1.5,
                        padding: "0.75rem",
                        background: "var(--bg-hover)",
                        borderRadius: "var(--radius-sm)",
                        borderLeft: "3px solid var(--brand-purple-500)",
                      }}
                    >
                      {result.stage3_explanation.slice(0, 280)}
                      {result.stage3_explanation.length > 280 ? "…" : ""}
                    </p>
                  )}

                  {/* Stage 1 reason */}
                  {result.stage1_reason && (
                    <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-muted)" }}>
                      <em>{result.stage1_reason}</em>
                    </p>
                  )}
                </div>

                {/* Feedback buttons */}
                <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", flexShrink: 0 }}>
                  {(["interview", "shortlist", "dismiss"] as FeedbackAction[]).map((action) => {
                    const isSelected = feedback === action
                    const loading = feedbackLoading[result.match_id]
                    const colors = {
                      interview: { bg: "var(--brand-purple-500)", label: "⭐ Interview" },
                      shortlist: { bg: "var(--brand-teal-400)", label: "🟢 Shortlist" },
                      dismiss:   { bg: "var(--danger)",          label: "❌ Dismiss" },
                    }
                    return (
                      <button
                        key={action}
                        id={`feedback-${result.match_id}-${action}`}
                        onClick={() => sendFeedback(result.match_id, action)}
                        disabled={loading}
                        style={{
                          padding: "0.35rem 0.75rem",
                          borderRadius: "var(--radius-sm)",
                          border: `1px solid ${isSelected ? colors[action].bg : "var(--border)"}`,
                          background: isSelected ? colors[action].bg : "transparent",
                          color: isSelected ? "white" : "var(--text-secondary)",
                          fontSize: "0.75rem",
                          fontWeight: isSelected ? 700 : 400,
                          cursor: loading ? "not-allowed" : "pointer",
                          transition: "all 0.15s",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {colors[action].label}
                      </button>
                    )
                  })}
                </div>
              </div>
            </article>
          )
        })}
      </div>
    </div>
  )
}
