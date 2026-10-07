import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { getHealth, type HealthResponse } from "@/lib/api"
import { useAuth } from "@/state/auth"

interface HealthValue {
  data: HealthResponse | null
  problemCount: number
  fetchedAt: number
}

const HealthContext = createContext<HealthValue>({ data: null, problemCount: 0, fetchedAt: 0 })

export function HealthProvider({ children }: { children: ReactNode }) {
  const { authed } = useAuth()
  const [data, setData] = useState<HealthResponse | null>(null)
  const [fetchedAt, setFetchedAt] = useState(0)

  useEffect(() => {
    if (!authed) return
    let cancelled = false
    const tick = async () => {
      try {
        const next = await getHealth()
        if (!cancelled) {
          setData(next)
          setFetchedAt(Date.now())
        }
      } catch {
        // health endpoint failures are surfaced through the previous snapshot
      }
    }
    void tick()
    const id = setInterval(tick, 10000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [authed])

  const problemCount = useMemo(() => {
    const systems = data?.systems ?? {}
    return Object.values(systems).filter(
      (entry) => entry?.status === "error" || entry?.status === "expired",
    ).length
  }, [data])

  const value = useMemo(() => ({ data, problemCount, fetchedAt }), [data, problemCount, fetchedAt])

  return <HealthContext.Provider value={value}>{children}</HealthContext.Provider>
}

export function useHealth(): HealthValue {
  return useContext(HealthContext)
}
