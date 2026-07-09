import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  addSchedulerEmail,
  deleteSchedulerEmail,
  fetchSchedulerEmails,
  fetchSchedulerStatus,
  updateSchedulerMode,
  updateSchedulerSettings,
} from "@/api/scheduler";
import { PageHeader } from "@/components/layout/PageHeader";

export function SchedulerPage() {
  const queryClient = useQueryClient();
  const statusQuery = useQuery({
    queryKey: ["scheduler-status"],
    queryFn: fetchSchedulerStatus,
    refetchInterval: 5_000,
  });
  const emailsQuery = useQuery({
    queryKey: ["scheduler-emails"],
    queryFn: fetchSchedulerEmails,
  });

  const [mode, setMode] = useState<"manual" | "auto">("manual");
  const [day, setDay] = useState(1);
  const [time, setTime] = useState("09:00");
  const [offset, setOffset] = useState(-1);
  const [email, setEmail] = useState("");

  const modeMutation = useMutation({
    mutationFn: updateSchedulerMode,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scheduler-status"] }),
  });

  const settingsMutation = useMutation({
    mutationFn: updateSchedulerSettings,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scheduler-status"] }),
  });

  const addEmailMutation = useMutation({
    mutationFn: addSchedulerEmail,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scheduler-emails"] });
      setEmail("");
    },
  });

  const deleteEmailMutation = useMutation({
    mutationFn: deleteSchedulerEmail,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scheduler-emails"] }),
  });

  const status = statusQuery.data;

  function handleSave() {
    settingsMutation.mutate({ mode, day, time, offset });
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Планировщик" description="Настройка автоматических проверок и рассылки отчётов" />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="card">
          <div className="card__header">
            <span>Расписание</span>
            <span className={`status-badge status-badge--${status?.mode === "auto" ? "ok" : "info"}`}>
              {status?.mode === "auto" ? "Авто" : "Ручной"}
            </span>
          </div>
          <div className="card__body space-y-4">
            <div className="text-sm text-steel">
              {status?.next_run_at
                ? `Следующий запуск: ${new Date(status.next_run_at).toLocaleString("ru-RU")}`
                : "Следующий запуск не запланирован"}
            </div>

            <div className="grid grid-cols-1 gap-3">
              <div className="flex items-center gap-3">
                <label className="w-20 text-sm font-semibold text-steel">Режим</label>
                <select
                  className="form-input flex-1"
                  value={status?.mode ?? mode}
                  onChange={(e) => {
                    const next = e.target.value as "manual" | "auto";
                    setMode(next);
                    modeMutation.mutate(next);
                  }}
                >
                  <option value="manual">Ручной</option>
                  <option value="auto">Автоматический</option>
                </select>
              </div>

              <div className="flex items-center gap-3">
                <label className="w-20 text-sm font-semibold text-steel">День</label>
                <input
                  className="form-input flex-1"
                  max={31}
                  min={1}
                  type="number"
                  value={day}
                  onChange={(e) => setDay(Number(e.target.value))}
                />
              </div>

              <div className="flex items-center gap-3">
                <label className="w-20 text-sm font-semibold text-steel">Время</label>
                <input
                  className="form-input flex-1"
                  step={60}
                  type="time"
                  value={time}
                  onChange={(e) => setTime(e.target.value)}
                />
              </div>

              <div className="flex items-center gap-3">
                <label className="w-20 text-sm font-semibold text-steel">Сдвиг</label>
                <input
                  className="form-input flex-1"
                  max={0}
                  min={-12}
                  type="number"
                  value={offset}
                  onChange={(e) => setOffset(Number(e.target.value))}
                />
              </div>
            </div>

            <div className="pt-2">
              <div className="mb-2 text-sm font-semibold text-steel">Email для отчётов</div>
              <div className="flex gap-2">
                <input
                  className="form-input flex-1"
                  placeholder="mail@example.ru"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
                <button
                  className="btn-primary"
                  disabled={addEmailMutation.isPending || !email}
                  type="button"
                  onClick={() => addEmailMutation.mutate(email)}
                >
                  Добавить
                </button>
              </div>
              <div className="mt-3 space-y-2">
                {emailsQuery.data?.map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center justify-between rounded-xl border border-line bg-surface-subtle px-3 py-2 text-sm"
                  >
                    <span>{item.email}</span>
                    <button
                      className="btn-danger btn-sm"
                      disabled={deleteEmailMutation.isPending}
                      type="button"
                      onClick={() => deleteEmailMutation.mutate(item.id)}
                    >
                      Удалить
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <button
              className="btn-primary w-full sm:w-auto"
              disabled={settingsMutation.isPending}
              type="button"
              onClick={handleSave}
            >
              Сохранить настройки
            </button>
          </div>
        </div>

        <div className="card">
          <div className="card__header">Информация</div>
          <div className="card__body space-y-4 text-sm leading-7 text-steel">
            <p>
              <strong className="text-ink">Ручной</strong> — проверка запускается только по запросу пользователя.
            </p>
            <p>
              <strong className="text-ink">Авто</strong> — проверка запускается автоматически по расписанию.
            </p>
            <p>
              <strong className="text-ink">Сдвиг</strong> — какой месяц проверять: 0 = текущий, -1 = прошлый.
            </p>
            <p>
              <strong className="text-ink">Email</strong> — отчёт отправляется всем адресам из списка после завершения проверки.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
