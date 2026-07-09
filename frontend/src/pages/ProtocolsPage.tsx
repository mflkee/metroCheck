import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { extractProtocol, listProtocols, scanProtocols } from "@/api/protocols";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/layout/PageHeader";

export function ProtocolsPage() {
  const queryClient = useQueryClient();
  const protocolsQuery = useQuery({
    queryKey: ["protocols"],
    queryFn: listProtocols,
  });

  const scanMutation = useMutation({
    mutationFn: scanProtocols,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["protocols"] }),
  });

  const extractMutation = useMutation({
    mutationFn: extractProtocol,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["protocols"] }),
  });

  const items = protocolsQuery.data?.items ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Протоколы"
        description="Сканирование папки и OCR-распознавание протоколов"
        action={
          <button
            className="btn-primary"
            disabled={scanMutation.isPending}
            type="button"
            onClick={() => scanMutation.mutate()}
          >
            <Icon name="refresh" className="h-4 w-4" />
            {scanMutation.isPending ? "Сканирование..." : "Сканировать"}
          </button>
        }
      />

      <div className="card">
        <div className="card__header">
          <span>Найденные файлы</span>
          <span className="status-badge status-badge--info">{protocolsQuery.data?.total ?? 0}</span>
        </div>
        <div className="card__body overflow-x-auto">
          <table className="data-table min-w-[500px]">
            <thead>
              <tr>
                <th>Файл</th>
                <th>Статус</th>
                <th className="text-right">Действия</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td className="empty-state" colSpan={3}>
                    Протоколы не найдены
                  </td>
                </tr>
              ) : (
                items.map((protocol) => (
                  <tr key={protocol.id}>
                    <td className="font-medium text-ink">{protocol.file_name}</td>
                    <td>
                      <span
                        className={`status-badge status-badge--${
                          protocol.status === "extracted" ? "ok" : "info"
                        }`}
                      >
                        {protocol.status === "extracted" ? "Распознан" : "Новый"}
                      </span>
                    </td>
                    <td className="text-right">
                      <button
                        className="btn-secondary btn-sm"
                        disabled={
                          extractMutation.isPending &&
                          extractMutation.variables === protocol.id
                        }
                        type="button"
                        onClick={() => extractMutation.mutate(protocol.id)}
                      >
                        {extractMutation.isPending && extractMutation.variables === protocol.id
                          ? "..."
                          : "Распознать"}
                      </button>
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
