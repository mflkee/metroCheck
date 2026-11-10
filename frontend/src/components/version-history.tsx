import { useState } from "react"
import changelogRaw from "../../../CHANGELOG.md?raw"
import { AppDialog } from "@/components/ui/app-dialog"
import { AppVersionBadge } from "@/components/layout/app-version-badge"
import { APP_STAGE, APP_VERSION } from "@/lib/appVersion"

/**
 * Версия в шапке + «Что нового».
 *
 * Версия приходит из сборки (`frontend/package.json`), история — из `CHANGELOG.md`
 * в корне репозитория (тот же файл, что читает человек в git и что проверяет CI).
 */

type Release = { version: string; date: string; items: string[] }

function parseChangelog(raw: string): Release[] {
  const releases: Release[] = []
  let current: Release | null = null
  for (const line of raw.split("\n")) {
    const heading = line.match(/^##\s+(.+)$/)
    if (heading) {
      const [version, date] = heading[1].split(/\s+—\s+/, 2)
      current = { version: version.trim(), date: (date ?? "").trim(), items: [] }
      releases.push(current)
      continue
    }
    if (!current) continue
    const bullet = line.match(/^-\s+(.*)$/)
    if (bullet) {
      current.items.push(bullet[1].trim())
    } else if (line.trim() && current.items.length) {
      current.items[current.items.length - 1] += " " + line.trim()
    }
  }
  return releases
}

/** Жирный текст `**…**` → <strong>, остальное как есть. */
function InlineText({ text }: { text: string }) {
  const parts = text.split(/\*\*(.+?)\*\*/g)
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <strong className="font-semibold text-ink" key={index}>
            {part}
          </strong>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  )
}

export function VersionBadgeWithHistory({ className }: { className?: string }) {
  const [open, setOpen] = useState(false)
  const releases = parseChangelog(changelogRaw)

  return (
    <>
      <AppVersionBadge className={className} onClick={() => setOpen(true)} />
      <AppDialog
        description={`Текущая версия ${APP_VERSION} · канал ${APP_STAGE}`}
        open={open}
        size="default"
        title="Что нового"
        onClose={() => setOpen(false)}
      >
        <div className="max-h-[60vh] space-y-5 overflow-y-auto pr-1">
          {releases.length === 0 ? (
            <p className="text-sm text-steel">История изменений пока пуста.</p>
          ) : (
            releases.map((release) => (
              <section key={release.version} className="space-y-2">
                <div className="flex items-baseline gap-2">
                  <h3 className="text-sm font-semibold text-ink">v{release.version}</h3>
                  {release.date ? (
                    <span className="text-xs text-steel">{release.date}</span>
                  ) : null}
                  {release.version === APP_VERSION ? (
                    <span className="text-[10px] uppercase tracking-[0.14em] text-[var(--success)]">
                      текущая
                    </span>
                  ) : null}
                </div>
                <ul className="space-y-1.5 text-sm leading-relaxed text-steel">
                  {release.items.map((item, index) => (
                    <li className="flex gap-2" key={index}>
                      <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-current" />
                      <span>
                        <InlineText text={item} />
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            ))
          )}
        </div>
      </AppDialog>
    </>
  )
}
