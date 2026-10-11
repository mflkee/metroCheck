import { type ReactNode } from "react"

/**
 * The fleet page header: the title, the one-line description and the page's actions.
 *
 * It is the header the fleet's pages actually use (metroLog and metroGen shipped the same local
 * copy), so it lives here once. The registry used to carry a different, shadcn-shaped header that
 * only two pilot pages used.
 */
export function PageHeader({
  title,
  description,
  action,
  className,
}: {
  title: string
  description: string
  action?: ReactNode
  className?: string
}) {
  return (
    <header
      className={[
        "mb-5 flex flex-col gap-2 sm:mb-6 sm:gap-3 md:flex-row md:items-start md:justify-between",
        className ?? "",
      ]
        .join(" ")
        .trim()}
    >
      <div className="space-y-1.5 sm:space-y-2">
        <h2 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">{title}</h2>
        <p className="max-w-3xl text-sm leading-6 text-steel">{description}</p>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  )
}
