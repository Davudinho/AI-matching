"use client"

import { useState } from "react"
import Link from "next/link"
import { useAuth } from "@/lib/auth"
import { ApiError } from "@/lib/api"

export default function LoginPage() {
  const { login } = useAuth()
  const [form, setForm] = useState({ email: "", password: "" })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      await login(form.email, form.password)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Login failed. Please check your credentials.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        minHeight: "calc(100dvh - 64px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem 1.5rem",
      }}
    >
      <div style={{ width: "100%", maxWidth: "400px" }}>
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 800, margin: "0 0 0.5rem", letterSpacing: "-0.02em" }}>
            Welcome back
          </h1>
          <p style={{ color: "var(--text-secondary)", margin: 0, fontSize: "0.9rem" }}>
            Log in to your recruiter dashboard
          </p>
        </div>

        <form className="card" onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          <div>
            <label className="label" htmlFor="login-email">Email</label>
            <input
              id="login-email"
              className="input"
              type="email"
              placeholder="jane@company.com"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
              autoComplete="email"
              autoFocus
            />
          </div>

          <div>
            <label className="label" htmlFor="login-password">Password</label>
            <input
              id="login-password"
              className="input"
              type="password"
              placeholder="Your password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
              autoComplete="current-password"
            />
          </div>

          {error && (
            <div
              style={{
                padding: "0.75rem 1rem",
                background: "hsla(0, 70%, 55%, 0.1)",
                border: "1px solid hsla(0, 70%, 55%, 0.25)",
                borderRadius: "var(--radius-md)",
                color: "var(--danger)",
                fontSize: "0.875rem",
              }}
            >
              {error}
            </div>
          )}

          <button
            id="login-submit"
            type="submit"
            className="btn btn-primary"
            style={{ justifyContent: "center", padding: "0.875rem", fontSize: "1rem", opacity: loading ? 0.7 : 1 }}
            disabled={loading}
          >
            {loading ? "Logging in…" : "Log in →"}
          </button>

          <hr className="divider" style={{ margin: 0 }} />

          <p style={{ textAlign: "center", fontSize: "0.875rem", color: "var(--text-muted)", margin: 0 }}>
            Don't have an account?{" "}
            <Link href="/auth/register" style={{ color: "var(--brand-purple-400)", fontWeight: 600, textDecoration: "none" }}>
              Sign up free
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}
