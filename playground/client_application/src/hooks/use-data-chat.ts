"use client";

import { useCallback, useMemo, useRef, useState } from "react";

import { describeError } from "@/lib/errors";
import {
  type ChatTurn,
  type DataChatAnswer,
  type DataChatPageContext,
  type KeywordContext,
  sendDataChatQuestion,
} from "@/services/data-chat";

export type DataChatMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; answer: DataChatAnswer }
  | { id: string; role: "error"; text: string };

/**
 * The turns to send with the next question: the exchanges that finished with an answer.
 *
 * A question whose reply was an error is dropped with its error, because the server needs the
 * turns to alternate from user to assistant and there is no answer to pair that question with.
 */
export function completedTurns(messages: DataChatMessage[]): ChatTurn[] {
  const turns: ChatTurn[] = [];
  let at = 0;
  while (at + 1 < messages.length) {
    const question = messages[at];
    const answer = messages[at + 1];
    if (question.role === "user" && answer.role === "assistant") {
      turns.push({ role: "user", content: question.text });
      turns.push({ role: "assistant", content: answer.answer.message });
      at += 2;
    } else {
      at += 1;
    }
  }
  return turns;
}

/**
 * The data chat's conversation: like useChat, but each reply is the server's answer or its error.
 * Questions carry the keyword or the page they were asked from, whichever is given.
 */
export function useDataChat(keyword: KeywordContext | null = null, page: DataChatPageContext | null = null) {
  const [chatMessages, setChatMessages] = useState<DataChatMessage[]>([]);
  const [isAwaitingReply, setAwaitingReply] = useState(false);
  // Each question gets a number, so a reply is dropped if Start over came first.
  const latestQuestionNumber = useRef(0);

  const submitQuestion = useCallback(
    async (question: string) => {
      const trimmedQuestion = question.trim();
      if (!trimmedQuestion) return;
      const questionNumber = ++latestQuestionNumber.current;
      const turns = completedTurns(chatMessages);
      setChatMessages((previous) => [...previous, { id: crypto.randomUUID(), role: "user", text: trimmedQuestion }]);
      setAwaitingReply(true);

      const reply: DataChatMessage = await sendDataChatQuestion(trimmedQuestion, turns, keyword, page)
        .then((answer) => ({ id: crypto.randomUUID(), role: "assistant" as const, answer }))
        .catch((error: unknown) => ({ id: crypto.randomUUID(), role: "error" as const, text: describeError(error) }));
      if (questionNumber !== latestQuestionNumber.current) return;
      setAwaitingReply(false);
      setChatMessages((previous) => [...previous, reply]);
    },
    [chatMessages, keyword, page],
  );

  const startNewChat = useCallback(() => {
    latestQuestionNumber.current += 1;
    setAwaitingReply(false);
    setChatMessages([]);
  }, []);

  // Memoized, so the shell's session doesn't change on renders where nothing in the conversation did.
  return useMemo(
    () => ({ chatMessages, isAwaitingReply, submitQuestion, startNewChat }),
    [chatMessages, isAwaitingReply, submitQuestion, startNewChat],
  );
}
