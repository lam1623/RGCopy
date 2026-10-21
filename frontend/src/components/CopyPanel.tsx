import {
  ArrowDown,
  Check,
  ChevronDown,
  CircleDashed,
  Copy,
  FileText,
  Folder,
  FolderOpen,
  LoaderCircle,
  MoveRight,
  Pause,
  Play,
  RotateCcw,
  SkipForward,
  Square,
  Trash2,
  TriangleAlert,
  Zap,
} from "lucide-react";
import { useEffect, useState } from "react";
import { jobAction, openPath, removeJobs } from "@/lib/actions";
import { api } from "@/lib/api";
import { basename, formatBytes, formatDuration, formatRelative, formatSpeed, prettyPath } from "@/lib/format";
import { type TranslationKey, useLang, useT } from "@/lib/i18n";
import { nativeApi } from "@/lib/native";
import { useStore } from "@/lib/store";
import type { FileState, FileStates, Job } from "@/lib/types";
import { cn, copyText } from "@/lib/utils";
import { SpeedChart } from "./SpeedChart";
import { Button } from "./ui/button";
import { Segmented } from "./ui/controls";
import { ProgressBar, StatusBadge } from "./ui/misc";
import { Tip } from "./ui/overlay";

const NO_SAMPLES: number[] = [];

const FILE_ICONS: Record<FileState, React.ReactNode> = {
  done: <Check className="size-3.5 text-success" />,
  current: <LoaderCircle className="size-3.5 animate-spin text-accent" />,
  pending: <CircleDashed className="size-3.5 text-subtle" />,
  skipped: <SkipForward className="size-3.5 text-subtle" />,
};

function headline(job: Job): TranslationKey {
  const moving = job.options.mode === "move";
  switch (job.status) {
    case "scanning":
      return "hero.scanning";
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

function FileList({ job }: { job: Job }) {
  const t = useT();
  const lang = useLang();
  const [data, setData] = useState<FileStates | null>(null);
  const running = job.status === "running";

  // Refreshed as files complete, and once more when the job changes state
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api
        .jobFiles(job.id, 0, 2000)
        .then((result) => !cancelled && setData(result))
        .catch(() => undefined);
    void load();
    const timer = running ? setInterval(load, 1500) : undefined;
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [job.id, job.status, running]);

  if (!data) return <p className="px-4 py-6 text-center text-xs text-subtle">…</p>;
  if (!data.files.length) return <p className="px-4 py-6 text-center text-xs text-subtle">{t("files.none")}</p>;
  const hidden = data.total - data.files.length;
  return (
    <div className="max-h-64 overflow-y-auto">
      <table className="w-full table-fixed text-[12.5px]">
        <tbody>
          {data.files.map((file) => (
            <tr key={file.path} className={cn("border-b border-border last:border-b-0", file.state === "current" && "bg-accent-soft")}>
              <td className="w-8 py-1.5 pl-3">
                <Tip content={t(`files.${file.state}`)}>{FILE_ICONS[file.state]}</Tip>
              </td>
              <td className={cn("truncate py-1.5 pr-3", file.state === "pending" || file.state === "skipped" ? "text-muted" : "text-fg")} title={file.path}>
                {file.path}
              </td>
              <td className="w-20 py-1.5 pr-3 text-right text-muted tabular">{formatBytes(file.size, lang)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {hidden > 0 && <p className="px-3 py-2 text-center text-xs text-subtle">{t("files.more", { count: hidden })}</p>}
    </div>
  );
}

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
    <div className="space-y-3 p-3">
      <div className="relative">
        <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-lg border border-border bg-surface px-3 py-2 pr-20 font-mono text-[11.5px] leading-relaxed text-muted">
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
      <pre className="max-h-48 overflow-auto rounded-lg border border-border bg-surface px-3 py-2 font-mono text-[11.5px] leading-relaxed text-muted">
        {log?.log.length ? log.log.join("\n") : t("job.noLog")}
      </pre>
    </div>
  );
}

function Place({ icon, label, path, title }: { icon: React.ReactNode; label: string; path: string; title?: string }) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-elevated text-accent [&_svg]:size-[18px]">{icon}</div>
      <div className="min-w-0">
        <div className="text-[11px] font-medium uppercase tracking-[0.06em] text-subtle">{label}</div>
        <div className="truncate text-[13px] font-medium text-fg" title={title ?? path}>
          {path}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] text-subtle">{label}</div>
      <div className={cn("truncate text-[13px] text-fg tabular", strong ? "font-semibold" : "font-medium")}>{value}</div>
    </div>
  );
}

export function CopyPanel({ job }: { job: Job }) {
  const t = useT();
  const lang = useLang();
  const home = useStore((s) => s.system?.home);
  const samples = useStore((s) => s.speeds[job.id] ?? NO_SAMPLES);
  const [more, setMore] = useState(false);
  const [tab, setTab] = useState<"files" | "log">("files");
  const native = !!nativeApi();
  const { progress } = job;
  const moving = job.options.mode === "move";
  const finished = job.status === "completed" || job.status === "failed" || job.status === "canceled";
  const active = job.status === "running" || job.status === "paused";
  const percent = job.status === "completed" ? 100 : progress.percent;
  const total = job.total_bytes || progress.total_bytes;
  const source =
    job.sources.length === 1
      ? basename(job.sources[0])
      : t("job.itemsNamed", { name: basename(job.sources[0]), count: job.sources.length - 1 });
  const from = job.sources.length === 1 ? job.sources[0] : job.sources[0].replace(/\/[^/]+\/?$/, "") || "/";

  // Failed transfers open their log: that is where rsync explains why
  useEffect(() => {
    if (job.status === "failed") {
      setMore(true);
      setTab("log");
    }
  }, [job.status]);

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-surface shadow-card">
      <div className="px-5 pb-5 pt-4">
        <div className="flex items-center gap-2">
          <h2 className="min-w-0 truncate text-[15px] font-semibold text-fg">
            {t(headline(job), { count: job.total_files, size: formatBytes(total, lang) })}
          </h2>
          {(job.status === "paused" || job.status === "failed" || job.status === "canceled") && <StatusBadge status={job.status} />}
          {job.fast_move && (
            <Tip content={t("job.fastMove")}>
              <Zap className="size-3.5 shrink-0 text-warning" />
            </Tip>
          )}
        </div>

        <div className="mt-4 grid items-center gap-3 sm:grid-cols-[1fr_auto_1fr]">
          <Place icon={moving ? <MoveRight /> : <Copy />} label={t("hero.from")} path={source} title={prettyPath(from, home)} />
          <ArrowDown className="mx-auto size-4 text-subtle sm:-rotate-90" />
          <Place
            icon={<Folder className="fill-accent/15" />}
            label={t("hero.to")}
            path={basename(job.destination)}
            title={prettyPath(job.destination, home)}
          />
        </div>

        <div className="mt-5 flex items-end gap-4">
          <div className="w-28 shrink-0">
            <div className="text-[40px] font-semibold leading-none tracking-tight text-fg tabular">
              {job.status === "scanning" ? "…" : `${Math.floor(percent)}`}
              <span className="text-xl text-muted">%</span>
            </div>
            <div className="mt-1.5 text-[13px] font-medium text-muted tabular">
              {job.status === "running" ? formatSpeed(progress.speed, lang) : job.status === "paused" ? t("status.paused") : " "}
            </div>
          </div>
          <SpeedChart samples={samples} paused={job.status === "paused"} className="min-w-0 flex-1" />
        </div>
        <ProgressBar className="mt-3 h-2.5" value={percent} status={job.status} indeterminate={job.status === "scanning"} />

        <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
          <Stat
            label={moving ? t("hero.moved.bytes") : t("hero.copied.bytes")}
            value={
              job.status === "scanning"
                ? "…"
                : t("job.ofTotal", { done: formatBytes(job.status === "completed" ? total : progress.bytes_done, lang), total: formatBytes(total, lang) })
            }
            strong
          />
          <Stat
            label={t("job.files")}
            value={job.status === "scanning" ? "…" : t("job.ofTotal", { done: job.status === "completed" ? job.total_files : progress.files_done, total: job.total_files })}
          />
          <Stat label={t("job.remaining")} value={job.status === "running" ? formatRelative(progress.eta_s) : "—"} />
          <Stat
            label={t("job.elapsed")}
            value={(active || finished) && !job.fast_move && job.started_at ? formatDuration(progress.elapsed_s) : "—"}
          />
        </div>

        <div
          className={cn(
            "mt-4 flex items-center gap-2 rounded-lg px-3 py-2 text-[12.5px]",
            job.status === "failed" ? "bg-danger/10 text-danger" : "bg-elevated/70 text-muted",
          )}
        >
          {job.status === "failed" ? <TriangleAlert className="size-3.5 shrink-0" /> : <FileText className="size-3.5 shrink-0 text-subtle" />}
          <span className={cn("min-w-0 flex-1 truncate", job.status === "running" && progress.current && "font-mono text-[11.5px] text-fg")}>
            {job.status === "failed"
              ? (job.error ?? t("status.failed"))
              : job.status === "running"
                ? (progress.current ?? t("job.starting"))
                : job.status === "paused"
                  ? (progress.current ?? t("status.paused"))
                  : job.status === "completed"
                    ? job.fast_move
                      ? t("job.fastMove")
                      : t("job.doneIn", { time: formatDuration(progress.elapsed_s) })
                    : job.status === "canceled"
                      ? t("job.canceledNote")
                      : job.status === "scanning"
                        ? t("job.scanning")
                        : t("job.waiting")}
          </span>
          {job.warning && (
            <Tip content={job.warning}>
              <TriangleAlert className="size-3.5 shrink-0 text-warning" />
            </Tip>
          )}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => setMore(!more)} aria-expanded={more}>
            <ChevronDown className={cn("transition-transform", more && "rotate-180")} />
            {more ? t("hero.less") : t("hero.more")}
          </Button>
          <div className="ml-auto flex flex-wrap gap-2">
            {job.status === "running" && (
              <Button onClick={() => jobAction(job, "pause")}>
                <Pause />
                {t("job.pause")}
              </Button>
            )}
            {job.status === "paused" && (
              <Button variant="primary" onClick={() => jobAction(job, "resume")}>
                <Play />
                {t("job.resume")}
              </Button>
            )}
            {!finished && (
              <Button variant="danger" onClick={() => jobAction(job, "cancel")}>
                <Square />
                {t("job.cancel")}
              </Button>
            )}
            {finished && native && (
              <Button onClick={() => openPath(job.destination)}>
                <FolderOpen />
                {t("job.openDestination")}
              </Button>
            )}
            {finished && (
              <Button onClick={() => jobAction(job, "retry")}>
                <RotateCcw />
                {t("job.retry")}
              </Button>
            )}
            {finished && (
              <Button variant="ghost" onClick={() => removeJobs([job.id])}>
                <Trash2 />
                {t("job.remove")}
              </Button>
            )}
          </div>
        </div>
      </div>

      {more && (
        <div className="border-t border-border bg-panel/60 animate-fade-in">
          <div className="flex items-center justify-between gap-3 px-3 pt-3">
            <Segmented
              size="sm"
              value={tab}
              onValueChange={setTab}
              options={[
                { value: "files", label: t("hero.tab.files", { count: job.total_files }) },
                { value: "log", label: t("hero.tab.log") },
              ]}
            />
          </div>
          <div className="mt-3 border-t border-border">{tab === "files" ? <FileList job={job} /> : <LogView job={job} />}</div>
        </div>
      )}
    </section>
  );
}
