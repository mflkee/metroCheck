import type { ReactNode } from "react"
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge"

/**
 * metroCheck's tone vocabulary, mapped onto the fleet's `StatusBadge`.
 *
 * The badge used to carry the Tailwind palette directly (`text-emerald-400`,
 * `text-sky-400`, `text-violet-400`, …), which is exactly what the fleet forbids: a
 * colour that is not a token cannot follow the theme. Every tone now resolves to a
 * semantic token.
 */
export type Tone = "green" | "red" | "amber" | "blue" | "violet" | "gray"

const TONE_TO_STATUS: Record<Tone, StatusTone> = {
  green: "success",
  red: "danger",
  amber: "warning",
  blue: "info",
  violet: "primary",
  gray: "neutral",
}

/** The same tones as text, for the numbers that carry a state on their own. */
export const TONE_TEXT: Record<Tone, string> = {
  green: "text-[var(--success)]",
  red: "text-[var(--danger-text)]",
  amber: "text-[var(--warning)]",
  blue: "text-[var(--info)]",
  violet: "text-[var(--mention)]",
  gray: "text-steel",
}

export function ToneBadge({
  tone,
  children,
  className,
}: {
  tone: Tone
  children: ReactNode
  className?: string
}) {
  return (
    <StatusBadge className={className} tone={TONE_TO_STATUS[tone]}>
      {children}
    </StatusBadge>
  )
}

const HEALTH_LABELS: Record<string, string> = {
  ok: "OK",
  expired: "Истек",
  error: "Ошибка",
  unreachable: "Недоступен",
  not_configured: "Не настроен",
  idle: "Ожидание",
  waiting: "Ожидание файла",
}

const HEALTH_TONES: Record<string, Tone> = {
  ok: "green",
  expired: "red",
  error: "red",
  unreachable: "red",
  waiting: "amber",
  idle: "blue",
  not_configured: "gray",
}

export function HealthBadge({ status }: { status?: string }) {
  const key = status ?? ""
  return (
    <ToneBadge tone={HEALTH_TONES[key] ?? "gray"}>
      {HEALTH_LABELS[key] ?? status ?? "—"}
    </ToneBadge>
  )
}

export function jobStatusTone(status?: string): Tone {
  if (status === "completed") return "green"
  if (status === "failed") return "red"
  return "amber"
}
