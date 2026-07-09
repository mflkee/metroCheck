import { apiRequest } from "@/api/client";

export type QueueStatus = {
  pending: JobStatus[];
  running: JobStatus | null;
};

export type JobStatus = {
  id: string;
  job_type: "manual" | "auto";
  year: number;
  month: number;
  status: string;
  progress_percent: number;
  processed_devices: number;
  total_devices: number;
  waiting_for_token: boolean;
  phase_stats?: Record<
    string,
    {
      saved?: number;
      found?: number;
      extracted?: number;
    }
  >;
  created_at: string;
  updated_at: string;
};

export type EnqueueResponse = {
  job_id: string;
  task_id: string;
};

export async function fetchQueueStatus(): Promise<QueueStatus> {
  return apiRequest<QueueStatus>("/jobs/status");
}

export async function enqueueManualJob(payload: {
  year: number;
  month: number;
}): Promise<EnqueueResponse> {
  return apiRequest<EnqueueResponse>("/jobs/enqueue", {
    method: "POST",
    body: payload,
  });
}

export async function enqueueAutoJob(payload: {
  year: number;
  month: number;
}): Promise<EnqueueResponse> {
  return apiRequest<EnqueueResponse>("/jobs/enqueue-auto", {
    method: "POST",
    body: payload,
  });
}

export async function cancelJob(jobId: string): Promise<unknown> {
  return apiRequest<unknown>(`/jobs/cancel/${jobId}`, {
    method: "POST",
  });
}

export async function pauseJob(jobId: string): Promise<unknown> {
  return apiRequest<unknown>(`/jobs/pause/${jobId}`, {
    method: "POST",
  });
}

export async function resumeJob(jobId: string): Promise<unknown> {
  return apiRequest<unknown>(`/jobs/resume/${jobId}`, {
    method: "POST",
  });
}

export async function deleteJob(jobId: string): Promise<unknown> {
  return apiRequest<unknown>(`/jobs/${jobId}`, {
    method: "DELETE",
  });
}

export async function generateJobReport(jobId: string): Promise<unknown> {
  return apiRequest<unknown>(`/jobs/${jobId}/generate-report`, {
    method: "POST",
  });
}

export async function downloadJobReport(jobId: string): Promise<Blob> {
  const { downloadFile } = await import("@/api/client");
  return downloadFile(`/jobs/${jobId}/download-report`, {
    method: "GET",
  });
}

export async function fetchJob(jobId: string): Promise<JobStatus> {
  return apiRequest<JobStatus>(`/jobs/${jobId}`);
}
