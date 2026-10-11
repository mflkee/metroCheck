import { AppVersionBadge as FleetVersionBadge } from "@/components/version-badge"
import { APP_STAGE, APP_VERSION } from "@/lib/appVersion"

type AppVersionBadgeProps = {
  className?: string
  onClick?: () => void
}

/**
 * metroCheck's version badge: the fleet badge (from `@metro/version-badge`) fed with
 * this build's version and channel.
 */
export function AppVersionBadge({ className, onClick }: AppVersionBadgeProps) {
  return (
    <FleetVersionBadge
      className={className}
      onClick={onClick}
      stage={APP_STAGE}
      title={`metroCheck ${APP_VERSION} (${APP_STAGE})`}
      version={APP_VERSION}
    />
  )
}
