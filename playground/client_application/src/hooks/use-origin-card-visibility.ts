"use client";

import { usePathname } from "next/navigation";
import { type RefObject, useContext, useEffect } from "react";

import { ChatPanelContext } from "@/hooks/use-chat-panel";
import { ChatSessionContext } from "@/hooks/use-chat-session";

/**
 * How far below the viewport's top a card counts as gone: the topbar (56px) plus a sticky filter bar. A card
 * tucked under them is out of sight even though it is still inside the viewport.
 */
export const ORIGIN_CARD_TOP_INSET_PX = 128;

/** How long a card must stay out of view before the chat hides, so a quick scroll past doesn't flash it. */
const HIDE_DELAY_MS = 150;

/**
 * Tells the chat session whether this card is on screen, while it is the card the open chat came from. The
 * floating chat hides while it isn't. Does nothing outside the app shell's chat session (as in stories).
 */
export function useOriginCardVisibility(id: string | undefined, ref: RefObject<HTMLElement | null>): void {
  const session = useContext(ChatSessionContext);
  const isChatOpen = useContext(ChatPanelContext)?.isChatPanelOpen ?? false;
  const pathname = usePathname();
  const origin = session?.origin ?? null;
  const setVisible = session?.setOriginCardVisible;
  const active = id !== undefined && isChatOpen && origin?.cardId === id && pathname === origin.path;

  useEffect(() => {
    const card = ref.current;
    if (!active || !setVisible || !card) return;
    let hideTimer: ReturnType<typeof setTimeout> | undefined;
    const observer = new IntersectionObserver(
      ([entry]) => {
        clearTimeout(hideTimer);
        if (entry.isIntersecting) setVisible(true);
        else hideTimer = setTimeout(() => setVisible(false), HIDE_DELAY_MS);
      },
      { threshold: 0, rootMargin: `-${ORIGIN_CARD_TOP_INSET_PX}px 0px 0px 0px` },
    );
    observer.observe(card);
    return () => {
      clearTimeout(hideTimer);
      observer.disconnect();
      setVisible(true);
    };
  }, [active, ref, setVisible]);
}
