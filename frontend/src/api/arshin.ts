import { apiRequest } from "@/api/client";

export type ArshinStatus = {
  available: boolean;
  details?: string;
};

export type TokenStatus = {
  token_available: boolean;
  status: string;
  expires_at?: string;
  age_seconds?: number;
  source?: string;
};

export async function fetchArshinStatus(): Promise<ArshinStatus> {
  return apiRequest<ArshinStatus>("/arshin/status");
}

export async function fetchTokenStatus(): Promise<TokenStatus> {
  return apiRequest<TokenStatus>("/arshin/token-status");
}

export async function refreshToken(): Promise<{ task_id: string }> {
  return apiRequest<{ task_id: string }>("/arshin/refresh-token", {
    method: "POST",
  });
}

export async function fetchTaskStatus(taskId: string): Promise<{
  status: string;
  result?: unknown;
  error?: string;
}> {
  return apiRequest<{ status: string; result?: unknown; error?: string }>(`/arshin/task/${taskId}`);
}
