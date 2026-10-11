import { useState, type FormEvent } from "react"
import { PasswordInput } from "@/components/ui/password-input"
import { useAuth } from "@/state/auth"

export function LoginPage() {
  const { login } = useAuth()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState(false)

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
    <main className="auth-layout">
      <section className="auth-panel space-y-6">
        <p className="text-base font-semibold tracking-[0.02em] text-signal-info">metroChek</p>
        <div>
          <h2 className="text-xl font-semibold text-ink">Вход</h2>
          <p className="mt-2 text-sm text-steel">Контроль протоколов поверки.</p>
        </div>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <label className="block text-sm text-steel">
            Email
            <input
              autoComplete="username"
              autoFocus
              className="form-input"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <PasswordInput
            autoComplete="current-password"
            label="Пароль"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          {error ? <p className="text-sm text-[var(--danger-text)]">Неверный email или пароль</p> : null}
          <button className="btn-primary disabled:opacity-60" disabled={busy} type="submit">
            {busy ? "Входим..." : "Войти"}
          </button>
        </form>
        <p className="text-sm text-steel">
          Нет доступа? Администратор должен создать учётную запись — на email придёт ссылка для
          задания пароля.
        </p>
      </section>
    </main>
  )
}
