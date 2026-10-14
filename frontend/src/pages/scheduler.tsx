import { useCallback, useEffect, useState } from "react"
import { Loader2, Mail, Plus, Save, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { ToneBadge } from "@/components/tone-badge"
import { EmptyState } from "@/components/ui/empty-state"
import { NumberInput } from "@/components/number-input"
import { PageHeader } from "@/components/ui/page-header"
import { Select } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { TimeInput } from "@/components/ui/time-input"
import * as api from "@/lib/api"

export function SchedulerPage() {
  const [mode, setMode] = useState("manual")
  const [day, setDay] = useState("1")
  const [time, setTime] = useState("09:00")
  const [offset, setOffset] = useState("-1")
  const [example, setExample] = useState("")
  const [emails, setEmails] = useState<api.Email[]>([])
  const [newEmail, setNewEmail] = useState("")
  const [saving, setSaving] = useState(false)
  const [adding, setAdding] = useState(false)

  const loadStatus = useCallback(async (init: boolean) => {
    try {
      const data = await api.getSchedulerStatus()
      const scheduler = data.scheduler ?? {}
      if (scheduler.example) setExample(scheduler.example)
      if (init) {
        setMode(scheduler.mode ?? "manual")
        setDay(String(scheduler.auto_day ?? 1))
        setTime(scheduler.auto_time ?? "09:00")
        setOffset(String(scheduler.month_offset ?? -1))
      } else {
        setMode(scheduler.mode ?? "manual")
      }
    } catch {
      // ignore polling errors
    }
  }, [])

  const loadEmails = useCallback(async () => {
    try {
      const data = await api.getEmails()
      setEmails(data.emails ?? [])
    } catch {
      // ignore polling errors
    }
  }, [])

  useEffect(() => {
    void loadStatus(true)
    void loadEmails()
    const statusId = setInterval(() => void loadStatus(false), 30000)
    const emailsId = setInterval(() => void loadEmails(), 30000)
    return () => {
      clearInterval(statusId)
      clearInterval(emailsId)
    }
  }, [loadStatus, loadEmails])

  async function changeMode(next: string) {
    setMode(next)
    try {
      await api.setSchedulerMode(next)
    } catch {
      toast.error("Не удалось изменить режим")
    }
  }

  async function save() {
    const dayNumber = Number(day)
    const offsetNumber = Number(offset)
    if (dayNumber < 1 || dayNumber > 31) {
      toast.error("День: от 1 до 31")
      return
    }
    if (offsetNumber < -12 || offsetNumber > 0) {
      toast.error("Сдвиг: от -12 до 0")
      return
    }
    setSaving(true)
    try {
      await api.setSchedulerMode(mode)
      await api.setSchedulerSettings({
        mode,
        auto_day: dayNumber,
        auto_time: time,
        month_offset: offsetNumber,
      })
      toast.success("Расписание сохранено")
      await loadStatus(true)
    } catch {
      toast.error("Ошибка сохранения")
    } finally {
      setSaving(false)
    }
  }

  async function add() {
    const email = newEmail.trim()
    if (!email || !email.includes("@")) {
      toast.error("Введите корректный email")
      return
    }
    setAdding(true)
    try {
      await api.addEmail(email)
      setNewEmail("")
      await loadEmails()
    } catch (error) {
      if (error instanceof api.ApiError && error.status === 409) {
        toast.error("Email уже добавлен")
      } else {
        toast.error("Ошибка добавления")
      }
    } finally {
      setAdding(false)
    }
  }

  async function remove(id: number) {
    try {
      await api.removeEmail(id)
      await loadEmails()
    } catch {
      toast.error("Ошибка удаления")
    }
  }

  async function toggleAutoSend(id: number, autoSend: boolean) {
    // Оптимистично: сразу переключаем в UI, при ошибке — откатываем.
    setEmails((prev) => prev.map((item) => (item.id === id ? { ...item, auto_send: autoSend } : item)))
    try {
      await api.setEmailAutoSend(id, autoSend)
    } catch {
      toast.error("Не удалось изменить автоотправку")
      await loadEmails()
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Планировщик" description="Настройка автоматических проверок" />

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="section-card">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold text-ink">Расписание</h3>
              <p className="mt-1 text-sm text-steel">{example || "—"}</p>
            </div>
            <ToneBadge tone={mode === "auto" ? "green" : "blue"}>
              {mode === "auto" ? "Авто" : "Ручной"}
            </ToneBadge>
          </div>

          <div className="mt-4 space-y-4">
            <div className="flex items-center gap-3">
              <label className="flex-1 text-sm text-steel">Режим</label>
              <Select
                className="w-48"
                onChange={(next) => void changeMode(next)}
                options={[
                  { value: "manual", label: "Ручной" },
                  { value: "auto", label: "Автоматический" },
                ]}
                value={mode}
              />
            </div>
            <div className="flex items-center gap-3">
              <label className="flex-1 text-sm text-steel" htmlFor="sched-day">
                День
              </label>
              <NumberInput
                className="form-input w-48"
                id="sched-day"
                maxLength={2}
                value={day}
                onValueChange={setDay}
              />
            </div>
            <div className="flex items-center gap-3">
              <label className="flex-1 text-sm text-steel" htmlFor="sched-time">
                Время (МСК)
              </label>
              <TimeInput
                className="form-input w-48"
                id="sched-time"
                value={time}
                onChange={setTime}
              />
            </div>
            <div className="flex items-center gap-3">
              <label className="flex-1 text-sm text-steel" htmlFor="sched-offset">
                Сдвиг
              </label>
              <NumberInput
                allowNegative
                className="form-input w-48"
                id="sched-offset"
                maxLength={3}
                value={offset}
                onValueChange={setOffset}
              />
            </div>

            <div className="border-t border-line" />

            <div className="space-y-2">
              <label className="text-sm text-steel">Email для отчётов</label>
              <p className="text-xs text-steel">
                Ползунок у адреса — автоматическая отправка отчёта после проверки именно ему.
                Если выключить у всех, отчёт всё равно формируется; отправить вручную можно на
                дашборде кнопкой «Отправить отчёт».
              </p>
              <div className="flex gap-2">
                <input
                  className="form-input"
                  placeholder="mail@example.ru"
                  type="email"
                  value={newEmail}
                  onChange={(event) => setNewEmail(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void add()
                  }}
                />
                <button className="btn-secondary btn-sm shrink-0" disabled={adding} type="button" onClick={add}>
                  {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                  Добавить
                </button>
              </div>
              <div className="space-y-1">
                {emails.length === 0 ? (
                  <EmptyState title="Email не добавлены" />
                ) : (
                  emails.map((item) => (
                    <div
                      className="flex items-center gap-2 rounded-2xl border border-line px-3 py-2 text-sm"
                      key={item.id}
                    >
                      <Mail className="size-4 text-steel" />
                      <span className="flex-1 truncate text-steel">{item.email}</span>
                      <Switch
                        checked={item.auto_send ?? true}
                        title="Автоматически отправлять отчёт после проверки"
                        onCheckedChange={(next) => void toggleAutoSend(item.id, next)}
                      />
                      <button
                        className="icon-action-button icon-action-button--danger icon-action-button--tiny"
                        title="Удалить"
                        type="button"
                        onClick={() => void remove(item.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>

            <button className="btn-primary disabled:opacity-60" disabled={saving} type="button" onClick={save}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Сохранить
            </button>
          </div>
        </section>

        <section className="section-card self-start">
          <h3 className="text-lg font-semibold text-ink">Информация</h3>
          <div className="mt-4 space-y-3 text-sm leading-relaxed text-steel">
            <p>
              <b className="text-ink">Ручной</b> — проверка только по запросу
            </p>
            <p>
              <b className="text-ink">Авто</b> — запуск по расписанию
            </p>
            <p>
              <b className="text-ink">Сдвиг</b> — какой месяц проверять (0 = текущий, -1 = прошлый)
            </p>
            <p>
              <b className="text-ink">Email</b> — отчёт уходит автоматически тем адресам, у кого
              включён ползунок; остальным можно отправить вручную с дашборда
            </p>
          </div>
        </section>
      </div>
    </div>
  )
}
