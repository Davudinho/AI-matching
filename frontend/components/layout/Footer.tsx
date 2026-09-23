import Link from "next/link"

export default function Footer() {
  return (
    <footer
      style={{
        borderTop: "1px solid var(--border-subtle)",
        padding: "3rem 1.5rem",
        marginTop: "auto",
      }}
    >
      <div
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          display: "grid",
          gridTemplateColumns: "1fr auto",
          gap: "2rem",
          alignItems: "center",
        }}
      >
        {/* Brand */}
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
            <span
              style={{
                width: "24px",
                height: "24px",
                borderRadius: "6px",
                background: "var(--gradient-brand)",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "0.75rem",
              }}
            >
              ✦
            </span>
            <span style={{ fontWeight: 700, fontSize: "0.95rem" }}>
              <span className="text-gradient">Dyver</span>
              <span style={{ color: "var(--text-primary)" }}>sifying</span>
            </span>
          </div>
          <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", margin: 0, maxWidth: "320px" }}>
            AI-powered recruitment that champions diversity and inclusion.
            Built for recruiters who care about fair hiring.
          </p>
        </div>

        {/* Links */}
        <div style={{ display: "flex", gap: "1.5rem" }}>
          <Link href="/jobs" style={{ fontSize: "0.8rem", color: "var(--text-muted)", textDecoration: "none" }}>
            Browse Jobs
          </Link>
          <Link href="/auth/register" style={{ fontSize: "0.8rem", color: "var(--text-muted)", textDecoration: "none" }}>
            For Recruiters
          </Link>
        </div>
      </div>

      <div
        style={{
          maxWidth: "1200px",
          margin: "1.5rem auto 0",
          paddingTop: "1.5rem",
          borderTop: "1px solid var(--border-subtle)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "0.5rem",
        }}
      >
        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", margin: 0 }}>
          © {new Date().getFullYear()} Dyversifying. All rights reserved.
        </p>
        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", margin: 0 }}>
          Powered by Gemini AI
        </p>
      </div>
    </footer>
  )
}
