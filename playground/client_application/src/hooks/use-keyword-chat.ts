"use client";

import { createContext, useCallback, useContext, useMemo } from "react";

import { useChatSession } from "@/hooks/use-chat-session";
import type { KeywordContext } from "@/services/data-chat";

type KeywordChatState = {
  /** What the shell's chat is about, or null when no keyword has been clicked. */
  keyword: KeywordContext | null;
  /** Open the shell's chat about one thing, from opener (focused again on close). A different thing starts a new conversation. */
  openKeyword: (keyword: KeywordContext, opener?: HTMLElement) => void;
  /** Close the shell's chat panel; the conversation stays. */
  closeKeyword: () => void;
};

export type KeywordChatOptions = {
  /** A line naming what the chat is scoped to, from the page's own labels. */
  scopeOf: (keyword: KeywordContext) => string;
  /** The questions to offer, all of which the published measures can answer. */
  suggestionsFor: (keyword: KeywordContext) => string[];
};

export const KeywordChatContext = createContext<KeywordChatState | null>(null);

/** The keyword chat's state, for anything under a KeywordChatProvider. */
export function useKeywordChat(): KeywordChatState {
  const state = useContext(KeywordChatContext);
  if (!state) throw new Error("useKeywordChat must be used inside KeywordChatProvider.");
  return state;
}

/**
 * A page's way into the app shell's chat: a clicked keyword opens the shell's panel about it, with the page's
 * scope line and suggestions worked out at the click, so they still show after following a link to another page.
 */
export function useKeywordChatState({ scopeOf, suggestionsFor }: KeywordChatOptions): KeywordChatState {
  const { keyword, openKeyword: openSessionKeyword, closeChat } = useChatSession();
  const openKeyword = useCallback(
    (next: KeywordContext, opener?: HTMLElement) => openSessionKeyword(next, scopeOf(next), suggestionsFor(next), opener),
    [openSessionKeyword, scopeOf, suggestionsFor],
  );

  return useMemo(() => ({ keyword, openKeyword, closeKeyword: closeChat }), [keyword, openKeyword, closeChat]);
}
