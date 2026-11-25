"use client";

import { ArrowUpRight, MessageCircleQuestionMark } from "lucide-react";
import { useContext, useEffect, useMemo, useRef } from "react";

import type { ChartMeta, SandboxLoader } from "@/lib/sandbox";
import { withinCaps } from "@/components/chat/chat-page-context";
import { LoadError } from "@/components/load-error";
import { AnswerNote } from "@/components/sandbox/answer-note";
import { FilterChips } from "@/components/sandbox/filter-chips";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { chartChatSuggestions } from "@/content/chart-chat-suggestions";
import { useApiResource } from "@/hooks/use-api-resource";
import { ChatSessionContext } from "@/hooks/use-chat-session";
import { useOriginCardVisibility } from "@/hooks/use-origin-card-visibility";
import { apiUrl } from "@/lib/links";
import { cn } from "@/lib/utils";
import type { DataChatPageContext } from "@/services/data-chat";

type ChartCardProps<Data extends { meta: ChartMeta }> = {
  /** The endpoint to load. Its path is also where the source badge links. */
  load: SandboxLoader<Data>;
  /** Draws the chart once the data has loaded. */
  children: (data: Data) => React.ReactNode;
  /** Filters for this chart alone, drawn under it. They stay on screen while the chart reloads. */
  controls?: React.ReactNode;
  /** Draws anything that belongs below the controls, such as a table of the values. */
  details?: (data: Data) => React.ReactNode;
  /** For dense single-screen pages: tighter spacing, no filter chips, definitions folded away. */
  compact?: boolean;
  /** Anchor id, so other pages can link straight to this chart. Ids in chartChatSuggestions also get an "Ask" button. */
  id?: string;
  className?: string;
};

/** A card that loads one sandbox endpoint and frames its chart with title, answer and fields. */
export function ChartCard<Data extends { meta: ChartMeta }>({ load, children, controls, details, compact = false, id, className }: ChartCardProps<Data>) {
  const { resource, retry } = useApiResource(load);
  const articleRef = useRef<HTMLElement>(null);
  // Tells a chat opened from this card when the card scrolls out of view, so the chat can step aside.
  useOriginCardVisibility(id, articleRef);
  const suggestions = id === undefined ? undefined : chartChatSuggestions[id];

  return (
    <article ref={articleRef} id={id} className={cn("chart-surface scroll-mt-6 flex min-w-0 flex-col gap-5 rounded-2xl border bg-background p-5 text-foreground sm:p-6", compact && "gap-3 p-4 sm:p-4", className)}>
      {resource.status === "loading" && <ChartSkeleton />}
      {resource.status === "error" && (
        <LoadError title="This chart couldn't load." message={resource.message} onRetry={retry} className="min-h-56" />
      )}
      {resource.status === "success" && (
        <>
          <ChartHeader meta={resource.data.meta} payloadPath={load.path} compact={compact} ask={id && suggestions ? { id, suggestions } : undefined} />
          {id && suggestions && <CardChatContext id={id} meta={resource.data.meta} />}
          <div className="min-w-0">{children(resource.data)}</div>
        </>
      )}
      {controls}
      {resource.status === "success" && (
        <>
          {details && <div className="min-w-0">{details(resource.data)}</div>}
          <ChartFooter meta={resource.data.meta} compact={compact} />
        </>
      )}
    </article>
  );
}

function ChartSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading chart">
      <Skeleton className="h-5 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="mt-2 h-48 rounded-lg" />
    </div>
  );
}

type CardAsk = { id: string; suggestions: readonly string[] };

/** Title, description and filters. The source badge opens the JSON the chart is drawn from. */
function ChartHeader({ meta, payloadPath, compact, ask }: { meta: ChartMeta; payloadPath: string; compact: boolean; ask?: CardAsk }) {
  return (
    <header className="flex flex-col gap-2">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-base font-semibold tracking-tight">{meta.title}</h3>
        <div className="flex shrink-0 items-center gap-1.5">
          {ask && <AskButton ask={ask} title={meta.title} />}
          <a
            href={apiUrl(payloadPath)}
            target="_blank"
            rel="noreferrer"
            title="Open the JSON this chart is drawn from"
            className="inline-flex shrink-0 items-center gap-0.5 rounded-full bg-foreground px-2 py-0.5 text-[10px] font-medium tracking-wide text-background uppercase transition-opacity hover:opacity-80"
          >
            {meta.source === "synthetic" ? "Synthetic data" : "Mock data"}
            <ArrowUpRight className="size-3" aria-hidden />
          </a>
        </div>
      </div>
      <p className="text-sm text-muted-foreground">{meta.description}</p>
      {!compact && <FilterChips filters={meta.filters} />}
    </header>
  );
}

/** Opens the shell's chat about this card with its questions. Only on the chat pages, inside the app shell. */
function AskButton({ ask, title }: { ask: CardAsk; title: string }) {
  const session = useContext(ChatSessionContext);
  if (!session?.availableHere) return null;

  return (
    <Button
      variant="ghost"
      size="xs"
      aria-label={`Ask about ${title}`}
      title={`Ask about ${title}`}
      onClick={(event) => session.openCard(ask.id, title, [...ask.suggestions], event.currentTarget)}
    >
      <MessageCircleQuestionMark data-icon="inline-start" aria-hidden />
      Ask
    </Button>
  );
}

/**
 * Registers this card's title, filters and specs with the chat, so questions asked from its "Ask" button are about
 * what the card shows now. Renders nothing; clears the context when the card reloads or goes away.
 */
function CardChatContext({ id, meta }: { id: string; meta: ChartMeta }) {
  const setCardContext = useContext(ChatSessionContext)?.setCardContext;
  // Compared as JSON, so a re-render with equal meta doesn't register it again.
  const cardJson = JSON.stringify(withinCaps({ title: meta.title, filters: meta.filters, specs: meta.specs }));

  const card = useMemo<DataChatPageContext | null>(() => {
    const parsed = JSON.parse(cardJson) as DataChatPageContext;
    // The server refuses a blank title, so a card without one sends no context.
    return parsed.title ? parsed : null;
  }, [cardJson]);

  useEffect(() => {
    if (!setCardContext || !card) return;
    setCardContext(id, card);
    return () => setCardContext(id, null);
  }, [setCardContext, id, card]);

  return null;
}

/** The chart's answer, its definitions, and the AR fields it draws on. */
function ChartFooter({ meta, compact }: { meta: ChartMeta; compact: boolean }) {
  const definitions = Object.entries(meta.definitions);
  const reference = (
    <>
      {definitions.length > 0 && (
        <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
          {definitions.map(([term, definition]) => (
            <div key={term}>
              <dt className="inline font-medium">{term}: </dt>
              <dd className="inline text-muted-foreground">{definition}</dd>
            </div>
          ))}
        </dl>
      )}

      <footer className="mt-auto flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <span>Fields used:</span>
        {meta.fields_used.map((field) => (
          <span key={field} className="rounded-md bg-muted px-1.5 py-0.5 text-foreground">
            {field}
          </span>
        ))}
      </footer>
    </>
  );

  return (
    <>
      {meta.takeaway && <AnswerNote takeaway={meta.takeaway} />}
      {compact ? (
        <details className="mt-auto text-xs text-muted-foreground">
          <summary className="cursor-pointer">Definitions and fields</summary>
          <div className="mt-2 flex flex-col gap-2">{reference}</div>
        </details>
      ) : (
        reference
      )}
    </>
  );
}
