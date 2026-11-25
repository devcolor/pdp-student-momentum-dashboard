"use client";

import { ArrowRight, Check, Copy, DatabaseZap, MessageCircleOff, Minus, RotateCw } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { QuestionComposer, SuggestedQuestions } from "@/components/chat/panel-chat";
import { EmptyState } from "@/components/empty-state";
import { Markdown } from "@/components/markdown";
import { QuestionBubble } from "@/components/question-bubble";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  DATA_CHAT_DESCRIPTION,
  DATA_CHAT_OFF_DESCRIPTION,
  DATA_CHAT_OFF_TITLE,
  DATA_CHAT_PLACEHOLDER,
  DATA_CHAT_SYNTHETIC_NOTE,
  DATA_CHAT_TITLE,
  DATA_CHAT_WELCOME,
  dataChatSuggestedQuestions,
} from "@/content/data-chat-ui";
import { useChatAvailable } from "@/hooks/use-chat-available";
import { type DataChatMessage, useDataChat } from "@/hooks/use-data-chat";
import { useScrollToLatest } from "@/hooks/use-scroll-to-latest";
import { isLinkPage, pageHref } from "@/lib/routes";
import type { DataChatAnswer, KeywordContext, PageLink, ToolResult } from "@/services/data-chat";

const MINIMIZE_LABEL = "Minimize chat (⌘J to reopen)";

type DataChatProps = {
  /** What the question is about, when the chat was opened from something on a page. */
  keyword?: KeywordContext | null;
  /** What to offer before the first question. Defaults to the general data-model questions. */
  suggestions?: string[];
  /** Questions to offer under an ongoing conversation, e.g. after the chat was pointed at something new. */
  followUpSuggestions?: string[];
  /** A line under the title saying what the chat is scoped to. */
  scope?: string;
  /** Closes the chat. Leave it out where the chat has no close, as on its own page. */
  onClose?: () => void;
  /** Called when the user follows a link from an answer, e.g. to close a chat that covers the page. */
  onNavigate?: () => void;
};

/** PanelChat's layout, answered by an LLM over the data model, holding its own conversation. */
export function DataChat({ keyword = null, suggestions, scope, onClose, onNavigate }: DataChatProps = {}) {
  const chat = useDataChat(keyword);
  const available = useChatAvailable();
  return (
    <DataChatView
      chat={chat}
      available={available}
      suggestions={suggestions}
      scope={scope}
      onClose={onClose}
      onNavigate={onNavigate}
    />
  );
}

type DataChatViewProps = Omit<DataChatProps, "keyword"> & {
  /** The conversation to show, from useDataChat or the app shell's chat session. */
  chat: ReturnType<typeof useDataChat>;
  /** False when the server's AI chat is off: the chat says how to turn it on, with no input to send from. */
  available?: boolean;
};

/** The data chat's UI for a conversation held elsewhere: markdown replies and the tool results behind them. */
export function DataChatView({
  chat,
  available = true,
  suggestions,
  followUpSuggestions,
  scope,
  onClose,
  onNavigate,
}: DataChatViewProps) {
  const { chatMessages, isAwaitingReply, submitQuestion, startNewChat } = chat;
  const conversationRef = useScrollToLatest<HTMLDivElement>(chatMessages.length + Number(isAwaitingReply));

  return (
    <section aria-label={DATA_CHAT_TITLE} className="flex h-full min-h-0 flex-col">
      <header className="flex items-center justify-between gap-3 border-b px-5 py-4">
        <div className="min-w-0">
          <h2 className="font-semibold tracking-tight">{DATA_CHAT_TITLE}</h2>
          <p className="truncate text-sm text-muted-foreground">{scope ?? DATA_CHAT_DESCRIPTION}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button variant="outline" size="icon" aria-label="Start over" title="Start over" onClick={startNewChat}>
            <RotateCw />
          </Button>
          {onClose && (
            // It only hides the window: the conversation stays, and ⌘J brings it back.
            <Button variant="ghost" size="icon" aria-label={MINIMIZE_LABEL} title={MINIMIZE_LABEL} onClick={onClose}>
              <Minus />
            </Button>
          )}
        </div>
      </header>

      <div ref={conversationRef} className="min-h-0 flex-1 overflow-y-auto px-5 py-6">
        {!available ? (
          <EmptyState
            icon={MessageCircleOff}
            title={DATA_CHAT_OFF_TITLE}
            description={DATA_CHAT_OFF_DESCRIPTION}
            bordered={false}
            className="h-full p-0"
          />
        ) : chatMessages.length === 0 ? (
          <EmptyState
            icon={DatabaseZap}
            title="Ask the data"
            description={DATA_CHAT_WELCOME}
            bordered={false}
            className="h-full p-0"
          >
            <SuggestedQuestions
              questions={suggestions ?? dataChatSuggestedQuestions}
              onQuestionChosen={submitQuestion}
            />
          </EmptyState>
        ) : (
          <ol className="flex flex-col gap-6">
            {chatMessages.map((message) => (
              <li key={message.id}>
                <DataChatMessageItem message={message} onNavigate={onNavigate} />
              </li>
            ))}
            {isAwaitingReply && (
              <li className="flex items-center gap-2 text-sm text-muted-foreground" aria-live="polite">
                <span className="size-1.5 rounded-full bg-muted-foreground motion-safe:animate-pulse" />
                Looking it up… this can take up to a minute.
              </li>
            )}
            {!isAwaitingReply && followUpSuggestions && followUpSuggestions.length > 0 && (
              <li aria-label="Suggested questions">
                <SuggestedQuestions questions={followUpSuggestions} onQuestionChosen={submitQuestion} />
              </li>
            )}
          </ol>
        )}
      </div>

      {/* No input while the chat is off, so nothing can send a question the server would refuse. */}
      {available && (
        <QuestionComposer onSubmit={submitQuestion} disabled={isAwaitingReply} placeholder={DATA_CHAT_PLACEHOLDER} />
      )}
    </section>
  );
}

/** One turn: the question, the assistant's answer, or why there's no answer. */
function DataChatMessageItem({ message, onNavigate }: { message: DataChatMessage; onNavigate?: () => void }) {
  if (message.role === "user") return <QuestionBubble>{message.text}</QuestionBubble>;
  if (message.role === "error") {
    return (
      <p role="alert" className="rounded-xl border border-destructive/40 px-4 py-3 text-sm text-destructive">
        {message.text}
      </p>
    );
  }
  return <AnswerView answer={message.answer} onNavigate={onNavigate} />;
}

/** The answer as markdown, the pages that show it, then the tool results it came from. */
function AnswerView({ answer, onNavigate }: { answer: DataChatAnswer; onNavigate?: () => void }) {
  return (
    <div className="flex flex-col gap-4">
      <Markdown>{answer.message}</Markdown>
      {answer.links.length > 0 && (
        // Reading the URL's query needs a Suspense boundary, or Next.js can't prerender the pages around the chat.
        <Suspense fallback={null}>
          <PageLinks links={answer.links} onNavigate={onNavigate} />
        </Suspense>
      )}
      {answer.query && <ToolResultView label="Query" result={answer.query} />}
      {answer.definitions && <ToolResultView label="Definitions" result={answer.definitions} />}
      {answer.results && <ToolResultView label="Published results" result={answer.results} />}
      <p className="text-xs text-muted-foreground">
        {answer.tools_used.length > 0 ? `Tools used: ${answer.tools_used.join(", ")}. ` : "No tools used. "}
        {DATA_CHAT_SYNTHETIC_NOTE}
      </p>
    </div>
  );
}

/**
 * "See it on" links to the pages that chart what the answer read. Same tab, so the shell's conversation stays.
 * A link to the page and picks already on screen is left out.
 */
function PageLinks({ links, onNavigate }: { links: PageLink[]; onNavigate?: () => void }) {
  const pathname = usePathname();
  // Null outside the App Router, as in stories.
  const search = useSearchParams()?.toString() ?? "";
  const elsewhere = links
    // A page this client doesn't know (a newer server) is skipped, not linked to a broken address.
    .filter((link) => isLinkPage(link.page))
    .map((link) => ({ link, href: pageHref(link.page, link.params) }))
    .filter(({ href }) => !isSameAddress(href, pathname, search));
  if (elsewhere.length === 0) return null;

  return (
    <nav aria-label="See it on" className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-muted-foreground">See it on</span>
      {elsewhere.map(({ link, href }) => (
        <Link
          key={href}
          href={href}
          onClick={onNavigate}
          className={buttonVariants({ variant: "outline", size: "sm", className: "max-w-full" })}
        >
          <span className="truncate">{link.label}</span>
          <ArrowRight data-icon="inline-end" />
        </Link>
      ))}
    </nav>
  );
}

/** Whether href is the page already open: same path and the same params, in any order. */
function isSameAddress(href: string, pathname: string, search: string): boolean {
  const [hrefPath, hrefSearch = ""] = href.split("?");
  return hrefPath === pathname && sortedParams(hrefSearch) === sortedParams(search);
}

/** A query string with its params sorted, so two orders of the same params compare equal. */
function sortedParams(search: string): string {
  const params = new URLSearchParams(search);
  params.sort();
  return params.toString();
}

/** One tool call, collapsed: the SQL it ran, if any, then its result as JSON. */
function ToolResultView({ label, result }: { label: string; result: ToolResult }) {
  // query_results sends the builder's SQL in sql; run_aggregate_query's SQL is its input.
  const sql = result.sql ?? (typeof result.input.sql === "string" ? result.input.sql : null);
  return (
    <details className="rounded-lg border px-3 py-2 text-sm">
      <summary className="cursor-pointer font-medium">
        {result.is_error ? `${label} failed` : label}: {result.tool}
      </summary>
      {sql && (
        <div className="mt-2">
          <div className="flex justify-end">
            <CopySqlButton sql={sql} />
          </div>
          <pre className="mt-1 overflow-x-auto rounded-lg bg-muted p-3 font-mono text-xs">{sql}</pre>
        </div>
      )}
      <pre className="mt-2 max-h-80 overflow-auto rounded-lg bg-muted p-3 font-mono text-xs">
        {JSON.stringify(result.output, null, 2)}
      </pre>
    </details>
  );
}

/** Copies the SQL to the clipboard, and says so for a moment. */
function CopySqlButton({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(timer);
  }, [copied]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
    } catch {
      // No clipboard (an insecure page, or permission denied): the SQL is still there to select.
    }
  }

  return (
    // The visible text is the name, so a screen reader hears "Copied" too.
    <Button variant="ghost" size="sm" onClick={copy} aria-live="polite">
      {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
      {copied ? "Copied" : "Copy SQL"}
    </Button>
  );
}
