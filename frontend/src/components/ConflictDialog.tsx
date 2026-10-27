import { TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { jobAction, resolveConflict } from "@/lib/actions";
import { basename, formatBytes } from "@/lib/format";
import { useLang, useT } from "@/lib/i18n";
import { useStore } from "@/lib/store";
import type { Resolution } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";
import { Checkbox } from "./ui/controls";
import { Modal } from "./ui/overlay";

/** Asked once per transfer, before it starts: what to do with the files that already exist. */
export function ConflictDialog() {
  const t = useT();
  const lang = useLang();
  // One transfer at a time, in list order
  const jobId = useStore((s) => s.order.find((id) => s.jobs[id]?.status === "conflict" && !s.conflictLater.includes(id)));
  const decideLater = useStore((s) => s.decideLater);
  const job = useStore((s) => (jobId ? s.jobs[jobId] : undefined));
  const [rule, setRule] = useState<Resolution>("update");
  const [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setRule("update");
    setRemember(false);
    setBusy(false);
  }, [job?.id]);

  if (!job) return null;
  const dates = new Intl.DateTimeFormat(lang, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const newer = job.conflicts.filter((c) => c.incoming_mtime > c.existing_mtime + 1).length;
  const same = job.conflicts.filter((c) => c.incoming_size === c.existing_size && Math.abs(c.incoming_mtime - c.existing_mtime) <= 1).length;
  const others = job.total_files - job.conflict_count;
  const choices: { value: Resolution; label: string; hint: string }[] = [
    { value: "overwrite", label: t("conflict.overwrite"), hint: t("conflict.overwrite.hint") },
    { value: "skip", label: t("conflict.skip"), hint: t("conflict.skip.hint") },
    {
      value: "update",
      label: t("conflict.update"),
      hint: newer === 1 ? t("conflict.update.one") : newer ? t("conflict.update.count", { count: newer }) : t("conflict.update.none"),
    },
    { value: "backup", label: t("conflict.backup"), hint: t("conflict.backup.hint") },
  ];

  const submit = async () => {
    setBusy(true);
    await resolveConflict(job, rule, remember);
    setBusy(false);
  };

  return (
    <Modal
      open
      // Closing puts the question off: the transfer waits, and its panel opens it again
      onOpenChange={(open) => !open && decideLater(job.id, true)}
      title={t("conflictDialog.title", { count: job.conflict_count, folder: basename(job.destination) })}
      description={others > 0 ? t("conflictDialog.others", { count: others }) : t("conflictDialog.all")}
      className="w-[min(640px,calc(100vw-24px))]"
      footer={
        <>
          <label className="flex items-center gap-2 text-[12.5px] text-muted">
            <Checkbox checked={remember} onCheckedChange={(value) => setRemember(value === true)} />
            {t("conflictDialog.remember")}
          </label>
          <Button variant="ghost" className="ml-auto" onClick={() => jobAction(job, "cancel")}>
            {t("job.cancel")}
          </Button>
          <Button variant="primary" disabled={busy} onClick={submit}>
            {t("conflictDialog.continue")}
          </Button>
        </>
      }
    >
      <div className="space-y-4 px-5 py-4">
        <div className="overflow-hidden rounded-xl border border-border text-[12.5px]">
          <div className="grid grid-cols-[minmax(0,1fr)_160px_160px] gap-2.5 bg-panel px-3 py-2 font-semibold text-muted">
            <span>{t("conflictDialog.file")}</span>
            <span>{t("conflictDialog.existing", { folder: basename(job.destination) })}</span>
            <span>{t("conflictDialog.incoming")}</span>
          </div>
          <div className="max-h-56 overflow-y-auto">
            {job.conflicts.map((c) => {
              const isNewer = c.incoming_mtime > c.existing_mtime + 1;
              return (
                <div key={c.path} className="grid grid-cols-[minmax(0,1fr)_160px_160px] items-center gap-2.5 border-t border-border px-3 py-2">
                  <span className="truncate font-medium text-fg" title={c.path}>
                    {c.path}
                  </span>
                  <span className="text-muted tabular">
                    {formatBytes(c.existing_size, lang)} · {dates.format(c.existing_mtime * 1000)}
                  </span>
                  <span className={cn("tabular", isNewer ? "font-semibold text-accent" : "text-muted")}>
                    {formatBytes(c.incoming_size, lang)} · {c.incoming_mtime ? dates.format(c.incoming_mtime * 1000) : "—"}
                  </span>
                </div>
              );
            })}
            {job.conflict_count > job.conflicts.length && (
              <p className="border-t border-border px-3 py-2 text-xs text-subtle">
                {t("files.more", { count: job.conflict_count - job.conflicts.length })}
              </p>
            )}
          </div>
        </div>
        {same > 0 && <p className="text-xs text-subtle">{t("conflictDialog.same", { count: same })}</p>}

        <div role="radiogroup" aria-label={t("compose.conflict")} className="grid gap-2 sm:grid-cols-2">
          {choices.map((choice) => (
            <button
              key={choice.value}
              type="button"
              role="radio"
              aria-checked={rule === choice.value}
              onClick={() => setRule(choice.value)}
              className={cn(
                "rounded-xl border-[1.5px] px-3 py-2.5 text-left outline-none transition focus-visible:ring-2 focus-visible:ring-ring",
                rule === choice.value ? "border-accent bg-accent-soft" : "border-border bg-surface hover:border-border-strong",
              )}
            >
              <div className="text-[13px] font-semibold text-fg">{choice.label}</div>
              <div className="mt-0.5 text-[11.5px] leading-snug text-muted">{choice.hint}</div>
            </button>
          ))}
        </div>
        <p className="flex items-center gap-2 text-xs text-subtle">
          <TriangleAlert className="size-3.5 shrink-0" />
          {t("conflictDialog.once")}
        </p>
      </div>
    </Modal>
  );
}
