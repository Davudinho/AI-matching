"use client"

import { useCallback, useEffect, useState, type ReactNode } from "react"
import { useRouter } from "next/navigation"
import { AuthContext, type AuthState } from "@/lib/auth"
import { api, tokenStorage } from "@/lib/api"

/**
 * AuthProvider — wraps the entire app to manage JWT auth state.
 * Must be a .tsx file because it contains JSX.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter()
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: true,
    isAuthenticated: false,
  })

  // On mount: restore session from stored JWT
  useEffect(() => {
    const restore = async () => {
      const token = tokenStorage.get()
      if (!token) {
        setState({ user: null, isLoading: false, isAuthenticated: false })
        return
      }
      try {
        const user = await api.auth.me()
        setState({ user, isLoading: false, isAuthenticated: true })
      } catch {
        tokenStorage.clear()
        setState({ user: null, isLoading: false, isAuthenticated: false })
      }
    }
    restore()
  }, [])

  const login = useCallback(
    async (email: string, password: string) => {
      const { access_token } = await api.auth.login(email, password)
      tokenStorage.set(access_token)
      const user = await api.auth.me()
      setState({ user, isLoading: false, isAuthenticated: true })
      router.push("/dashboard")
    },
    [router]
  )

  const register = useCallback(
    async (email: string, password: string, fullName?: string) => {
      const { access_token } = await api.auth.register(email, password, fullName)
      tokenStorage.set(access_token)
      const user = await api.auth.me()
      setState({ user, isLoading: false, isAuthenticated: true })
      router.push("/dashboard")
    },
    [router]
  )

  const logout = useCallback(() => {
    tokenStorage.clear()
    setState({ user: null, isLoading: false, isAuthenticated: false })
    router.push("/auth/login")
  }, [router])

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
