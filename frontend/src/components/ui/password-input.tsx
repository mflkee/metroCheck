import { useId, useState, type InputHTMLAttributes } from "react"

type PasswordInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label: string
}

/**
 * The fleet password field: the app's own input (never a bare `type="password"` with no way to look
 * at what you typed) with a show/hide control that reads as a control, not as a second field.
 */
export function PasswordInput({ className, id, label, ...props }: PasswordInputProps) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const [isVisible, setIsVisible] = useState(false)

  return (
    <label className="block text-sm text-steel" htmlFor={inputId}>
      {label}
      <div className="relative mt-2">
        <input
          {...props}
          id={inputId}
          className={["form-input pr-28", className ?? ""].join(" ").trim()}
          type={isVisible ? "text" : "password"}
        />
        <button
          aria-label={isVisible ? "Скрыть пароль" : "Показать пароль"}
          className="absolute right-3 top-1/2 inline-flex -translate-y-1/2 items-center gap-2 rounded-full border border-line bg-[var(--panel-bg)] px-3 py-1 text-xs font-medium text-steel transition hover:bg-[var(--accent-soft)] hover:text-ink"
          type="button"
          onClick={() => setIsVisible((value) => !value)}
        >
          <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24">
            <path
              d="M2 12C4.6 7.8 8 5.75 12 5.75S19.4 7.8 22 12c-2.6 4.2-6 6.25-10 6.25S4.6 16.2 2 12Z"
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="1.5"
            />
            <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.5" />
          </svg>
          <span>{isVisible ? "Скрыть" : "Показать"}</span>
        </button>
      </div>
    </label>
  )
}
