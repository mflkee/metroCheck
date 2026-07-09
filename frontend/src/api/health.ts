import { apiRequest } from "@/api/client";

export type HealthResponse = {
  status: string;
  systems?: Record<
    string,
    {
      status: string;
      age_seconds?: number;
      balance?: number;
      detail?: string;
    }
  >;
};

export async function fetchHealth(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/health");
}

export async function fetchHealthLive(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/health/live");
}
