import { apiRequest } from "@/api/client";

export type SchedulerStatus = {
  mode: "manual" | "auto";
  day: number;
  time: string;
  offset: number;
  next_run_at: string | null;
  is_due: boolean;
  check_email_enabled: boolean;
  check_emails: string[];
};

export type SchedulerSettings = {
  mode: "manual" | "auto";
  day: number;
  time: string;
  offset: number;
};

export type SchedulerEmail = {
  id: string;
  email: string;
};

export async function fetchSchedulerStatus(): Promise<SchedulerStatus> {
  return apiRequest<SchedulerStatus>("/arshin/scheduler/status");
}

export async function updateSchedulerMode(mode: "manual" | "auto"): Promise<SchedulerStatus> {
  return apiRequest<SchedulerStatus>("/arshin/scheduler/mode", {
    method: "POST",
    body: { mode },
  });
}

export async function updateSchedulerSettings(
  payload: SchedulerSettings,
): Promise<SchedulerStatus> {
  return apiRequest<SchedulerStatus>("/arshin/scheduler/settings", {
    method: "POST",
    body: payload,
  });
}

export async function fetchSchedulerEmails(): Promise<SchedulerEmail[]> {
  return apiRequest<SchedulerEmail[]>("/arshin/scheduler/emails");
}

export async function addSchedulerEmail(email: string): Promise<SchedulerEmail> {
  return apiRequest<SchedulerEmail>("/arshin/scheduler/emails", {
    method: "POST",
    body: { email },
  });
}

export async function deleteSchedulerEmail(emailId: string): Promise<unknown> {
  return apiRequest<unknown>(`/arshin/scheduler/emails/${emailId}`, {
    method: "DELETE",
  });
}
