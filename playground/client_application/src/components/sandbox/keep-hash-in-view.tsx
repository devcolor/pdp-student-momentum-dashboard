"use client";

import { useEffect } from "react";

// Long enough for a page's charts to load; after that the layout has settled.
const SETTLE_MS = 6000;
const CHECK_EVERY_MS = 200;
const USER_SCROLL_EVENTS = ["wheel", "touchstart", "keydown", "pointerdown"] as const;

/**
 * Keeps the element named in the URL's #hash at the top while the page's charts load. The browser jumps to it on
 * load, but charts above it then grow from their skeletons and push it down. Stops once the reader scrolls.
 */
export function KeepHashInView() {
  useEffect(() => {
    const id = decodeURIComponent(window.location.hash.slice(1));
    const target = id ? document.getElementById(id) : null;
    if (!target) return;

    // Scrolling to where it already is does nothing, so repeating this is safe until the layout settles.
    const scrollToTarget = () => target.scrollIntoView({ block: "start" });
    scrollToTarget();
    const check = window.setInterval(scrollToTarget, CHECK_EVERY_MS);

    const stop = () => {
      window.clearInterval(check);
      window.clearTimeout(timer);
      for (const name of USER_SCROLL_EVENTS) window.removeEventListener(name, stop);
    };
    const timer = window.setTimeout(stop, SETTLE_MS);
    for (const name of USER_SCROLL_EVENTS) window.addEventListener(name, stop, { once: true });

    return stop;
  }, []);

  return null;
}
