"use client"

import { useEffect, useState } from "react"
import { api, type Job } from "@/lib/api"
import Link from "next/link"

export default function JobsListPage() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [total, setTotal] = useState(0)

  useEffect(() => {
    api.jobs.list({ limit: 100 })
      .then((r) => { setJobs(r.items); setTotal(r.total) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleDelete = async (jdId: string) => {
    if (!confirm("Are you sure you want to delete this job description? All associated candidates and matches will also be removed.")) return
    try {
      await api.jobs.delete(jdId)
      setJobs((prev) => prev.filter((j) => j.jd_id !== jdId))
      setTotal((prev) => prev - 1)
    } catch {
      alert("Failed to delete. Please try again.")
    }
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "2rem", gap: "1rem", flexWrap: "wrap" }}>
        <div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 800, margin: "0 0 0.25rem", letterSpacing: "-0.02em" }}>
            Job Descriptions
          </h1>
          <p style={{ color: "var(--text-secondary)", margin: 0 }}>
            {total} job{total !== 1 ? "s" : ""} total · Manage your roles and view candidates
          </p>
        </div>
        <Link href="/dashboard/jobs/new" className="btn btn-primary">
          + Create new JD
        </Link>
      </div>

      {/* Loading */}
      {loading && <div style={{ color: "var(--text-muted)", padding: "3rem 0", textAlign: "center" }}>Loading…</div>}

      {/* Empty state */}
      {!loading && jobs.length === 0 && (
        <div className="card" style={{ textAlign: "center", padding: "4rem", border: "2px dashed var(--border)" }}>
          <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>📋</div>
          <p style={{ color: "var(--text-muted)", margin: "0 0 1.5rem" }}>
            No job descriptions yet. Create your first one to start matching candidates!
          </p>
          <Link href="/dashboard/jobs/new" className="btn btn-primary">
            Create your first JD →
          </Link>
        </div>
      )}

      {/* Jobs list */}
      {!loading && jobs.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {jobs.map((job) => (
            <div
              key={job.jd_id}
              className="card"
              style={{
                display: "grid",
                gridTemplateColumns: "1fr auto",
                alignItems: "center",
                gap: "1rem",
                padding: "1.25rem 1.5rem",
              }}
            >
              <Link href={`/dashboard/jobs/${job.jd_id}`} style={{ textDecoration: "none", color: "inherit" }}>
                <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.4rem", flexWrap: "wrap" }}>
                  {job.sector && <span className="badge badge-purple">{job.sector}</span>}
                  {job.seniority_level && <span className="badge badge-teal">{job.seniority_level}</span>}
                  {job.contract_type && <span className="badge" style={{ background: "var(--bg-hover)", color: "var(--text-secondary)" }}>{job.contract_type}</span>}
                </div>
                <h3 style={{ fontWeight: 700, margin: "0 0 0.15rem", fontSize: "1rem" }}>{job.title}</h3>
                <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", margin: 0 }}>
                  {job.organisation || "—"} · {job.location || "Location not specified"} · {new Date(job.created_at).toLocaleDateString("de-DE")}
                </p>
              </Link>

              <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                <Link
                  href={`/dashboard/jobs/${job.jd_id}`}
                  className="btn btn-secondary"
                  style={{ fontSize: "0.8rem", padding: "0.4rem 0.75rem" }}
                >
                  Candidates →
                </Link>
                <button
                  onClick={() => handleDelete(job.jd_id)}
                  style={{
                    background: "hsla(0, 70%, 55%, 0.1)",
                    color: "var(--danger)",
                    border: "none",
                    borderRadius: "var(--radius-sm)",
                    padding: "0.45rem 0.6rem",
                    cursor: "pointer",
                    fontSize: "0.9rem",
                    transition: "all 0.2s",
                  }}
                  title="Delete Job Description"
                >
                  🗑️
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
