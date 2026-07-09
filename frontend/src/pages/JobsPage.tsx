import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelJob,
  deleteJob,
  downloadJobReport,
  fetchQueueStatus,
  generateJobReport,
  pauseJob,
  resumeJob,
} from "@/api/jobs";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/layout/PageHeader";


const statusLabels: Record<string, string> = {
  pending: "В очереди",
  running: "Выполняется",
  paused: "Приостановлена",
  completed: "Завершена",
  failed: "Ошибка",
  cancelled: "Отменена",
  waiting_for_token: "Ожидание токена",
};

export function JobsPage() {
  const queryClient = useQueryClient();
  const queueQuery = useQuery({
    queryKey: ["queue-status"],
    queryFn: fetchQueueStatus,
    refetchInterval: 3_000,
  });

  const cancelMutation = useMutation({
    mutationFn: cancelJob,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["queue-status"] }),
  });
  const pauseMutation = useMutation({
    mutationFn: pauseJob,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["queue-status"] }),
  });
  const resumeMutation = useMutation({
    mutationFn: resumeJob,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["queue-status"] }),
  });
  const deleteMutation = useMutation({
    mutationFn: deleteJob,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["queue-status"] }),
  });
  const reportMutation = useMutation({
    mutationFn: generateJobReport,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["queue-status"] }),
  });

  const jobs = queueQuery.data?.pending ?? [];
  if (queueQuery.data?.running) {
    jobs.unshift(queueQuery.data.running);
  }

  async function handleDownload(jobId: string) {
    const blob = await downloadJobReport(jobId);
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `report-${jobId}.xlsx`;
    a.click();
    window.URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Очередь" description="Управление задачами на проверку протоколов" />

      <div className="card">
        <div className="card__header">
          <span>Задачи</span>
          <button
            className="icon-action-button icon-action-button--tiny"
            type="button"
            onClick={() => queryClient.invalidateQueries({ queryKey: ["queue-status"] })}
          >
            <Icon name="refresh" className="h-4 w-4" />
          </button>
        </div>
        <div className="card__body overflow-x-auto">
          <table className="data-table min-w-[600px]">
            <thead>
              <tr>
                <th>ID</th>
                <th>Период</th>
                <th>Тип</th>
                <th>Статус</th>
                <th>Прогресс</th>
                <th className="text-right">Действия</th>
              </tr>
            </thead>
            <tbody>
              {jobs.length === 0 ? (
                <tr>
                  <td className="empty-state" colSpan={6}>Нет задач в очереди</td>
                </tr>
              ) : (
                jobs.map((job) => (
                  <tr key={job.id}>
                    <td className="font-medium text-ink">#{job.id}</td>
                    <td>
                      {job.year}-{job.month.toString().padStart(2, "0")}
                    </td>
                    <td>{job.job_type === "manual" ? "Ручная" : "Авто"}</td>
                    <td>
                      <span className={`status-badge status-badge--${getStatusVariant(job.status)}`}>
                        {statusLabels[job.status] ?? job.status}
                      </span>
                    </td>
                    <td>
                      <div className="w-32">
                        <div className="progress-bar">
                          <div
                            className="progress-bar__fill"
                            style={{ width: `${job.progress_percent ?? 0}%` }}
                          />
                        </div>
                        <div className="mt-1 text-xs text-steel">
                          {job.processed_devices}/{job.total_devices}
                        </div>
                      </div>
                    </td>
                    <td className="text-right">
                      <div className="flex justify-end gap-2">
                        {job.status === "running" || job.status === "waiting_for_token" ? (
                          <>
                            <button
                              className="btn-secondary btn-sm"
                              disabled={pauseMutation.isPending}
                              type="button"
                              onClick={() => pauseMutation.mutate(job.id)}
                            >
                              Пауза
                            </button>
                            <button
                              className="btn-danger btn-sm"
                              disabled={cancelMutation.isPending}
                              type="button"
                              onClick={() => cancelMutation.mutate(job.id)}
                            >
                              Отмена
                            </button>
                          </>
                        ) : job.status === "paused" ? (
                          <button
                            className="btn-accent btn-sm"
                            disabled={resumeMutation.isPending}
                            type="button"
                            onClick={() => resumeMutation.mutate(job.id)}
                          >
                            Продолжить
                          </button>
                        ) : null}
                        <button
                          className="btn-secondary btn-sm"
                          disabled={reportMutation.isPending}
                          type="button"
                          onClick={() => reportMutation.mutate(job.id)}
                        >
                          Отчёт
                        </button>
                        <button
                          className="btn-secondary btn-sm"
                          type="button"
                          onClick={() => void handleDownload(job.id)}
                        >
                          Скачать
                        </button>
                        <button
                          className="btn-danger btn-sm"
                          disabled={deleteMutation.isPending}
                          type="button"
                          onClick={() => {
                            if (window.confirm("Удалить задачу?")) {
                              deleteMutation.mutate(job.id);
                            }
                          }}
                        >
                          <Icon name="delete" className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function getStatusVariant(status: string): string {
  if (status === "completed") return "ok";
  if (status === "failed" || status === "cancelled") return "danger";
  if (status === "waiting_for_token" || status === "paused" || status === "pending") return "warn";
  return "info";
}

