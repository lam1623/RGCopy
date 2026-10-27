import type { ReactNode } from "react";
import { saveSettings } from "@/lib/actions";
import { useT } from "@/lib/i18n";
import { useStore } from "@/lib/store";
import type { Conflict, Settings, WhenDone } from "@/lib/types";
import { Input, Segmented, Select, Switch } from "./ui/controls";
import { Row, SectionTitle } from "./ui/misc";
import { Modal } from "./ui/overlay";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <SectionTitle>{title}</SectionTitle>
      <div className="divide-y divide-border rounded-xl border border-border bg-surface px-4 shadow-card">{children}</div>
    </section>
  );
}

function Toggle({ field, title, description }: { field: keyof Settings; title: string; description?: string }) {
  const value = useStore((s) => s.settings?.[field]);
  return (
    <Row
      title={title}
      description={description}
      control={<Switch checked={!!value} onCheckedChange={(checked) => saveSettings({ [field]: checked })} />}
    />
  );
}

export function SettingsDialog() {
  const t = useT();
  const settings = useStore((s) => s.settings);
  const system = useStore((s) => s.system);
  const open = useStore((s) => s.settingsOpen);
  const setOpen = useStore((s) => s.setSettingsOpen);
  if (!settings) return null;

  const conflicts: { value: Conflict; label: string }[] = [
    { value: "ask", label: t("conflict.ask") },
    { value: "overwrite", label: t("conflict.overwrite") },
    { value: "skip", label: t("conflict.skip") },
    { value: "update", label: t("conflict.update") },
    { value: "backup", label: t("conflict.backup") },
  ];

  return (
    <Modal
      open={open}
      onOpenChange={setOpen}
      title={t("settings.title")}
      description={t("settings.subtitle")}
      className="w-[min(720px,calc(100vw-24px))]"
    >
      <div className="space-y-6 px-5 py-5">
        <Section title={t("settings.transfers")}>
          <Row
            title={t("settings.concurrency")}
            description={t("settings.concurrency.hint")}
            control={
              <Segmented
                value={String(settings.concurrency)}
                onValueChange={(value) => saveSettings({ concurrency: Number(value) })}
                options={["1", "2", "3", "4"].map((value) => ({ value, label: value }))}
              />
            }
          />
          <Toggle field="auto_start" title={t("settings.autoStart")} description={t("settings.autoStart.hint")} />
          <Row
            title={t("settings.conflict")}
            description={t("settings.conflict.hint")}
            control={
              <Select<Conflict>
                className="w-44"
                value={settings.conflict}
                onValueChange={(conflict) => saveSettings({ conflict })}
                options={conflicts}
              />
            }
          />
          <Toggle field="checksum" title={t("settings.checksum")} description={t("settings.checksum.hint")} />
          <Toggle field="preserve" title={t("settings.preserve")} description={t("settings.preserve.hint")} />
          <Row
            title={t("settings.bwlimit")}
            description={t("settings.bwlimit.hint")}
            control={
              <div className="flex items-center gap-2">
                <Input
                  key={settings.bwlimit}
                  type="number"
                  min={0}
                  step={1024}
                  defaultValue={settings.bwlimit}
                  onBlur={(event) => {
                    const value = Math.max(0, Math.round(Number(event.target.value) || 0));
                    if (value !== settings.bwlimit) void saveSettings({ bwlimit: value });
                  }}
                  className="w-28 text-right tabular"
                  aria-label={t("settings.bwlimit")}
                />
                <span className="text-xs text-muted">KiB/s</span>
              </div>
            }
          />
          <Toggle field="check_space" title={t("settings.checkSpace")} description={t("settings.checkSpace.hint")} />
        </Section>

        <Section title={t("settings.interface")}>
          <Row
            title={t("settings.language")}
            control={
              <Select
                className="w-44"
                value={settings.language}
                onValueChange={(language) => saveSettings({ language })}
                options={[
                  { value: "auto", label: t("lang.auto") },
                  { value: "es", label: "Español" },
                  { value: "en", label: "English" },
                ]}
              />
            }
          />
          <Row
            title={t("settings.theme")}
            control={
              <Segmented
                value={settings.theme}
                onValueChange={(theme) => saveSettings({ theme })}
                options={[
                  { value: "light", label: t("theme.light") },
                  { value: "dark", label: t("theme.dark") },
                  { value: "system", label: t("theme.system") },
                ]}
              />
            }
          />
          <Row
            title={t("settings.notify")}
            description={t("settings.notify.hint")}
            control={
              <Switch
                checked={settings.notify_on_finish}
                onCheckedChange={(checked) => {
                  if (checked && "Notification" in window && Notification.permission === "default") {
                    void Notification.requestPermission();
                  }
                  void saveSettings({ notify_on_finish: checked });
                }}
              />
            }
          />
          {system?.desktop && (
            <Row
              title={t("whenDone.label")}
              description={t("settings.whenDone.hint")}
              control={
                <Select<WhenDone>
                  className="w-44"
                  value={settings.when_done}
                  onValueChange={(when_done) => saveSettings({ when_done })}
                  options={[
                    { value: "nothing", label: t("whenDone.nothing") },
                    { value: "close", label: t("whenDone.close") },
                    { value: "verify", label: t("whenDone.verify") },
                    { value: "shutdown", label: t("whenDone.shutdown") },
                  ]}
                />
              }
            />
          )}
        </Section>

        <Section title={t("settings.about")}>
          <Row title={t("settings.version")} control={<span className="text-sm text-muted tabular">RGCopy {system?.version}</span>} />
          <Row
            title="rsync"
            description={system?.rsync.available ? system.rsync.path : (system?.rsync.error ?? undefined)}
            control={
              <span className={system?.rsync.available ? "text-sm text-muted tabular" : "text-sm font-medium text-danger"}>
                {system?.rsync.available ? system.rsync.version : t("engine.missing")}
              </span>
            }
          />
          <Row
            title={t("settings.integration")}
            description={t("settings.integration.hint")}
            control={<code className="rounded-md bg-elevated px-2 py-1 font-mono text-xs text-fg">rgcopy integrate</code>}
          />
          <Row
            title={t("settings.dataDir")}
            control={<span className="max-w-64 truncate font-mono text-xs text-muted">{system?.data_dir}</span>}
          />
        </Section>
      </div>
    </Modal>
  );
}
