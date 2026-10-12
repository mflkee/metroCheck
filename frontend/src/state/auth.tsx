import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import * as api from "@/lib/api"

interface AuthValue {
  authed: boolean
  /** Who is signed in — the account menu shows it. */
  user: api.AuthUser | null
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authed, setAuthed] = useState(() => api.isLoggedIn())
  const [user, setUser] = useState<api.AuthUser | null>(null)

  const logout = useCallback(() => {
    api.clearToken()
    setAuthed(false)
    setUser(null)
  }, [])

  useEffect(() => {
    api.setUnauthorizedHandler(logout)
    return () => api.setUnauthorizedHandler(null)
  }, [logout])

  const login = useCallback(async (email: string, password: string) => {
    const session = await api.login(email, password)
    api.setToken(session.accessToken)
    setUser(session.user)
    setAuthed(true)
  }, [])

  // A reload keeps the token, so the identity is fetched back from the API.
  useEffect(() => {
    if (!authed || user) return
    let cancelled = false
    api
      .getMe()
      .then((me) => {
        if (!cancelled) setUser(me)
      })
      .catch(() => {
        // the token is checked on the next request; a failed lookup is not fatal
      })
    return () => {
      cancelled = true
    }
  }, [authed, user])

  const value = useMemo(
    () => ({ authed, user, login, logout }),
    [authed, user, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error("useAuth must be used within AuthProvider")
  return context
}
