"use client";

import { KeywordChatContext, type KeywordChatOptions, useKeywordChatState } from "@/hooks/use-keyword-chat";

/**
 * Lets keywords on a page open the app shell's chat about them. The chat itself is the shell's panel
 * (see shell-chat.tsx), so nothing renders here and no model is called on open.
 */
export function KeywordChatProvider({
  scopeOf,
  suggestionsFor,
  children,
}: KeywordChatOptions & { children: React.ReactNode }) {
  return (
    <KeywordChatContext.Provider value={useKeywordChatState({ scopeOf, suggestionsFor })}>
      {children}
    </KeywordChatContext.Provider>
  );
}
