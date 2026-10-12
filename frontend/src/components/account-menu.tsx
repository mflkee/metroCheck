import { useState } from "react"
import { Link } from "react-router-dom"

import { ThemeSwitcher } from "@/components/theme-switcher"
import { AppDialog } from "@/components/ui/app-dialog"

type AccountMenuProps = {
  /** Who is signed in, as the dialog's second line ("Фамилия Имя · Роль", or an email). */
  identity?: string
  /** The service's profile page — omit it where the service has none. */
  profileTo?: string
  /** Called once the user confirms the exit. */
  onLogout: () => void
  /** Where to send a visitor who is not signed in (renders a login button instead). */
  loginTo?: string
  className?: string
}

/**
 * The fleet account block of the top bar: the theme picker, the profile link and the account
 * button, which opens the identity and the way out.
 *
 * Each service used to assemble this itself — metroLog and metroGen had a menu, metroCheck a
 * bare «Выйти», the console an address and a button — so the right-hand side of the top bar
 * differed in every service. The shape is the same here; only `profileTo` and the identity
 * vary, because only the service knows whether it has a profile page and who is signed in.
 */
export function AccountMenu({
  identity,
  profileTo,
  onLogout,
  loginTo,
  className,
}: AccountMenuProps) {
  const [accountOpen, setAccountOpen] = useState(false)
  const [logoutOpen, setLogoutOpen] = useState(false)
  const signedIn = !loginTo

  return (
    <>
      <div className={["flex min-w-0 items-center justify-end gap-2", className ?? ""].join(" ").trim()}>
        <div className="hidden md:flex">
          <ThemeSwitcher />
        </div>
        {profileTo ? (
          <Link className="btn-secondary btn-sm hidden shrink-0 xl:inline-flex" to={profileTo}>
            Профиль
          </Link>
        ) : null}
        {signedIn ? (
          // The exit lives in this dialog, so the top bar needs no separate «Выйти» button.
          <button
            className="btn-secondary btn-sm shrink-0"
            type="button"
            onClick={() => setAccountOpen(true)}
          >
            Аккаунт
          </button>
        ) : (
          <Link className="btn-primary btn-sm shrink-0" to={loginTo ?? "/"}>
            Войти
          </Link>
        )}
      </div>

      <AppDialog
        description={identity ?? "Управление текущей сессией."}
        open={accountOpen}
        size="sm"
        title="Аккаунт"
        onClose={() => setAccountOpen(false)}
      >
        <div className="space-y-3">
          <div className="md:hidden">
            <ThemeSwitcher />
          </div>
          {profileTo ? (
            <Link
              className="btn-secondary w-full justify-center"
              to={profileTo}
              onClick={() => setAccountOpen(false)}
            >
              Профиль
            </Link>
          ) : null}
          {signedIn ? (
            <button
              className="btn-danger w-full justify-center"
              type="button"
              onClick={() => {
                setAccountOpen(false)
                setLogoutOpen(true)
              }}
            >
              Выйти
            </button>
          ) : (
            <Link
              className="btn-primary w-full justify-center"
              to={loginTo ?? "/"}
              onClick={() => setAccountOpen(false)}
            >
              Войти
            </Link>
          )}
        </div>
      </AppDialog>

      <AppDialog
        description="Текущая сессия будет завершена, и приложение вернет вас на экран входа."
        footer={
          <div className="flex justify-end gap-3">
            <button className="btn-secondary btn-sm" type="button" onClick={() => setLogoutOpen(false)}>
              Отмена
            </button>
            <button
              className="btn-danger btn-sm"
              type="button"
              onClick={() => {
                setLogoutOpen(false)
                onLogout()
              }}
            >
              Выйти
            </button>
          </div>
        }
        open={logoutOpen}
        size="sm"
        title="Выйти из аккаунта?"
        onClose={() => setLogoutOpen(false)}
      >
        {null}
      </AppDialog>
    </>
  )
}
