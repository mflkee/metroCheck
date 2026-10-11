import { type ChangeEvent, type FocusEvent, type InputHTMLAttributes } from "react"

type TimeInputProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "autoComplete" | "inputMode" | "onChange" | "type" | "value"
> & {
  /** `"HH:MM"`, or `""` when nothing is set. */
  value: string
  onChange: (value: string) => void
}

/** Keeps digits and inserts the colon, so the field reads `09:30` while it is typed. */
function maskTime(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 4)
  if (digits.length <= 2) {
    return digits
  }
  return `${digits.slice(0, 2)}:${digits.slice(2)}`
}

/** Pads and clamps a typed time to a real one; `"9"` becomes `"09:00"`, `"99:99"` becomes `"23:59"`. */
function normalizeTime(value: string): string {
  if (!value.trim()) {
    return ""
  }
  const [rawHours = "", rawMinutes = "00"] = value.split(":")
  const hours = Math.min(23, Number(rawHours || 0))
  const minutes = Math.min(59, Number(rawMinutes || 0))
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`
}

/**
 * A time field the app owns, mirroring `DateInput` and `NumberInput`: the browser is
 * handed a text field, so it never opens the operating system's clock picker and never
 * shows a time in the browser's own format.
 */
export function TimeInput({ value, onChange, onBlur, placeholder = "ЧЧ:ММ", ...rest }: TimeInputProps) {
  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    onChange(maskTime(event.target.value))
  }

  function handleBlur(event: FocusEvent<HTMLInputElement>) {
    const normalized = normalizeTime(event.target.value)
    if (normalized !== event.target.value) {
      onChange(normalized)
    }
    onBlur?.(event)
  }

  return (
    <input
      {...rest}
      autoComplete="off"
      inputMode="numeric"
      placeholder={placeholder}
      type="text"
      value={value}
      onBlur={handleBlur}
      onChange={handleChange}
    />
  )
}
