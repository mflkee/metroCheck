export const MONTHS = [
  "Янв",
  "Фев",
  "Мар",
  "Апр",
  "Май",
  "Июн",
  "Июл",
  "Авг",
  "Сен",
  "Окт",
  "Ноя",
  "Дек",
]

export const START_YEAR = 2022

export function yearOptions(): number[] {
  const current = new Date().getFullYear()
  const years: number[] = []
  for (let y = current; y >= START_YEAR; y--) years.push(y)
  return years
}

export function padMonth(month: number): string {
  return String(month).padStart(2, "0")
}

export function fmtDate(iso?: string | null): string {
  if (!iso) return "—"
  const date = new Date(iso)
  return date.toLocaleString("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
}

export function formatSeconds(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds))
  const mm = String(Math.floor(safe / 60)).padStart(2, "0")
  const ss = String(safe % 60).padStart(2, "0")
  return `${mm}:${ss}`
}
