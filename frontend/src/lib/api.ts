// ── Types ──

export type HealthStatus =
  | "ok"
  | "expired"
  | "error"
  | "unreachable"
  | "not_configured"
  | "idle"
  | "waiting"
  | string

export interface SystemHealth {
  status: HealthStatus
  age_seconds?: number
  balance?: string | number
}

export interface HealthResponse {
  status?: string
  systems?: Record<string, SystemHealth>
}

export interface PhaseStats {
  public_api?: { saved?: number }
  protocol_scan?: { found?: number }
  protocol_ocr?: { extracted?: number }
  full_check?: { errors?: number }
}

export interface Job {
  id: number
  year: number
  month: number
  job_type: "manual" | "auto" | string
  status: string
  progress?: string
  progress_percent?: number
  processed_devices?: number
  total_devices?: number
  waiting_for_token?: boolean
  phase_stats?: PhaseStats
  started_at?: string | null
  completed_at?: string | null
}

export interface JobsStatus {
  running?: Job | null
  pending?: Job[]
  recent?: Job[]
}

export interface Scheduler {
  mode?: string
  auto_day?: number
  auto_time?: string
  month_offset?: number
  example?: string
}

export interface SchedulerStatus {
  scheduler?: Scheduler
}

export interface Email {
  id: number
  email: string
}

export interface EmailsResponse {
  emails?: Email[]
}

// ── Auth token ──

const TOKEN_KEY = "token"

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export function isLoggedIn(): boolean {
  const token = getToken()
  if (!token) return false
  try {
    const payload = JSON.parse(atob(token.split(".")[1]))
    return payload.exp * 1000 > Date.now()
  } catch {
    return false
  }
}

// ── Fetch core ──

const BASE = "/api"

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

let unauthorizedHandler: (() => void) | null = null

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler
}

function authHeaders(json = true): Record<string, string> {
  const headers: Record<string, string> = {}
  if (json) headers["Content-Type"] = "application/json"
  const token = getToken()
  if (token) headers["Authorization"] = "Bearer " + token
  return headers
}

async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    headers: authHeaders(),
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (res.status === 401) {
    unauthorizedHandler?.()
    throw new ApiError("Unauthorized", 401)
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "")
    throw new ApiError(text || res.statusText || `HTTP ${res.status}`, res.status)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

// ── Endpoints ──

export async function login(username: string, password: string): Promise<string> {
  const data = await api<{ access_token: string }>("/v1/auth/login", "POST", {
    username,
    password,
  })
  return data.access_token
}

export function getHealth(): Promise<HealthResponse> {
  return api<HealthResponse>("/health")
}

export function getJobsStatus(): Promise<JobsStatus> {
  return api<JobsStatus>("/v1/jobs/status")
}

export function enqueueJob(year: number, month: number, useLk: boolean): Promise<unknown> {
  return api("/v1/jobs/enqueue", "POST", { year, month, use_lk: useLk })
}

export function cancelJob(id: number): Promise<unknown> {
  return api(`/v1/jobs/cancel/${id}`, "POST")
}

export function deleteJob(id: number): Promise<unknown> {
  return api(`/v1/jobs/${id}`, "DELETE")
}

export async function generateReport(id: number): Promise<Blob> {
  const res = await fetch(`${BASE}/v1/jobs/${id}/generate-report`, {
    method: "POST",
    headers: authHeaders(false),
  })
  if (res.status === 401) {
    unauthorizedHandler?.()
    throw new ApiError("Unauthorized", 401)
  }
  if (!res.ok) throw new ApiError("Не удалось сгенерировать отчёт", res.status)
  return res.blob()
}

export function getSchedulerStatus(): Promise<SchedulerStatus> {
  return api<SchedulerStatus>("/v1/arshin/scheduler/status")
}

export function setSchedulerMode(mode: string): Promise<unknown> {
  return api("/v1/arshin/scheduler/mode", "POST", { mode })
}

export interface SchedulerSettings {
  mode: string
  auto_day: number
  auto_time: string
  month_offset: number
}

export function setSchedulerSettings(settings: SchedulerSettings): Promise<unknown> {
  return api("/v1/arshin/scheduler/settings", "POST", settings)
}

export function getEmails(): Promise<EmailsResponse> {
  return api<EmailsResponse>("/v1/arshin/scheduler/emails")
}

export function addEmail(email: string): Promise<unknown> {
  return api("/v1/arshin/scheduler/emails", "POST", { email })
}

export function removeEmail(id: number): Promise<unknown> {
  return api(`/v1/arshin/scheduler/emails/${id}`, "DELETE")
}

// ── Download helper ──

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  URL.revokeObjectURL(url)
  document.body.removeChild(link)
}
