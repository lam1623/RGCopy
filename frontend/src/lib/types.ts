export type JobStatus = "scanning" | "conflict" | "queued" | "running" | "paused" | "completed" | "failed" | "canceled";
export type Mode = "copy" | "move";
export type Resolution = "overwrite" | "skip" | "update" | "backup";
/** "ask": RGCopy looks for existing files first and asks which rule to use */
export type Conflict = "ask" | Resolution;
export type WhenDone = "nothing" | "close" | "verify" | "shutdown";
export type Verify = "running" | "ok" | "mismatch" | "error";
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
  current_bytes: number;
  current_size: number | null;
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
  conflicts: ConflictFile[];
  conflict_count: number;
  skipped: string[];
  verify: Verify | null;
  verify_detail: string | null;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  revision: number;
}

export interface ConflictFile {
  path: string;
  existing_size: number;
  existing_mtime: number;
  incoming_size: number;
  incoming_mtime: number;
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
  when_done: WhenDone;
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

export type FileState = "done" | "current" | "pending" | "skipped" | "uptodate";

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
