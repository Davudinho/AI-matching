"use client"

import { useState } from "react"
import { api, ApiError } from "@/lib/api"
import { useRouter } from "next/navigation"

type Tab = "text" | "upload"
type Status = "idle" | "loading" | "success" | "error"

export default function NewJDPage() {
  const router = useRouter()
  const [tab, setTab] = useState<Tab>("text")
  const [status, setStatus] = useState<Status>("idle")
  const [error, setError] = useState("")

  // Text form
  const [textForm, setTextForm] = useState({ title: "", organisation: "", raw_text: "" })

  // File upload
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)

  const handleTextSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (textForm.raw_text.length < 100) {
      setError("Please enter at least 100 characters of job description.")
      return
    }
    setStatus("loading")
    setError("")
    try {
      const res = await api.jobs.createFromText({
        title: textForm.title || undefined,
        organisation: textForm.organisation || undefined,
        raw_text: textForm.raw_text,
      })
      router.push(`/dashboard/jobs/${res.jd_id}`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to create JD. Please try again.")
      setStatus("error")
    }
  }

  const handleFileSubmit = async () => {
    if (!uploadFile) return
    setStatus("loading")
    setError("")
    try {
      const res = await api.jobs.upload(uploadFile)
      router.push(`/dashboard/jobs/${res.jd_id}`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to upload JD. Please try again.")
      setStatus("error")
    }
  }

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) {
      const ext = "." + f.name.split(".").pop()?.toLowerCase()
      if (![".pdf", ".docx"].includes(ext)) {
        setError("Only PDF and DOCX files are supported for JD upload.")
        return
      }
      setError("")
      setUploadFile(f)
    }
  }

  const isLoading = status === "loading"

  return (
    <div style={{ maxWidth: "760px" }}>
      {/* Header */}
      <div style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "1.75rem", fontWeight: 800, margin: "0 0 0.25rem", letterSpacing: "-0.02em" }}>
          Create Job Description
        </h1>
        <p style={{ color: "var(--text-secondary)", margin: 0 }}>
          Gemini AI will automatically extract and structure all fields. Embeddings are generated immediately for matching.
        </p>
      </div>

      {/* Tabs */}
      <div
        style={{
          display: "flex",
          gap: "0",
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-md)",
          padding: "4px",
          marginBottom: "1.5rem",
          width: "fit-content",
        }}
      >
        {(["text", "upload"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => { setTab(t); setError("") }}
            style={{
              padding: "0.5rem 1.25rem",
              borderRadius: "calc(var(--radius-md) - 4px)",
              border: "none",
              cursor: "pointer",
              fontSize: "0.875rem",
              fontWeight: tab === t ? 700 : 400,
              background: tab === t ? "var(--gradient-brand)" : "transparent",
              color: tab === t ? "white" : "var(--text-secondary)",
              transition: "all 0.15s",
            }}
          >
            {t === "text" ? "✏️ Paste / Type" : "📄 Upload File"}
          </button>
        ))}
      </div>

      {/* --- TEXT FORM --- */}
      {tab === "text" && (
        <form className="card" onSubmit={handleTextSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <div>
              <label className="label" htmlFor="jd-title">Job title (optional)</label>
              <input
                id="jd-title"
                className="input"
                placeholder="e.g. Senior Data Engineer"
                value={textForm.title}
                onChange={(e) => setTextForm({ ...textForm, title: e.target.value })}
              />
            </div>
            <div>
              <label className="label" htmlFor="jd-org">Organisation (optional)</label>
              <input
                id="jd-org"
                className="input"
                placeholder="e.g. Acme Charity"
                value={textForm.organisation}
                onChange={(e) => setTextForm({ ...textForm, organisation: e.target.value })}
              />
            </div>
          </div>

          <div>
            <label className="label" htmlFor="jd-text">
              Job description text <span style={{ color: "var(--danger)" }}>*</span>
            </label>
            <textarea
              id="jd-text"
              className="input"
              placeholder="Paste the full job description here. Include responsibilities, requirements, skills, and qualifications. The AI will extract and structure all fields automatically."
              value={textForm.raw_text}
              onChange={(e) => setTextForm({ ...textForm, raw_text: e.target.value })}
              rows={14}
              required
              style={{ resize: "vertical", fontFamily: "inherit", lineHeight: 1.6 }}
            />
            <p style={{ margin: "0.4rem 0 0", fontSize: "0.75rem", color: textForm.raw_text.length < 100 ? "var(--warning)" : "var(--text-muted)" }}>
              {textForm.raw_text.length} chars · Min. 100 required
            </p>
          </div>

          {error && <ErrorBanner msg={error} />}

          <button
            id="jd-text-submit"
            type="submit"
            className="btn btn-primary"
            style={{ justifyContent: "center", padding: "0.875rem", fontSize: "1rem", opacity: isLoading ? 0.7 : 1 }}
            disabled={isLoading}
          >
            {isLoading ? "AI is processing…" : "Create JD with AI →"}
          </button>

          {isLoading && (
            <p style={{ textAlign: "center", fontSize: "0.75rem", color: "var(--text-muted)", margin: 0 }}>
              Gemini is extracting fields and generating embeddings. This takes 10–20 seconds.
            </p>
          )}
        </form>
      )}

      {/* --- FILE UPLOAD --- */}
      {tab === "upload" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleFileDrop}
            onClick={() => document.getElementById("jd-file-input")?.click()}
            style={{
              border: `2px dashed ${dragging ? "var(--brand-purple-500)" : uploadFile ? "var(--brand-teal-400)" : "var(--border)"}`,
              borderRadius: "var(--radius-lg)",
              padding: "3rem 1.5rem",
              textAlign: "center",
              cursor: "pointer",
              transition: "all 0.2s",
              background: dragging
                ? "hsla(267, 65%, 55%, 0.05)"
                : uploadFile
                ? "hsla(174, 65%, 38%, 0.05)"
                : "var(--bg-elevated)",
            }}
          >
            <input
              id="jd-file-input"
              type="file"
              accept=".pdf,.docx"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) { setError(""); setUploadFile(f) }
              }}
            />
            {uploadFile ? (
              <>
                <div style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>📋</div>
                <p style={{ fontWeight: 700, margin: "0 0 0.25rem" }}>{uploadFile.name}</p>
                <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", margin: 0 }}>
                  {(uploadFile.size / 1024).toFixed(0)} KB · Click to change
                </p>
              </>
            ) : (
              <>
                <div style={{ fontSize: "2.5rem", marginBottom: "0.75rem" }}>⬆️</div>
                <p style={{ fontWeight: 600, margin: "0 0 0.25rem" }}>Drop your JD file here</p>
                <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", margin: 0 }}>PDF or DOCX · Max 20 MB</p>
              </>
            )}
          </div>

          {error && <ErrorBanner msg={error} />}

          <button
            id="jd-upload-submit"
            className="btn btn-primary"
            style={{ justifyContent: "center", padding: "0.875rem", fontSize: "1rem", opacity: (!uploadFile || isLoading) ? 0.6 : 1 }}
            disabled={!uploadFile || isLoading}
            onClick={handleFileSubmit}
          >
            {isLoading ? "AI is parsing…" : "Upload & Parse with AI →"}
          </button>

          {isLoading && (
            <p style={{ textAlign: "center", fontSize: "0.75rem", color: "var(--text-muted)", margin: 0 }}>
              Extracting text from file and running Gemini AI. ~15–25 seconds.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function ErrorBanner({ msg }: { msg: string }) {
  return (
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
      {msg}
    </div>
  )
}
