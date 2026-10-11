import { useSyncExternalStore } from "react"

export type ThemeName =
  | "dark"
  | "tokyonight"
  | "catppuccin"
  | "kanagawa"
  | "nord"
  | "dracula"
  | "gruvbox"

export type ThemeOption = {
  value: ThemeName
  label: string
}

/** The fleet-wide storage key: one preference, remembered across every service. */
export const THEME_STORAGE_KEY = "metro.theme"

/**
 * Keys the services used before the fleet shared one theme. Read once, so nobody
 * loses the theme they picked before the unification.
 */
const LEGACY_STORAGE_KEYS = ["metrolog.theme", "metroGen.theme", "metroCheck.theme"]

/** The catalogue is dark-only and curated: there is no light theme. */
export const DEFAULT_THEME: ThemeName = "dark"

export const themeOptions: ThemeOption[] = [
  { value: "dark", label: "Темная" },
  { value: "tokyonight", label: "Tokyo Night" },
  { value: "catppuccin", label: "Catppuccin" },
  { value: "kanagawa", label: "Kanagawa" },
  { value: "nord", label: "Nord" },
  { value: "dracula", label: "Dracula" },
  { value: "gruvbox", label: "Gruvbox" },
]

export const themeNames: ThemeName[] = themeOptions.map((option) => option.value)

export function isThemeName(value: unknown): value is ThemeName {
  return typeof value === "string" && themeNames.includes(value as ThemeName)
}

/**
 * A stored value may be unknown (a theme this build no longer ships, an old name),
 * so it is coerced: a known theme is kept, a legacy alias falls back to the default,
 * anything else means "never chose".
 */
export function coerceThemePreference(value: string | null | undefined): ThemeName | null {
  if (isThemeName(value)) {
    return value
  }

  if (value === "tokyo-night") {
    return DEFAULT_THEME
  }

  if (value === "light" || value === "gray" || value === "flexoki" || value === "moonfly") {
    return DEFAULT_THEME
  }

  return null
}

export function getStoredTheme(): ThemeName {
  if (typeof window === "undefined") {
    return DEFAULT_THEME
  }

  const stored = coerceThemePreference(window.localStorage.getItem(THEME_STORAGE_KEY))
  if (stored) {
    return stored
  }

  for (const key of LEGACY_STORAGE_KEYS) {
    const legacy = coerceThemePreference(window.localStorage.getItem(key))
    if (legacy) {
      return legacy
    }
  }

  return DEFAULT_THEME
}

export function applyTheme(theme: ThemeName): void {
  if (typeof document === "undefined") {
    return
  }

  document.documentElement.dataset.theme = theme
  // Every theme in the catalogue is dark, so form controls are always the dark set.
  document.documentElement.style.colorScheme = "dark"
}

export function initializeTheme(): ThemeName {
  const theme = getStoredTheme()
  applyTheme(theme)
  currentTheme = theme
  return theme
}

function persistTheme(theme: ThemeName): void {
  if (typeof window === "undefined") {
    return
  }

  window.localStorage.setItem(THEME_STORAGE_KEY, theme)
}

let currentTheme: ThemeName = typeof window === "undefined" ? DEFAULT_THEME : getStoredTheme()
const listeners = new Set<() => void>()

function emit(): void {
  for (const listener of listeners) {
    listener()
  }
}

export function setTheme(theme: ThemeName): void {
  persistTheme(theme)
  applyTheme(theme)
  currentTheme = theme
  emit()
}

export function getTheme(): ThemeName {
  return currentTheme
}

export function subscribeTheme(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Keeps the theme in sync when another tab of the same service changes it. */
if (typeof window !== "undefined") {
  window.addEventListener("storage", (event) => {
    if (event.key !== THEME_STORAGE_KEY || !event.newValue) {
      return
    }

    const theme = coerceThemePreference(event.newValue)
    if (theme && theme !== currentTheme) {
      applyTheme(theme)
      currentTheme = theme
      emit()
    }
  })
}

export function useTheme(): {
  theme: ThemeName
  setTheme: (theme: ThemeName) => void
  options: ThemeOption[]
} {
  const theme = useSyncExternalStore(subscribeTheme, getTheme, () => DEFAULT_THEME)
  return { theme, setTheme, options: themeOptions }
}
