import { toast } from "sonner";
import { closeWindow, verifyAll } from "./actions";
import { api } from "./api";
import { resolveLang, translate } from "./i18n";
import { nativeApi } from "./native";
import { useStore } from "./store";
import type { ServerEvent } from "./types";

function tr(key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) {
  return translate(resolveLang(useStore.getState().settings?.language), key, vars);
}

function notify(title: string, body: string) {
  const settings = useStore.getState().settings;
  if (!settings?.notify_on_finish || !("Notification" in window) || Notification.permission !== "granted") return;
  if (document.visibilityState === "visible" && document.hasFocus()) return;
  try {
    new Notification(title, { body, icon: "/favicon.svg" });
  } catch {
    // Some webviews expose the API but refuse to show notifications
  }
}

/** "When done": only once everything finished without errors. */
function whenDone() {
  const { settings, jobs, system } = useStore.getState();
  const list = Object.values(jobs);
  if (!settings || !list.length || !list.every((job) => job.status === "completed")) return;
  if (settings.when_done === "verify") void verifyAll();
  else if (settings.when_done === "close" && nativeApi()) {
    // Leave a moment to see the result
    setTimeout(() => void closeWindow(), 1500);
  } else if (settings.when_done === "shutdown" && system?.desktop) {
    useStore.getState().setShutdownIn(60);
  }
}

function handle(event: ServerEvent) {
  const store = useStore.getState();
  switch (event.type) {
    case "snapshot":
      store.applySnapshot(event.jobs, event.queue);
      break;
    case "job": {
      const before = store.jobs[event.job.id];
      store.upsertJob(event.job);
      if (event.job.status === "failed" && before && before.status !== "failed") {
        toast.error(tr("toast.jobFailed", { name: event.job.name }), { description: event.job.error ?? undefined });
      }
      break;
    }
    case "progress":
      store.applyProgress(event.items);
      break;
    case "removed":
      store.removeJobs(event.ids);
      break;
    case "queue":
      store.setQueue(event.queue);
      break;
    case "queue_finished": {
      const { completed, failed, canceled } = event.counts;
      const body = tr("toast.queueDoneBody", { completed, failed: failed + canceled });
      if (failed) toast.warning(tr("toast.queueDone"), { description: body });
      else toast.success(tr("toast.queueDone"), { description: body });
      notify(tr("toast.queueDone"), body);
      whenDone();
      break;
    }
    case "settings":
      store.setData({ settings: event.settings });
      break;
    case "resync":
      api
        .jobs()
        .then(({ jobs, queue }) => useStore.getState().applySnapshot(jobs, queue))
        .catch(() => undefined);
      break;
  }
}

/** Keep a WebSocket open to the server, reconnecting with backoff. Returns a disposer. */
export function connectEvents(onUnauthorized: () => void): () => void {
  let socket: WebSocket | null = null;
  let attempts = 0;
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const open = () => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${protocol}://${window.location.host}/api/events`);
    useStore.getState().setConnection(attempts ? "offline" : "connecting");
    socket.onopen = () => {
      attempts = 0;
      useStore.getState().setConnection("online");
    };
    socket.onmessage = (message) => {
      try {
        handle(JSON.parse(message.data as string) as ServerEvent);
      } catch (error) {
        console.error("Bad event", error);
      }
    };
    socket.onclose = (close) => {
      if (stopped) return;
      if (close.code === 4401) {
        onUnauthorized();
        return;
      }
      useStore.getState().setConnection("offline");
      const delay = Math.min(10_000, 400 * 2 ** attempts++);
      timer = setTimeout(open, delay);
    };
  };

  open();
  return () => {
    stopped = true;
    clearTimeout(timer);
    socket?.close();
  };
}
