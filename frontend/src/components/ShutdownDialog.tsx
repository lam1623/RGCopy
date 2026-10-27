import { Power } from "lucide-react";
import { useEffect } from "react";
import { poweroff } from "@/lib/actions";
import { useT } from "@/lib/i18n";
import { useStore } from "@/lib/store";
import { Button } from "./ui/button";
import { Modal } from "./ui/overlay";

/** "Shut down when done": a countdown that can always be stopped. */
export function ShutdownDialog() {
  const t = useT();
  const seconds = useStore((s) => s.shutdownIn);
  const setSeconds = useStore((s) => s.setShutdownIn);

  useEffect(() => {
    if (seconds == null) return;
    if (seconds <= 0) {
      setSeconds(null);
      void poweroff();
      return;
    }
    const timer = setTimeout(() => setSeconds(seconds - 1), 1000);
    return () => clearTimeout(timer);
  }, [seconds, setSeconds]);

  if (seconds == null) return null;
  return (
    <Modal
      open
      onOpenChange={(open) => !open && setSeconds(null)}
      title={t("shutdown.title")}
      description={t("shutdown.body", { seconds })}
      className="w-[min(440px,calc(100vw-24px))]"
      footer={
        <>
          <Button variant="ghost" className="ml-auto" onClick={() => setSeconds(0)}>
            <Power />
            {t("shutdown.now")}
          </Button>
          <Button variant="primary" autoFocus onClick={() => setSeconds(null)}>
            {t("shutdown.cancel")}
          </Button>
        </>
      }
    >
      <div className="grid place-items-center px-5 py-6">
        <div className="text-6xl font-extrabold text-brand tabular">{seconds}</div>
      </div>
    </Modal>
  );
}
