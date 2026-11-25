"use client";

import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { useChatAvailable } from "@/hooks/use-chat-available";
import { useChatPanel } from "@/hooks/use-chat-panel";
import { useDataChat } from "@/hooks/use-data-chat";
import { env } from "@/lib/env";
import { routes } from "@/lib/routes";
import type { DataChatPageContext, KeywordContext } from "@/services/data-chat";

/** The pages with the floating data chat: the executive and presidential views and the pages answers link to. */
const CHAT_PATHS: readonly string[] = [
  routes.sandboxExecutiveView,
  routes.sandboxPresidentialView,
  routes.sandboxDeaggregation,
  routes.sandboxCourseOutcomes,
  routes.sandboxAidMomentum,
  routes.sandboxStudentSuccess,
];

/** Where the conversation was last pointed from: a clicked keyword, a card's Ask button, or nothing yet. */
export type ChatOrigin =
  | { kind: "keyword"; keyword: KeywordContext; path: string; cardId: string | null }
  | { kind: "card"; cardId: string; path: string }
  | null;

export type ChatSession = {
  /** What the conversation was last pointed from. Its card, if any, decides when the chat hides on scroll. */
  origin: ChatOrigin;
  /** The clicked keyword, when the origin is one. */
  keyword: KeywordContext | null;
  /** Whether this page has the floating data chat: the sandbox is on and it is one of the chat pages. */
  availableHere: boolean;
  /** False when the server says its AI chat is off, so the chat shows how to turn it on instead of an input. */
  chatAvailable: boolean;
  /** False while the origin's card is scrolled out of view. */
  originCardVisible: boolean;
  /** Set by the origin card's visibility hook. */
  setOriginCardVisible: (visible: boolean) => void;
  /** True after the launcher or ⌘J opened the chat: it doesn't hide on scroll until the next card or keyword click. */
  pinned: boolean;
  /** A line naming what the chat is scoped to, set by the last keyword or card click. */
  scope?: string;
  /** The questions to offer before the first one, set by the last keyword or card click. */
  suggestions?: string[];
  /** The last click's questions, offered under the conversation until the next question is sent. */
  followUpSuggestions?: string[];
  /** The page the user is on, registered by the page's main chart. Sent when no keyword or card context applies. */
  pageContext: DataChatPageContext | null;
  /** The conversation itself. It lives here, so it survives moving between pages. */
  chat: ReturnType<typeof useDataChat>;
  /** Open the chat about a keyword, from opener (focused again on close). A different keyword starts a new conversation. */
  openKeyword: (keyword: KeywordContext, scope?: string, suggestions?: string[], opener?: HTMLElement) => void;
  /** Open the chat about a card. Any card carries on the conversation, pointed at the new card. */
  openCard: (cardId: string, scope: string, suggestions: string[], opener?: HTMLElement) => void;
  /** Open (or show) the chat from the launcher. It stays put on scroll until the next card or keyword click. */
  openFromLauncher: () => void;
  /** Close the chat and put focus back on what opened it. The conversation stays, so reopening it carries on. */
  closeChat: () => void;
  /** Focus what opened the chat, if it is still on the page. False when there was nothing to focus. */
  returnFocus: () => boolean;
  /** Register the page the user is asking from, or null when that page goes away. */
  setPageContext: (page: DataChatPageContext | null) => void;
  /** Register what a card shows, sent with questions while that card is the origin, or null when it goes away. */
  setCardContext: (cardId: string, page: DataChatPageContext | null) => void;
  /** True after a click opened the chat, until the chat has taken focus. */
  wantsFocus: boolean;
  /** The chat took focus, so the next mount shouldn't steal it from the page. */
  focusTaken: () => void;
};

export const ChatSessionContext = createContext<ChatSession | null>(null);

/** The shell's chat session, for anything inside the app shell. */
export function useChatSession(): ChatSession {
  const session = useContext(ChatSessionContext);
  if (!session) throw new Error("useChatSession must be used inside ChatSessionProvider.");
  return session;
}

/**
 * One conversation for the whole app shell. It sits above the pages, so following a link from an answer to
 * another page keeps the turns. Memory only: a reload starts over.
 */
export function useChatSessionState(): ChatSession {
  const pathname = usePathname();
  const { isChatPanelOpen, setChatPanelOpen } = useChatPanel();
  const availableHere = env.sandboxEnabled && CHAT_PATHS.includes(pathname);
  const chatAvailable = useChatAvailable();
  const [origin, setOrigin] = useState<ChatOrigin>(null);
  const [scope, setScope] = useState<string | undefined>(undefined);
  const [suggestions, setSuggestions] = useState<string[] | undefined>(undefined);
  const [pageContext, setPageContext] = useState<DataChatPageContext | null>(null);
  const [cardContexts, setCardContexts] = useState<Record<string, DataChatPageContext>>({});
  const [originCardVisible, setOriginCardVisible] = useState(true);
  const [pinned, setPinned] = useState(false);
  const [wantsFocus, setWantsFocus] = useState(false);
  // True from a click that set suggestions until the next question, so they show under an ongoing conversation.
  const [suggestionsFresh, setSuggestionsFresh] = useState(false);
  // Read in openKeyword without making it change on every click.
  const originRef = useRef<ChatOrigin>(null);
  // What opened the chat, so closing it doesn't leave keyboard focus on nothing.
  const openerRef = useRef<HTMLElement | null>(null);
  // Whether the chat was open at the last render, and whether one of the open functions below is opening it, so an
  // open by ⌘J or the topbar (through useChatPanel) can be told apart.
  const [wasOpen, setWasOpen] = useState(isChatPanelOpen);
  const [openingHere, setOpeningHere] = useState(false);
  // Counts opens by ⌘J or the topbar, so an effect can note what had focus.
  const [shortcutOpens, setShortcutOpens] = useState(0);
  const wasAvailableRef = useRef(availableHere);

  // ⌘J and the topbar button open the chat like the launcher: pinned, and taking focus.
  if (isChatPanelOpen !== wasOpen) {
    setWasOpen(isChatPanelOpen);
    setOpeningHere(false);
    if (isChatPanelOpen && !openingHere && availableHere) {
      setPinned(true);
      setWantsFocus(true);
      setShortcutOpens((count) => count + 1);
    }
  }

  // A keyword or card names things on the page it came from, so elsewhere the page's own context goes instead.
  const onOriginPath = origin !== null && pathname === origin.path;
  const keywordHere = onOriginPath && origin.kind === "keyword" ? origin.keyword : null;
  const cardHere = onOriginPath && origin.kind === "card" ? (cardContexts[origin.cardId] ?? null) : null;
  const dataChat = useDataChat(keywordHere, keywordHere ? null : (cardHere ?? pageContext));
  const { startNewChat, submitQuestion: submitToChat } = dataChat;

  /** Send a question; the click's suggestions have done their job, so they stop showing. */
  const submitQuestion = useCallback(
    (question: string) => {
      setSuggestionsFresh(false);
      return submitToChat(question);
    },
    [submitToChat],
  );
  const chat = useMemo(() => ({ ...dataChat, submitQuestion }), [dataChat, submitQuestion]);

  /** Remember what to focus on close, then open the chat and ask it to take focus. */
  const beginOpen = useCallback(
    (opener?: HTMLElement) => {
      // Safari doesn't focus a clicked button, so the opener is passed in where it can be.
      const focused = document.activeElement;
      openerRef.current = opener ?? (focused instanceof HTMLElement && focused !== document.body ? focused : null);
      if (!isChatPanelOpen) setOpeningHere(true);
      setWantsFocus(true);
      setChatPanelOpen(true);
    },
    [isChatPanelOpen, setChatPanelOpen],
  );

  /** Point the chat at a keyword; a different keyword than last time starts a new conversation. */
  const openKeyword = useCallback(
    (next: KeywordContext, nextScope?: string, nextSuggestions?: string[], opener?: HTMLElement) => {
      const previous = originRef.current;
      if (previous?.kind !== "keyword" || keywordKey(previous.keyword) !== keywordKey(next)) startNewChat();
      const cardId = opener?.closest("article[id]")?.id ?? null;
      const nextOrigin: ChatOrigin = { kind: "keyword", keyword: next, path: pathname, cardId };
      originRef.current = nextOrigin;
      setOrigin(nextOrigin);
      setScope(nextScope);
      setSuggestions(nextSuggestions);
      setSuggestionsFresh(Boolean(nextSuggestions?.length));
      setOriginCardVisible(true);
      setPinned(false);
      beginOpen(opener);
    },
    [pathname, startNewChat, beginOpen],
  );

  /** Point the chat at a card, carrying on the conversation. */
  const openCard = useCallback(
    (cardId: string, nextScope: string, nextSuggestions: string[], opener?: HTMLElement) => {
      // Any card, this one or another, carries on the conversation (Ben's decision 4).
      const nextOrigin: ChatOrigin = { kind: "card", cardId, path: pathname };
      originRef.current = nextOrigin;
      setOrigin(nextOrigin);
      setScope(nextScope);
      setSuggestions(nextSuggestions);
      setSuggestionsFresh(Boolean(nextSuggestions?.length));
      // The card was just clicked, so it is on screen; its observer says otherwise once it scrolls away.
      setOriginCardVisible(true);
      setPinned(false);
      beginOpen(opener);
    },
    [pathname, beginOpen],
  );

  /** Open or show the chat and pin it, so scrolling doesn't hide it. */
  const openFromLauncher = useCallback(() => {
    setPinned(true);
    beginOpen();
  }, [beginOpen]);

  /** Focus the opener, but only while it is still on the page: after a link it has gone. */
  const returnFocus = useCallback(() => {
    const opener = openerRef.current;
    if (!opener?.isConnected) return false;
    opener.focus();
    return true;
  }, []);

  /** Close the chat and hand focus back to what opened it. */
  const closeChat = useCallback(() => {
    setChatPanelOpen(false);
    returnFocus();
  }, [setChatPanelOpen, returnFocus]);

  /** Keep or drop one card's context. */
  const setCardContext = useCallback((cardId: string, page: DataChatPageContext | null) => {
    setCardContexts((previous) => {
      if (page === null) {
        if (!(cardId in previous)) return previous;
        const rest = { ...previous };
        delete rest[cardId];
        return rest;
      }
      // Unchanged, so a card registering the same context again doesn't re-render the session.
      if (JSON.stringify(previous[cardId]) === JSON.stringify(page)) return previous;
      return { ...previous, [cardId]: page };
    });
  }, []);

  /** The chat took focus, so stop asking for it. */
  const focusTaken = useCallback(() => setWantsFocus(false), []);

  // What had focus when ⌘J or the topbar opened the chat. A layout effect, so it runs before the chat takes focus.
  useLayoutEffect(() => {
    if (shortcutOpens === 0) return;
    const focused = document.activeElement;
    openerRef.current = focused instanceof HTMLElement && focused !== document.body ? focused : null;
  }, [shortcutOpens]);

  // Leaving the chat pages closes the chat, so the next page doesn't open the shell's empty panel in its place.
  useEffect(() => {
    if (wasAvailableRef.current && !availableHere) setChatPanelOpen(false);
    wasAvailableRef.current = availableHere;
  }, [availableHere, setChatPanelOpen]);

  const keyword = origin?.kind === "keyword" ? origin.keyword : null;
  const followUpSuggestions = suggestionsFresh ? suggestions : undefined;

  return useMemo(
    () => ({
      origin,
      keyword,
      availableHere,
      chatAvailable,
      originCardVisible,
      setOriginCardVisible,
      pinned,
      scope,
      suggestions,
      followUpSuggestions,
      pageContext,
      chat,
      openKeyword,
      openCard,
      openFromLauncher,
      closeChat,
      returnFocus,
      setPageContext,
      setCardContext,
      wantsFocus,
      focusTaken,
    }),
    [
      origin,
      keyword,
      availableHere,
      chatAvailable,
      originCardVisible,
      pinned,
      scope,
      suggestions,
      followUpSuggestions,
      pageContext,
      chat,
      openKeyword,
      openCard,
      openFromLauncher,
      closeChat,
      returnFocus,
      setCardContext,
      wantsFocus,
      focusTaken,
    ],
  );
}

/** One keyword's identity, so clicking the same one again carries on its conversation. */
function keywordKey(keyword: KeywordContext): string {
  // The view too: Retention on the executive and presidential views are different cards.
  return [keyword.view, keyword.kind, keyword.measure, keyword.group, keyword.cohort].join("|");
}
