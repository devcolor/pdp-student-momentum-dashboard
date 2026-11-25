"use client";

import { MessageCircle } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { DataChatView } from "@/components/chat/data-chat";
import { Button } from "@/components/ui/button";
import { useChatPanel } from "@/hooks/use-chat-panel";
import { useChatSession } from "@/hooks/use-chat-session";
import { useMediaQuery } from "@/hooks/use-media-query";
import { cn } from "@/lib/utils";

const WINDOW_ID = "data-chat-window";
const LAUNCHER_ID = "data-chat-launcher";
/** The topbar's chat toggle (app-topbar.tsx). Matched by name, so that file needn't know about the floating chat. */
const TOPBAR_TOGGLE_SELECTOR = 'button[aria-label="Toggle chat panel (⌘J)"]';

/** From this width the chat floats as a resizable window; below it, it is a bottom sheet. */
const WIDE_QUERY = "(min-width: 640px)";

/** Where the window's size is kept between visits. */
const SIZE_STORAGE_KEY = "data-chat-size";

const DEFAULT_SIZE: ChatSize = { width: 448, height: 576 };
const MIN_WIDTH = 320;
const MAX_WIDTH = 720;
const MIN_HEIGHT = 360;
// The window sits 1rem from each side and 5rem above the bottom (clear of the launcher), and keeps 2rem above it.
const SIDE_MARGIN_PX = 32;
const VERTICAL_MARGIN_PX = 112;
/** How far one arrow key press resizes the window. */
const KEY_STEP_PX = 16;

type ChatSize = { width: number; height: number };

/**
 * The round button in the bottom-right corner of the chat pages. It opens and closes the floating chat, and shows
 * it again while it is hidden because its card scrolled away; a dot marks that state.
 */
export function ChatLauncher() {
  const { availableHere, openFromLauncher, closeChat } = useChatSession();
  const { isChatPanelOpen } = useChatPanel();
  const scrollHidden = useChatScrollHidden();
  const launcherRef = useRef<HTMLButtonElement>(null);
  if (!availableHere) return null;

  const shown = isChatPanelOpen && !scrollHidden;

  /** Close a shown chat; open a closed one, or bring back a hidden one and keep it until the next card click. */
  function toggle() {
    if (shown) {
      closeChat();
      launcherRef.current?.focus();
      return;
    }
    // Focused first, so closing the chat later puts focus back here (Safari doesn't focus a clicked button).
    launcherRef.current?.focus();
    openFromLauncher();
  }

  return (
    <Button
      ref={launcherRef}
      id={LAUNCHER_ID}
      size="icon"
      aria-label="Open data chat (⌘J)"
      title={scrollHidden ? "The chat is hidden while its chart is off screen. Click to show it." : "Open data chat (⌘J)"}
      aria-expanded={shown}
      aria-controls={isChatPanelOpen ? WINDOW_ID : undefined}
      onClick={toggle}
      className="fixed right-4 bottom-4 z-40 size-12 rounded-full shadow-lg"
    >
      <MessageCircle className="size-5" />
      {scrollHidden && (
        <span aria-hidden className="absolute top-1 right-1 size-2.5 rounded-full bg-primary-foreground ring-2 ring-primary" />
      )}
    </Button>
  );
}

/**
 * The data chat, floating over the chat pages: a resizable window from 640px up, a bottom sheet on phones. Closed,
 * it is gone; hidden on scroll, it stays mounted, so a draft and the scroll position survive.
 */
export function FloatingChat() {
  const { availableHere } = useChatSession();
  const { isChatPanelOpen } = useChatPanel();
  if (!availableHere || !isChatPanelOpen) return null;
  return <ChatWindow />;
}

/** The open chat: the window or sheet around the conversation, with its focus, Escape and resize handling. */
function ChatWindow() {
  const {
    chat,
    chatAvailable,
    scope,
    suggestions,
    followUpSuggestions,
    closeChat,
    returnFocus,
    wantsFocus,
    focusTaken,
    openFromLauncher,
  } = useChatSession();
  const wide = useMediaQuery(WIDE_QUERY, true);
  const scrollHidden = useChatScrollHidden();
  // The window only opens on a click, never in the server's render, so localStorage is there to read.
  const [size, setSize] = useState(readSavedSize);
  const windowRef = useRef<HTMLDivElement>(null);
  const dragStart = useRef<{ x: number; y: number; size: ChatSize } | null>(null);

  // A click that opened the chat moves focus here, so a keyboard user is not left on the page behind it.
  useEffect(() => {
    if (!wantsFocus || scrollHidden) return;
    windowRef.current?.focus();
    focusTaken();
  }, [wantsFocus, scrollHidden, focusTaken]);

  // A smaller browser window shrinks the chat to fit.
  useEffect(() => {
    const refit = () => setSize((current) => sameSize(current, clampSize(current)));
    window.addEventListener("resize", refit);
    return () => window.removeEventListener("resize", refit);
  }, []);

  // Hiding a window with focus inside would strand it, so focus moves to the launcher first. A layout effect, so it
  // moves in the same frame the window hides, before the browser drops focus from the inert window.
  useLayoutEffect(() => {
    if (scrollHidden && windowRef.current?.contains(document.activeElement)) focusLauncher();
  }, [scrollHidden]);

  // ⌘J or the topbar closing the chat unmounts it: focus inside goes back to the opener, or the launcher. A layout
  // cleanup, so it runs while the window is still in the document.
  useLayoutEffect(() => {
    const chatWindow = windowRef.current;
    return () => {
      if (chatWindow?.contains(document.activeElement) && !returnFocus()) focusLauncher();
    };
  }, [returnFocus]);

  // ⌘J and the topbar button show a hidden chat instead of closing it unseen. Caught in the capture phase, before
  // useChatPanel's ⌘J listener and the topbar button's React click handler.
  useEffect(() => {
    if (!scrollHidden) return;
    /** ⌘J or Ctrl+J: show and pin the chat. */
    function showOnShortcut(event: KeyboardEvent) {
      if (event.key !== "j" || !(event.metaKey || event.ctrlKey)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      openFromLauncher();
    }
    /** A click on the topbar's chat toggle: show and pin the chat. */
    function showOnTopbarClick(event: MouseEvent) {
      if (!(event.target instanceof Element) || !event.target.closest(TOPBAR_TOGGLE_SELECTOR)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      openFromLauncher();
    }
    window.addEventListener("keydown", showOnShortcut, { capture: true });
    window.addEventListener("click", showOnTopbarClick, { capture: true });
    return () => {
      window.removeEventListener("keydown", showOnShortcut, { capture: true });
      window.removeEventListener("click", showOnTopbarClick, { capture: true });
    };
  }, [scrollHidden, openFromLauncher]);

  /** The size a drag from dragStart to this pointer gives. The grip is top-left, so left and up grow the window. */
  function draggedSize(event: React.PointerEvent): ChatSize | null {
    const start = dragStart.current;
    if (!start) return null;
    return clampSize({
      width: start.size.width + start.x - event.clientX,
      height: start.size.height + start.y - event.clientY,
    });
  }

  /** Stop dragging and keep the size for next time. */
  function endDrag(event: React.PointerEvent) {
    const next = draggedSize(event);
    dragStart.current = null;
    if (!next) return;
    setSize(next);
    saveSize(next);
  }

  /** Arrow keys on the grip: left and up grow the window, right and down shrink it. */
  function resizeWithKeys(event: React.KeyboardEvent) {
    const [dx, dy] = KEY_STEPS[event.key] ?? [0, 0];
    if (dx === 0 && dy === 0) return;
    event.preventDefault();
    const next = clampSize({ width: size.width + dx, height: size.height + dy });
    setSize(next);
    saveSize(next);
  }

  return (
    <div
      ref={windowRef}
      id={WINDOW_ID}
      role="dialog"
      aria-modal="false"
      aria-label="Data chat"
      tabIndex={-1}
      hidden={scrollHidden}
      inert={scrollHidden}
      onKeyDown={(event) => {
        if (event.key === "Escape") closeChat();
      }}
      className={cn(
        "fixed z-40 flex flex-col overflow-hidden bg-card shadow-xl outline-none",
        wide ? "right-4 bottom-20 rounded-2xl border" : "inset-x-0 bottom-0 h-[85svh] rounded-t-2xl border-t",
      )}
      style={wide ? { width: size.width, height: size.height } : undefined}
    >
      {wide && (
        <button
          type="button"
          aria-label="Resize chat"
          title="Drag, or use the arrow keys, to resize"
          onPointerDown={(event) => {
            event.preventDefault();
            event.currentTarget.focus();
            event.currentTarget.setPointerCapture(event.pointerId);
            dragStart.current = { x: event.clientX, y: event.clientY, size };
          }}
          onPointerMove={(event) => {
            const next = draggedSize(event);
            if (next) setSize(next);
          }}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onKeyDown={resizeWithKeys}
          className="absolute top-0 left-0 z-10 flex size-5 cursor-nwse-resize touch-none items-start justify-start rounded-tl-2xl p-1 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          <span aria-hidden className="block size-2 rounded-tl-sm border-t-2 border-l-2 border-muted-foreground/60" />
        </button>
      )}
      <div className="min-h-0 flex-1">
        <DataChatView
          chat={chat}
          available={chatAvailable}
          scope={scope}
          suggestions={suggestions}
          followUpSuggestions={followUpSuggestions}
          onClose={closeChat}
          // A sheet covers the page a link goes to, so it closes; a window floats beside it and stays.
          onNavigate={wide ? undefined : closeChat}
        />
      </div>
    </div>
  );
}

const KEY_STEPS: Record<string, [number, number]> = {
  ArrowLeft: [KEY_STEP_PX, 0],
  ArrowRight: [-KEY_STEP_PX, 0],
  ArrowUp: [0, KEY_STEP_PX],
  ArrowDown: [0, -KEY_STEP_PX],
};

/**
 * Whether the open chat is hidden because the card it came from scrolled out of view. Never on phones, and never
 * after the launcher or ⌘J pinned it. Focus inside doesn't keep it: the window moves focus to the launcher first.
 */
function useChatScrollHidden(): boolean {
  const { origin, originCardVisible, pinned } = useChatSession();
  const { isChatPanelOpen } = useChatPanel();
  const pathname = usePathname();
  const wide = useMediaQuery(WIDE_QUERY, true);
  return (
    wide &&
    isChatPanelOpen &&
    Boolean(origin?.cardId) &&
    pathname === origin?.path &&
    !originCardVisible &&
    !pinned
  );
}

/** Focus the launcher, the one control that stays put while the chat is hidden or closed. */
function focusLauncher(): void {
  document.getElementById(LAUNCHER_ID)?.focus();
}

/** The size within its limits for this browser window: 320–720px wide (less on a narrow screen), 360px up to tall. */
function clampSize({ width, height }: ChatSize): ChatSize {
  const maxWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, window.innerWidth - SIDE_MARGIN_PX));
  const maxHeight = Math.max(MIN_HEIGHT, window.innerHeight - VERTICAL_MARGIN_PX);
  return {
    width: Math.round(Math.min(maxWidth, Math.max(MIN_WIDTH, width))),
    height: Math.round(Math.min(maxHeight, Math.max(MIN_HEIGHT, height))),
  };
}

/** next, or current when they match, so an unchanged size doesn't re-render. */
function sameSize(current: ChatSize, next: ChatSize): ChatSize {
  return current.width === next.width && current.height === next.height ? current : next;
}

/** The size saved last time, or the default when there is none or the browser blocks storage. */
function readSavedSize(): ChatSize {
  try {
    const saved: unknown = JSON.parse(window.localStorage.getItem(SIZE_STORAGE_KEY) ?? "null");
    if (isChatSize(saved)) return clampSize(saved);
  } catch {
    // Unreadable or blocked: the default below.
  }
  return clampSize(DEFAULT_SIZE);
}

/** Keep the size for next time. Blocked storage just means the default next time. */
function saveSize(size: ChatSize): void {
  try {
    window.localStorage.setItem(SIZE_STORAGE_KEY, JSON.stringify(size));
  } catch {
    // Not saved: the window opens at its default size next time.
  }
}

/** Whether a saved value is a size: two finite numbers. */
function isChatSize(value: unknown): value is ChatSize {
  if (typeof value !== "object" || value === null) return false;
  const { width, height } = value as Record<string, unknown>;
  return typeof width === "number" && Number.isFinite(width) && typeof height === "number" && Number.isFinite(height);
}
