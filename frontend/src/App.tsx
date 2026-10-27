import { RefreshCw, ServerCrash } from "lucide-react";
import { Tooltip } from "radix-ui";
import { useEffect, useState } from "react";
import { toast, Toaster } from "sonner";
import { Logo } from "./components/Brand";
import { ComposeDialog } from "./components/ComposeDialog";
import { ConflictDialog } from "./components/ConflictDialog";
import { FileBrowser } from "./components/FileBrowser";
import { LoginScreen } from "./components/LoginScreen";
import { CopierView } from "./components/CopierView";
import { SettingsDialog } from "./components/SettingsDialog";
import { ShutdownDialog } from "./components/ShutdownDialog";
import { Button } from "./components/ui/button";
import { Spinner } from "./components/ui/misc";
import { api, onUnauthorized } from "./lib/api";
import { connectEvents } from "./lib/events";
import { useLang, useT } from "./lib/i18n";
import { waitForNative } from "./lib/native";
import { useStore } from "./lib/store";

function useBootstrap() {
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let dispose: (() => void) | undefined;
    let cancelled = false;
    const store = useStore.getState();
    const unauthorized = () => useStore.getState().setBoot({ authenticated: false, booted: true });
    onUnauthorized(unauthorized);

    (async () => {
      try {
        const status = await api.authStatus();
        store.setBoot({ authRequired: status.required, authenticated: status.authenticated });
        if (!status.authenticated) return;
        const [system, settings, jobs] = await Promise.all([api.system(), api.settings(), api.jobs(), waitForNative()]);
        if (cancelled) return;
        store.setData({ system, settings });
        store.applySnapshot(jobs.jobs, jobs.queue);
        dispose = connectEvents(unauthorized);
        setFailed(false);
      } catch {
        if (!cancelled) setFailed(true);
      } finally {
        if (!cancelled) useStore.getState().setBoot({ booted: true });
      }
    })();

    return () => {
      cancelled = true;
      dispose?.();
    };
  }, [attempt]);

  return { failed, retry: () => setAttempt((n) => n + 1) };
}

function useTheme() {
  const theme = useStore((s) => s.settings?.theme);
  const lang = useLang();
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  useEffect(() => {
    if (!theme) return;
    try {
      localStorage.setItem("rgcopy-theme", theme);
    } catch {
      // storage may be unavailable
    }
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => document.documentElement.classList.toggle("dark", theme === "dark" || (theme === "system" && media.matches));
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);
  return theme ?? "light";
}

function useDropGuard() {
  const t = useT();
  useEffect(() => {
    // Browsers cannot reveal the real path of dropped files; keep them from navigating away
    const over = (event: DragEvent) => event.preventDefault();
    const drop = (event: DragEvent) => {
      event.preventDefault();
      if (event.dataTransfer?.files.length) toast(t("toast.dropHint"));
    };
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, [t]);
}

function Splash() {
  return (
    <div className="grid h-full place-items-center bg-bg">
      <div className="flex flex-col items-center gap-5">
        <Logo size="lg" />
        <Spinner className="text-subtle" />
      </div>
    </div>
  );
}

function ServerDown({ retry }: { retry: () => void }) {
  const t = useT();
  return (
    <div className="grid h-full place-items-center bg-bg p-6">
      <div className="max-w-sm text-center">
        <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-danger/10 text-danger">
          <ServerCrash className="size-6" />
        </div>
        <h1 className="mt-5 text-lg font-semibold text-fg">{t("conn.error")}</h1>
        <p className="mt-2 text-sm text-muted">{t("conn.errorHint")}</p>
        <Button className="mt-6" onClick={retry}>
          <RefreshCw />
          {t("conn.retry")}
        </Button>
      </div>
    </div>
  );
}

export default function App() {
  const { failed, retry } = useBootstrap();
  const theme = useTheme();
  useDropGuard();
  const booted = useStore((s) => s.booted);
  const authRequired = useStore((s) => s.authRequired);
  const authenticated = useStore((s) => s.authenticated);

  let content;
  if (!booted) content = <Splash />;
  else if (authRequired && !authenticated) content = <LoginScreen />;
  else if (failed) content = <ServerDown retry={retry} />;
  else
    content = (
      <>
        <CopierView />
        <ComposeDialog />
        <SettingsDialog />
        <ConflictDialog />
        <ShutdownDialog />
        <FileBrowser />
      </>
    );

  return (
    <Tooltip.Provider delayDuration={350} skipDelayDuration={150}>
      {content}
      <Toaster theme={theme} position="bottom-right" closeButton richColors offset={20} toastOptions={{ className: "font-sans" }} />
    </Tooltip.Provider>
  );
}
