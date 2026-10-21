// Bridge to the pywebview window used by the desktop launcher

export interface NativeApi {
  pick_files(): Promise<string[]>;
  pick_folder(): Promise<string | null>;
  open_path(path: string): Promise<boolean>;
  set_title(title: string): Promise<void>;
  close(): Promise<void>;
}

declare global {
  interface Window {
    pywebview?: { api: NativeApi };
  }
}

let cached: NativeApi | null = null;

export function nativeApi(): NativeApi | null {
  if (cached) return cached;
  const api = window.pywebview?.api;
  if (api && typeof api.pick_files === "function") cached = api;
  return cached;
}

/** Resolve once pywebview has injected its API, or null in a regular browser. */
export function waitForNative(timeout = 1200): Promise<NativeApi | null> {
  const ready = nativeApi();
  if (ready) return Promise.resolve(ready);
  return new Promise((resolve) => {
    const done = () => resolve(nativeApi());
    window.addEventListener("pywebviewready", done, { once: true });
    setTimeout(done, timeout);
  });
}
