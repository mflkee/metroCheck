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
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authed, setAuthed] = useState(() => api.isLoggedIn())

  const logout = useCallback(() => {
    api.clearToken()
    setAuthed(false)
  }, [])

  useEffect(() => {
    api.setUnauthorizedHandler(logout)
    return () => api.setUnauthorizedHandler(null)
  }, [logout])

  const login = useCallback(async (email: string, password: string) => {
    const token = await api.login(email, password)
    api.setToken(token)
    setAuthed(true)
  }, [])

  const value = useMemo(() => ({ authed, login, logout }), [authed, login, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error("useAuth must be used within AuthProvider")
  return context
}
