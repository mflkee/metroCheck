type AppVersionBadgeProps = {
  version: string
  /** The release channel — `beta` for a pre-1.0 service. */
  stage?: string
  onClick?: () => void
  className?: string
  title?: string
}

/**
 * The version and the release channel, set next to the wordmark and on its baseline
 * rather than in a chip of their own. The version comes from the build (Vite injects
 * it), so the shell never hardcodes it.
 */
export function AppVersionBadge({
  version,
  stage,
  onClick,
  className,
  title,
}: AppVersionBadgeProps) {
  return (
    <button
      className={[
        "shrink-0 whitespace-nowrap text-[10px] font-semibold tracking-[0.08em] text-steel",
        onClick ? "transition hover:text-ink" : "",
        className ?? "",
      ].join(" ")}
      onClick={onClick}
      title={title ?? (stage ? `v${version} (${stage})` : `v${version}`)}
      type="button"
    >
      <span className="whitespace-nowrap">v{version}</span>
      {stage ? (
        <span
          className="ml-1.5 text-[9px] uppercase tracking-[0.16em] text-steel/70"
          data-testid="app-stage"
        >
          {stage}
        </span>
      ) : null}
    </button>
  )
}
