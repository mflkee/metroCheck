import { useCallback, useEffect, useState } from "react"
import { Loader2, Mail, Plus, Save, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { ToneBadge } from "@/components/tone-badge"
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

  return (
    <div className="fade-in space-y-6">
      <header>
        <h2 className="text-2xl font-bold">Планировщик</h2>
        <p className="text-sm text-muted-foreground">Настройка автоматических проверок</p>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Расписание</CardTitle>
            <CardDescription>{example || "—"}</CardDescription>
            <CardAction>
              <ToneBadge tone={mode === "auto" ? "green" : "blue"}>
                {mode === "auto" ? "Авто" : "Ручной"}
              </ToneBadge>
            </CardAction>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3">
              <Label className="flex-1 text-muted-foreground">Режим</Label>
              <Select value={mode} onValueChange={changeMode}>
                <SelectTrigger className="w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="manual">Ручной</SelectItem>
                  <SelectItem value="auto">Автоматический</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-3">
              <Label htmlFor="sched-day" className="flex-1 text-muted-foreground">
                День
              </Label>
              <Input
                id="sched-day"
                type="number"
                min={1}
                max={31}
                value={day}
                onChange={(event) => setDay(event.target.value)}
                className="w-48"
              />
            </div>
            <div className="flex items-center gap-3">
              <Label htmlFor="sched-time" className="flex-1 text-muted-foreground">
                Время (МСК)
              </Label>
              <Input
                id="sched-time"
                type="time"
                step={60}
                value={time}
                onChange={(event) => setTime(event.target.value)}
                className="w-48"
              />
            </div>
            <div className="flex items-center gap-3">
              <Label htmlFor="sched-offset" className="flex-1 text-muted-foreground">
                Сдвиг
              </Label>
              <Input
                id="sched-offset"
                type="number"
                min={-12}
                max={0}
                value={offset}
                onChange={(event) => setOffset(event.target.value)}
                className="w-48"
              />
            </div>

            <Separator />

            <div className="space-y-2">
              <Label className="text-muted-foreground">Email для отчётов</Label>
              <div className="flex gap-2">
                <Input
                  type="email"
                  placeholder="mail@example.ru"
                  value={newEmail}
                  onChange={(event) => setNewEmail(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void add()
                  }}
                />
                <Button variant="secondary" onClick={add} disabled={adding}>
                  {adding ? <Loader2 className="animate-spin" /> : <Plus />}
                  Добавить
                </Button>
              </div>
              <div className="space-y-1">
                {emails.length === 0 ? (
                  <p className="py-2 text-xs text-muted-foreground">Email не добавлены</p>
                ) : (
                  emails.map((item) => (
                    <div
                      key={item.id}
                      className="flex items-center gap-2 rounded-lg bg-muted/40 px-3 py-2 text-sm"
                    >
                      <Mail className="size-4 text-muted-foreground" />
                      <span className="flex-1 truncate text-muted-foreground">{item.email}</span>
                      <Button
                        variant="destructive"
                        size="icon-xs"
                        title="Удалить"
                        onClick={() => void remove(item.id)}
                      >
                        <Trash2 />
                      </Button>
                    </div>
                  ))
                )}
              </div>
            </div>

            <Button onClick={save} disabled={saving}>
              {saving ? <Loader2 className="animate-spin" /> : <Save />}
              Сохранить
            </Button>
          </CardContent>
        </Card>

        <Card className="self-start">
          <CardHeader>
            <CardTitle>Информация</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm leading-relaxed text-muted-foreground">
            <p>
              <b className="text-foreground">Ручной</b> — проверка только по запросу
            </p>
            <p>
              <b className="text-foreground">Авто</b> — запуск по расписанию
            </p>
            <p>
              <b className="text-foreground">Сдвиг</b> — какой месяц проверять (0 = текущий, -1 =
              прошлый)
            </p>
            <p>
              <b className="text-foreground">Email</b> — отчёт отправляется всем из списка
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
