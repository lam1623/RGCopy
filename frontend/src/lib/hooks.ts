import { useSyncExternalStore } from "react";

/** Live result of a CSS media query. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const media = window.matchMedia(query);
      media.addEventListener("change", onChange);
      return () => media.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

function subscribeResize(onChange: () => void) {
  window.addEventListener("resize", onChange);
  return () => window.removeEventListener("resize", onChange);
}

/** Live inner width or height of the window. */
export function useWindowSize(axis: "width" | "height"): number {
  return useSyncExternalStore(
    subscribeResize,
    () => (axis === "width" ? window.innerWidth : window.innerHeight),
    () => (axis === "width" ? 1280 : 800),
  );
}
