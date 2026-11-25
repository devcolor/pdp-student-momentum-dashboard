"use client";

import { MessageCircleQuestionMark } from "lucide-react";
import type { ComponentPropsWithRef } from "react";

import { useKeywordChat } from "@/hooks/use-keyword-chat";
import { cn } from "@/lib/utils";
import type { KeywordContext } from "@/services/data-chat";

type KeywordButtonProps = ComponentPropsWithRef<"button"> & {
  /** What the chat should be about when this is clicked. */
  keyword: KeywordContext;
  /** What the chat will be scoped to, for the button's accessible name. */
  label: string;
};

/**
 * A name on the page that opens the chat about it: text with a dotted underline, not a button
 * that looks like one, so the page still reads as a report.
 *
 * Everything else is passed to the button, so a wrapper such as a tooltip can add its own
 * handlers and ref. Without that a tooltip around one silently never opens.
 */
export function KeywordButton({
  keyword,
  label,
  children,
  className,
  onClick,
  ...rest
}: KeywordButtonProps) {
  const { openKeyword } = useKeywordChat();

  return (
    <button
      type="button"
      onClick={(event) => {
        onClick?.(event);
        openKeyword(keyword, event.currentTarget);
      }}
      aria-label={`Ask about ${label}`}
      className={cn(
        "group inline-flex cursor-pointer items-center gap-1 rounded text-left underline",
        "decoration-dotted decoration-from-font underline-offset-4 hover:decoration-solid",
        "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
        className,
      )}
      {...rest}
    >
      <span>{children}</span>
      <MessageCircleQuestionMark
        aria-hidden
        className="size-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
      />
    </button>
  );
}
