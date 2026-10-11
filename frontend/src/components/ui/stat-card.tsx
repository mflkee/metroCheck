import type { ComponentType, ReactNode } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { StatusTone } from "@/components/ui/status-badge"

const TONE_TEXT: Record<StatusTone, string> = {
  neutral: "text-foreground",
  primary: "text-primary",
  info: "text-info",
  success: "text-success",
  warning: "text-warning",
  danger: "text-[color:var(--danger-text)]",
}

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "neutral",
  className,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  icon?: ComponentType<{ className?: string }>
  tone?: StatusTone
  className?: string
}) {
  return (
    <Card className={cn("gap-0 transition-colors hover:ring-foreground/20", className)}>
      <CardContent className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className={cn("text-3xl leading-tight font-bold", TONE_TEXT[tone])}>{value}</div>
          <div className="mt-0.5 text-xs text-muted-foreground">{label}</div>
          {hint ? <div className="mt-1 text-xs text-muted-foreground/80">{hint}</div> : null}
        </div>
        {Icon ? <Icon className="size-5 shrink-0 text-muted-foreground" /> : null}
      </CardContent>
    </Card>
  )
}
