import { create } from "zustand";

export type ThemeName = "light" | "dark" | "gray";

const THEME_STORAGE_KEY = "metrocheck.theme";
const DEFAULT_THEME: ThemeName = "light";

function isThemeName(value: string | null): value is ThemeName {
  return value === "light" || value === "dark" || value === "gray";
}

function getStoredTheme(): ThemeName {
  if (typeof window === "undefined") {
    return DEFAULT_THEME;
  }
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  return isThemeName(stored) ? stored : DEFAULT_THEME;
}

export function applyTheme(theme: ThemeName): void {
  if (typeof document === "undefined") {
    return;
  }
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme === "dark" ? "dark" : "light";
}

type ThemeState = {
  theme: ThemeName;
  setTheme: (theme: ThemeName) => void;
};

export const useThemeStore = create<ThemeState>((set) => ({
  theme: getStoredTheme(),
  setTheme: (theme) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    }
    applyTheme(theme);
    set({ theme });
  },
}));

export function initializeTheme(): void {
  applyTheme(getStoredTheme());
}
