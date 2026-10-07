import type { ReactNode } from "react"
import { Badge } from "@/components/ui/badge"
import { cn } from "cn"

export type Tone = "green" | "red" | "amber" | "blue" | "violet" | "gray"

const TONE_CLASS: Record<Tone, string> = {
  green: "bg-emerald-500/15 text-emerald-400",
  red: "bg-destructive/15 text-destructive",
  amber: "bg-amber-500/15 text-amber-400",
  blue: "bg-sky-500/15 text-sky-400",
  violet: "bg-violet-500/15 text-violet-400",
  gray: "bg-muted text-muted-foreground",
}

export const TONE_TEXT: Record<Tone, string> = {
  green: "text-emerald-400",
  red: "text-destructive",
  amber: "text-amber-400",
  blue: "text-sky-400",
  violet: "text-violet-400",
  gray: "text-muted-foreground",
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
    <Badge
      variant="outline"
      className={cn("border-transparent font-semibold", TONE_CLASS[tone], className)}
    >
      {children}
    </Badge>
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
