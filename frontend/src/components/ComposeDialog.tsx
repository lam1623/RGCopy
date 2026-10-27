import { ArrowRight, Copy, File, FilePlus2, Folder, FolderInput, FolderPlus, MoveRight, X } from "lucide-react";
import { useEffect, useState } from "react";
import { browse, pickFiles, pickFolder, submitTransfer } from "@/lib/actions";
import { basename, prettyPath } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { nativeApi } from "@/lib/native";
import { useStore } from "@/lib/store";
import type { Conflict, Mode } from "@/lib/types";
import { Button } from "./ui/button";
import { Input, Segmented, Select, Switch } from "./ui/controls";
import { Field, Row, Spinner } from "./ui/misc";
import { Modal } from "./ui/overlay";

function parentOf(path: string): string {
  const index = path.replace(/\/+$/, "").lastIndexOf("/");
  return index <= 0 ? "/" : path.slice(0, index);
}

export function ComposeDialog() {
  const t = useT();
  const draft = useStore((s) => s.draft);
  const setDraft = useStore((s) => s.setDraft);
  const patchDraft = useStore((s) => s.patchDraft);
  const settings = useStore((s) => s.settings);
  const home = useStore((s) => s.system?.home);

  const [conflict, setConflict] = useState<Conflict>("ask");
  const [checksum, setChecksum] = useState(false);
  const [preserve, setPreserve] = useState(true);
  const [bwlimit, setBwlimit] = useState(0);
  const [busy, setBusy] = useState(false);
  const open = !!draft;

  // Every new transfer starts from the defaults in Settings
  useEffect(() => {
    if (!open || !settings) return;
    setConflict(settings.conflict);
    setChecksum(settings.checksum);
    setPreserve(settings.preserve);
    setBwlimit(settings.bwlimit);
    setBusy(false);
  }, [open, settings]);

  if (!draft) return null;
  const sources = draft.sources;

  const addSources = (paths: string[]) => patchDraft({ sources: [...new Set([...sources, ...paths])] });
  // Folders cannot be picked together with files in the native dialog: the built-in browser can
  const addFolder = async () => {
    if (nativeApi()) {
      const folder = await pickFolder();
      if (folder) addSources([folder]);
    } else addSources(await browse("sources", sources[0] ? parentOf(sources[0]) : undefined));
  };
  const chooseDestination = async () => {
    const folder = await pickFolder(draft.destination ?? undefined);
    if (folder) patchDraft({ destination: folder });
  };

  const submit = async () => {
    if (!draft.destination || !sources.length) return;
    setBusy(true);
    const ok = await submitTransfer(sources, draft.destination, { mode: draft.mode, conflict, checksum, preserve, bwlimit });
    setBusy(false);
    if (ok) setDraft(null);
  };

  const conflicts: { value: Conflict; label: string; hint: string }[] = [
    { value: "ask", label: t("conflict.ask"), hint: t("conflict.ask.hint") },
    { value: "overwrite", label: t("conflict.overwrite"), hint: t("conflict.overwrite.hint") },
    { value: "skip", label: t("conflict.skip"), hint: t("conflict.skip.hint") },
    { value: "update", label: t("conflict.update"), hint: t("conflict.update.hint") },
    { value: "backup", label: t("conflict.backup"), hint: t("conflict.backup.hint") },
  ];
  const count = sources.length;
  const verb = draft.mode === "move" ? t("compose.submitMove", { count }) : t("compose.submitCopy", { count });

  return (
    <Modal
      open={open}
      onOpenChange={(next) => !next && setDraft(null)}
      title={t("compose.title")}
      description={t("compose.description")}
      className="w-[min(680px,calc(100vw-32px))]"
      footer={
        <>
          <span className="truncate text-xs text-muted">
            {draft.destination && count > 0 && (
              <>
                {count === 1 ? basename(sources[0]) : t("job.items", { count })}
                <ArrowRight className="mx-1 inline size-3" />
                {prettyPath(draft.destination, home)}
              </>
            )}
          </span>
          <Button variant="ghost" className="ml-auto" onClick={() => setDraft(null)}>
            {t("common.cancel")}
          </Button>
          <Button variant="primary" disabled={busy || !count || !draft.destination} onClick={submit}>
            {busy ? <Spinner /> : draft.mode === "move" ? <MoveRight /> : <Copy />}
            {verb}
          </Button>
        </>
      }
    >
      <div className="space-y-6 px-5 py-5">
        <Field
          label={t("compose.sources")}
          aside={
            <span className="flex gap-1">
              <Button size="xs" variant="ghost" onClick={async () => addSources(await pickFiles())}>
                <FilePlus2 />
                {t("compose.addFiles")}
              </Button>
              <Button size="xs" variant="ghost" onClick={addFolder}>
                <FolderPlus />
                {nativeApi() ? t("compose.addFolder") : t("compose.browse")}
              </Button>
            </span>
          }
        >
          <div className="max-h-48 overflow-y-auto rounded-xl border border-border bg-surface">
            {!count && <p className="px-4 py-6 text-center text-[13px] text-subtle">{t("compose.noSources")}</p>}
            {sources.map((path) => (
              <div key={path} className="group flex items-center gap-3 border-b border-border px-3 py-2 last:border-b-0">
                {/\.[^/]{1,8}$/.test(path) ? (
                  <File className="size-4 shrink-0 text-subtle" />
                ) : (
                  <Folder className="size-4 shrink-0 fill-accent/20 text-accent" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-medium text-fg">{basename(path)}</div>
                  <div className="truncate text-xs text-subtle">{prettyPath(parentOf(path), home)}</div>
                </div>
                <button
                  aria-label={t("compose.remove")}
                  title={t("compose.remove")}
                  onClick={() => patchDraft({ sources: sources.filter((p) => p !== path) })}
                  className="grid size-6 place-items-center rounded-md text-subtle opacity-0 outline-none transition hover:bg-elevated hover:text-fg focus-visible:opacity-100 group-hover:opacity-100"
                >
                  <X className="size-3.5" />
                </button>
              </div>
            ))}
          </div>
        </Field>

        <Field label={t("compose.destination")}>
          <button
            onClick={chooseDestination}
            className="flex h-11 w-full items-center gap-3 rounded-xl border border-border bg-surface px-3 text-left text-sm shadow-card outline-none transition hover:border-border-strong focus-visible:ring-2 focus-visible:ring-ring"
          >
            <FolderInput className="size-4 shrink-0 text-accent" />
            <span className={draft.destination ? "truncate text-fg" : "truncate text-subtle"}>
              {draft.destination ? prettyPath(draft.destination, home) : t("compose.chooseDestination")}
            </span>
            <span className="ml-auto text-xs font-medium text-accent">{t("common.change")}</span>
          </button>
        </Field>

        <div className="grid gap-5 sm:grid-cols-2">
          <Field label={t("compose.mode")}>
            <Segmented<Mode>
              className="w-full"
              value={draft.mode}
              onValueChange={(mode) => patchDraft({ mode })}
              options={[
                { value: "copy", label: (<><Copy />{t("mode.copy")}</>) },
                { value: "move", label: (<><MoveRight />{t("mode.move")}</>) },
              ]}
            />
          </Field>
          <Field label={t("compose.conflict")} hint={conflicts.find((c) => c.value === conflict)?.hint}>
            <Select<Conflict> value={conflict} onValueChange={setConflict} options={conflicts.map(({ value, label }) => ({ value, label }))} />
          </Field>
        </div>

        <details className="group rounded-xl border border-border bg-surface/60 px-4 [&_summary::-webkit-details-marker]:hidden">
          <summary className="cursor-pointer select-none py-3 text-[13px] font-medium text-muted outline-none transition hover:text-fg">
            {t("compose.advanced")}
          </summary>
          <div className="divide-y divide-border border-t border-border">
            <Row
              title={t("settings.checksum")}
              description={t("settings.checksum.hint")}
              control={<Switch checked={checksum} onCheckedChange={setChecksum} />}
            />
            <Row
              title={t("settings.preserve")}
              description={t("settings.preserve.hint")}
              control={<Switch checked={preserve} onCheckedChange={setPreserve} />}
            />
            <Row
              title={t("settings.bwlimit")}
              description={t("settings.bwlimit.hint")}
              control={
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    min={0}
                    step={1024}
                    value={bwlimit}
                    onChange={(event) => setBwlimit(Math.max(0, Number(event.target.value) || 0))}
                    className="w-28 text-right tabular"
                    aria-label={t("settings.bwlimit")}
                  />
                  <span className="text-xs text-muted">KiB/s</span>
                </div>
              }
            />
          </div>
        </details>
      </div>
    </Modal>
  );
}
