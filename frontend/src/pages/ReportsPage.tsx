import { useQuery } from "@tanstack/react-query";

import { fetchSummary } from "@/api/reports";
import { PageHeader } from "@/components/layout/PageHeader";

export function ReportsPage() {
  const summaryQuery = useQuery({
    queryKey: ["checks-summary"],
    queryFn: fetchSummary,
  });

  const summary = summaryQuery.data;

  return (
    <div className="space-y-5">
      <PageHeader title="Отчёты" description="Сводка и результаты проверок протоколов" />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="card">
          <div className="card__body">
            <div className="text-3xl font-bold text-ink">{summary?.total ?? "—"}</div>
            <div className="text-sm text-steel">Всего проверок</div>
          </div>
        </div>
        <div className="card">
          <div className="card__body">
            <div className="text-3xl font-bold text-[var(--success)]">
              {summary?.by_status?.find((s) => s.status === "completed")?.count ?? 0}
            </div>
            <div className="text-sm text-steel">Успешно</div>
          </div>
        </div>
        <div className="card">
          <div className="card__body">
            <div className="text-3xl font-bold text-[var(--danger)]">
              {summary?.by_status?.find((s) => s.status === "failed")?.count ?? 0}
            </div>
            <div className="text-sm text-steel">С ошибками</div>
          </div>
        </div>
        <div className="card">
          <div className="card__body">
            <div className="text-3xl font-bold text-[var(--info)]">
              {summary?.by_status?.find((s) => s.status === "pending")?.count ?? 0}
            </div>
            <div className="text-sm text-steel">В очереди</div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card__header">История проверок</div>
        <div className="card__body overflow-x-auto">
          <table className="data-table min-w-[600px]">
            <thead>
              <tr>
                <th>ID</th>
                <th>Период</th>
                <th>Статус</th>
                <th>Создана</th>
              </tr>
            </thead>
            <tbody>
              {summary?.recent && summary.recent.length > 0 ? (
                summary.recent.map((run) => (
                  <tr key={run.id}>
                    <td className="font-medium text-ink">#{run.id}</td>
                    <td>
                      {run.year}-{run.month.toString().padStart(2, "0")}
                    </td>
                    <td>
                      <span
                        className={`status-badge status-badge--${
                          run.status === "completed"
                            ? "ok"
                            : run.status === "failed"
                              ? "danger"
                              : "info"
                        }`}
                      >
                        {run.status}
                      </span>
                    </td>
                    <td className="text-steel">
                      {new Date(run.created_at).toLocaleString("ru-RU")}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="empty-state" colSpan={4}>
                    Нет данных
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
