import {
  Check,
  ChevronDown,
  CircleDashed,
  Copy,
  Folder,
  LoaderCircle,
  MoveRight,
  Pause,
  Play,
  SkipForward,
  Square,
  Trash2,
  TriangleAlert,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { jobAction, removeJobs, saveSettings } from "@/lib/actions";
import { api } from "@/lib/api";
import { basename, formatBytes, formatDuration, formatRelative, formatSpeed, prettyPath } from "@/lib/format";
import { type TranslationKey, useLang, useT } from "@/lib/i18n";
import { ACTIVE_STATUSES, useStore } from "@/lib/store";
import type { FileState, FileStates, Job, WhenDone } from "@/lib/types";
import { cn, copyText } from "@/lib/utils";
import { SpeedChart } from "./SpeedChart";
import { Bar, SegmentedBar, TONE_DOT, TONE_TEXT, toneOf } from "./ui/bars";
import { Button } from "./ui/button";
import { Select } from "./ui/controls";
import { Tip } from "./ui/overlay";

const NO_SAMPLES: number[] = [];

/** Bytes a transfer has done: all of them once it completed. */
function doneBytes(job: Job): number {
  return job.status === "completed" ? job.total_bytes : job.progress.bytes_done;
}

function headline(job: Job): TranslationKey {
  const moving = job.options.mode === "move";
  switch (job.status) {
    case "scanning":
      return "hero.scanning";
    case "conflict":
      return "hero.conflict";
    case "queued":
      return moving ? "hero.queuedMove" : "hero.queuedCopy";
    case "running":
      return moving ? "hero.moving" : "hero.copying";
    case "paused":
      return "hero.paused";
    case "completed":
      return moving ? "hero.moved" : "hero.copied";
    case "failed":
      return "hero.failed";
    case "canceled":
      return "hero.canceled";
  }
}

function jobTitle(job: Job, t: ReturnType<typeof useT>): string {
  return job.sources.length === 1
    ? basename(job.sources[0])
    : t("job.itemsNamed", { name: basename(job.sources[0]), count: job.sources.length - 1 });
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] text-subtle">{label}</div>
      <div className="truncate text-[15px] font-bold text-fg tabular">{value}</div>
    </div>
  );
}

/** The transfer in the spotlight, with the whole list's progress under it. */
function Hero({ job, list }: { job: Job; list: Job[] }) {
  const t = useT();
  const lang = useLang();
  const home = useStore((s) => s.system?.home);
  const samples = useStore((s) => s.speeds[job.id] ?? NO_SAMPLES);
  const queue = useStore((s) => s.queue);
  const focus = useStore((s) => s.focus);
  const { progress } = job;
  const tone = toneOf(job.status);
  const waiting = list.filter((j) => j.status === "queued" || j.status === "scanning").length;

  // The big number is the whole list, like the bar under it
  const counted = list.filter((j) => j.status !== "canceled");
  const total = counted.reduce((sum, j) => sum + j.total_bytes, 0);
  const done = counted.reduce((sum, j) => sum + Math.min(j.total_bytes, doneBytes(j)), 0);
  const listPct = total ? (done / total) * 100 : 0;
  const filesTotal = counted.reduce((sum, j) => sum + j.total_files, 0);
  const filesDone = counted.reduce((sum, j) => sum + (j.status === "completed" ? j.total_files : j.progress.files_done), 0);
  const remaining = queue.speed ? Math.max(0, total - done) / queue.speed : null;
  const average = progress.elapsed_s ? progress.bytes_done / progress.elapsed_s : null;
  const peak = samples.length ? Math.max(...samples) : 0;
  const fileSize = progress.current_size;
  const filePct = fileSize ? (progress.current_bytes / fileSize) * 100 : job.status === "completed" ? 100 : 0;
  const from = job.sources.length === 1 ? job.sources[0] : job.sources[0].replace(/\/[^/]+\/?$/, "") || "/";

  let badge = t(`status.${job.status}`);
  if (job.status === "running") badge = t("hero.running");
  if (waiting && ACTIVE_STATUSES.has(job.status)) badge += ` · ${t("hero.waiting", { count: waiting })}`;

  const segments = list.map((j, index) => ({
    id: j.id,
    weight: Math.round(j.total_bytes / 1048576) || 1,
    value: j.total_bytes ? (Math.min(j.total_bytes, doneBytes(j)) / j.total_bytes) * 100 : 0,
    tone: toneOf(j.status),
    title: `#${index + 1} ${jobTitle(j, t)} → ${basename(j.destination)}`,
    onClick: () => focus(j.id),
  }));

  return (
    <div className="px-5 pb-4 pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="min-w-0 truncate text-lg font-bold tracking-tight text-fg">
          {t(headline(job), { count: job.total_files, size: formatBytes(job.total_bytes, lang) })}
        </h2>
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-xs font-semibold",
            tone === "active" && "bg-accent-soft text-accent",
            tone === "paused" && "bg-warning/12 text-warning",
            tone === "done" && "bg-success/12 text-success",
            tone === "failed" && "bg-danger/12 text-danger",
            tone === "waiting" && "bg-elevated text-muted",
          )}
        >
          {badge}
        </span>
        {job.fast_move && (
          <Tip content={t("job.fastMove")}>
            <Zap className="size-4 shrink-0 text-warning" />
          </Tip>
        )}
      </div>

      <dl className="mt-3 grid grid-cols-[64px_minmax(0,1fr)] gap-x-2.5 gap-y-1 text-[13px]">
        <dt className="text-subtle">{t("hero.from")}</dt>
        <dd className="truncate font-medium text-fg" title={prettyPath(from, home)}>
          {jobTitle(job, t)} <span className="font-normal text-subtle">· {prettyPath(from, home)}</span>
        </dd>
        <dt className="text-subtle">{t("hero.to")}</dt>
        <dd className="truncate font-medium text-fg" title={job.destination}>
          {prettyPath(job.destination, home)}
        </dd>
      </dl>

      <div className="mt-4 flex items-stretch gap-4">
        <div className="flex w-36 shrink-0 flex-col justify-center">
          <div className={cn("text-[52px] font-extrabold leading-none tracking-tighter tabular", TONE_TEXT[tone])}>
            {job.status === "scanning" ? "…" : Math.floor(listPct)}
            <span className="text-[26px]">%</span>
          </div>
          <div className="mt-1.5 text-xs text-subtle">{t("hero.ofList")}</div>
        </div>
        <div className="relative h-[92px] min-w-0 flex-1 overflow-hidden rounded-xl border border-border bg-panel">
          <SpeedChart samples={samples} tone={tone} />
          <div className="absolute left-2.5 top-2 flex items-baseline gap-1.5">
            <span className="text-[17px] font-bold text-fg tabular">
              {job.status === "running" ? formatSpeed(progress.speed, lang) : "—"}
            </span>
            <span className="text-[11px] text-subtle">{t("hero.now")}</span>
          </div>
          {peak > 0 && (
            <div className="absolute right-2.5 top-2.5 text-[11px] text-subtle tabular">
              {t("hero.peak", { speed: formatSpeed(peak, lang) })}
            </div>
          )}
        </div>
      </div>

      <div className="mt-4">
        <div className="flex items-center justify-between gap-3 text-xs text-muted">
          <span className="flex min-w-0 items-center gap-2">
            <span className={cn("size-[7px] shrink-0 rounded-full", TONE_DOT[tone], tone === "active" && "animate-pulse")} />
            <span className="truncate font-mono text-[11.5px] text-fg" title={progress.current ?? undefined}>
              {progress.current ?? (job.status === "completed" ? t("hero.allDone") : t(job.status === "scanning" ? "job.scanning" : "job.waiting"))}
            </span>
          </span>
          {fileSize != null && progress.current && (
            <span className="shrink-0 tabular">
              {t("job.ofTotal", { done: formatBytes(progress.current_bytes, lang), total: formatBytes(fileSize, lang) })} ·{" "}
              <strong className="text-fg">{Math.floor(filePct)}%</strong>
            </span>
          )}
        </div>
        <Bar className="mt-1.5" value={filePct} tone={tone} indeterminate={job.status === "scanning"} label={t("hero.fileBar")} />
      </div>

      <div className="mt-4">
        <div className="flex items-center justify-between gap-3 text-xs text-muted">
          <span>
            <strong className="text-fg">{t("hero.list")}</strong> · {t("hero.filesOf", { done: filesDone, total: filesTotal })}
          </span>
          <span className="shrink-0 tabular">{t("job.ofTotal", { done: formatBytes(done, lang), total: formatBytes(total, lang) })}</span>
        </div>
        <SegmentedBar className="mt-1.5" segments={segments} />
        <div className="mt-2 flex flex-wrap gap-x-3.5 gap-y-1.5">
          {list.map((j, index) => {
            const pct = j.total_bytes ? Math.floor((Math.min(j.total_bytes, doneBytes(j)) / j.total_bytes) * 100) : 0;
            return (
              <button
                key={j.id}
                type="button"
                onClick={() => focus(j.id)}
                className={cn(
                  "inline-flex max-w-full items-center gap-1.5 rounded text-[11.5px] text-muted outline-none hover:text-fg focus-visible:ring-2 focus-visible:ring-ring",
                  j.id === job.id && "text-fg",
                )}
              >
                <span className={cn("size-2.5 shrink-0 rounded-[3px]", TONE_DOT[toneOf(j.status)])} />
                <strong className="text-fg">#{index + 1}</strong>
                <span className="truncate">{jobTitle(j, t)}</span>
                <span className="tabular">
                  ·{" "}
                  {j.status === "queued" || j.status === "scanning"
                    ? t("status.queued").toLowerCase()
                    : j.status === "conflict"
                      ? t("status.conflict").toLowerCase()
                      : `${pct}%`}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2.5 rounded-xl border border-border bg-panel px-3 py-2.5">
        <Stat label={t("job.elapsed")} value={job.started_at && !job.fast_move ? formatDuration(progress.elapsed_s) : "—"} />
        <Stat label={t("job.remaining")} value={job.status === "running" ? formatRelative(remaining) : job.status === "paused" ? t("status.paused") : "—"} />
        <Stat label={t("hero.average")} value={average && !job.fast_move ? formatSpeed(average, lang) : "—"} />
      </div>

      {job.status === "failed" && job.error && (
        <p className="mt-3 flex items-start gap-2 rounded-lg bg-danger/10 px-3 py-2 text-[12.5px] text-danger">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
          {job.error}
        </p>
      )}
    </div>
  );
}

function Actions({ job, more, onToggle }: { job: Job; more: boolean; onToggle: () => void }) {
  const t = useT();
  const desktop = useStore((s) => s.system?.desktop);
  const whenDone = useStore((s) => s.settings?.when_done ?? "nothing");
  const active = job.status === "running" || job.status === "paused";
  const options: { value: WhenDone; label: string }[] = [
    { value: "nothing", label: t("whenDone.nothing") },
    ...(desktop ? [{ value: "close" as const, label: t("whenDone.close") }] : []),
    { value: "verify", label: t("whenDone.verify") },
    ...(desktop ? [{ value: "shutdown" as const, label: t("whenDone.shutdown") }] : []),
  ];
  return (
    <div className="flex flex-wrap items-center gap-2 px-5 pb-4">
      {job.status === "paused" ? (
        <Button variant="primary" onClick={() => jobAction(job, "resume")}>
          <Play />
          {t("job.resume")}
        </Button>
      ) : (
        <Button disabled={job.status !== "running"} onClick={() => jobAction(job, "pause")}>
          <Pause />
          {t("job.pause")}
        </Button>
      )}
      <Button disabled={!active || !job.progress.current} onClick={() => jobAction(job, "skip")}>
        <SkipForward />
        {t("job.skip")}
      </Button>
      <Button variant="danger" disabled={!ACTIVE_STATUSES.has(job.status)} onClick={() => jobAction(job, "cancel")}>
        <Square />
        {t("job.cancel")}
      </Button>
      <label className="ml-auto flex items-center gap-2 text-xs text-muted">
        {t("whenDone.label")}
        <Select<WhenDone>
          aria-label={t("whenDone.label")}
          className="h-8 w-44 text-xs"
          value={options.some((o) => o.value === whenDone) ? whenDone : "nothing"}
          onValueChange={(when_done) => saveSettings({ when_done })}
          options={options}
        />
      </label>
      <Button size="sm" variant="ghost" onClick={onToggle} aria-expanded={more}>
        <ChevronDown className={cn("transition-transform", more && "rotate-180")} />
        {more ? t("hero.less") : t("hero.more")}
      </Button>
    </div>
  );
}

type Filter = "all" | "done" | "pending" | "skipped" | "log";

const FILE_ICONS: Record<FileState, React.ReactNode> = {
  done: <Check className="size-3.5 text-success" strokeWidth={2.6} />,
  current: <LoaderCircle className="size-3.5 animate-spin text-accent" />,
  pending: <CircleDashed className="size-3.5 text-subtle" />,
  skipped: <SkipForward className="size-3.5 text-warning" />,
  uptodate: <Check className="size-3.5 text-subtle" />,
};

function matches(state: FileState, filter: Filter): boolean {
  if (filter === "all" || filter === "log") return true;
  if (filter === "done") return state === "done";
  if (filter === "skipped") return state === "skipped" || state === "uptodate";
  return state === "pending" || state === "current";
}

/** The rsync command of a transfer and what rsync said. */
function LogView({ job }: { job: Job }) {
  const t = useT();
  const [log, setLog] = useState<{ log: string[]; command: string } | null>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    let cancelled = false;
    api
      .jobLog(job.id)
      .then((data) => !cancelled && setLog(data))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [job.id, job.status]);
  return (
    <div className="space-y-2.5 border-t border-border p-4">
      <div className="relative">
        <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-lg border border-border bg-panel px-3 py-2 pr-24 font-mono text-[11.5px] leading-relaxed text-muted">
          {log?.command ?? "…"}
        </pre>
        {log && (
          <Button
            size="xs"
            variant="ghost"
            className="absolute right-1.5 top-1.5"
            onClick={async () => {
              if (await copyText(log.command)) {
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }
            }}
          >
            {copied ? <Check /> : <Copy />}
            {copied ? t("job.copied") : t("job.copyCommand")}
          </Button>
        )}
      </div>
      <pre className="max-h-56 overflow-auto rounded-lg border border-border bg-panel px-3 py-2 font-mono text-[11.5px] leading-relaxed text-muted">
        {log?.log.length ? log.log.join("\n") : t("job.noLog")}
      </pre>
    </div>
  );
}

/** Every transfer of the list with its files, like the file list of the original RGCopy. */
function FileList({ list, hero }: { list: Job[]; hero: Job }) {
  const t = useT();
  const lang = useLang();
  const focus = useStore((s) => s.focus);
  const [filter, setFilter] = useState<Filter>("all");
  const [files, setFiles] = useState<Record<string, FileStates>>({});
  const key = list.map((j) => `${j.id}:${j.status}`).join(",");
  const running = list.some((j) => j.status === "running");

  // Reloaded when a transfer changes state, and every second and a half while one copies
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      Promise.all(list.map((j) => api.jobFiles(j.id, 0, 2000).then((data) => [j.id, data] as const).catch(() => null))).then(
        (entries) => {
          if (!cancelled) setFiles(Object.fromEntries(entries.filter((e): e is [string, FileStates] => e !== null)));
        },
      );
    void load();
    const timer = running ? setInterval(load, 1500) : undefined;
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
    // `key` stands for `list`: a new array on every progress event must not reload the files
  }, [key, running]);

  const counts = useMemo(() => {
    const all = Object.values(files).flatMap((f) => f.files);
    return {
      all: all.length,
      done: all.filter((f) => matches(f.state, "done")).length,
      pending: all.filter((f) => matches(f.state, "pending")).length,
      skipped: all.filter((f) => matches(f.state, "skipped")).length,
    };
  }, [files]);

  const tabs: { id: Filter; label: string }[] = [
    { id: "all", label: t("files.tab.all", { count: counts.all }) },
    { id: "done", label: t("files.tab.done", { count: counts.done }) },
    { id: "pending", label: t("files.tab.pending", { count: counts.pending }) },
    { id: "skipped", label: t("files.tab.skipped", { count: counts.skipped }) },
    { id: "log", label: t("files.tab.log") },
  ];

  return (
    <div className="border-t border-border animate-fade-in">
      <div role="tablist" aria-label={t("files.tabs")} className="flex flex-wrap gap-1 px-4 py-2.5">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={filter === tab.id}
            onClick={() => setFilter(tab.id)}
            className={cn(
              "h-7 rounded-md px-2.5 text-xs font-semibold outline-none transition focus-visible:ring-2 focus-visible:ring-ring",
              filter === tab.id ? "bg-fg text-bg" : "bg-elevated text-muted hover:text-fg",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {filter === "log" ? (
        <LogView job={hero} />
      ) : (
      <div className="max-h-80 overflow-y-auto border-t border-border">
        {list.map((job, index) => {
          const data = files[job.id];
          const shown = (data?.files ?? []).filter((f) => matches(f.state, filter));
          const tone = toneOf(job.status);
          const pct = job.total_bytes ? (Math.min(job.total_bytes, doneBytes(job)) / job.total_bytes) * 100 : 0;
          // Waiting or finished; a transfer in progress is canceled with the button above
          const removable = !["scanning", "running", "paused"].includes(job.status);
          return (
            <section key={job.id} aria-label={`#${index + 1} ${jobTitle(job, t)}`}>
              <div
                className={cn(
                  "sticky top-0 z-[1] flex items-center gap-2 border-b border-border px-4 py-1.5 text-xs",
                  job.id === hero.id ? "bg-accent-soft" : "bg-panel",
                )}
              >
                <button
                  type="button"
                  onClick={() => focus(job.id)}
                  className="flex min-w-0 flex-1 items-center gap-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <strong className="text-fg">#{index + 1}</strong>
                  {job.options.mode === "move" ? <MoveRight className="size-3.5 shrink-0 text-accent-2" /> : <Copy className="size-3.5 shrink-0 text-accent" />}
                  <span className="truncate text-muted">
                    {jobTitle(job, t)} → {basename(job.destination)} ({t("hero.files", { count: job.total_files })})
                  </span>
                </button>
                <Bar className="h-1.5 w-16 shrink-0" value={pct} tone={tone} />
                <span
                  className={cn(
                    "shrink-0 rounded-full px-2 py-px text-[11px] font-semibold",
                    tone === "active" && "bg-accent-soft text-accent",
                    tone === "paused" && "bg-warning/12 text-warning",
                    tone === "done" && "bg-success/12 text-success",
                    tone === "failed" && "bg-danger/12 text-danger",
                    tone === "waiting" && "bg-elevated text-muted",
                  )}
                >
                  {t(`status.${job.status}`)}
                </span>
                {removable && (
                  <Tip content={job.status === "queued" ? t("job.removeQueued") : t("job.remove")}>
                    <Button size="icon-sm" variant="ghost" aria-label={t("job.remove")} onClick={() => removeJobs([job.id])}>
                      <Trash2 />
                    </Button>
                  </Tip>
                )}
              </div>
              {shown.map((file) => (
                <div
                  key={file.path}
                  className={cn(
                    "grid grid-cols-[18px_minmax(0,1fr)_84px_70px] items-center gap-2.5 border-b border-border/60 px-4 py-1.5 text-[12.5px] last:border-b-0",
                    file.state === "current" && "bg-accent-soft/60",
                  )}
                >
                  <Tip content={t(`files.${file.state}`)}>
                    <span className="grid place-items-center">{FILE_ICONS[file.state]}</span>
                  </Tip>
                  <span className="flex min-w-0 flex-col gap-1">
                    <span className={cn("truncate", file.state === "pending" || file.state === "uptodate" ? "text-muted" : "text-fg")} title={file.path}>
                      {file.path}
                    </span>
                    {file.state === "current" && job.progress.current_size ? (
                      <Bar
                        className="h-1"
                        value={(job.progress.current_bytes / job.progress.current_size) * 100}
                        tone={tone}
                      />
                    ) : null}
                  </span>
                  <span className="text-right text-muted tabular">{formatBytes(file.size, lang)}</span>
                  <span
                    className={cn(
                      "text-right text-[11.5px] font-semibold tabular",
                      file.state === "done" && "text-success",
                      file.state === "current" && "text-accent",
                      file.state === "skipped" && "text-warning",
                      (file.state === "pending" || file.state === "uptodate") && "text-subtle",
                    )}
                  >
                    {file.state === "current" && job.progress.current_size
                      ? `${Math.floor((job.progress.current_bytes / job.progress.current_size) * 100)}%`
                      : t(`files.short.${file.state}`)}
                  </span>
                </div>
              ))}
              {data && !shown.length && <p className="px-4 py-2 pl-11 text-xs text-subtle">{t("files.emptyFilter")}</p>}
              {data?.truncated && filter === "all" && (
                <p className="px-4 py-2 pl-11 text-xs text-subtle">{t("files.more", { count: data.total - data.files.length })}</p>
              )}
            </section>
          );
        })}
      </div>
      )}
    </div>
  );
}

/** RGCopy's window while something is pending: the transfer in progress and the list. */
export function TransferWindow({ job, list }: { job: Job; list: Job[] }) {
  const t = useT();
  const decideLater = useStore((s) => s.decideLater);
  const [more, setMore] = useState(true);
  return (
    <section aria-label={t("hero.region")} className="overflow-hidden rounded-2xl border border-border bg-surface shadow-card">
      <Hero job={job} list={list} />
      {job.status === "conflict" && (
        <div className="mx-5 mb-4 flex items-center gap-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-[12.5px] text-warning">
          <Folder className="size-3.5 shrink-0" />
          <span className="flex-1">{t("hero.conflictHint", { count: job.conflict_count, folder: basename(job.destination) })}</span>
          <Button size="xs" onClick={() => decideLater(job.id, false)}>
            {t("hero.decide")}
          </Button>
        </div>
      )}
      <Actions job={job} more={more} onToggle={() => setMore(!more)} />
      {more && <FileList list={list} hero={job} />}
      <p className="border-t border-border bg-panel px-4 py-2 text-xs text-subtle">
        {list.filter((j) => j.status === "queued").length ? t("hero.footerQueued") : t("hero.footer")}
      </p>
    </section>
  );
}
