import { ThemeSwitcher } from "@/components/theme-switcher"
import { useAuth } from "@/state/auth"

/**
 * The top-bar actions: the fleet theme picker and the way out.
 *
 * metroCheck has no profile or settings screen of its own, so the account block is
 * just the exit — there is nothing else to put behind it.
 */
export function AccountMenu() {
  const { logout } = useAuth()

  return (
    <div className="flex min-w-0 items-center justify-end gap-2">
      <div className="hidden md:flex">
        <ThemeSwitcher />
      </div>
      <button className="btn-secondary btn-sm shrink-0" type="button" onClick={logout}>
        Выйти
      </button>
    </div>
  )
}
