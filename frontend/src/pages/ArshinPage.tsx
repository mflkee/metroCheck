import { useQuery } from "@tanstack/react-query";

import { fetchArshinStatus, fetchTokenStatus } from "@/api/arshin";
import { PageHeader } from "@/components/layout/PageHeader";

export function ArshinPage() {
  const arshinQuery = useQuery({
    queryKey: ["arshin-status"],
    queryFn: fetchArshinStatus,
    refetchInterval: 5_000,
  });
  const tokenQuery = useQuery({
    queryKey: ["token-status"],
    queryFn: fetchTokenStatus,
    refetchInterval: 5_000,
  });

  const token = tokenQuery.data;
  const arshin = arshinQuery.data;

  return (
    <div className="space-y-5">
      <PageHeader title="Аршин" description="Состояние API и токена ФГИС «Аршин»" />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="card">
          <div className="card__header">
            <span>Доступность API</span>
            <span
              className={`status-badge status-badge--${
                arshin?.available ? "ok" : "danger"
              }`}
            >
              {arshin?.available ? "Доступен" : "Недоступен"}
            </span>
          </div>
          <div className="card__body text-sm text-steel">
            {arshin?.details ?? "Нет дополнительной информации"}
          </div>
        </div>

        <div className="card">
          <div className="card__header">
            <span>Токен</span>
            <span
              className={`status-badge status-badge--${
                token?.status === "ok" ? "ok" : "warn"
              }`}
            >
              {token?.status === "ok" ? "Активен" : token?.status ?? "Неизвестно"}
            </span>
          </div>
          <div className="card__body space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-steel">Источник</span>
              <span className="font-medium text-ink">{token?.source ?? "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-steel">Возраст</span>
              <span className="font-medium text-ink">
                {token?.age_seconds ? formatAge(token.age_seconds) : "—"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-steel">Истекает</span>
              <span className="font-medium text-ink">
                {token?.expires_at
                  ? new Date(token.expires_at).toLocaleString("ru-RU")
                  : "—"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function formatAge(seconds: number): string {
  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}
