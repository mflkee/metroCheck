import { useCallback, useEffect, useState, type ReactNode } from "react"
import { Download, FileText, Inbox, Loader2, Play, RefreshCw, Trash2, X } from "lucide-react"
import { cn } from "cn"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { ConfirmDialog } from "@/components/confirm-dialog"
import { HealthBadge, jobStatusTone, ToneBadge, TONE_TEXT, type Tone } from "@/components/tone-badge"
import { useHealth } from "@/state/health"
import * as api from "@/lib/api"
import { formatSeconds, fmtDate, MONTHS, padMonth, yearOptions } from "@/lib/format"
import { toast } from "sonner"

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
  const lastCompleted = recent.find((job) => job.status === "completed")

  const devices = running
    ? (running.total_devices ?? 0) > 0
      ? `${running.processed_devices ?? 0}/${running.total_devices}`
      : "—"
    : (lastCompleted?.phase_stats?.public_api?.saved ?? "—")
  const errors = lastCompleted?.phase_stats?.full_check?.errors ?? "—"

  async function manualRefresh() {
    setRefreshing(true)
    await load()
    setRefreshing(false)
  }

  return (
    <div className="fade-in space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">Дашборд</h2>
          <p className="text-sm text-muted-foreground">Контроль протоколов поверки</p>
        </div>
        <Button variant="outline" size="sm" onClick={manualRefresh} disabled={refreshing}>
          <RefreshCw className={cn(refreshing && "animate-spin")} />
          Обновить
        </Button>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard value={pending.length} label="В очереди" tone="blue" />
        <StatCard
          value={running ? <Loader2 className="size-6 animate-spin" /> : "—"}
          label="Выполняется"
          tone="green"
        />
        <StatCard value={devices} label="Приборов в последней проверке" tone="green" />
        <StatCard value={errors} label="Расхождений в последней проверке" tone="amber" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <SystemCard />
        <RunCheckCard onEnqueued={load} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Очередь</CardTitle>
            <CardDescription>Задачи, ожидающие запуска</CardDescription>
            <CardAction>
              <ToneBadge tone="blue">{pending.length}</ToneBadge>
            </CardAction>
          </CardHeader>
          <CardContent>
            {jobs === null ? (
              <Skeleton className="h-24 w-full" />
            ) : pending.length === 0 ? (
              <EmptyState icon={<Inbox className="size-7" />} text="Очередь пуста" />
            ) : (
              <div className="space-y-2">
                {pending.map((job) => (
                  <div
                    key={job.id}
                    className="flex min-h-9 flex-wrap items-center gap-2 rounded-lg bg-muted/40 px-3 py-2 text-sm"
                  >
                    <span className="font-semibold text-sky-400">#{job.id}</span>
                    <span className="text-muted-foreground">
                      {job.year}-{padMonth(job.month)}
                    </span>
                    <ToneBadge tone="amber">{job.job_type === "manual" ? "Ручн" : "Авто"}</ToneBadge>
                    <span className="flex-1 truncate text-muted-foreground">
                      {job.progress || "Ожидание..."}
                    </span>
                    <ConfirmDialog
                      title={`Отменить задачу #${job.id}?`}
                      description="Задача будет удалена из очереди."
                      confirmLabel="Отменить"
                      destructive
                      onConfirm={async () => {
                        await api.cancelJob(job.id)
                        await load()
                      }}
                      trigger={
                        <Button variant="destructive" size="icon-sm" title="Отменить">
                          <X />
                        </Button>
                      }
                    />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Последние</CardTitle>
            <CardDescription>История проверок</CardDescription>
          </CardHeader>
          <CardContent>
            {jobs === null ? (
              <Skeleton className="h-24 w-full" />
            ) : recent.length === 0 ? (
              <EmptyState icon={<FileText className="size-7" />} text="История пуста" />
            ) : (
              <div className="space-y-2">
                {recent.slice(0, 10).map((job) => (
                  <div
                    key={job.id}
                    className="flex min-h-9 flex-wrap items-center gap-2 rounded-lg bg-muted/40 px-3 py-2 text-sm"
                  >
                    <span className="font-semibold text-sky-400">#{job.id}</span>
                    <span className="text-muted-foreground">
                      {job.year}-{padMonth(job.month)}
                    </span>
                    <ToneBadge tone={jobStatusTone(job.status)}>{job.status}</ToneBadge>
                    <span className="flex-1 truncate text-muted-foreground">{job.progress || "—"}</span>
                    <span className="text-xs text-muted-foreground">
                      {fmtDate(job.completed_at || job.started_at)}
                    </span>
                    <ReportButton id={job.id} />
                    <ConfirmDialog
                      title={`Удалить задачу #${job.id}?`}
                      description="Действие необратимо."
                      confirmLabel="Удалить"
                      destructive
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
                        <Button variant="destructive" size="icon-sm" title="Удалить">
                          <Trash2 />
                        </Button>
                      }
                    />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <RunningJobCard
        running={running}
        loading={jobs === null}
        onCancel={async () => {
          if (!running) return
          await api.cancelJob(running.id)
          await load()
        }}
      />
    </div>
  )
}

function StatCard({ value, label, tone }: { value: ReactNode; label: string; tone: Tone }) {
  return (
    <Card className="gap-0 transition-colors hover:ring-foreground/20">
      <CardContent>
        <div className={cn("text-3xl leading-tight font-bold", TONE_TEXT[tone])}>{value}</div>
        <div className="mt-0.5 text-xs text-muted-foreground">{label}</div>
      </CardContent>
    </Card>
  )
}

function EmptyState({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
      <span className="text-muted-foreground/70">{icon}</span>
      {text}
    </div>
  )
}

function SystemCard() {
  const { data, problemCount, fetchedAt } = useHealth()
  const systems = data?.systems ?? {}

  return (
    <Card>
      <CardHeader>
        <CardTitle>Система</CardTitle>
        <CardDescription>Состояние внешних зависимостей</CardDescription>
        <CardAction>
          <ToneBadge tone={problemCount === 0 ? "green" : "red"}>
            {problemCount === 0 ? "OK" : `Ошибки: ${problemCount}`}
          </ToneBadge>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-2">
        {HEALTH_ITEMS.map((item) => {
          const state = systems[item.key]
          return (
            <div
              key={item.key}
              className="flex items-center gap-3 rounded-lg border border-border/60 bg-muted/30 px-3 py-2.5 text-sm"
            >
              <span className="text-xs text-muted-foreground">{item.label}</span>
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
      </CardContent>
    </Card>
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
    <Card>
      <CardHeader>
        <CardTitle>Запустить проверку</CardTitle>
        <CardDescription>Поставить задачу в очередь вручную</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex min-w-24 flex-1 flex-col gap-1.5">
            <Label>Год</Label>
            <Select value={year} onValueChange={setYear}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {years.map((value) => (
                  <SelectItem key={value} value={String(value)}>
                    {value}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex min-w-24 flex-1 flex-col gap-1.5">
            <Label>Месяц</Label>
            <Select value={month} onValueChange={setMonth}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MONTHS.map((name, index) => (
                  <SelectItem key={name} value={String(index + 1)}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button onClick={run} disabled={busy}>
            {busy ? <Loader2 className="animate-spin" /> : <Play />}
            Запустить
          </Button>
        </div>
        <Separator />
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <Checkbox checked={useLk} onCheckedChange={(value) => setUseLk(value === true)} />
          С ЛК (Личный кабинет АРШИН)
        </label>
      </CardContent>
    </Card>
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
    <Card>
      <CardHeader>
        <CardTitle>Активная проверка</CardTitle>
        <CardDescription>Текущий прогресс выполнения</CardDescription>
        <CardAction>{running && <ReportButton id={running.id} />}</CardAction>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-20 w-full" />
        ) : !running ? (
          <EmptyState icon={<FileText className="size-7" />} text="Нет активных проверок" />
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-2xl">{running.waiting_for_token ? "⏳" : "⚙️"}</span>
              <div className="min-w-0">
                <div className="text-base font-semibold">
                  {running.year}-{padMonth(running.month)}
                </div>
                <div className="text-xs text-muted-foreground">
                  #{running.id} · {running.job_type === "manual" ? "Ручная" : "Авто"}
                  {running.waiting_for_token && (
                    <span className="text-amber-400"> · Токен истёк</span>
                  )}
                </div>
              </div>
              <ConfirmDialog
                title="Отменить текущую проверку?"
                confirmLabel="Отменить"
                destructive
                onConfirm={onCancel}
                trigger={
                  <Button variant="destructive" size="sm" className="ml-auto">
                    <X />
                    Отменить
                  </Button>
                }
              />
            </div>
            <div className="space-y-1.5">
              <Progress value={running.progress_percent ?? 0} />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>{running.progress || "Инициализация..."}</span>
                <span>{running.progress_percent ?? 0}%</span>
              </div>
            </div>
            {renderPhaseStats(running)}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function renderPhaseStats(job: api.Job) {
  const stats = job.phase_stats
  if (!stats?.public_api) return null
  return (
    <>
      <Separator />
      <div className="text-xs text-muted-foreground">
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
    <Button variant="ghost" size="icon-sm" title="Скачать отчёт" onClick={download} disabled={busy}>
      {busy ? <Loader2 className="animate-spin" /> : <Download />}
    </Button>
  )
}
