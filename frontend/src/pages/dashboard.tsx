import { useCallback, useEffect, useState } from "react"
import { Download, FileText, Inbox, Loader2, Mail, Play, RefreshCw, Send, Trash2, X } from "lucide-react"
import { toast } from "sonner"
import { ConfirmDialog } from "@/components/confirm-dialog"
import { HealthBadge, jobStatusTone, ToneBadge } from "@/components/tone-badge"
import { AppDialog } from "@/components/ui/app-dialog"
import { EmptyState } from "@/components/ui/empty-state"
import { PageHeader } from "@/components/ui/page-header"
import { Progress } from "@/components/ui/progress"
import { Select } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { useHealth } from "@/state/health"
import * as api from "@/lib/api"
import { formatSeconds, fmtDate, MONTHS, padMonth, yearOptions } from "@/lib/format"

const HEALTH_ITEMS = [
  { label: "АРШИН API", key: "arshin_api" },
  { label: "Токен АРШИН", key: "arshin_token" },
  { label: "Token Agent", key: "token_agent" },
  { label: "OpenRouter", key: "openrouter" },
]

export function DashboardPage() {
  const [jobs, setJobs] = useState<api.JobsStatus | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async () => {
    try {
      setJobs(await api.getJobsStatus())
    } catch {
      // polling errors are non-fatal
    }
  }, [])

  useEffect(() => {
    void load()
    const id = setInterval(() => void load(), 3000)
    return () => clearInterval(id)
  }, [load])

  const running = jobs?.running ?? null
  const pending = jobs?.pending ?? []
  const recent = jobs?.recent ?? []

  async function manualRefresh() {
    setRefreshing(true)
    await load()
    setRefreshing(false)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Дашборд"
        description="Контроль протоколов поверки"
        action={
          <button className="btn-secondary btn-sm" disabled={refreshing} type="button" onClick={manualRefresh}>
            <RefreshCw className={["h-4 w-4", refreshing ? "animate-spin" : ""].join(" ")} />
            Обновить
          </button>
        }
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <SystemCard />
        <RunCheckCard onEnqueued={load} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="section-card">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold text-ink">Очередь</h3>
              <p className="mt-1 text-sm text-steel">Задачи, ожидающие запуска</p>
            </div>
            <ToneBadge tone="blue">{pending.length}</ToneBadge>
          </div>
          <div className="mt-4">
            {jobs === null ? (
              <p className="text-sm text-steel">Загрузка...</p>
            ) : pending.length === 0 ? (
              <EmptyState icon={<Inbox className="size-7" />} title="Очередь пуста" />
            ) : (
              <div className="space-y-2">
                {pending.map((job) => (
                  <div
                    className="flex min-h-9 flex-wrap items-center gap-2 rounded-2xl border border-line px-3 py-2 text-sm"
                    key={job.id}
                  >
                    <span className="font-semibold text-signal-info">#{job.id}</span>
                    <span className="text-steel">
                      {job.year}-{padMonth(job.month)}
                    </span>
                    <ToneBadge tone="amber">{job.job_type === "manual" ? "Ручн" : "Авто"}</ToneBadge>
                    <span className="flex-1 truncate text-steel">{job.progress || "Ожидание..."}</span>
                    <ConfirmDialog
                      confirmLabel="Отменить"
                      description="Задача будет удалена из очереди."
                      destructive
                      title={`Отменить задачу #${job.id}?`}
                      onConfirm={async () => {
                        await api.cancelJob(job.id)
                        await load()
                      }}
                      trigger={
                        <button className="icon-action-button icon-action-button--danger" title="Отменить" type="button">
                          <X className="h-4 w-4" />
                        </button>
                      }
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="section-card">
          <div>
            <h3 className="text-lg font-semibold text-ink">Последние</h3>
            <p className="mt-1 text-sm text-steel">История проверок</p>
          </div>
          <div className="mt-4">
            {jobs === null ? (
              <p className="text-sm text-steel">Загрузка...</p>
            ) : recent.length === 0 ? (
              <EmptyState icon={<FileText className="size-7" />} title="История пуста" />
            ) : (
              <div className="space-y-2">
                {recent.slice(0, 10).map((job) => (
                  <div
                    className="flex min-h-9 flex-wrap items-center gap-2 rounded-2xl border border-line px-3 py-2 text-sm"
                    key={job.id}
                  >
                    <span className="font-semibold text-signal-info">#{job.id}</span>
                    <span className="text-steel">
                      {job.year}-{padMonth(job.month)}
                    </span>
                    <ToneBadge tone={jobStatusTone(job.status)}>{job.status}</ToneBadge>
                    <span className="flex-1 truncate text-steel">{job.progress || "—"}</span>
                    <span className="text-xs text-steel">{fmtDate(job.completed_at || job.started_at)}</span>
                    <ReportButton id={job.id} />
                    <SendReportButton job={job} />
                    <ConfirmDialog
                      confirmLabel="Удалить"
                      description="Действие необратимо."
                      destructive
                      title={`Удалить задачу #${job.id}?`}
                      onConfirm={async () => {
                        try {
                          await api.deleteJob(job.id)
                          await load()
                        } catch (error) {
                          toast.error(
                            error instanceof api.ApiError ? error.message : "Ошибка удаления",
                          )
                        }
                      }}
                      trigger={
                        <button className="icon-action-button icon-action-button--danger" title="Удалить" type="button">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      }
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>

      <RunningJobCard
        loading={jobs === null}
        running={running}
        onCancel={async () => {
          if (!running) return
          await api.cancelJob(running.id)
          await load()
        }}
      />
    </div>
  )
}

function SystemCard() {
  const { data, problemCount, fetchedAt } = useHealth()
  const systems = data?.systems ?? {}

  return (
    <section className="section-card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-ink">Система</h3>
          <p className="mt-1 text-sm text-steel">Состояние внешних зависимостей</p>
        </div>
        <ToneBadge tone={problemCount === 0 ? "green" : "red"}>
          {problemCount === 0 ? "OK" : `Ошибки: ${problemCount}`}
        </ToneBadge>
      </div>
      <div className="mt-4 space-y-2">
        {HEALTH_ITEMS.map((item) => {
          const state = systems[item.key]
          return (
            <div
              className="flex items-center gap-3 rounded-2xl border border-line px-3 py-2.5 text-sm"
              key={item.key}
            >
              <span className="text-xs text-steel">{item.label}</span>
              <div className="ml-auto flex items-center gap-2">
                {item.key === "arshin_token" && state?.status === "ok" && fetchedAt > 0 ? (
                  <TokenTimer baseSeconds={state.age_seconds ?? 0} fetchedAt={fetchedAt} />
                ) : (
                  <HealthBadge status={state?.status} />
                )}
                {item.key === "openrouter" && state?.balance != null && (
                  <ToneBadge tone="gray">${state.balance}</ToneBadge>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function TokenTimer({ baseSeconds, fetchedAt }: { baseSeconds: number; fetchedAt: number }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  const total = baseSeconds + Math.max(0, Math.floor((now - fetchedAt) / 1000))
  return <ToneBadge tone="green">{formatSeconds(total)}</ToneBadge>
}

function RunCheckCard({ onEnqueued }: { onEnqueued: () => void | Promise<void> }) {
  const years = yearOptions()
  const [year, setYear] = useState(String(years[0]))
  const [month, setMonth] = useState(String(new Date().getMonth() + 1))
  const [useLk, setUseLk] = useState(true)
  const [busy, setBusy] = useState(false)

  async function run() {
    setBusy(true)
    try {
      await api.enqueueJob(Number(year), Number(month), useLk)
      toast.success("Проверка добавлена в очередь")
      await onEnqueued()
    } catch (error) {
      toast.error(error instanceof api.ApiError ? error.message : "Ошибка запуска")
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="section-card">
      <div>
        <h3 className="text-lg font-semibold text-ink">Запустить проверку</h3>
        <p className="mt-1 text-sm text-steel">Поставить задачу в очередь вручную</p>
      </div>
      <div className="mt-4 space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <label className="block min-w-24 flex-1 text-sm text-steel">
            Год
            <Select
              className="mt-1"
              onChange={(next) => setYear(next)}
              options={years.map((value) => ({ value: String(value), label: String(value) }))}
              value={year}
            />
          </label>
          <label className="block min-w-24 flex-1 text-sm text-steel">
            Месяц
            <Select
              className="mt-1"
              onChange={(next) => setMonth(next)}
              options={MONTHS.map((name, index) => ({ value: String(index + 1), label: name }))}
              value={month}
            />
          </label>
          <button className="btn-primary disabled:opacity-60" disabled={busy} type="button" onClick={run}>
            {busy ? <Loader2 className="animate-spin" /> : <Play />}
            Запустить
          </button>
        </div>
        <div className="border-t border-line" />
        <label className="flex items-center gap-3 text-sm text-ink" htmlFor="run-check-lk">
          <Switch checked={useLk} id="run-check-lk" onCheckedChange={setUseLk} />
          С ЛК (Личный кабинет АРШИН)
        </label>
      </div>
    </section>
  )
}

function RunningJobCard({
  running,
  loading,
  onCancel,
}: {
  running: api.Job | null
  loading: boolean
  onCancel: () => void
}) {
  return (
    <section className="section-card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-ink">Активная проверка</h3>
          <p className="mt-1 text-sm text-steel">Текущий прогресс выполнения</p>
        </div>
        {running ? <ReportButton id={running.id} /> : null}
        {running ? <SendReportButton job={running} /> : null}
      </div>
      <div className="mt-4">
        {loading ? (
          <p className="text-sm text-steel">Загрузка...</p>
        ) : !running ? (
          <EmptyState icon={<FileText className="size-7" />} title="Нет активных проверок" />
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-2xl">{running.waiting_for_token ? "⏳" : "⚙️"}</span>
              <div className="min-w-0">
                <div className="text-base font-semibold text-ink">
                  {running.year}-{padMonth(running.month)}
                </div>
                <div className="text-xs text-steel">
                  #{running.id} · {running.job_type === "manual" ? "Ручная" : "Авто"}
                  {running.waiting_for_token && (
                    <span className="text-[var(--warning)]"> · Токен истёк</span>
                  )}
                </div>
              </div>
              <ConfirmDialog
                confirmLabel="Отменить"
                destructive
                title="Отменить текущую проверку?"
                onConfirm={onCancel}
                trigger={
                  <button className="btn-danger btn-sm ml-auto" type="button">
                    <X className="h-4 w-4" />
                    Отменить
                  </button>
                }
              />
            </div>
            <Progress
              label={running.progress || "Инициализация..."}
              showValue
              value={running.progress_percent ?? 0}
            />
            {renderPhaseStats(running)}
          </div>
        )}
      </div>
    </section>
  )
}

function renderPhaseStats(job: api.Job) {
  const stats = job.phase_stats
  if (!stats?.public_api) return null
  return (
    <>
      <div className="border-t border-line" />
      <div className="text-xs text-steel">
        📊 {stats.public_api?.saved ?? 0} записей · 📁 {stats.protocol_scan?.found ?? 0} файлов · 🔍{" "}
        {stats.protocol_ocr?.extracted ?? 0} обработано
      </div>
    </>
  )
}

function ReportButton({ id }: { id: number }) {
  const [busy, setBusy] = useState(false)
  async function download() {
    setBusy(true)
    try {
      const blob = await api.generateReport(id)
      api.downloadBlob(blob, `report_${id}.xlsx`)
    } catch {
      toast.error("Ошибка генерации отчёта")
    } finally {
      setBusy(false)
    }
  }
  return (
    <button
      className="icon-action-button"
      disabled={busy}
      title="Скачать отчёт"
      type="button"
      onClick={download}
    >
      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
    </button>
  )
}

function SendReportButton({ job }: { job: api.Job }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        className="icon-action-button"
        title="Отправить отчёт"
        type="button"
        onClick={() => setOpen(true)}
      >
        <Send className="h-4 w-4" />
      </button>
      <SendReportDialog job={job} open={open} onClose={() => setOpen(false)} />
    </>
  )
}

function SendReportDialog({
  job,
  open,
  onClose,
}: {
  job: api.Job
  open: boolean
  onClose: () => void
}) {
  const [emails, setEmails] = useState<api.Email[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    setSelected(new Set())
    api
      .getEmails()
      .then((data) => setEmails(data.emails ?? []))
      .catch(() => toast.error("Не удалось загрузить список адресов"))
      .finally(() => setLoading(false))
  }, [open])

  function toggle(email: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(email)) {
        next.delete(email)
      } else {
        next.add(email)
      }
      return next
    })
  }

  async function send() {
    if (selected.size === 0) {
      toast.error("Отметьте хотя бы одного получателя")
      return
    }
    setSending(true)
    try {
      const result = await api.sendReport(job.id, [...selected])
      toast.success(
        `Отчёт за ${padMonth(job.month)}.${job.year} отправлен (${result.sent.length})`,
      )
      onClose()
    } catch (error) {
      toast.error(
        error instanceof api.ApiError ? error.message : "Не удалось отправить отчёт",
      )
    } finally {
      setSending(false)
    }
  }

  return (
    <AppDialog
      description="Отчёт будет сгенерирован заново по актуальным данным и отправлен письмом."
      footer={
        <div className="flex justify-end gap-2">
          <button className="btn-secondary" disabled={sending} type="button" onClick={onClose}>
            Отмена
          </button>
          <button
            className="btn-primary disabled:opacity-60"
            disabled={sending || loading || selected.size === 0}
            type="button"
            onClick={send}
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Отправить{selected.size > 0 ? ` (${selected.size})` : ""}
          </button>
        </div>
      }
      open={open}
      size="sm"
      title={`Отправить отчёт за ${padMonth(job.month)}.${job.year}`}
      onClose={onClose}
    >
      {loading ? (
        <p className="text-sm text-steel">Загрузка...</p>
      ) : emails.length === 0 ? (
        <EmptyState
          description="Добавьте адреса в планировщике"
          icon={<Mail className="size-7" />}
          title="Список адресов пуст"
        />
      ) : (
        <div className="space-y-1">
          {emails.map((item) => (
            <label
              className="flex cursor-pointer items-center gap-3 rounded-2xl border border-line px-3 py-2 text-sm"
              key={item.id}
            >
              <input
                checked={selected.has(item.email)}
                className="size-4 accent-[var(--primary)]"
                type="checkbox"
                onChange={() => toggle(item.email)}
              />
              <span className="truncate text-ink">{item.email}</span>
            </label>
          ))}
        </div>
      )}
    </AppDialog>
  )
}
