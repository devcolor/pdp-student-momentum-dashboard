"use client";

import { useSyncExternalStore } from "react";

import {
  CHART_PALETTE_STORAGE_KEY,
  DEFAULT_CHART_PALETTE,
  DEFAULT_PALETTE,
  PALETTE_STORAGE_KEY,
  toChartPaletteId,
  toPaletteId,
} from "@/lib/theme";

type HtmlPreference<Value extends string> = {
  /** The data attribute on <html> that globals.css reads, in dataset form. */
  datasetKey: "palette" | "chartPalette";
  storageKey: string;
  parse: (value: string | undefined) => Value;
  fallback: Value;
};

/** Builds a hook for a saved choice that lives on <html> as a data attribute. */
function createHtmlPreferenceHook<Value extends string>({ datasetKey, storageKey, parse, fallback }: HtmlPreference<Value>) {
  const changedEvent = `${storageKey}-changed`;

  /** Calls back whenever this choice changes. */
  function subscribe(onChange: () => void) {
    window.addEventListener(changedEvent, onChange);
    return () => window.removeEventListener(changedEvent, onChange);
  }

  /** The value currently applied to <html>. */
  function read(): Value {
    return parse(document.documentElement.dataset[datasetKey]);
  }

  /** Applies a value to the page and remembers it for the next visit. */
  function apply(value: Value) {
    document.documentElement.dataset[datasetKey] = value;
    try {
      localStorage.setItem(storageKey, value);
    } catch {
      // Storage can be blocked; the choice still applies until the page reloads.
    }
    window.dispatchEvent(new Event(changedEvent));
  }

  /** The current value and a function to change it. */
  return function useHtmlPreference() {
    const value = useSyncExternalStore(subscribe, read, () => fallback);
    return [value, apply] as const;
  };
}

/** The active UI theme and a function to change it. */
export const usePalette = createHtmlPreferenceHook({
  datasetKey: "palette",
  storageKey: PALETTE_STORAGE_KEY,
  parse: toPaletteId,
  fallback: DEFAULT_PALETTE,
});

/** The active chart colors and a function to change them. */
export const useChartPalette = createHtmlPreferenceHook({
  datasetKey: "chartPalette",
  storageKey: CHART_PALETTE_STORAGE_KEY,
  parse: toChartPaletteId,
  fallback: DEFAULT_CHART_PALETTE,
});
