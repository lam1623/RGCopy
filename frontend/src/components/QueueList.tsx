import { Check, Copy, Eraser, MoreHorizontal, MoveRight, Pause, Play, Square, Trash2, TriangleAlert } from "lucide-react";
import { clearQueue, jobAction, removeJobs } from "@/lib/actions";
import { basename, formatBytes } from "@/lib/format";
import { useLang, useT } from "@/lib/i18n";
import { ACTIVE_STATUSES, useStore } from "@/lib/store";
import type { Job } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";
import { ProgressBar } from "./ui/misc";
import { Menu, MenuContent, MenuItem, MenuTrigger, Tip } from "./ui/overlay";

function Row({ job, selected }: { job: Job; selected: boolean }) {
  const t = useT();
  const lang = useLang();
  const focus = useStore((s) => s.focus);
  const moving = job.options.mode === "move";
  const active = ACTIVE_STATUSES.has(job.status);
  const percent = job.status === "completed" ? 100 : job.progress.percent;
  const name =
    job.sources.length === 1 ? basename(job.sources[0]) : t("job.itemsNamed", { name: basename(job.sources[0]), count: job.sources.length - 1 });

  let detail: string;
  if (job.status === "running" || job.status === "paused") detail = `${Math.floor(percent)}%`;
  else if (job.status === "scanning") detail = t("status.scanning");
  else if (job.status === "queued") detail = formatBytes(job.total_bytes, lang);
  else detail = t(`status.${job.status}`);

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => focus(job.id)}
      onKeyDown={(event) => event.key === "Enter" && focus(job.id)}
      aria-current={selected || undefined}
      className={cn(
        "group flex items-center gap-3 border-b border-border px-4 py-2.5 outline-none transition last:border-b-0 focus-visible:bg-elevated/70",
        selected ? "bg-accent-soft" : "hover:bg-elevated/60",
      )}
    >
      <div
        className={cn(
          "grid size-7 shrink-0 place-items-center rounded-lg [&_svg]:size-3.5",
          job.status === "completed"
            ? "bg-success/12 text-success"
            : job.status === "failed" || job.status === "canceled"
              ? "bg-danger/12 text-danger"
              : moving
                ? "bg-accent-2/14 text-accent-2"
                : "bg-accent-soft text-accent",
        )}
      >
        {job.status === "completed" ? <Check /> : job.status === "failed" || job.status === "canceled" ? <TriangleAlert /> : moving ? <MoveRight /> : <Copy />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-1.5 text-[13px]">
          <span className="truncate font-medium text-fg">{name}</span>
          <span className="shrink-0 text-subtle">→</span>
          <span className="truncate text-muted">{basename(job.destination)}</span>
        </div>
        {(job.status === "running" || job.status === "paused") && (
          <ProgressBar className="mt-1.5 h-1" value={percent} status={job.status} />
        )}
      </div>
      <span
        className={cn(
          "w-20 shrink-0 text-right text-xs tabular",
          job.status === "failed" ? "font-medium text-danger" : job.status === "paused" ? "text-warning" : "text-muted",
        )}
      >
        {detail}
      </span>
      <div className="flex w-16 shrink-0 justify-end gap-0.5" onClick={(event) => event.stopPropagation()}>
        {job.status === "running" && (
          <Tip content={t("job.pause")}>
            <Button size="icon-sm" variant="ghost" aria-label={t("job.pause")} onClick={() => jobAction(job, "pause")}>
              <Pause />
            </Button>
          </Tip>
        )}
        {job.status === "paused" && (
          <Tip content={t("job.resume")}>
            <Button size="icon-sm" variant="ghost" aria-label={t("job.resume")} onClick={() => jobAction(job, "resume")}>
              <Play />
            </Button>
          </Tip>
        )}
        {active ? (
          <Tip content={t("job.cancel")}>
            <Button size="icon-sm" variant="ghost" aria-label={t("job.cancel")} onClick={() => jobAction(job, "cancel")}>
              <Square />
            </Button>
          </Tip>
        ) : (
          <Tip content={t("job.remove")}>
            <Button
              size="icon-sm"
              variant="ghost"
              className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
              aria-label={t("job.remove")}
              onClick={() => removeJobs([job.id])}
            >
              <Trash2 />
            </Button>
          </Tip>
        )}
      </div>
    </div>
  );
}

/** Every transfer but the one in the big panel: what is waiting first, then the history. */
export function QueueList({ hero }: { hero: string | null }) {
  const t = useT();
  const jobs = useStore((s) => s.jobs);
  const order = useStore((s) => s.order);
  const counts = useStore((s) => s.queue.counts);
  const list = order.map((id) => jobs[id]).filter((job): job is Job => !!job);
  const pending = list.filter((job) => ACTIVE_STATUSES.has(job.status));
  const history = list.filter((job) => !ACTIVE_STATUSES.has(job.status)).reverse();
  const rows = [...pending, ...history];
  if (rows.length <= 1 && rows[0]?.id === hero) return null;
  const finished = counts.completed + counts.failed + counts.canceled;

  return (
    <section>
      <div className="mb-2 flex items-center justify-between px-1">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-subtle">
          {t("queue.title")} <span className="tabular">· {rows.length}</span>
        </h3>
        <Menu>
          <MenuTrigger asChild>
            <Button size="icon-sm" variant="ghost" aria-label={t("transfers.more")}>
              <MoreHorizontal />
            </Button>
          </MenuTrigger>
          <MenuContent>
            <MenuItem icon={<Eraser />} disabled={!counts.completed} onSelect={() => clearQueue(["completed"])}>
              {t("transfers.clearCompleted")}
            </MenuItem>
            <MenuItem icon={<Eraser />} disabled={!finished} onSelect={() => clearQueue(["completed", "failed", "canceled"])}>
              {t("transfers.clearFinished")}
            </MenuItem>
          </MenuContent>
        </Menu>
      </div>
      <div className="overflow-hidden rounded-2xl border border-border bg-surface shadow-card">
        {rows.map((job) => (
          <Row key={job.id} job={job} selected={job.id === hero} />
        ))}
      </div>
    </section>
  );
}
