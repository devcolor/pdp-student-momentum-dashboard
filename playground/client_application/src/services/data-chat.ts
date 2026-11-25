/** Ask the server's /sandbox/chat endpoint a question. Types come from the server's OpenAPI schema. */

import { apiRequest } from "@/lib/api-client";
import type { Schemas } from "@/lib/api/types";

/** One tool call: on success output is the tool's answer, on error it is { error: { code, message, details } }. */
export type ToolResult = Schemas["ToolResult"];

/**
 * message is Markdown. query is the last aggregate query (only groups of 10 or more students);
 * results is the last published-results lookup.
 */
export type DataChatAnswer = Schemas["SuggestResponse"];

/** A page that charts what an answer read: the page's name, its link text and picker values. Never a URL. */
export type PageLink = Schemas["PageLink"];

/** One earlier turn of the conversation, sent back so a follow-up keeps its subject. */
export type ChatTurn = Schemas["Turn"];

/** The thing on a page a question came from. The server checks every name in it. */
export type KeywordContext = Schemas["KeywordContext"];

/**
 * The page the user is asking from: its title, the filter chips they see, and the query_results
 * specs behind its numbers (empty when the page computes them live).
 */
export type DataChatPageContext = Schemas["PageContext"];

const DATA_CHAT_PATH = "/sandbox/chat/suggest";

// The model may take several rounds of tool calls, far longer than the default 10 seconds.
const DATA_CHAT_TIMEOUT_MS = 90_000;

// The server's caps, which it rejects a request for exceeding. Trimming here keeps a long
// conversation going instead of failing it.
export const MAX_TURNS = 10;
export const MAX_TURN_CHARS = 8_000;
export const MAX_HISTORY_CHARS = 12_000;

/**
 * The turns to send: the newest complete exchanges that fit inside the server's caps.
 *
 * Turns have to alternate from user to assistant, so they are dropped a whole exchange at a time,
 * oldest first. An over-long turn is cut rather than dropping the exchange it belongs to.
 */
export function turnsWithinCaps(turns: ChatTurn[]): ChatTurn[] {
  const cut = turns.map((turn) =>
    turn.content.length <= MAX_TURN_CHARS ? turn : { ...turn, content: turn.content.slice(0, MAX_TURN_CHARS) },
  );
  // Exchanges, so dropping one never leaves a user turn without its answer.
  const exchanges: ChatTurn[][] = [];
  for (let at = 0; at + 1 < cut.length; at += 2) exchanges.push([cut[at], cut[at + 1]]);

  let kept = exchanges;
  const tooLong = () =>
    kept.flat().length > MAX_TURNS || kept.flat().reduce((total, turn) => total + turn.content.length, 0) > MAX_HISTORY_CHARS;
  while (kept.length > 0 && tooLong()) kept = kept.slice(1);
  return kept.flat();
}

/**
 * The assistant's answer to one question, asked from a page when page is given.
 * Throws ApiError when the server can't answer.
 */
export function sendDataChatQuestion(
  question: string,
  turns: ChatTurn[] = [],
  context: KeywordContext | null = null,
  page: DataChatPageContext | null = null,
): Promise<DataChatAnswer> {
  const body: Schemas["SuggestRequest"] = { prompt: question, turns: turnsWithinCaps(turns) };
  if (context) body.context = context;
  if (page) body.page = page;
  return apiRequest<DataChatAnswer>(DATA_CHAT_PATH, {
    method: "POST",
    json: body,
    timeoutMs: DATA_CHAT_TIMEOUT_MS,
  });
}
