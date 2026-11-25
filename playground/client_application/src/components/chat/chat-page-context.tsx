"use client";

import { useContext, useEffect, useMemo } from "react";

import { ChatSessionContext } from "@/hooks/use-chat-session";
import type { Schemas } from "@/lib/api/types";
import type { DataChatPageContext } from "@/services/data-chat";

type QuerySpec = Schemas["QuerySpec"];

// The server's caps on a page context (chat/schemas.py: MAX_PAGE_FILTERS, PageText, MAX_PAGE_SPECS, MAX_PAGE_SPECS_CHARS).
const MAX_FILTERS = 12;
const MAX_TEXT_CHARS = 120;
const MAX_SPECS = 16;
const MAX_SPECS_CHARS = 4000;

/**
 * Tells the shell's chat which page the user is on: its title, filter chips and the specs behind its numbers.
 * Put it inside the page's main chart, so it registers only once that chart has loaded. Renders nothing, and
 * does nothing outside the app shell's chat session (as in stories).
 */
export function ChatPageContext({ page }: { page: DataChatPageContext }) {
  const setPageContext = useContext(ChatSessionContext)?.setPageContext;
  // Compared as JSON, so a re-render with an equal page doesn't register it again.
  const pageJson = JSON.stringify(withinCaps(page));

  const clipped = useMemo<DataChatPageContext | null>(() => {
    const parsed = JSON.parse(pageJson) as DataChatPageContext;
    // The server refuses a blank title, so a page without one sends no context.
    return parsed.title ? parsed : null;
  }, [pageJson]);

  useEffect(() => {
    if (!setPageContext || !clipped) return;
    setPageContext(clipped);
    return () => setPageContext(null);
  }, [setPageContext, clipped]);

  return null;
}

/**
 * The page cut to the server's caps: 12 filters, each and the title at most 120 characters, no blanks. Specs over
 * the server's caps are dropped whole, since half of a page's specs would mislead: the question goes without them.
 */
export function withinCaps(page: DataChatPageContext): DataChatPageContext {
  const filters = (page.filters ?? [])
    .map(clipText)
    .filter((filter) => filter !== "")
    .slice(0, MAX_FILTERS);
  const specs = page.specs ?? [];
  const specsFit = specs.length <= MAX_SPECS && specsChars(specs) <= MAX_SPECS_CHARS;
  return { title: clipText(page.title), filters, specs: specsFit ? specs : [] };
}

/**
 * The specs' size as the server measures it (spec_json): compact JSON without default fields. Python escapes
 * "<" and every non-ASCII character as \uXXXX, so each of those counts as six characters.
 */
export function specsChars(specs: QuerySpec[]): number {
  let total = 0;
  for (const spec of specs) {
    for (const char of JSON.stringify(withoutDefaults(spec))) {
      // Iterating a string yields code points; Python writes one \uXXXX per UTF-16 unit.
      total += char === "<" || char.charCodeAt(0) > 0x7f ? 6 * char.length : 1;
    }
  }
  return total;
}

/** A spec without the fields at QuerySpec's defaults, in the server's field order, as model_dump(exclude_defaults) gives it. */
function withoutDefaults(spec: QuerySpec): Partial<QuerySpec> {
  const { measure, cohort, group_by, where, include, min_denominator } = spec;
  const isDefaultInclude = include === undefined || (include.length === 1 && include[0] === "rates");
  return {
    measure,
    cohort,
    group_by,
    ...(where && Object.keys(where).length > 0 && { where }),
    ...(!isDefaultInclude && { include }),
    ...(min_denominator != null && { min_denominator }),
  };
}

/** Text trimmed, as the server trims it, then cut to its 120-character cap. */
function clipText(text: string): string {
  return text.trim().slice(0, MAX_TEXT_CHARS).trim();
}
