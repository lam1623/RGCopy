import type { ClipboardFiles, FileStates, FsEntry, FsListing, Job, QueueState, Root, Settings, SystemInfo, TransferOptions } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

let unauthorizedHandler: (() => void) | null = null;

export function onUnauthorized(handler: () => void) {
  unauthorizedHandler = handler;
}

function errorMessage(data: unknown, fallback: string): string {
  if (data && typeof data === "object") {
    const record = data as Record<string, unknown>;
    if (typeof record.message === "string") return record.message;
    if (typeof record.detail === "string") return record.detail;
    if (Array.isArray(record.detail)) {
      return record.detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d))).join("; ");
    }
  }
  return fallback;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) unauthorizedHandler?.();
    const code =
      data && typeof data === "object" && typeof (data as { code?: unknown }).code === "string"
        ? (data as { code: string }).code
        : `http_${response.status}`;
    throw new ApiError(response.status, code, errorMessage(data, response.statusText));
  }
  return data as T;
}

export const api = {
  authStatus: () => request<{ required: boolean; authenticated: boolean }>("GET", "/api/auth/status"),
  login: (token: string) => request<void>("POST", "/api/auth/login", { token }),
  logout: () => request<void>("POST", "/api/auth/logout"),

  system: () => request<SystemInfo>("GET", "/api/system"),
  settings: () => request<Settings>("GET", "/api/settings"),
  saveSettings: (patch: Partial<Settings>) => request<Settings>("PUT", "/api/settings", patch),
  clipboard: () => request<ClipboardFiles>("GET", "/api/clipboard"),

  roots: () => request<Root[]>("GET", "/api/fs/roots"),
  list: (path: string, hidden = false) =>
    request<FsListing>("GET", `/api/fs/list?path=${encodeURIComponent(path)}${hidden ? "&hidden=true" : ""}`),
  mkdir: (parent: string, name: string) => request<FsEntry>("POST", "/api/fs/mkdir", { parent, name }),

  jobs: () => request<{ jobs: Job[]; queue: QueueState }>("GET", "/api/jobs"),
  addJob: (sources: string[], destination: string, options: Partial<TransferOptions>) =>
    request<Job>("POST", "/api/jobs", { sources, destination, options }),
  removeJobs: (ids: string[]) => request<{ removed: string[] }>("POST", "/api/jobs/remove", { ids }),
  jobAction: (id: string, action: "pause" | "resume" | "cancel" | "retry") =>
    request<Job>("POST", `/api/jobs/${id}/${action}`),
  jobFiles: (id: string, offset = 0, limit = 500) =>
    request<FileStates>("GET", `/api/jobs/${id}/files?offset=${offset}&limit=${limit}`),
  jobLog: (id: string) => request<{ log: string[]; error: string | null; command: string }>("GET", `/api/jobs/${id}/log`),

  startQueue: () => request<QueueState>("POST", "/api/queue/start"),
  pauseQueue: () => request<QueueState>("POST", "/api/queue/pause"),
  clearQueue: (statuses: string[]) => request<{ removed: string[] }>("POST", "/api/queue/clear", { statuses }),
};
