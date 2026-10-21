export type JobStatus = "scanning" | "queued" | "running" | "paused" | "completed" | "failed" | "canceled";
export type Mode = "copy" | "move";
export type Conflict = "overwrite" | "skip" | "update" | "backup";
export type Theme = "system" | "dark" | "light";

export interface TransferOptions {
  mode: Mode;
  conflict: Conflict;
  checksum: boolean;
  preserve: boolean;
  bwlimit: number;
}

export interface Progress {
  percent: number;
  bytes_done: number;
  total_bytes: number;
  files_done: number;
  total_files: number;
  speed: number | null;
  eta_s: number | null;
  elapsed_s: number;
  current: string | null;
}

export interface Job {
  id: string;
  name: string;
  sources: string[];
  destination: string;
  options: TransferOptions;
  status: JobStatus;
  progress: Progress;
  total_bytes: number;
  total_files: number;
  total_dirs: number;
  error: string | null;
  warning: string | null;
  fast_move: boolean;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  revision: number;
}

export interface QueueState {
  running: boolean;
  counts: Record<JobStatus, number>;
  total_bytes: number;
  bytes_done: number;
  speed: number | null;
}

export interface Settings {
  concurrency: number;
  auto_start: boolean;
  conflict: Conflict;
  checksum: boolean;
  preserve: boolean;
  bwlimit: number;
  check_space: boolean;
  notify_on_finish: boolean;
  close_when_done: boolean;
  theme: Theme;
  language: "auto" | "es" | "en";
}

export interface Root {
  name: string;
  path: string;
}

export interface SystemInfo {
  version: string;
  platform: string;
  desktop: boolean;
  data_dir: string;
  home: string;
  roots: Root[];
  rsync: { available: boolean; version: string | null; path: string | null; error: string | null };
  clipboard: boolean;
}

export type EntryKind = "dir" | "file";

export interface FsEntry {
  name: string;
  path: string;
  kind: EntryKind;
  size: number | null;
  modified: number | null;
  link: boolean;
}

export interface FsListing {
  path: string;
  parent: string | null;
  root: string;
  entries: FsEntry[];
  truncated: boolean;
}

export type FileState = "done" | "current" | "pending" | "skipped";

export interface FileStates {
  total: number;
  listed: number;
  truncated: boolean;
  files: { path: string; size: number; state: FileState }[];
}

export interface ClipboardFiles {
  action: "copy" | "cut";
  paths: string[];
  source: string | null;
}

export type ServerEvent =
  | { type: "snapshot"; jobs: Job[]; queue: QueueState }
  | { type: "job"; job: Job }
  | { type: "progress"; items: { id: string; progress: Progress }[] }
  | { type: "removed"; ids: string[] }
  | { type: "queue"; queue: QueueState }
  | { type: "queue_finished"; counts: Record<JobStatus, number> }
  | { type: "settings"; settings: Settings }
  | { type: "resync" };
