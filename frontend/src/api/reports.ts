import { apiRequest } from "@/api/client";

export type SummaryItem = {
  status: string;
  count: number;
};

export type CheckSummary = {
  total: number;
  by_status: SummaryItem[];
  recent: Array<{
    id: string;
    year: number;
    month: number;
    status: string;
    created_at: string;
  }>;
};

export async function fetchSummary(): Promise<CheckSummary> {
  return apiRequest<CheckSummary>("/checks/summary");
}

export async function downloadReport(runId: string): Promise<Blob> {
  const { downloadFile } = await import("@/api/client");
  return downloadFile(`/reports/download/${runId}`, {
    method: "GET",
  });
}
