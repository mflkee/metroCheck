import { useEffect, useState, type FormEvent } from "react"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LogoMark } from "@/components/logo"
import * as api from "@/lib/api"
import { oidcErrorMessage } from "@/lib/oidc"
import { useAuth } from "@/state/auth"

export function LoginPage() {
  const { login, oidcError } = useAuth()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState(false)
  const [ssoEnabled, setSsoEnabled] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .getOidcStatus()
      .then((status) => {
        if (!cancelled) setSsoEnabled(status.enabled)
      })
      .catch(() => {
        // Single sign-on is optional: a failure just hides the button.
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(false)
    setBusy(true)
    try {
      await login(email, password)
    } catch {
      setError(true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden p-4">
      <div
        aria-hidden
        className="pointer-events-none absolute -top-40 left-1/2 size-[32rem] -translate-x-1/2 rounded-full bg-violet-500/10 blur-3xl"
      />
      <Card className="w-full max-w-sm">
        <CardContent className="flex flex-col items-center gap-4 py-2">
          <LogoMark size={48} />
          <div className="text-center">
            <h1 className="text-2xl font-bold">metroChek</h1>
            <p className="text-sm text-muted-foreground">Вход в систему</p>
          </div>
          {oidcError && (
            <p className="text-center text-sm text-destructive">{oidcErrorMessage(oidcError)}</p>
          )}
          {ssoEnabled && (
            <div className="flex w-full flex-col gap-3">
              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={() => {
                  window.location.href = api.oidcLoginUrl()
                }}
              >
                Войти через МКАИР
              </Button>
              <p className="text-center text-sm text-muted-foreground">
                или войдите по логину и паролю
              </p>
            </div>
          )}
          <form className="flex w-full flex-col gap-3" onSubmit={handleSubmit}>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="login-email">Email</Label>
              <Input
                id="login-email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoFocus
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="login-pass">Пароль</Label>
              <Input
                id="login-pass"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>
            <Button type="submit" className="mt-1 w-full" disabled={busy}>
              {busy && <Loader2 className="animate-spin" />}
              Войти
            </Button>
            {error && (
              <p className="text-center text-sm text-destructive">
                Неверное имя пользователя или пароль
              </p>
            )}
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
