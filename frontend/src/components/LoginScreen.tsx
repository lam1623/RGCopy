import { KeyRound } from "lucide-react";
import { type FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { Logo } from "./Brand";
import { Button } from "./ui/button";
import { Input } from "./ui/controls";
import { Spinner } from "./ui/misc";

export function LoginScreen() {
  const t = useT();
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(() => new URLSearchParams(window.location.search).get("auth") === "failed");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!token.trim()) return;
    setBusy(true);
    try {
      await api.login(token.trim());
      window.location.replace("/");
    } catch {
      setFailed(true);
      setBusy(false);
    }
  };

  return (
    <div className="relative grid h-full place-items-center overflow-hidden bg-bg p-6">
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-1/3 h-[28rem] w-[44rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-brand opacity-[0.12] blur-3xl dark:opacity-[0.06]"
      />
      <form
        onSubmit={submit}
        className="relative w-full max-w-sm rounded-2xl border border-border bg-surface p-7 shadow-2xl"
      >
        <Logo size="lg" className="mx-auto" />
        <h1 className="mt-5 text-center text-xl font-semibold tracking-tight text-fg">{t("login.title")}</h1>
        <p className="mt-2 text-center text-[13px] leading-relaxed text-muted">{t("login.body")}</p>
        <div className="relative mt-6">
          <KeyRound className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-subtle" />
          <Input
            autoFocus
            type="password"
            autoComplete="current-password"
            aria-label={t("login.token")}
            placeholder={t("login.token")}
            value={token}
            onChange={(event) => {
              setToken(event.target.value);
              setFailed(false);
            }}
            className="h-10 pl-9"
          />
        </div>
        {failed && <p className="mt-2 text-xs font-medium text-danger">{t("login.failed")}</p>}
        <Button type="submit" variant="primary" size="lg" className="mt-4 w-full" disabled={busy || !token.trim()}>
          {busy && <Spinner />}
          {t("login.submit")}
        </Button>
      </form>
    </div>
  );
}
