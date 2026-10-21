import { ArrowUp, ChevronRight, File, Folder, FolderPlus, HardDrive, House, Link2 } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { errorText } from "@/lib/actions";
import { api } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { useLang, useT } from "@/lib/i18n";
import { useStore } from "@/lib/store";
import type { FsEntry, FsListing } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";
import { Checkbox, Input, Switch } from "./ui/controls";
import { Spinner } from "./ui/misc";
import { Modal } from "./ui/overlay";

const LAST_DIR_KEY = "rgcopy-last-dir";

function readLastDir(): string | null {
  try {
    return localStorage.getItem(LAST_DIR_KEY);
  } catch {
    return null;
  }
}

function crumbs(listing: FsListing): { label: string; path: string }[] {
  const root = listing.root;
  const rest = listing.path.slice(root.length).split("/").filter(Boolean);
  const items = [{ label: root, path: root }];
  let current = root;
  for (const part of rest) {
    current = current.endsWith("/") ? current + part : `${current}/${part}`;
    items.push({ label: part, path: current });
  }
  return items;
}

function NewFolder({ parent, onCreated }: { parent: string; onCreated: (entry: FsEntry) => void }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      onCreated(await api.mkdir(parent, name.trim()));
      setOpen(false);
      setName("");
      setError(null);
    } catch (err) {
      setError(errorText(err));
    }
  };

  if (!open)
    return (
      <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
        <FolderPlus />
        {t("fb.newFolder")}
      </Button>
    );
  return (
    <form onSubmit={submit} className="flex items-center gap-2">
      <Input
        autoFocus
        value={name}
        onChange={(event) => {
          setName(event.target.value);
          setError(null);
        }}
        onKeyDown={(event) => event.key === "Escape" && (event.stopPropagation(), setOpen(false))}
        placeholder={t("fb.newFolderName")}
        aria-invalid={!!error}
        title={error ?? undefined}
        className={cn("h-8 w-48", error && "border-danger")}
      />
      <Button type="submit" size="sm" disabled={!name.trim()}>
        {t("fb.create")}
      </Button>
    </form>
  );
}

export function FileBrowser() {
  const t = useT();
  const lang = useLang();
  const request = useStore((s) => s.browser);
  const openBrowser = useStore((s) => s.openBrowser);
  const system = useStore((s) => s.system);
  const mode = request?.mode ?? "sources";

  const [path, setPath] = useState<string | null>(null);
  const [listing, setListing] = useState<FsListing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [hidden, setHidden] = useState(false);
  const fallback = system?.roots[0]?.path ?? null;

  useEffect(() => {
    if (!request) return;
    setSelected([]);
    setError(null);
    setPath(request.start ?? readLastDir() ?? fallback);
  }, [request, fallback]);

  const load = useCallback(
    async (target: string) => {
      setLoading(true);
      try {
        const result = await api.list(target, hidden);
        setListing(result);
        setError(null);
        try {
          localStorage.setItem(LAST_DIR_KEY, result.path);
        } catch {
          // storage may be unavailable
        }
      } catch (err) {
        setError(errorText(err));
        // A stale remembered folder should not trap the user: fall back to the first root
        if (fallback && target !== fallback) setPath(fallback);
      } finally {
        setLoading(false);
      }
    },
    [hidden, fallback],
  );

  useEffect(() => {
    if (request && path) void load(path);
  }, [request, path, load]);

  const entries = useMemo(() => {
    const all = listing?.entries ?? [];
    return mode === "folder" ? all.filter((e) => e.kind === "dir") : all;
  }, [listing, mode]);

  const close = (paths: string[]) => {
    request?.resolve(paths);
    openBrowser(null);
  };

  const toggle = (entry: FsEntry) =>
    setSelected((current) => (current.includes(entry.path) ? current.filter((p) => p !== entry.path) : [...current, entry.path]));

  const onEntry = (entry: FsEntry) => {
    if (entry.kind === "dir") {
      setPath(entry.path);
      setSelected([]);
    } else if (mode === "sources") toggle(entry);
  };

  const allChecked = entries.length > 0 && entries.every((e) => selected.includes(e.path));
  const someChecked = selected.length > 0 && !allChecked;
  const dateFormat = new Intl.DateTimeFormat(lang, { dateStyle: "medium" });
  const roots = system?.roots ?? [];

  return (
    <Modal
      open={!!request}
      onOpenChange={(open) => !open && close([])}
      title={mode === "folder" ? t("fb.chooseFolder") : t("fb.chooseSources")}
      description={mode === "sources" ? t("fb.sourcesHint") : undefined}
      // Fixed height: moving between folders must not resize the dialog
      className="h-[min(86vh,680px)] w-[min(820px,calc(100vw-32px))]"
      footer={
        <>
          <label className="flex items-center gap-2 text-xs text-muted">
            <Switch checked={hidden} onCheckedChange={setHidden} />
            {t("fb.showHidden")}
          </label>
          <span className="ml-auto text-xs text-muted tabular">
            {mode === "sources" && selected.length > 0 && t("fb.selected", { count: selected.length })}
          </span>
          <Button variant="ghost" onClick={() => close([])}>
            {t("common.cancel")}
          </Button>
          {mode === "folder" ? (
            <Button variant="primary" disabled={!listing} onClick={() => listing && close([listing.path])}>
              {t("fb.useFolder")}
            </Button>
          ) : (
            <Button variant="primary" disabled={!selected.length} onClick={() => close(selected)}>
              {t("fb.add", { count: selected.length || "" })}
            </Button>
          )}
        </>
      }
    >
      <div className="sticky top-0 z-10 bg-panel">
        <div className="flex flex-wrap items-center gap-1.5 border-b border-border px-4 py-2.5">
          {roots.map((root) => (
            <Button
              key={root.path}
              variant="ghost"
              size="sm"
              onClick={() => setPath(root.path)}
              className={cn(listing?.path === root.path && "bg-elevated text-fg")}
            >
              {root.path === system?.home ? <House /> : <HardDrive />}
              {root.name === "Home" ? t("fb.home") : root.name}
            </Button>
          ))}
          <span className="mx-1 h-5 w-px bg-border" />
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("fb.up")}
            title={t("fb.up")}
            disabled={!listing?.parent}
            onClick={() => listing?.parent && setPath(listing.parent)}
          >
            <ArrowUp />
          </Button>
          <div className="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto text-[13px]">
            {listing &&
              crumbs(listing).map((crumb, index, all) => (
                <span key={crumb.path} className="flex shrink-0 items-center gap-0.5">
                  {index > 0 && <ChevronRight className="size-3.5 text-subtle" />}
                  <button
                    onClick={() => setPath(crumb.path)}
                    className={cn(
                      "rounded-md px-1.5 py-1 outline-none transition hover:bg-elevated focus-visible:ring-2 focus-visible:ring-ring",
                      index === all.length - 1 ? "font-medium text-fg" : "text-muted",
                    )}
                  >
                    {crumb.label}
                  </button>
                </span>
              ))}
          </div>
          {loading && <Spinner className="text-subtle" />}
          {mode === "folder" && listing && (
            <NewFolder
              parent={listing.path}
              onCreated={(entry) => {
                setPath(entry.path);
              }}
            />
          )}
        </div>

        {mode === "sources" && entries.length > 0 && (
          <div className="flex items-center gap-3 border-b border-border px-5 py-2 text-xs text-muted">
            <Checkbox
              aria-label={t("fb.selectAll")}
              checked={allChecked ? true : someChecked ? "indeterminate" : false}
              onCheckedChange={() => setSelected(allChecked ? [] : entries.map((e) => e.path))}
            />
            {t("fb.selectAll")}
          </div>
        )}
      </div>

      <div className="min-h-[320px] px-2 py-2">
        {error && <p className="px-3 py-10 text-center text-sm text-danger">{error}</p>}
        {!error && listing && !entries.length && <p className="px-3 py-16 text-center text-sm text-muted">{t("fb.empty")}</p>}
        {!error &&
          entries.map((entry) => {
            const checked = selected.includes(entry.path);
            return (
              <div
                key={entry.path}
                role="button"
                tabIndex={0}
                onClick={() => onEntry(entry)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") onEntry(entry);
                  if (event.key === " " && mode === "sources") {
                    event.preventDefault();
                    toggle(entry);
                  }
                }}
                className={cn(
                  "grid grid-cols-[1.25rem_1.25rem_1fr_auto_auto] items-center gap-3 rounded-lg px-3 py-2 text-[13px] outline-none transition focus-visible:ring-2 focus-visible:ring-ring",
                  checked ? "bg-accent-soft" : "hover:bg-elevated/70",
                )}
              >
                <span className="grid place-items-center">
                  {mode === "sources" && (
                    <Checkbox
                      checked={checked}
                      tabIndex={-1}
                      aria-label={entry.name}
                      onClick={(event) => event.stopPropagation()}
                      onCheckedChange={() => toggle(entry)}
                    />
                  )}
                </span>
                {entry.kind === "dir" ? (
                  <Folder className="size-4 fill-accent/20 text-accent" />
                ) : entry.link ? (
                  <Link2 className="size-4 text-subtle" />
                ) : (
                  <File className="size-4 text-subtle" />
                )}
                <span className={cn("truncate text-fg", entry.kind === "dir" && "font-medium")}>{entry.name}</span>
                <span className="w-20 text-right text-xs text-muted tabular">
                  {entry.size != null ? formatBytes(entry.size, lang) : ""}
                </span>
                <span className="hidden w-28 text-right text-xs text-subtle sm:block">
                  {entry.modified ? dateFormat.format(entry.modified * 1000) : ""}
                </span>
              </div>
            );
          })}
        {listing?.truncated && (
          <p className="px-3 py-3 text-center text-xs text-subtle">{t("fb.truncated", { count: listing.entries.length })}</p>
        )}
      </div>
    </Modal>
  );
}
