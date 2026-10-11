import type { ReactNode } from "react"

/**
 * The fleet empty state: what a list shows when it has nothing to show. One shape
 * everywhere, so an empty queue, an empty history and an empty folder look alike.
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      className={[
        "flex flex-col items-center gap-2 px-4 py-8 text-center text-sm text-steel",
        className ?? "",
      ]
        .join(" ")
        .trim()}
    >
      {icon ? <span className="text-steel/70">{icon}</span> : null}
      <span className="font-medium text-ink">{title}</span>
      {description ? <span className="max-w-md">{description}</span> : null}
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  )
}
