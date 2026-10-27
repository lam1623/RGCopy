import { ClipboardPaste, CopyPlus, Pause, Play, Settings2, Terminal, WifiOff } from "lucide-react";
import { useEffect, useMemo } from "react";
import { openCompose, pasteFromClipboard, pauseQueue, startQueue } from "@/lib/actions";
import { formatSpeed } from "@/lib/format";
import { useLang, useT } from "@/lib/i18n";
import { nativeApi } from "@/lib/native";
import { ACTIVE_STATUSES, heroId, useStore } from "@/lib/store";
import type { Job } from "@/lib/types";
import { cn, isMac } from "@/lib/utils";
import { Logo } from "./Brand";
import { DonePanel } from "./DonePanel";
import { TransferWindow } from "./TransferWindow";
import { Button } from "./ui/button";
import { Kbd } from "./ui/misc";
import { Tip } from "./ui/overlay";

const MOD = isMac ? "⌘" : "Ctrl";

function useShortcuts(canPaste: boolean) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, [contenteditable=true], [role=dialog]")) return;
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key === "n") {
        event.preventDefault();
        openCompose();
      } else if (key === "v" && canPaste) {
        event.preventDefault();
        void pasteFromClipboard();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [canPaste]);
}

/** "45% · Copiando · 2.4 MB/s — RGCopy", like the window title of the original RGCopy. */
function useWindowTitle() {
  const t = useT();
  const lang = useLang();
  const queue = useStore((s) => s.queue);
  const pending = queue.counts.scanning + queue.counts.queued + queue.counts.running + queue.counts.paused;
  const percent = queue.total_bytes ? Math.floor((queue.bytes_done / queue.total_bytes) * 100) : 0;
  let title = "RGCopy";
  if (queue.counts.running) title = `${percent}% · ${formatSpeed(queue.speed, lang)} — RGCopy`;
  else if (queue.counts.paused) title = `${percent}% · ${t("status.paused")} — RGCopy`;
  else if (pending) title = `${t("status.queued")} — RGCopy`;
  useEffect(() => {
    document.title = title;
    void nativeApi()?.set_title(title)?.catch(() => undefined);
  }, [title]);
}

function Footer() {
  const t = useT();
  const counts = useStore((s) => s.queue.counts);
  const rsync = useStore((s) => s.system?.rsync);
  const connection = useStore((s) => s.connection);

  return (
    <footer className="flex items-center gap-4 border-t border-border bg-panel px-4 py-2 text-xs text-muted">
      {connection === "offline" ? (
        <span className="flex items-center gap-1.5 font-medium text-warning">
          <WifiOff className="size-3.5" />
          {t("conn.offline")}
        </span>
      ) : (
        <Tip content={rsync?.available ? rsync.path : t("engine.missingHelp")}>
          <span className="flex shrink-0 items-center gap-1.5">
            <span className={cn("size-2 rounded-full", rsync?.available ? "bg-success" : "bg-danger")} />
            {rsync?.available ? t("engine.ok", { version: rsync.version ?? "" }) : t("engine.missing")}
          </span>
        </Tip>
      )}
      <span className="ml-auto" />
      {counts.running > 0 ? (
        <Button size="xs" variant="ghost" onClick={() => pauseQueue()}>
          <Pause />
          {t("transfers.pauseAll")}
        </Button>
      ) : counts.conflict > 0 ? (
        <span className="font-medium text-warning">{t("hero.conflict")}</span>
      ) : counts.paused > 0 || counts.queued > 0 ? (
        <Button size="xs" variant="subtle" onClick={() => startQueue()}>
          <Play />
          {counts.paused ? t("transfers.resumeAll") : t("transfers.start")}
        </Button>
      ) : (
        <span>{t("transfers.idle")}</span>
      )}
    </footer>
  );
}

function EmptyState({ canPaste }: { canPaste: boolean }) {
  const t = useT();
  const desktop = useStore((s) => s.system?.desktop);
  return (
    <div className="grid flex-1 place-items-center px-6 py-10">
      <div className="w-full max-w-md text-center">
        <button
          onClick={() => (canPaste ? pasteFromClipboard() : openCompose())}
          className="group mx-auto flex w-full flex-col items-center rounded-3xl border-2 border-dashed border-border-strong px-6 py-10 outline-none transition hover:border-accent hover:bg-accent-soft/40 focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Logo size="lg" className="transition-transform group-hover:scale-105" />
          <span className="mt-5 text-lg font-semibold tracking-tight text-fg">{t("empty.title")}</span>
          <span className="mt-1.5 text-[13px] leading-relaxed text-muted">{canPaste ? t("empty.bodyPaste") : t("empty.body")}</span>
        </button>
        <div className="mt-5 flex flex-wrap justify-center gap-2">
          {canPaste && (
            <Button variant="primary" onClick={() => pasteFromClipboard()}>
              <ClipboardPaste />
              {t("transfers.paste")}
            </Button>
          )}
          <Button variant={canPaste ? "secondary" : "primary"} onClick={() => openCompose()}>
            <CopyPlus />
            {t("transfers.new")}
          </Button>
        </div>
        <p className="mt-4 text-xs text-subtle">
          <Kbd>{MOD}</Kbd> <Kbd>N</Kbd> {t("transfers.new").toLowerCase()}
          {canPaste && (
            <>
              {"   "}
              <Kbd>{MOD}</Kbd> <Kbd>V</Kbd> {t("transfers.paste").toLowerCase()}
            </>
          )}
        </p>
        {desktop && (
          <div className="mt-6 flex items-start gap-3 rounded-xl border border-border bg-surface px-4 py-3 text-left text-[12.5px] text-muted shadow-card">
            <Terminal className="mt-0.5 size-4 shrink-0 text-accent" />
            <span>
              {t("empty.integrate.before")} <code className="rounded bg-elevated px-1 py-0.5 font-mono text-[11.5px] text-fg">rgcopy integrate</code>{" "}
              {t("empty.integrate.after")}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

export function CopierView() {
  const t = useT();
  const hero = useStore(heroId);
  const job = useStore((s) => (hero ? s.jobs[hero] : undefined));
  const jobs = useStore((s) => s.jobs);
  const order = useStore((s) => s.order);
  const list = useMemo(() => order.map((id) => jobs[id]).filter((j): j is Job => !!j), [order, jobs]);
  const pending = list.some((j) => ACTIVE_STATUSES.has(j.status));
  const canPaste = useStore((s) => !!s.system?.clipboard);
  const setSettingsOpen = useStore((s) => s.setSettingsOpen);
  useShortcuts(canPaste);
  useWindowTitle();

  return (
    <div className="flex h-full flex-col bg-bg text-fg">
      <header className="flex items-center gap-2 border-b border-border bg-panel px-4 py-2.5">
        <Logo size="sm" />
        <span className="mr-auto text-[14px] font-semibold tracking-tight text-fg">RGCopy</span>
        {canPaste && (
          <Tip content={t("transfers.pasteHint")}>
            <Button size="sm" onClick={() => pasteFromClipboard()}>
              <ClipboardPaste />
              <span className="hidden sm:inline">{t("transfers.paste")}</span>
            </Button>
          </Tip>
        )}
        <Button size="sm" variant="primary" onClick={() => openCompose()}>
          <CopyPlus />
          <span className="hidden sm:inline">{t("transfers.new")}</span>
        </Button>
        <Tip content={t("nav.settings")}>
          <Button size="icon" variant="ghost" aria-label={t("nav.settings")} onClick={() => setSettingsOpen(true)}>
            <Settings2 />
          </Button>
        </Tip>
      </header>

      {job ? (
        <main className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl px-3 py-3 sm:px-5 sm:py-4">
            {pending ? <TransferWindow job={job} list={list} /> : <DonePanel list={list} />}
          </div>
        </main>
      ) : (
        <EmptyState canPaste={canPaste} />
      )}
      <Footer />
    </div>
  );
}
