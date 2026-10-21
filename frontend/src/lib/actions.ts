import { toast } from "sonner";
import { ApiError, api } from "./api";
import { hasKey, resolveLang, type TranslationKey, translate } from "./i18n";
import { nativeApi } from "./native";
import { type BrowserMode, useStore } from "./store";
import type { Job, JobStatus, Mode, Settings, TransferOptions } from "./types";

function tr(key: TranslationKey, vars?: Record<string, string | number>): string {
  return translate(resolveLang(useStore.getState().settings?.language), key, vars);
}

export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    const key = `errors.${error.code}`;
    return hasKey(key) ? tr(key) : error.message;
  }
  return error instanceof Error ? error.message : tr("errors.generic");
}

function reportError(error: unknown) {
  toast.error(errorText(error));
}

/** The built-in browser (works everywhere, and can pick files and folders together). */
export function browse(mode: BrowserMode, start?: string): Promise<string[]> {
  return new Promise((resolve) => useStore.getState().openBrowser({ mode, start, resolve }));
}

/** Native dialogs in the desktop app, the built-in browser everywhere else. */
export async function pickFiles(): Promise<string[]> {
  const native = nativeApi();
  if (!native) return browse("sources");
  try {
    return await native.pick_files();
  } catch (error) {
    reportError(error);
    return [];
  }
}

export async function pickFolder(start?: string): Promise<string | null> {
  const native = nativeApi();
  if (!native) return (await browse("folder", start))[0] ?? null;
  try {
    return await native.pick_folder();
  } catch (error) {
    reportError(error);
    return null;
  }
}

export function openCompose(prefill: { sources?: string[]; destination?: string | null; mode?: Mode } = {}) {
  useStore.getState().setDraft({
    sources: prefill.sources ?? [],
    destination: prefill.destination ?? null,
    mode: prefill.mode ?? "copy",
  });
}

export async function submitTransfer(sources: string[], destination: string, options: Partial<TransferOptions>) {
  try {
    const job = await api.addJob(sources, destination, options);
    useStore.getState().upsertJob(job);
    toast.success(tr("toast.added"));
    return true;
  } catch (error) {
    reportError(error);
    return false;
  }
}

/** Files copied or cut in the file manager (desktop app only). */
export async function pasteFromClipboard(destination?: string) {
  try {
    const clip = await api.clipboard();
    if (!clip.paths.length) {
      toast(tr("toast.clipboardEmpty"));
      return;
    }
    openCompose({ sources: clip.paths, destination: destination ?? null, mode: clip.action === "cut" ? "move" : "copy" });
  } catch (error) {
    reportError(error);
  }
}

export async function jobAction(job: Job, action: "pause" | "resume" | "cancel" | "retry") {
  try {
    useStore.getState().upsertJob(await api.jobAction(job.id, action));
  } catch (error) {
    reportError(error);
  }
}

export async function removeJobs(ids: string[]) {
  if (!ids.length) return;
  try {
    const { removed } = await api.removeJobs(ids);
    useStore.getState().removeJobs(removed);
  } catch (error) {
    reportError(error);
  }
}

export async function startQueue() {
  try {
    useStore.getState().setQueue(await api.startQueue());
  } catch (error) {
    reportError(error);
  }
}

export async function pauseQueue() {
  try {
    useStore.getState().setQueue(await api.pauseQueue());
  } catch (error) {
    reportError(error);
  }
}

export async function clearQueue(statuses: JobStatus[]) {
  try {
    const { removed } = await api.clearQueue(statuses);
    useStore.getState().removeJobs(removed);
  } catch (error) {
    reportError(error);
  }
}

export async function saveSettings(patch: Partial<Settings>) {
  const store = useStore.getState();
  const previous = store.settings;
  if (previous) store.setData({ settings: { ...previous, ...patch } });
  try {
    store.setData({ settings: await api.saveSettings(patch) });
  } catch (error) {
    if (previous) useStore.getState().setData({ settings: previous });
    reportError(error);
  }
}

export async function openPath(path: string) {
  const native = nativeApi();
  if (!native) return;
  try {
    if (!(await native.open_path(path))) toast.error(tr("errors.not_found"));
  } catch (error) {
    reportError(error);
  }
}
