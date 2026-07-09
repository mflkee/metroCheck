import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { fetchHealth } from "@/api/health";
import { enqueueManualJob, fetchQueueStatus } from "@/api/jobs";
import { fetchSummary } from "@/api/reports";
import { PageHeader } from "@/components/layout/PageHeader";

const statusLabels: Record<string, string> = {
  ok: "OK",
  expired: "Истек",
  error: "Ошибка",
  unreachable: "Недоступен",
  not_configured: "Не настроен",
  idle: "Ожидание",
  waiting: "Ожидание файла",
};

export function DashboardPage() {
  const queryClient = useQueryClient();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [isRunning, setIsRunning] = useState(false);

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 5_000,
  });

  const queueQuery = useQuery({
    queryKey: ["queue-status"],
    queryFn: fetchQueueStatus,
    refetchInterval: 3_000,
  });

  const summaryQuery = useQuery({
    queryKey: ["checks-summary"],
    queryFn: fetchSummary,
  });

  const enqueueMutation = useMutation({
    mutationFn: enqueueManualJob,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["queue-status"] });
      setIsRunning(false);
    },
    onError: () => {
      setIsRunning(false);
    },
  });

  const systems = useMemo(() => {
    const s = healthQuery.data?.systems ?? {};
    return [
      { label: "АРШИН API", key: "arshin_api" },
      { label: "Токен АРШИН", key: "arshin_token" },
      { label: "Token Agent", key: "token_agent" },
      { label: "OpenRouter", key: "openrouter" },
    ].map((item) => ({
      ...item,
      status: (s[item.key]?.status ?? "unknown") as string,
      detail: s[item.key]?.balance ? `$${s[item.key].balance}` : undefined,
    }));
  }, [healthQuery.data]);

  const hasProblems = systems.some((s) => s.status === "error" || s.status === "expired");

  useEffect(() => {
    const interval = setInterval(() => {
      queryClient.invalidateQueries({ queryKey: ["queue-status"] });
    }, 3_000);
    return () => clearInterval(interval);
  }, [queryClient]);

  const pendingCount = queueQuery.data?.pending?.length ?? 0;
  const running = queueQuery.data?.running;

  function handleRun() {
    setIsRunning(true);
    enqueueMutation.mutate({ year, month });
  }

  const years = useMemo(() => {
    const start = 2022;
    const current = new Date().getFullYear();
    const list: number[] = [];
    for (let y = current; y >= start; y--) {
      list.push(y);
    }
    return list;
  }, []);

  const summary = summaryQuery.data;

  return (
    <div className="space-y-5">
      <PageHeader title="Главная" description="Контроль протоколов поверки и состояние системы" />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard value={pendingCount} label="В очереди" />
        <StatCard value={running ? 1 : 0} label="Выполняется" />
        <StatCard value={running ? `${running.processed_devices}/${running.total_devices}` : "—"} label="Приборов проверено" />
        <StatCard value={summary?.total ?? "—"} label="Всего проверок" />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="card">
          <div className="card__header">
            <span>Система</span>
            <span className={hasProblems ? "status-badge status-badge--danger" : "status-badge status-badge--ok"}>
              {hasProblems ? "Есть проблемы" : "OK"}
            </span>
          </div>
          <div className="card__body">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {systems.map((s) => (
                <div
                  key={s.key}
                  className="flex items-center justify-between rounded-2xl border border-line bg-surface-subtle p-3 text-sm"
                >
                  <span className="text-steel">{s.label}</span>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={s.status} />
                    {s.detail ? <span className="text-xs text-steel">{s.detail}</span> : null}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card__header">Запустить проверку</div>
          <div className="card__body">
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex-1 min-w-[120px]">
                <label className="block text-xs font-semibold text-steel mb-1">Год</label>
                <select className="form-input" value={year} onChange={(e) => setYear(Number(e.target.value))}>
                  {years.map((y) => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </div>
              <div className="flex-1 min-w-[120px]">
                <label className="block text-xs font-semibold text-steel mb-1">Месяц</label>
                <select className="form-input" value={month} onChange={(e) => setMonth(Number(e.target.value))}>
                  {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                    <option key={m} value={m}>
                      {m.toString().padStart(2, "0")}
                    </option>
                  ))}
                </select>
              </div>
              <button
                className="btn-primary"
                disabled={isRunning || enqueueMutation.isPending}
                type="button"
                onClick={handleRun}
              >
                {enqueueMutation.isPending ? "Запуск..." : "Запустить"}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="card">
          <div className="card__header">
            <span>Очередь</span>
            <span className="status-badge status-badge--info">{pendingCount}</span>
          </div>
          <div className="card__body">
            {running ? (
              <JobCard job={running} />
            ) : null}
            {pendingCount === 0 && !running ? (
              <div className="empty-state">Нет активных задач</div>
            ) : null}
            {queueQuery.data?.pending
              ?.filter((j) => j.id !== running?.id)
              .map((job) => (
                <JobCard key={job.id} job={job} />
              ))}
          </div>
        </div>

        <div className="card">
          <div className="card__header">Последние проверки</div>
          <div className="card__body">
            {summary?.recent && summary.recent.length > 0 ? (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Период</th>
                    <th>Статус</th>
                    <th>Дата</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.recent.slice(0, 10).map((run) => (
                    <tr key={run.id}>
                      <td className="font-medium">
                        {run.year}-{run.month.toString().padStart(2, "0")}
                      </td>
                      <td>
                        <StatusBadge status={run.status} />
                      </td>
                      <td className="text-steel">{new Date(run.created_at).toLocaleString("ru-RU")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty-state">Нет завершённых проверок</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ value, label }: { value: number | string; label: string }) {
  return (
    <div className="card">
      <div className="card__body">
        <div className="text-3xl font-bold text-ink">{value}</div>
        <div className="text-sm text-steel">{label}</div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  let variant = "info";
  if (status === "ok" || status === "done" || status === "completed") variant = "ok";
  else if (status === "expired" || status === "error" || status === "failed") variant = "danger";
  else if (status === "waiting" || status === "pending") variant = "warn";

  return (
    <span className={`status-badge status-badge--${variant}`}>
      {statusLabels[status] ?? status ?? "—"}
    </span>
  );
}

function JobCard({ job }: { job: import("@/api/jobs").JobStatus }) {
  return (
    <div className="rounded-2xl border border-line bg-surface-subtle p-4 mb-3">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-base font-semibold text-ink">
            {job.year}-{job.month.toString().padStart(2, "0")}
          </div>
          <div className="text-xs text-steel">
            #{job.id} · {job.job_type === "manual" ? "Ручная" : "Авто"}
            {job.waiting_for_token ? " · Токен истек" : ""}
          </div>
        </div>
        <StatusBadge status={job.status} />
      </div>
      <div className="mt-4">
        <div className="progress-bar">
          <div
            className={`progress-bar__fill ${job.waiting_for_token ? "progress-bar__fill--waiting" : ""}`}
            style={{ width: `${job.progress_percent ?? 0}%` }}
          />
        </div>
        <div className="mt-1 flex justify-between text-xs text-steel">
          <span>{job.progress_percent ?? 0}%</span>
          <span>
            {job.processed_devices}/{job.total_devices}
          </span>
        </div>
      </div>
    </div>
  );
}
