"use client";

import { ChatSessionContext, useChatSessionState } from "@/hooks/use-chat-session";

/**
 * Shares the shell's one chat conversation with everything in the app shell. Goes inside ChatPanelProvider. The
 * chat itself is the floating window in floating-chat.tsx.
 */
export function ChatSessionProvider({ children }: { children: React.ReactNode }) {
  return <ChatSessionContext.Provider value={useChatSessionState()}>{children}</ChatSessionContext.Provider>;
}
