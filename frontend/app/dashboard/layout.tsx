"use client"

import { useRequireAuth } from "@/lib/auth"

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { isLoading, isAuthenticated } = useRequireAuth()

  if (isLoading) {
    return (
      <div
        style={{
          minHeight: "calc(100dvh - 64px)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            width: "40px",
            height: "40px",
            border: "3px solid var(--border)",
            borderTopColor: "var(--brand-purple-500)",
            borderRadius: "50%",
            animation: "spin 0.8s linear infinite",
          }}
        />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    )
  }

  if (!isAuthenticated) return null // redirect handled by useRequireAuth

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "220px 1fr",
        minHeight: "calc(100dvh - 64px)",
      }}
    >
      {/* Sidebar */}
      <aside
        style={{
          borderRight: "1px solid var(--border-subtle)",
          padding: "1.5rem 1rem",
          background: "var(--bg-surface)",
          position: "sticky",
          top: "64px",
          height: "calc(100dvh - 64px)",
        }}
      >
        <nav style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          <SidebarLink href="/dashboard" icon="📊" label="Overview" />
          <SidebarLink href="/dashboard/jobs" icon="💼" label="Job Descriptions" />
          <SidebarLink href="/dashboard/jobs/new" icon="+" label="Create JD" isAccent />
        </nav>
      </aside>

      {/* Main content */}
      <main style={{ padding: "2rem" }}>{children}</main>
    </div>
  )
}

function SidebarLink({
  href,
  icon,
  label,
  isAccent = false,
}: {
  href: string
  icon: string
  label: string
  isAccent?: boolean
}) {
  return (
    <a
      href={href}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.6rem",
        padding: "0.6rem 0.75rem",
        borderRadius: "var(--radius-sm)",
        textDecoration: "none",
        fontSize: "0.875rem",
        fontWeight: isAccent ? 700 : 400,
        color: isAccent ? "white" : "var(--text-secondary)",
        background: isAccent ? "var(--gradient-brand)" : "transparent",
        transition: "all 0.15s",
      }}
    >
      <span style={{ fontSize: "1rem" }}>{icon}</span>
      {label}
    </a>
  )
}
