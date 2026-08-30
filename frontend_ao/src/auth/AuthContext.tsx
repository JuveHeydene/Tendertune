import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { fetchMe, getToken, login as apiLogin, logout as apiLogout, setToken, type AuthUser } from '../api/client'

type AuthState = {
  user: AuthUser | null
  loading: boolean
  login: (email: string, password: string) => Promise<AuthUser>
  logout: () => Promise<void>
}

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = getToken()
    if (!token) {
      setLoading(false)
      return
    }
    fetchMe()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false))
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      async login(email, password) {
        const res = await apiLogin(email, password)
        setToken(res.access_token)
        setUser(res.user)
        return res.user
      },
      async logout() {
        await apiLogout()
        setToken(null)
        setUser(null)
      },
    }),
    [user, loading],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth hors AuthProvider')
  return ctx
}
