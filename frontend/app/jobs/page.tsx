import type { Metadata } from "next"
import { api, type Job } from "@/lib/api"
import Link from "next/link"

export const metadata: Metadata = {
  title: "Browse Open Roles",
  description: "Browse all open job opportunities. Apply with your CV and let our AI find the best match.",
}

const SECTORS = [
  "All", "Charity", "Finance", "Digital", "Legal", "Health",
  "Education", "Creative & Media", "HR", "Operations",
]

const CONTRACT_COLORS: Record<string, string> = {
  Permanent: "badge-teal",
  Interim: "badge-warning",
  "Fixed-term": "badge-purple",
  Freelance: "badge-purple",
}

export default async function JobsPage({
  searchParams,
}: {
  searchParams: Promise<{ sector?: string; page?: string }>
}) {
  const params = await searchParams
  const sector = params.sector && params.sector !== "All" ? params.sector : undefined
  const page = Math.max(1, Number(params.page) || 1)
  const limit = 12
  const skip = (page - 1) * limit

  let jobs: Job[] = []
  let total = 0
  let error = ""

  try {
    const res = await api.jobs.list({ skip, limit, sector })
    jobs = res.items
    total = res.total
  } catch (e) {
    error = "Could not load jobs right now. Please try again in a moment."
  }

  const totalPages = Math.ceil(total / limit)

  return (
    <div className="section" style={{ paddingTop: "3rem" }}>
      {/* Header */}
      <div style={{ marginBottom: "2.5rem" }}>
        <div className="badge badge-purple" style={{ marginBottom: "0.75rem" }}>
          {total} open role{total !== 1 ? "s" : ""}
        </div>
        <h1 style={{ fontSize: "2.5rem", fontWeight: 800, letterSpacing: "-0.03em", margin: "0 0 0.75rem" }}>
          Find your next role
        </h1>
        <p style={{ color: "var(--text-secondary)", margin: 0 }}>
          Every application is anonymised before review. Your skills speak for themselves.
        </p>
      </div>

      {/* Sector filter */}
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          flexWrap: "wrap",
          marginBottom: "2rem",
          padding: "1rem",
          background: "var(--bg-surface)",
          borderRadius: "var(--radius-lg)",
          border: "1px solid var(--border)",
        }}
      >
        {SECTORS.map((s) => {
          const isActive = (!sector && s === "All") || sector === s
          return (
            <Link
              key={s}
              href={s === "All" ? "/jobs" : `/jobs?sector=${encodeURIComponent(s)}`}
              style={{
                padding: "0.35rem 0.85rem",
                borderRadius: "999px",
                fontSize: "0.8rem",
                fontWeight: isActive ? 700 : 400,
                textDecoration: "none",
                background: isActive ? "var(--gradient-brand)" : "var(--bg-elevated)",
                color: isActive ? "white" : "var(--text-secondary)",
                border: isActive ? "none" : "1px solid var(--border)",
                transition: "all 0.15s",
              }}
            >
              {s}
            </Link>
          )
        })}
      </div>

      {/* Error state */}
      {error && (
        <div
          style={{
            padding: "1.5rem",
            background: "hsla(0, 70%, 55%, 0.1)",
            border: "1px solid hsla(0, 70%, 55%, 0.3)",
            borderRadius: "var(--radius-md)",
            color: "var(--danger)",
            marginBottom: "2rem",
          }}
        >
          {error}
        </div>
      )}

      {/* Job grid */}
      {jobs.length === 0 && !error ? (
        <div style={{ textAlign: "center", padding: "5rem 0", color: "var(--text-muted)" }}>
          <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>🔍</div>
          <p style={{ fontSize: "1.1rem" }}>No open roles in this sector right now.</p>
          <Link href="/jobs" className="btn btn-secondary" style={{ marginTop: "1rem" }}>
            View all roles
          </Link>
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
            gap: "1.25rem",
          }}
        >
          {jobs.map((job) => (
            <JobCard key={job.jd_id} job={job} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div
          style={{
            display: "flex",
            gap: "0.5rem",
            justifyContent: "center",
            marginTop: "3rem",
            flexWrap: "wrap",
          }}
        >
          {page > 1 && (
            <Link
              href={`/jobs?${sector ? `sector=${sector}&` : ""}page=${page - 1}`}
              className="btn btn-secondary"
            >
              ← Previous
            </Link>
          )}
          <span
            style={{
              display: "flex",
              alignItems: "center",
              padding: "0 1rem",
              color: "var(--text-muted)",
              fontSize: "0.875rem",
            }}
          >
            Page {page} of {totalPages}
          </span>
          {page < totalPages && (
            <Link
              href={`/jobs?${sector ? `sector=${sector}&` : ""}page=${page + 1}`}
              className="btn btn-secondary"
            >
              Next →
            </Link>
          )}
        </div>
      )}
    </div>
  )
}

function JobCard({ job }: { job: Job }) {
  const contractClass = CONTRACT_COLORS[job.contract_type] || "badge-purple"
  const topSkills = (job.skills_technical || []).slice(0, 4)

  return (
    <article className="card" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {/* Header */}
      <div>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
          {job.contract_type && (
            <span className={`badge ${contractClass}`}>{job.contract_type}</span>
          )}
          {job.sector && (
            <span className="badge badge-purple">{job.sector}</span>
          )}
        </div>
        <h2 style={{ fontWeight: 700, fontSize: "1.1rem", margin: "0 0 0.25rem", lineHeight: 1.3 }}>
          {job.title}
        </h2>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", margin: 0 }}>
          {job.organisation}
          {job.location && <span> · {job.location}</span>}
        </p>
      </div>

      {/* Salary */}
      {job.salary_range && (
        <div style={{ fontSize: "0.875rem", color: "var(--brand-teal-400)", fontWeight: 600 }}>
          💷 {job.salary_range}
        </div>
      )}

      {/* Skills */}
      {topSkills.length > 0 && (
        <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
          {topSkills.map((skill) => (
            <span
              key={skill}
              style={{
                padding: "0.2rem 0.6rem",
                background: "var(--bg-hover)",
                borderRadius: "999px",
                fontSize: "0.7rem",
                color: "var(--text-secondary)",
                border: "1px solid var(--border)",
              }}
            >
              {skill}
            </span>
          ))}
        </div>
      )}

      {/* CTA */}
      <div style={{ marginTop: "auto", paddingTop: "0.5rem" }}>
        <Link
          href={`/jobs/${job.jd_id}`}
          className="btn btn-primary"
          style={{ width: "100%", justifyContent: "center" }}
        >
          View & Apply →
        </Link>
      </div>
    </article>
  )
}
