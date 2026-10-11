import type { ReactNode } from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

/**
 * Tone variants map to semantic theme tokens (--success/--warning/--info/
 * --destructive), so they follow the metro theme instead of hardcoded colors.
 */
export const statusBadgeVariants = cva("border-transparent font-semibold", {
  variants: {
    tone: {
      neutral: "bg-muted text-muted-foreground",
      primary: "bg-primary/15 text-primary",
      info: "bg-info/15 text-info",
      success: "bg-success/15 text-success",
      warning: "bg-warning/15 text-warning",
      danger: "bg-destructive/15 text-[color:var(--danger-text)]",
    },
  },
  defaultVariants: { tone: "neutral" },
})

export type StatusTone = NonNullable<VariantProps<typeof statusBadgeVariants>["tone"]>

export function StatusBadge({
  tone,
  children,
  className,
}: {
  tone?: StatusTone
  children: ReactNode
  className?: string
}) {
  return (
    <Badge variant="outline" className={cn(statusBadgeVariants({ tone }), className)}>
      {children}
    </Badge>
  )
}

/** Common domain tones for verification/protocol workflows. */
export const STATUS_TONES = {
  ok: "success",
  completed: "success",
  active: "info",
  running: "info",
  pending: "warning",
  waiting: "warning",
  warning: "warning",
  failed: "danger",
  error: "danger",
  expired: "danger",
  cancelled: "neutral",
  archived: "neutral",
} as const satisfies Record<string, StatusTone>

export function statusTone(status?: string): StatusTone {
  if (!status) return "neutral"
  return STATUS_TONES[status as keyof typeof STATUS_TONES] ?? "neutral"
}
