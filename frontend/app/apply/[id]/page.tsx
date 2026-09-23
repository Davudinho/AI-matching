"use client"

import { useState, useRef } from "react"
import { useParams, useRouter } from "next/navigation"
import { api, ApiError } from "@/lib/api"
import Link from "next/link"

type Step = "upload" | "uploading" | "success" | "error"

export default function ApplyPage() {
  const params = useParams()
  const jdId = params.id as string

  const [step, setStep] = useState<Step>("upload")
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [appRef, setAppRef] = useState("")
  const [errorMsg, setErrorMsg] = useState("")
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFile = (f: File) => {
    const allowed = [".pdf", ".docx", ".txt"]
    const ext = "." + f.name.split(".").pop()?.toLowerCase()
    if (!allowed.includes(ext)) {
      setErrorMsg(`File type '${ext}' is not supported. Please use PDF, DOCX, or TXT.`)
      return
    }
    if (f.size > 10 * 1024 * 1024) {
      setErrorMsg("File is too large. Maximum size is 10 MB.")
      return
    }
    setErrorMsg("")
    setFile(f)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }

  const handleSubmit = async () => {
    if (!file) return
    setStep("uploading")
    setErrorMsg("")
    try {
      const res = await api.candidates.apply(jdId, file)
      setAppRef(res.application_ref)
      setStep("success")
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Something went wrong. Please try again."
      setErrorMsg(msg)
      setStep("error")
    }
  }

  if (step === "success") {
    return (
      <div style={{ maxWidth: "520px", margin: "6rem auto", padding: "0 1.5rem", textAlign: "center" }}>
        <div
          style={{
            width: "80px",
            height: "80px",
            borderRadius: "50%",
            background: "hsla(142, 60%, 45%, 0.15)",
            border: "2px solid var(--success)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "2rem",
            margin: "0 auto 1.5rem",
          }}
        >
          ✓
        </div>
        <h1 style={{ fontSize: "1.75rem", fontWeight: 800, margin: "0 0 0.75rem" }}>
          Application received!
        </h1>
        <p style={{ color: "var(--text-secondary)", marginBottom: "1rem" }}>
          Your CV has been anonymised and submitted for review. Our AI is matching
          your profile against the role requirements.
        </p>
        <div
          style={{
            padding: "0.75rem 1.5rem",
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-md)",
            display: "inline-block",
            marginBottom: "2rem",
          }}
        >
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block" }}>
            Application reference
          </span>
          <span style={{ fontWeight: 800, fontSize: "1.25rem", letterSpacing: "0.1em", color: "var(--brand-purple-400)" }}>
            #{appRef}
          </span>
        </div>
        <div style={{ display: "flex", gap: "0.75rem", justifyContent: "center", flexWrap: "wrap" }}>
          <Link href="/jobs" className="btn btn-secondary">Browse more roles</Link>
          <Link href="/" className="btn btn-ghost">Back to home</Link>
        </div>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: "600px", margin: "4rem auto", padding: "0 1.5rem" }}>
      {/* Back */}
      <Link
        href={`/jobs/${jdId}`}
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
        ← Back to job details
      </Link>

      <div className="card">
        {/* Header */}
        <div style={{ marginBottom: "2rem" }}>
          <div className="badge badge-purple" style={{ marginBottom: "0.75rem" }}>Apply now</div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 800, margin: "0 0 0.5rem", letterSpacing: "-0.02em" }}>
            Upload your CV
          </h1>
          <p style={{ color: "var(--text-secondary)", margin: 0, fontSize: "0.9rem" }}>
            Your personal details will be automatically removed before any recruiter sees your application.
            Only your skills and experience matter here.
          </p>
        </div>

        {/* Anonymisation notice */}
        <div
          style={{
            padding: "0.875rem 1rem",
            background: "hsla(267, 65%, 55%, 0.08)",
            border: "1px solid hsla(267, 65%, 55%, 0.2)",
            borderRadius: "var(--radius-md)",
            display: "flex",
            gap: "0.75rem",
            alignItems: "flex-start",
            marginBottom: "1.5rem",
          }}
        >
          <span style={{ fontSize: "1.2rem" }}>🔒</span>
          <div>
            <p style={{ margin: "0 0 0.25rem", fontWeight: 600, fontSize: "0.875rem" }}>
              Privacy by design
            </p>
            <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-secondary)" }}>
              Name, email, phone, and address are removed before AI processing.
              Recruiters only see your professional profile.
            </p>
          </div>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          style={{
            border: `2px dashed ${dragging ? "var(--brand-purple-500)" : file ? "var(--brand-teal-400)" : "var(--border)"}`,
            borderRadius: "var(--radius-lg)",
            padding: "2.5rem 1.5rem",
            textAlign: "center",
            cursor: "pointer",
            transition: "all 0.2s",
            background: dragging
              ? "hsla(267, 65%, 55%, 0.05)"
              : file
              ? "hsla(174, 65%, 38%, 0.05)"
              : "var(--bg-elevated)",
            marginBottom: "1.25rem",
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt"
            style={{ display: "none" }}
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
          />
          {file ? (
            <>
              <div style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>📄</div>
              <p style={{ fontWeight: 700, margin: "0 0 0.25rem" }}>{file.name}</p>
              <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", margin: 0 }}>
                {(file.size / 1024).toFixed(0)} KB · Click to change
              </p>
            </>
          ) : (
            <>
              <div style={{ fontSize: "2.5rem", marginBottom: "0.75rem" }}>⬆️</div>
              <p style={{ fontWeight: 600, margin: "0 0 0.25rem" }}>
                Drop your CV here or click to browse
              </p>
              <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", margin: 0 }}>
                PDF, DOCX, or TXT · Max 10 MB
              </p>
            </>
          )}
        </div>

        {/* Error */}
        {(errorMsg || step === "error") && (
          <div
            style={{
              padding: "0.875rem 1rem",
              background: "hsla(0, 70%, 55%, 0.1)",
              border: "1px solid hsla(0, 70%, 55%, 0.3)",
              borderRadius: "var(--radius-md)",
              color: "var(--danger)",
              fontSize: "0.875rem",
              marginBottom: "1rem",
            }}
          >
            {errorMsg || "An error occurred. Please try again."}
          </div>
        )}

        {/* Submit */}
        <button
          id="apply-submit-btn"
          className="btn btn-primary"
          style={{
            width: "100%",
            justifyContent: "center",
            padding: "0.875rem",
            fontSize: "1rem",
            opacity: !file || step === "uploading" ? 0.6 : 1,
            cursor: !file || step === "uploading" ? "not-allowed" : "pointer",
          }}
          disabled={!file || step === "uploading"}
          onClick={handleSubmit}
        >
          {step === "uploading" ? (
            <>
              <span
                style={{
                  display: "inline-block",
                  width: "16px",
                  height: "16px",
                  border: "2px solid rgba(255,255,255,0.3)",
                  borderTopColor: "white",
                  borderRadius: "50%",
                  animation: "spin 0.8s linear infinite",
                }}
              />
              Processing your CV…
            </>
          ) : (
            "Submit Application →"
          )}
        </button>

        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

        <p style={{ textAlign: "center", fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.75rem" }}>
          Processing takes 10–20 seconds while AI extracts your profile
        </p>
      </div>
    </div>
  )
}
