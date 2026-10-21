import type { Lang } from "./i18n";

export function formatBytes(bytes: number | null | undefined, lang: Lang): string {
  if (bytes == null || bytes < 0) return "—";
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  const exponent = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const value = bytes / 1024 ** exponent;
  const digits = exponent >= 1 && value < 100 ? 1 : 0;
  return `${value.toLocaleString(lang, { maximumFractionDigits: digits })} ${units[exponent]}`;
}

export function formatSpeed(bytesPerSecond: number | null | undefined, lang: Lang): string {
  if (!bytesPerSecond) return "—";
  return `${formatBytes(bytesPerSecond, lang)}/s`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(h ? 2 : 1, "0");
  return h ? `${h}:${mm}:${String(s).padStart(2, "0")}` : `${mm}:${String(s).padStart(2, "0")}`;
}

/** Human "remaining" time: 45 s, 12 min, 1 h 20 min */
export function formatRelative(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total} s`;
  const minutes = Math.round(total / 60);
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

export function formatNumber(value: number, lang: Lang): string {
  return value.toLocaleString(lang);
}

export function basename(path: string): string {
  const trimmed = path.replace(/\/+$/, "");
  return trimmed.slice(trimmed.lastIndexOf("/") + 1) || "/";
}

/** "/home/ana/Fotos" → "~/Fotos" */
export function prettyPath(path: string, home: string | undefined): string {
  if (home && (path === home || path.startsWith(`${home}/`))) return `~${path.slice(home.length)}`;
  return path;
}
