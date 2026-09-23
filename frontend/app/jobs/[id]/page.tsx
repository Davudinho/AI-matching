import { api, type JobDetail } from "@/lib/api"
import { notFound } from "next/navigation"
import type { Metadata } from "next"
import Link from "next/link"

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>
}): Promise<Metadata> {
  const { id } = await params
  try {
    const job = await api.jobs.get(id)
    return {
      title: `${job.title} at ${job.organisation}`,
      description: (job.essential_requirements || []).slice(0, 2).join(". "),
    }
  } catch {
    return { title: "Job not found" }
  }
}

export default async function JobDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  let job: JobDetail

  try {
    job = await api.jobs.get(id)
  } catch {
    notFound()
  }

  return (
    <div style={{ maxWidth: "900px", margin: "0 auto", padding: "3rem 1.5rem" }}>
      {/* Back */}
      <Link
        href="/jobs"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "0.4rem",
          color: "var(--text-muted)",
          textDecoration: "none",
          fontSize: "0.875rem",
          marginBottom: "2rem",
        }}
      >
        ← Back to all roles
      </Link>

      {/* Header card */}
      <div
        className="card"
        style={{
          marginBottom: "1.5rem",
          background: "linear-gradient(145deg, hsl(267, 30%, 12%) 0%, hsl(240, 10%, 12%) 100%)",
          borderColor: "hsla(267, 65%, 55%, 0.2)",
        }}
      >
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "1rem" }}>
          {job.contract_type && <span className="badge badge-purple">{job.contract_type}</span>}
          {job.sector && <span className="badge badge-teal">{job.sector}</span>}
          {job.seniority_level && <span className="badge badge-purple">{job.seniority_level}</span>}
        </div>

        <h1 style={{ fontSize: "2rem", fontWeight: 800, margin: "0 0 0.5rem", letterSpacing: "-0.02em" }}>
          {job.title}
        </h1>

        <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap", color: "var(--text-secondary)", fontSize: "0.9rem" }}>
          <span>🏢 {job.organisation}</span>
          {job.location && <span>📍 {job.location}</span>}
          {job.salary_range && <span style={{ color: "var(--brand-teal-400)", fontWeight: 600 }}>💷 {job.salary_range}</span>}
        </div>

        {/* Apply CTA */}
        <div style={{ marginTop: "1.5rem" }}>
          <Link
            href={`/apply/${job.jd_id}`}
            className="btn btn-primary"
            style={{ padding: "0.875rem 2rem", fontSize: "1rem" }}
          >
            Apply Now — Upload Your CV →
          </Link>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "1.25rem" }}>
        {/* Main content */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          {/* Responsibilities */}
          {(job.responsibilities || []).length > 0 && (
            <Section title="Responsibilities">
              <ul style={{ margin: 0, paddingLeft: "1.25rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {job.responsibilities.map((r, i) => (
                  <li key={i} style={{ color: "var(--text-secondary)", fontSize: "0.9rem", lineHeight: 1.5 }}>{r}</li>
                ))}
              </ul>
            </Section>
          )}

          {/* Essential requirements */}
          {(job.essential_requirements || []).length > 0 && (
            <Section title="Essential Requirements">
              <ul style={{ margin: 0, paddingLeft: "1.25rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {job.essential_requirements.map((r, i) => (
                  <li key={i} style={{ color: "var(--text-secondary)", fontSize: "0.9rem", lineHeight: 1.5 }}>{r}</li>
                ))}
              </ul>
            </Section>
          )}

          {/* Desirable */}
          {(job.desirable_requirements || []).length > 0 && (
            <Section title="Desirable Requirements">
              <ul style={{ margin: 0, paddingLeft: "1.25rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {job.desirable_requirements.map((r, i) => (
                  <li key={i} style={{ color: "var(--text-secondary)", fontSize: "0.9rem", lineHeight: 1.5 }}>{r}</li>
                ))}
              </ul>
            </Section>
          )}
        </div>

        {/* Sidebar */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          {/* Skills */}
          {(job.skills_technical || []).length > 0 && (
            <Section title="Technical Skills">
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                {job.skills_technical.map((s) => (
                  <span key={s} className="badge badge-teal">{s}</span>
                ))}
              </div>
            </Section>
          )}

          {(job.skills_soft || []).length > 0 && (
            <Section title="Soft Skills">
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                {job.skills_soft.map((s) => (
                  <span key={s} className="badge badge-purple">{s}</span>
                ))}
              </div>
            </Section>
          )}

          {(job.qualifications || []).length > 0 && (
            <Section title="Qualifications">
              <ul style={{ margin: 0, paddingLeft: "1.25rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                {job.qualifications.map((q, i) => (
                  <li key={i} style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>{q}</li>
                ))}
              </ul>
            </Section>
          )}

          {/* Apply again CTA in sidebar */}
          <div
            style={{
              padding: "1.25rem",
              background: "hsla(267, 65%, 55%, 0.08)",
              border: "1px solid hsla(267, 65%, 55%, 0.2)",
              borderRadius: "var(--radius-md)",
              textAlign: "center",
            }}
          >
            <p style={{ margin: "0 0 1rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
              Ready to apply? Your CV will be anonymised before review.
            </p>
            <Link href={`/apply/${job.jd_id}`} className="btn btn-primary" style={{ width: "100%", justifyContent: "center" }}>
              Apply →
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card">
      <h2
        style={{
          fontSize: "0.75rem",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          color: "var(--text-muted)",
          margin: "0 0 1rem",
        }}
      >
        {title}
      </h2>
      {children}
    </div>
  )
}
