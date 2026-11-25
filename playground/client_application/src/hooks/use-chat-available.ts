"use client";

import { useEffect, useState } from "react";

import { env } from "@/lib/env";
import { checkHealth } from "@/services/health";

/**
 * Whether the server's AI chat can answer, from /health's chat_available. Checked once on mount.
 *
 * True until the server says otherwise, so a slow or unreachable API leaves the chat as it was. Only an explicit
 * false (no ANTHROPIC_API_KEY, or SANDBOX_CHAT_ENABLED off) turns it off.
 */
export function useChatAvailable(): boolean {
  const [available, setAvailable] = useState(true);

  useEffect(() => {
    if (!env.sandboxEnabled) return;
    let cancelled = false;
    void checkHealth().then((outcome) => {
      if (!cancelled && outcome.reachable && outcome.health.chat_available === false) setAvailable(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return available;
}
