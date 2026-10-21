import { create } from "zustand";
import type { Job, Mode, Progress, QueueState, Settings, SystemInfo } from "./types";

export type Connection = "connecting" | "online" | "offline";
/** What the built-in browser picks: sources (files and folders) or one destination folder. */
export type BrowserMode = "sources" | "folder";

export interface BrowserRequest {
  mode: BrowserMode;
  start?: string;
  resolve: (paths: string[]) => void;
}

export interface Draft {
  sources: string[];
  destination: string | null;
  mode: Mode;
}

// Speed samples kept per transfer for the chart (about a minute: progress comes every 0.25-0.5 s)
export const SPEED_SAMPLES = 160;

const EMPTY_COUNTS = { scanning: 0, queued: 0, running: 0, paused: 0, completed: 0, failed: 0, canceled: 0 };

interface State {
  booted: boolean;
  authRequired: boolean;
  authenticated: boolean;
  system: SystemInfo | null;
  settings: Settings | null;
  jobs: Record<string, Job>;
  order: string[];
  queue: QueueState;
  connection: Connection;
  browser: BrowserRequest | null;
  /** The "new transfer" dialog, null when closed */
  draft: Draft | null;
  settingsOpen: boolean;
  /** The transfer shown in the big panel (null: the one that is copying) */
  focused: string | null;
  /** Bytes per second of each transfer, oldest first */
  speeds: Record<string, number[]>;

  setBoot: (patch: Partial<Pick<State, "booted" | "authRequired" | "authenticated">>) => void;
  setData: (patch: Partial<Pick<State, "system" | "settings">>) => void;
  setConnection: (connection: Connection) => void;
  openBrowser: (request: BrowserRequest | null) => void;
  setDraft: (draft: Draft | null) => void;
  patchDraft: (patch: Partial<Draft>) => void;
  setSettingsOpen: (open: boolean) => void;
  focus: (id: string | null) => void;

  applySnapshot: (jobs: Job[], queue: QueueState) => void;
  upsertJob: (job: Job) => void;
  applyProgress: (items: { id: string; progress: Progress }[]) => void;
  removeJobs: (ids: string[]) => void;
  setQueue: (queue: QueueState) => void;
}

export const ACTIVE_STATUSES = new Set(["scanning", "queued", "running", "paused"]);

/** What the big panel shows: the chosen transfer, else the one copying, else the next or the last. */
export function heroId(state: Pick<State, "focused" | "jobs" | "order">): string | null {
  if (state.focused && state.jobs[state.focused]) return state.focused;
  const list = state.order.map((id) => state.jobs[id]).filter(Boolean);
  const pick =
    list.find((job) => job.status === "running") ??
    list.find((job) => job.status === "paused") ??
    list.find((job) => job.status === "scanning" || job.status === "queued") ??
    list[list.length - 1];
  return pick?.id ?? null;
}

export const useStore = create<State>()((set) => ({
  booted: false,
  authRequired: false,
  authenticated: false,
  system: null,
  settings: null,
  jobs: {},
  order: [],
  queue: { running: false, counts: EMPTY_COUNTS, total_bytes: 0, bytes_done: 0, speed: null },
  connection: "connecting",
  browser: null,
  draft: null,
  settingsOpen: false,
  focused: null,
  speeds: {},

  setBoot: (patch) => set(patch),
  setData: (patch) => set(patch),
  setConnection: (connection) => set({ connection }),
  openBrowser: (browser) => set({ browser }),
  setDraft: (draft) => set({ draft }),
  patchDraft: (patch) => set((state) => (state.draft ? { draft: { ...state.draft, ...patch } } : state)),
  setSettingsOpen: (settingsOpen) => set({ settingsOpen }),
  focus: (focused) => set({ focused }),

  applySnapshot: (list, queue) =>
    set(() => ({
      jobs: Object.fromEntries(list.map((job) => [job.id, job])),
      order: list.map((job) => job.id),
      queue,
    })),

  upsertJob: (job) =>
    set((state) => {
      const current = state.jobs[job.id];
      // Ignore copies older than what the WebSocket already delivered
      if (current && current.revision > job.revision) return state;
      const order = current !== undefined ? state.order : [...state.order, job.id];
      // A transfer that starts over gets a fresh speed chart
      const restarted = job.status === "scanning" && current && current.status !== "scanning";
      const speeds = restarted ? { ...state.speeds, [job.id]: [] } : state.speeds;
      return { jobs: { ...state.jobs, [job.id]: job }, order, speeds };
    }),

  applyProgress: (items) =>
    set((state) => {
      const jobs = { ...state.jobs };
      const speeds = { ...state.speeds };
      for (const { id, progress } of items) {
        const job = jobs[id];
        if (!job) continue;
        jobs[id] = { ...job, progress };
        if (job.status === "running") speeds[id] = [...(speeds[id] ?? []), progress.speed ?? 0].slice(-SPEED_SAMPLES);
      }
      return { jobs, speeds };
    }),

  removeJobs: (ids) =>
    set((state) => {
      const gone = new Set(ids);
      const jobs = { ...state.jobs };
      const speeds = { ...state.speeds };
      ids.forEach((id) => {
        delete jobs[id];
        delete speeds[id];
      });
      return {
        jobs,
        speeds,
        order: state.order.filter((id) => !gone.has(id)),
        focused: state.focused && gone.has(state.focused) ? null : state.focused,
      };
    }),

  setQueue: (queue) => set({ queue }),
}));

