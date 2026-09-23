import Link from "next/link"
import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Dyversifying — AI-Powered Diverse Hiring",
  description:
    "Find your next role or hire diverse talent with our AI-powered matching platform. Fair, transparent, and built for inclusion.",
}

const FEATURES = [
  {
    icon: "🧠",
    title: "AI-Powered Matching",
    desc: "Our 3-stage Gemini AI pipeline evaluates candidates against every requirement — objectively, every time.",
  },
  {
    icon: "⚖️",
    title: "Anonymised by Design",
    desc: "CVs are stripped of personal identifiers before matching. Skills and experience speak first.",
  },
  {
    icon: "📊",
    title: "Transparent Scoring",
    desc: "Recruiters see evidence-based scores and AI explanations — no black-box decisions.",
  },
  {
    icon: "🔄",
    title: "Continuous Learning",
    desc: "The model calibrates with real recruiter decisions, improving match quality over time.",
  },
]

const SECTORS = [
  "Charity & Non-Profit", "Finance", "Legal", "Digital & Tech",
  "Health & Social Care", "Education", "Creative & Media", "HR & Operations",
]

export default function HomePage() {
  return (
    <>
      {/* ---- Hero ---- */}
      <section
        style={{
          minHeight: "calc(100dvh - 64px)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          padding: "6rem 1.5rem 4rem",
          position: "relative",
          overflow: "hidden",
        }}
      >
        {/* Background glow */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: "var(--gradient-hero)",
            pointerEvents: "none",
          }}
        />
        <div
          style={{
            position: "absolute",
            width: "600px",
            height: "600px",
            borderRadius: "50%",
            background: "radial-gradient(circle, hsla(174, 65%, 38%, 0.08) 0%, transparent 70%)",
            top: "30%",
            left: "60%",
            transform: "translate(-50%, -50%)",
            pointerEvents: "none",
          }}
        />

        {/* Badge */}
        <div className="badge badge-purple animate-fade-up" style={{ marginBottom: "1.5rem" }}>
          ✦ AI-Powered · Anonymised · Fair
        </div>

        {/* Headline */}
        <h1
          className="animate-fade-up"
          style={{
            fontSize: "clamp(2.5rem, 6vw, 4.5rem)",
            fontWeight: 900,
            lineHeight: 1.05,
            letterSpacing: "-0.03em",
            maxWidth: "800px",
            animationDelay: "0.1s",
            opacity: 0,
          }}
        >
          Hire for potential,{" "}
          <span className="text-gradient">not prejudice</span>
        </h1>

        <p
          className="animate-fade-up"
          style={{
            fontSize: "1.2rem",
            color: "var(--text-secondary)",
            maxWidth: "560px",
            margin: "1.5rem auto",
            lineHeight: 1.7,
            animationDelay: "0.2s",
            opacity: 0,
          }}
        >
          Dyversifying uses Gemini AI to match candidates to jobs based purely on
          skills and experience — anonymised, evidence-based, and built for inclusion.
        </p>

        {/* CTAs */}
        <div
          className="animate-fade-up"
          style={{
            display: "flex",
            gap: "1rem",
            flexWrap: "wrap",
            justifyContent: "center",
            animationDelay: "0.3s",
            opacity: 0,
          }}
        >
          <Link href="/jobs" className="btn btn-primary" style={{ padding: "0.875rem 2rem", fontSize: "1rem" }}>
            Browse Open Roles →
          </Link>
          <Link href="/auth/register" className="btn btn-secondary" style={{ padding: "0.875rem 2rem", fontSize: "1rem" }}>
            I'm a Recruiter
          </Link>
        </div>

        {/* Stats */}
        <div
          className="animate-fade-up"
          style={{
            display: "flex",
            gap: "3rem",
            marginTop: "4rem",
            flexWrap: "wrap",
            justifyContent: "center",
            animationDelay: "0.4s",
            opacity: 0,
          }}
        >
          {[
            { value: "3-Stage", label: "AI Pipeline" },
            { value: "100%", label: "Anonymised" },
            { value: "3072-dim", label: "Embeddings" },
          ].map((stat) => (
            <div key={stat.label} style={{ textAlign: "center" }}>
              <div
                style={{
                  fontSize: "2rem",
                  fontWeight: 800,
                  letterSpacing: "-0.03em",
                  background: "var(--gradient-brand)",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                }}
              >
                {stat.value}
              </div>
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                {stat.label}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ---- Features ---- */}
      <section className="section">
        <div style={{ textAlign: "center", marginBottom: "3rem" }}>
          <div className="badge badge-teal" style={{ marginBottom: "1rem" }}>How it works</div>
          <h2 style={{ fontSize: "2.25rem", fontWeight: 800, letterSpacing: "-0.03em", margin: "0 0 1rem" }}>
            Built different. Built fair.
          </h2>
          <p style={{ color: "var(--text-secondary)", maxWidth: "480px", margin: "0 auto" }}>
            Every design decision puts fairness first — from anonymisation to explainability.
          </p>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: "1.25rem",
          }}
        >
          {FEATURES.map((f, i) => (
            <div
              key={f.title}
              className="card"
              style={{ animationDelay: `${i * 0.1}s` }}
            >
              <div style={{ fontSize: "2rem", marginBottom: "1rem" }}>{f.icon}</div>
              <h3 style={{ fontWeight: 700, margin: "0 0 0.5rem", fontSize: "1.05rem" }}>{f.title}</h3>
              <p style={{ color: "var(--text-secondary)", margin: 0, fontSize: "0.9rem", lineHeight: 1.6 }}>
                {f.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ---- Sectors ---- */}
      <section style={{ padding: "4rem 1.5rem", borderTop: "1px solid var(--border-subtle)" }}>
        <div style={{ maxWidth: "1200px", margin: "0 auto", textAlign: "center" }}>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: "1.5rem" }}>
            Roles across all sectors
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", justifyContent: "center" }}>
            {SECTORS.map((s) => (
              <Link
                key={s}
                href={`/jobs?sector=${encodeURIComponent(s)}`}
                className="badge badge-purple"
                style={{ textDecoration: "none", padding: "0.4rem 1rem", fontSize: "0.8rem" }}
              >
                {s}
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* ---- CTA Banner ---- */}
      <section style={{ padding: "5rem 1.5rem" }}>
        <div
          style={{
            maxWidth: "760px",
            margin: "0 auto",
            background: "var(--gradient-brand)",
            borderRadius: "var(--radius-xl)",
            padding: "3.5rem 2rem",
            textAlign: "center",
            boxShadow: "var(--shadow-glow)",
          }}
        >
          <h2 style={{ fontSize: "2rem", fontWeight: 800, margin: "0 0 1rem", color: "white", letterSpacing: "-0.03em" }}>
            Ready to apply?
          </h2>
          <p style={{ color: "rgba(255,255,255,0.8)", margin: "0 0 2rem", fontSize: "1.05rem" }}>
            Browse all open roles and upload your CV — the AI handles the matching,
            you just need to show up as yourself.
          </p>
          <Link
            href="/jobs"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.875rem 2.5rem",
              background: "white",
              color: "hsl(267, 65%, 45%)",
              borderRadius: "var(--radius-md)",
              fontWeight: 700,
              fontSize: "1rem",
              textDecoration: "none",
              boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
            }}
          >
            See all open roles →
          </Link>
        </div>
      </section>
    </>
  )
}
