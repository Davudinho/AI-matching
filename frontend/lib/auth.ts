/**
 * frontend/lib/auth.ts — Auth context, hooks, and types (NO JSX)
 *
 * The AuthProvider JSX component lives in: components/AuthProvider.tsx
 *
 * Usage anywhere in the app:
 *   import { useAuth, useRequireAuth, AuthContext } from "@/lib/auth"
 */

"use client"

import { createContext, useContext, useEffect } from "react"
import { useRouter } from "next/navigation"
import type { RecruiterProfile } from "@/lib/api"

export interface AuthState {
  user: RecruiterProfile | null
  isLoading: boolean
  isAuthenticated: boolean
}

export interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, fullName?: string) => Promise<void>
  logout: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>")
  return ctx
}

/** Redirect to login if not authenticated. Use in dashboard layouts. */
export function useRequireAuth() {
  const auth = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!auth.isLoading && !auth.isAuthenticated) {
      router.replace("/auth/login")
    }
  }, [auth.isLoading, auth.isAuthenticated, router])

  return auth
}
