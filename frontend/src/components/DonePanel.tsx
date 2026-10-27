import { Check, Eraser, FolderOpen, LoaderCircle, RotateCcw, ShieldCheck, TriangleAlert, X } from "lucide-react";
import { clearQueue, closeWindow, jobAction, openPath, verifyAll } from "@/lib/actions";
import { basename, formatBytes, formatDuration, formatSpeed } from "@/lib/format";
import { useLang, useT } from "@/lib/i18n";
import { nativeApi } from "@/lib/native";
import type { Job } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Bar } from "./ui/bars";
import { Button } from "./ui/button";

function detail(job: Job, t: ReturnType<typeof useT>, lang: ReturnType<typeof useLang>): string {
  if (job.status === "failed") return job.error ?? t("status.failed");
  if (job.status === "canceled") return t("job.canceledNote");
  const parts = [t("hero.files", { count: job.total_files }), formatBytes(job.total_bytes, lang)];
  if (job.fast_move) parts.push(t("done.instant"));
  else parts.push(formatDuration(job.progress.elapsed_s));
  if (job.skipped.length) parts.push(t("done.skipped", { count: job.skipped.length }));
  return parts.join(" · ");
}

/** Everything finished: what was done, and what can still be done about it. */
export function DonePanel({ list }: { list: Job[] }) {
  const t = useT();
  const lang = useLang();
  const native = !!nativeApi();
  const completed = list.filter((job) => job.status === "completed");
  const problems = list.filter((job) => job.status !== "completed" || job.skipped.length || job.verify === "mismatch");
  const bytes = completed.reduce((sum, job) => sum + job.total_bytes, 0);
  const files = completed.reduce((sum, job) => sum + job.total_files, 0);
  const seconds = completed.reduce((sum, job) => sum + (job.fast_move ? 0 : job.progress.elapsed_s), 0);
  const verifiable = completed.filter((job) => job.options.mode === "copy");
  const verifying = list.some((job) => job.verify === "running");
  const ok = !problems.length;

  return (
    <section aria-label={t("done.region")} className="overflow-hidden rounded-2xl border border-border bg-surface shadow-card">
      <div className="px-5 pb-5 pt-5">
        <div className="flex items-center gap-3.5">
          <div
            className={cn(
              "grid size-11 shrink-0 place-items-center rounded-xl [&_svg]:size-[22px]",
              ok ? "bg-success/12 text-success" : "bg-warning/12 text-warning",
            )}
          >
            {ok ? <Check strokeWidth={2.6} /> : <TriangleAlert />}
          </div>
          <div className="min-w-0">
            <h2 className="text-lg font-bold tracking-tight text-fg">
              {completed.length === 1 ? t("done.titleOne") : t("done.title", { count: completed.length })}
            </h2>
            <p className="mt-0.5 text-[13px] text-muted tabular">
              {t("hero.files", { count: files })} · {formatBytes(bytes, lang)}
              {seconds > 0 && ` · ${formatDuration(seconds)} · ${t("done.average", { speed: formatSpeed(bytes / seconds, lang) })}`}
            </p>
          </div>
        </div>
        <Bar className="mt-4 h-3" value={100} tone={ok ? "done" : "paused"} label={t("done.region")} />

        <ul className="mt-4 overflow-hidden rounded-xl border border-border">
          {list.map((job, index) => (
            <li key={job.id} className="grid grid-cols-[20px_minmax(0,1fr)_auto] items-center gap-2.5 border-b border-border px-3 py-2.5 text-[13px] last:border-b-0">
              {job.status === "completed" && !job.skipped.length ? (
                <Check className="size-4 text-success" strokeWidth={2.6} />
              ) : job.status === "completed" ? (
                <TriangleAlert className="size-4 text-warning" />
              ) : (
                <X className="size-4 text-danger" />
              )}
              <div className="min-w-0">
                <div className="truncate font-semibold text-fg">
                  #{index + 1} {job.options.mode === "move" ? t("mode.move") : t("mode.copy")}{" "}
                  {job.sources.length === 1 ? basename(job.sources[0]) : t("job.items", { count: job.sources.length })} →{" "}
                  {basename(job.destination)}
                </div>
                <div className={cn("truncate text-xs", job.status === "failed" ? "text-danger" : "text-subtle")}>{detail(job, t, lang)}</div>
                {job.verify && (
                  <div
                    className={cn(
                      "mt-0.5 flex items-center gap-1 text-xs",
                      job.verify === "ok" && "text-success",
                      job.verify === "running" && "text-muted",
                      (job.verify === "mismatch" || job.verify === "error") && "text-danger",
                    )}
                  >
                    {job.verify === "running" ? <LoaderCircle className="size-3 animate-spin" /> : <ShieldCheck className="size-3" />}
                    <span className="truncate">{t(`verify.${job.verify}`)}{job.verify_detail ? `: ${job.verify_detail}` : ""}</span>
                  </div>
                )}
              </div>
              <div className="flex shrink-0 gap-1">
                {job.status !== "completed" || job.skipped.length ? (
                  <Button size="xs" variant="ghost" onClick={() => jobAction(job, "retry")}>
                    <RotateCcw />
                    {t("job.retry")}
                  </Button>
                ) : null}
                {native && (
                  <Button size="xs" variant="ghost" onClick={() => openPath(job.destination)}>
                    <FolderOpen />
                    {t("job.openDestination")}
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>

        {problems.some((job) => job.skipped.length) && (
          <p className="mt-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-[12.5px] text-warning">{t("done.skippedHint")}</p>
        )}

        <div className="mt-4 flex flex-wrap gap-2">
          <Button disabled={!verifiable.length || verifying} onClick={() => verifyAll()}>
            {verifying ? <LoaderCircle className="animate-spin" /> : <ShieldCheck />}
            {t("done.verify")}
          </Button>
          <Button variant="ghost" onClick={() => clearQueue(["completed", "failed", "canceled"])}>
            <Eraser />
            {t("done.clear")}
          </Button>
          {native && (
            <Button variant="primary" className="ml-auto" onClick={() => closeWindow()}>
              {t("done.close")}
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}
