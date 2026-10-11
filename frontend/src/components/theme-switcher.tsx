import { useEffect, useRef, useState } from "react"

import { themeOptions, useTheme, type ThemeName } from "@/lib/theme-store"

type ThemeSwitcherProps = {
  /** Themes to offer; defaults to the whole catalogue. */
  themes?: ThemeName[]
  /** Called after the theme is applied — a service may persist it on the profile. */
  onChange?: (theme: ThemeName) => void
  label?: string
}

/**
 * The fleet theme picker: a small button that opens the list of dark themes.
 *
 * It is deliberately not a shadcn dropdown — the fleet's controls are the fleet's
 * own, and metroCheck has no dropdown primitive. The look comes from the shared
 * theme classes (`.theme-menu*`), so it is identical everywhere.
 */
export function ThemeSwitcher({ themes, onChange, label = "Тема" }: ThemeSwitcherProps) {
  const { theme, setTheme } = useTheme()
  const options = themes?.length
    ? themeOptions.filter((option) => themes.includes(option.value))
    : themeOptions

  return (
    <div className="theme-switcher">
      <Picker
        activeLabel={(themeOptions.find((option) => option.value === theme) ?? themeOptions[0]).label}
        label={label}
        options={options.map((option) => ({ value: option.value, label: option.label }))}
        selectedValue={theme}
        onSelect={(value) => {
          const next = value as ThemeName
          setTheme(next)
          onChange?.(next)
        }}
      />
    </div>
  )
}

type PickerProps = {
  label: string
  activeLabel: string
  selectedValue: string
  options: Array<{ value: string; label: string }>
  onSelect: (value: string) => void
}

function Picker({ label, activeLabel, selectedValue, options, onSelect }: PickerProps) {
  const [isOpen, setIsOpen] = useState(false)
  const pickerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!isOpen) {
      return undefined
    }

    function handlePointerDown(event: MouseEvent) {
      if (!pickerRef.current?.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsOpen(false)
      }
    }

    document.addEventListener("mousedown", handlePointerDown)
    document.addEventListener("keydown", handleEscape)

    return () => {
      document.removeEventListener("mousedown", handlePointerDown)
      document.removeEventListener("keydown", handleEscape)
    }
  }, [isOpen])

  return (
    <div ref={pickerRef} className="theme-picker">
      <div className="theme-menu">
        <button
          aria-expanded={isOpen}
          aria-haspopup="listbox"
          aria-label={`Выбор: ${label}`}
          className="btn-secondary btn-sm"
          type="button"
          onClick={() => setIsOpen((open) => !open)}
        >
          <span>{activeLabel}</span>
          <span
            aria-hidden="true"
            className={["theme-menu__caret", isOpen ? "theme-menu__caret--open" : ""].join(" ")}
          >
            ▾
          </span>
        </button>
        {isOpen ? (
          <div aria-label={`Выбор: ${label}`} className="theme-menu__panel" role="listbox">
            {options.map((option) => (
              <button
                key={option.value}
                aria-selected={selectedValue === option.value}
                className={[
                  "theme-menu__option",
                  selectedValue === option.value ? "theme-menu__option--active" : "",
                ].join(" ")}
                role="option"
                type="button"
                onClick={() => {
                  onSelect(option.value)
                  setIsOpen(false)
                }}
              >
                <span>{option.label}</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}
