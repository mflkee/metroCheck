import { useCallback, useEffect, useRef, useState } from "react"
import { Download, FileCheck2, Loader2, RefreshCw, Trash2, Upload } from "lucide-react"
import { toast } from "sonner"
import { PageHeader } from "@/components/ui/page-header"
import { TONE_TEXT, ToneBadge } from "@/components/tone-badge"
import * as api from "@/lib/api"

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`
}

export function PrecheckPage() {
  const [files, setFiles] = useState<File[]>([])
  const [profile, setProfile] = useState<"mvp" | "full">("mvp")
  const [online, setOnline] = useState(true)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<api.PrecheckRunResult | null>(null)
  const [runs, setRuns] = useState<api.PrecheckRunItem[]>([])
  const [reference, setReference] = useState<api.PrecheckReference | null>(null)
  const [ots, setOts] = useState("")
  const [syncing, setSyncing] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [rejected, setRejected] = useState<string[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  const loadHistory = useCallback(async () => {
    try {
      const [items, ref] = await Promise.all([
        api.getPrecheckRuns(10),
        api.getPrecheckReference(),
      ])
      setRuns(items)
      setReference(ref)
    } catch {
      // история не критична для работы страницы
    }
  }, [])

  useEffect(() => {
    void loadHistory()
  }, [loadHistory])

  function addFiles(list: FileList | null) {
    if (!list) return
    const next = [...files]
    const bad: string[] = []
    for (const file of Array.from(list)) {
      const name = file.name.toLowerCase()
      if (name.endsWith(".xls")) {
        bad.push(`${file.name} — старый формат .xls, сохраните как .xlsm или .xlsx`)
        continue
      }
      if (!/\.(xlsm|xlsx|xml)$/.test(name)) {
        bad.push(`${file.name} — нужен .xlsm, .xlsx или .xml`)
        continue
      }
      if (!next.some((f) => f.name === file.name && f.size === file.size)) next.push(file)
    }
    setRejected(bad)
    if (bad.length) toast.error(bad[0], { duration: 8000 })
    else if (next.length > files.length) toast.success(`Добавлено: ${next.length - files.length}`)
    setFiles(next)
  }

  async function run() {
    if (files.length === 0) {
      toast.error("Добавьте файл пачки")
      return
    }
    setRunning(true)
    setResult(null)
    try {
      const data = await api.runPrecheck(files, { profile, online })
      setResult(data)
      toast.success(
        data.totals.errors > 0
          ? `Найдено ошибок: ${data.totals.errors}`
          : "Замечаний нет — пачка прошла проверку",
      )
      void loadHistory()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Проверка не удалась")
    } finally {
      setRunning(false)
    }
  }

  async function download(runId: number) {
    try {
      await api.downloadPrecheckReport(runId)
    } catch {
      toast.error("Не удалось скачать отчёт")
    }
  }

  async function syncReference() {
    if (!ots.trim()) {
      toast.error("Укажите номера ОТ для обновления справочника")
      return
    }
    setSyncing(true)
    try {
      const stats = await api.syncPrecheckReference(ots)
      toast.success(`Обновлено: ${stats.saved ?? 0}, не найдено: ${stats.not_found ?? 0}`)
      setOts("")
      void loadHistory()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось обновить справочник")
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Перед АРШИНом"
        description="Проверка пачки перед загрузкой: МПИ, тип СИ, имя файла, XML-схема"
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="section-card lg:col-span-2">
          <h3 className="text-lg font-semibold text-ink">Файлы пачки</h3>
          <p className="mt-1 text-sm text-steel">
            Перетащите файлы или выберите их вручную. Можно загрузить пачку (.xlsm) и её XML
            вместе — тогда проверится и состав.
          </p>

          <div
            className={
              "mt-4 flex flex-col items-center justify-center gap-2 rounded-lg border-2 " +
              "border-dashed p-6 text-center transition-colors " +
              (dragging ? "border-[var(--success)]" : "border-line")
            }
            onDragOver={(event) => {
              event.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault()
              setDragging(false)
              addFiles(event.dataTransfer.files)
            }}
          >
            <Upload className="h-6 w-6 text-steel" />
            <p className="text-sm text-steel">
              Перетащите сюда файлы или{" "}
              <button
                className={TONE_TEXT.green + " underline"}
                type="button"
                onClick={() => inputRef.current?.click()}
              >
                выберите
              </button>
            </p>
            <input
              ref={inputRef}
              accept=".xlsm,.xlsx,.xml,.xls"
              className="hidden"
              multiple
              type="file"
              onChange={(event) => addFiles(event.target.files)}
            />
          </div>

          {files.length > 0 ? (
            <div className="mt-3 rounded-lg border border-[var(--success)] p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-ink">
                  Выбрано файлов: {files.length}
                </span>
                <button
                  className="text-xs text-steel underline"
                  type="button"
                  onClick={() => setFiles([])}
                >
                  очистить
                </button>
              </div>
              <ul className="mt-2 space-y-1">
                {files.map((file) => (
                  <li
                    className="flex items-center justify-between gap-2 rounded border border-line px-2 py-1.5"
                    key={file.name + file.size}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <FileCheck2 className="h-4 w-4 shrink-0 text-[var(--success)]" />
                      <span className="truncate text-sm text-ink">{file.name}</span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2 text-xs text-steel">
                      {formatSize(file.size)}
                      <button
                        aria-label="Убрать файл"
                        className="btn-secondary btn-sm"
                        type="button"
                        onClick={() => setFiles(files.filter((f) => f !== file))}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="mt-3 text-sm text-steel">
              Файлы не выбраны. Перетащите пачку в рамку выше или нажмите «выберите».
            </p>
          )}

          {rejected.length > 0 && (
            <div className="mt-2 rounded-lg border border-[var(--danger)] p-2 text-xs text-[var(--danger-text)]">
              {rejected.map((item) => (
                <div key={item}>{item}</div>
              ))}
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-steel">
              <input
                checked={online}
                className="h-4 w-4"
                type="checkbox"
                onChange={(event) => setOnline(event.target.checked)}
              />
              догружать новые типы СИ из АРШИН
            </label>
            <label className="flex items-center gap-2 text-sm text-steel">
              <input
                checked={profile === "full"}
                className="h-4 w-4"
                type="checkbox"
                onChange={(event) => setProfile(event.target.checked ? "full" : "mvp")}
              />
              полный набор проверок
            </label>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              className="btn-primary"
              disabled={running || files.length === 0}
              type="button"
              onClick={run}
            >
              {running ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Проверяю…
                </>
              ) : (
                <>
                  <FileCheck2 className="mr-2 h-4 w-4" /> Проверить
                </>
              )}
            </button>
            {result && (
              <button
                className="btn-secondary"
                type="button"
                onClick={() => void download(result.run_id)}
              >
                <Download className="mr-2 h-4 w-4" /> Скачать отчёт
              </button>
            )}
          </div>
        </section>

        <section className="section-card">
          <h3 className="text-lg font-semibold text-ink">Справочник типов СИ</h3>
          <p className="mt-1 text-sm text-steel">
            {reference
              ? `${reference.types} типов · ${reference.mpi} интервалов · ${reference.meth} методик`
              : "загрузка…"}
          </p>
          <p className="mt-2 text-xs text-steel">
            Пополняется автоматически при проверке (если включена догрузка). Можно обновить
            вручную — по списку номеров ОТ из реестра.
          </p>
          <textarea
            className="form-input mt-3 h-24 w-full"
            placeholder="32854-13, 10135-15, 25913-08…"
            value={ots}
            onChange={(event) => setOts(event.target.value)}
          />
          <button
            className="btn-secondary btn-sm mt-2"
            disabled={syncing}
            type="button"
            onClick={syncReference}
          >
            <RefreshCw className={(syncing ? "animate-spin " : "") + "mr-2 h-4 w-4"} />
            Обновить справочник
          </button>
        </section>
      </div>

      {result && (
        <section className="section-card">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-lg font-semibold text-ink">Результат проверки</h3>
            <div className="flex items-center gap-2 text-sm">
              <ToneBadge tone="blue">записей: {result.totals.rows}</ToneBadge>
              <ToneBadge tone={result.totals.errors > 0 ? "red" : "green"}>
                ошибок: {result.totals.errors}
              </ToneBadge>
              <ToneBadge tone={result.totals.warnings > 0 ? "amber" : "green"}>
                предупреждений: {result.totals.warnings}
              </ToneBadge>
            </div>
          </div>

          <table className="mt-3 w-full text-sm">
            <thead className="text-left text-steel">
              <tr>
                <th className="py-1">Файл</th>
                <th className="py-1">Лист</th>
                <th className="py-1 text-right">Записей</th>
                <th className="py-1 text-right">Ошибок</th>
                <th className="py-1 text-right">Предупр.</th>
              </tr>
            </thead>
            <tbody>
              {result.files.map((file) => (
                <tr className="border-t border-line" key={file.name}>
                  <td className="py-1 text-ink">{file.name}</td>
                  <td className="py-1 text-steel">{file.sheet}</td>
                  <td className="py-1 text-right">{file.rows}</td>
                  <td className={"py-1 text-right " + (file.errors ? TONE_TEXT.red : "text-steel")}>
                    {file.errors}
                  </td>
                  <td
                    className={"py-1 text-right " + (file.warnings ? TONE_TEXT.amber : "text-steel")}
                  >
                    {file.warnings}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {result.skipped.length > 0 && (
            <div className="mt-3 rounded-lg border border-[var(--warning)] p-3 text-sm">
              <p className="font-medium text-[var(--warning)]">Пропущенные файлы</p>
              <ul className="mt-1 list-disc pl-5 text-steel">
                {result.skipped.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <section className="section-card">
        <h3 className="text-lg font-semibold text-ink">Последние проверки</h3>
        {runs.length === 0 ? (
          <p className="mt-2 text-sm text-steel">Пока пусто — проверок ещё не было.</p>
        ) : (
          <table className="mt-3 w-full text-sm">
            <thead className="text-left text-steel">
              <tr>
                <th className="py-1">Когда</th>
                <th className="py-1">Кто</th>
                <th className="py-1">Профиль</th>
                <th className="py-1 text-right">Записей</th>
                <th className="py-1 text-right">Ошибок</th>
                <th className="py-1 text-right">Предупр.</th>
                <th className="py-1" />
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr className="border-t border-line" key={run.id}>
                  <td className="py-1 text-ink">{run.created_at}</td>
                  <td className="py-1 text-steel">{run.user ?? "—"}</td>
                  <td className="py-1 text-steel">{run.profile}</td>
                  <td className="py-1 text-right">{run.rows}</td>
                  <td className={"py-1 text-right " + (run.errors ? TONE_TEXT.red : "text-steel")}>
                    {run.errors}
                  </td>
                  <td
                    className={"py-1 text-right " + (run.warnings ? TONE_TEXT.amber : "text-steel")}
                  >
                    {run.warnings}
                  </td>
                  <td className="py-1 text-right">
                    <button
                      aria-label="Скачать отчёт"
                      className="btn-secondary btn-sm"
                      type="button"
                      onClick={() => void download(run.id)}
                    >
                      <Download className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
