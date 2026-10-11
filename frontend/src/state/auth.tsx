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
  /** Error code handed back by the SSO callback, if the flow failed. */
  oidcError: string | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [sso] = useState(() => api.readOidcHash())
  const [authed, setAuthed] = useState(() => {
    if (sso.token) {
      api.setToken(sso.token)
      return true
    }
    return api.isLoggedIn()
  })

  const logout = useCallback(() => {
    api.clearToken()
    setAuthed(false)
  }, [])

  useEffect(() => {
    api.clearOidcHash()
  }, [])

  useEffect(() => {
    api.setUnauthorizedHandler(logout)
    return () => api.setUnauthorizedHandler(null)
  }, [logout])

  const login = useCallback(async (username: string, password: string) => {
    const token = await api.login(username, password)
    api.setToken(token)
    setAuthed(true)
  }, [])

  const value = useMemo(
    () => ({ authed, oidcError: sso.error, login, logout }),
    [authed, sso.error, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error("useAuth must be used within AuthProvider")
  return context
}
