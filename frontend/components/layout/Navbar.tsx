"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useState } from "react"
import { useAuth } from "@/lib/auth"

export default function Navbar() {
  const { isAuthenticated, user, logout } = useAuth()
  const pathname = usePathname()
  const [mobileOpen, setMobileOpen] = useState(false)

  const isDashboard = pathname?.startsWith("/dashboard")

  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 50,
        borderBottom: "1px solid var(--border-subtle)",
        backdropFilter: "blur(20px)",
        backgroundColor: "rgba(10, 10, 15, 0.85)",
      }}
    >
      <nav
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          padding: "0 1.5rem",
          height: "64px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "2rem",
        }}
      >
        {/* Logo */}
        <Link href="/" style={{ textDecoration: "none", display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span
            style={{
              width: "32px",
              height: "32px",
              borderRadius: "8px",
              background: "var(--gradient-brand)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "1rem",
              flexShrink: 0,
            }}
          >
            ✦
          </span>
          <span style={{ fontWeight: 800, fontSize: "1.1rem", letterSpacing: "-0.02em" }}>
            <span className="text-gradient">Dyver</span>
            <span style={{ color: "var(--text-primary)" }}>sifying</span>
          </span>
        </Link>

        {/* Desktop nav */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.25rem", flex: 1 }}>
          <NavLink href="/jobs" active={pathname === "/jobs"}>Browse Jobs</NavLink>
          {isAuthenticated && (
            <NavLink href="/dashboard" active={isDashboard}>Dashboard</NavLink>
          )}
        </div>

        {/* Auth actions */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          {isAuthenticated ? (
            <>
              <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", display: "none" }}>
                {user?.email}
              </span>
              <button
                className="btn btn-secondary"
                onClick={logout}
                style={{ fontSize: "0.8rem", padding: "0.5rem 1rem" }}
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link href="/auth/login" className="btn btn-ghost" style={{ fontSize: "0.875rem" }}>
                Log in
              </Link>
              <Link href="/auth/register" className="btn btn-primary" style={{ fontSize: "0.875rem" }}>
                Post a Job
              </Link>
            </>
          )}
        </div>
      </nav>
    </header>
  )
}

function NavLink({
  href,
  active,
  children,
}: {
  href: string
  active: boolean
  children: React.ReactNode
}) {
  return (
    <Link
      href={href}
      style={{
        padding: "0.4rem 0.75rem",
        borderRadius: "8px",
        fontSize: "0.875rem",
        fontWeight: active ? 600 : 400,
        color: active ? "var(--text-primary)" : "var(--text-secondary)",
        background: active ? "var(--bg-elevated)" : "transparent",
        textDecoration: "none",
        transition: "all 0.15s",
      }}
      onMouseEnter={(e) => {
        if (!active) {
          e.currentTarget.style.color = "var(--text-primary)"
          e.currentTarget.style.background = "var(--bg-elevated)"
        }
      }}
      onMouseLeave={(e) => {
        if (!active) {
          e.currentTarget.style.color = "var(--text-secondary)"
          e.currentTarget.style.background = "transparent"
        }
      }}
    >
      {children}
    </Link>
  )
}
