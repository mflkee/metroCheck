import { useHealth } from "@/state/health"

/**
 * The health dot of the top bar: it reads the same poll the pages use and shows
 * whether every external dependency is fine. It lives in the shell's status slot,
 * so the top bar itself stays generic.
 */
export function HealthIndicator() {
  const { problemCount } = useHealth()
  const online = problemCount === 0
  const title = online ? "Сервер онлайн" : `Есть проблемы: ${problemCount}`

  return (
    <div
      aria-label={title}
      className={[
        "hidden shrink-0 items-center gap-2 text-xs font-medium sm:inline-flex",
        online ? "text-[var(--success)]" : "text-[var(--danger-text)]",
      ].join(" ")}
      title={title}
    >
      <span
        aria-hidden="true"
        className={[
          "h-2 w-2 rounded-full",
          online ? "bg-[var(--success)]" : "bg-[var(--danger)]",
        ].join(" ")}
      />
      <span className="whitespace-nowrap">Сервер</span>
    </div>
  )
}
