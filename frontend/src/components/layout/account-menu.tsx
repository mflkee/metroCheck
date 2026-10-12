import { AccountMenu as FleetAccountMenu } from "@/components/account-menu"
import { useAuth } from "@/state/auth"

/**
 * metroCheck's account block — the fleet's menu (from `@metro/account-menu`) with this app's
 * identity. metroCheck has no profile screen, so the menu offers only the identity and the exit.
 */
export function AccountMenu() {
  const { user, logout } = useAuth()

  return (
    <FleetAccountMenu
      identity={user ? `${user.name || user.email} · ${user.email}` : undefined}
      loginTo={user ? undefined : "/"}
      onLogout={logout}
    />
  )
}
