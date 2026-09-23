"use client"

import { useEffect, useState } from "react"
import { api, type Job } from "@/lib/api"
import Link from "next/link"
import { useAuth } from "@/lib/auth"

export default function DashboardPage() {
  const { user } = useAuth()
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.jobs.list({ limit: 6 })
      .then((r) => setJobs(r.items))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "1.75rem", fontWeight: 800, margin: "0 0 0.25rem", letterSpacing: "-0.02em" }}>
          Welcome back{user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""} 👋
        </h1>
        <p style={{ color: "var(--text-secondary)", margin: 0 }}>
          Here's an overview of your active roles and latest applications.
        </p>
      </div>

      {/* Quick actions */}
      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "2.5rem", flexWrap: "wrap" }}>
        <Link href="/dashboard/jobs/new" className="btn btn-primary">
          + Create new JD
        </Link>
        <Link href="/dashboard/jobs" className="btn btn-secondary">
          View all jobs
        </Link>
      </div>

      {/* Active jobs */}
      <div>
        <h2 style={{ fontSize: "1rem", fontWeight: 700, margin: "0 0 1rem", color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
          Active Roles
        </h2>

        {loading ? (
          <div style={{ color: "var(--text-muted)", padding: "2rem 0" }}>Loading…</div>
        ) : jobs.length === 0 ? (
          <div
            className="card"
            style={{ textAlign: "center", padding: "3rem", border: "2px dashed var(--border)" }}
          >
            <p style={{ color: "var(--text-muted)", margin: "0 0 1rem" }}>
              No job descriptions yet. Create your first one!
            </p>
            <Link href="/dashboard/jobs/new" className="btn btn-primary">
              Create your first JD →
            </Link>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "1rem" }}>
            {jobs.map((job) => (
              <Link
                key={job.jd_id}
                href={`/dashboard/jobs/${job.jd_id}`}
                style={{ textDecoration: "none" }}
              >
                <article
                  className="card"
                  style={{ cursor: "pointer", height: "100%" }}
                >
                  <div style={{ display: "flex", gap: "0.4rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
                    {job.sector && <span className="badge badge-purple">{job.sector}</span>}
                    {job.contract_type && <span className="badge badge-teal">{job.contract_type}</span>}
                  </div>
                  <h3 style={{ fontWeight: 700, margin: "0 0 0.25rem", fontSize: "1rem" }}>{job.title}</h3>
                  <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", margin: 0 }}>{job.organisation}</p>
                  <div
                    style={{
                      marginTop: "1rem",
                      paddingTop: "1rem",
                      borderTop: "1px solid var(--border-subtle)",
                      fontSize: "0.8rem",
                      color: "var(--brand-purple-400)",
                      fontWeight: 600,
                    }}
                  >
                    View candidates →
                  </div>
                </article>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
