"use client"

import { useState } from "react"
import Link from "next/link"
import { useAuth } from "@/lib/auth"
import { ApiError } from "@/lib/api"

export default function RegisterPage() {
  const { register } = useAuth()
  const [form, setForm] = useState({ fullName: "", email: "", password: "", confirm: "" })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    if (form.password !== form.confirm) {
      setError("Passwords don't match.")
      return
    }
    if (form.password.length < 8) {
      setError("Password must be at least 8 characters.")
      return
    }

    setLoading(true)
    try {
      await register(form.email, form.password, form.fullName || undefined)
      // redirect handled by auth context
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Registration failed. Please try again.")
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
      <div style={{ width: "100%", maxWidth: "420px" }}>
        {/* Header */}
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <div className="badge badge-purple" style={{ marginBottom: "0.75rem" }}>For Recruiters</div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 800, margin: "0 0 0.5rem", letterSpacing: "-0.02em" }}>
            Create your account
          </h1>
          <p style={{ color: "var(--text-secondary)", margin: 0, fontSize: "0.9rem" }}>
            Start posting jobs and finding diverse talent with AI.
          </p>
        </div>

        <form className="card" onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          {/* Full name */}
          <div>
            <label className="label" htmlFor="reg-name">Full name (optional)</label>
            <input
              id="reg-name"
              className="input"
              type="text"
              placeholder="Jane Smith"
              value={form.fullName}
              onChange={(e) => setForm({ ...form, fullName: e.target.value })}
              autoComplete="name"
            />
          </div>

          {/* Email */}
          <div>
            <label className="label" htmlFor="reg-email">Work email</label>
            <input
              id="reg-email"
              className="input"
              type="email"
              placeholder="jane@company.com"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
              autoComplete="email"
            />
          </div>

          {/* Password */}
          <div>
            <label className="label" htmlFor="reg-password">Password</label>
            <input
              id="reg-password"
              className="input"
              type="password"
              placeholder="Min. 8 characters"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
              autoComplete="new-password"
            />
          </div>

          {/* Confirm */}
          <div>
            <label className="label" htmlFor="reg-confirm">Confirm password</label>
            <input
              id="reg-confirm"
              className="input"
              type="password"
              placeholder="Repeat password"
              value={form.confirm}
              onChange={(e) => setForm({ ...form, confirm: e.target.value })}
              required
              autoComplete="new-password"
            />
          </div>

          {/* Error */}
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

          {/* Submit */}
          <button
            id="reg-submit"
            type="submit"
            className="btn btn-primary"
            style={{ justifyContent: "center", padding: "0.875rem", fontSize: "1rem", opacity: loading ? 0.7 : 1 }}
            disabled={loading}
          >
            {loading ? "Creating account…" : "Create account →"}
          </button>

          <hr className="divider" style={{ margin: "0" }} />

          <p style={{ textAlign: "center", fontSize: "0.875rem", color: "var(--text-muted)", margin: 0 }}>
            Already have an account?{" "}
            <Link href="/auth/login" style={{ color: "var(--brand-purple-400)", fontWeight: 600, textDecoration: "none" }}>
              Log in
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}
