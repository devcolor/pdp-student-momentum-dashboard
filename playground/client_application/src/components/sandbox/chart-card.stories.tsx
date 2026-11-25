import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useContext, useState } from "react";
import { expect, spyOn, waitFor, within } from "storybook/test";

import { ChatPanelProvider } from "@/components/app-shell/chat-panel-provider";
import { FloatingChat } from "@/components/chat/floating-chat";
import { ChatSessionProvider } from "@/components/chat/shell-chat";
import { Button } from "@/components/ui/button";
import { chartChatSuggestions } from "@/content/chart-chat-suggestions";
import { ChatSessionContext } from "@/hooks/use-chat-session";
import type { ChartMeta, SandboxLoader } from "@/lib/sandbox";
import { routes } from "@/lib/routes";

import { ChartCard } from "./chart-card";

// Synthetic figures; nothing here is a finding about real students.
const META: ChartMeta = {
  title: "Retention gaps by group",
  description: "Each group's fall-to-fall retention against everyone else.",
  takeaway: null,
  fields_used: ["Retention", "Race"],
  filters: ["Cohort: All"],
  definitions: {},
  source: "synthetic",
  specs: [{ measure: "retention", cohort: "all", group_by: ["race"] }],
};

/** A loader that answers at once without a request, so a fetch spy only sees the chat. */
const LOAD: SandboxLoader<{ meta: ChartMeta }> = Object.assign(async () => ({ meta: META }), { path: "/sandbox/example" });

// Every ChartCard id in the app's pages, read from their source, so a registry key can't name a card that isn't there.
const PAGE_SOURCES = import.meta.glob<string>("../../app/**/*.tsx", { query: "?raw", import: "default", eager: true });
const CARD_IDS = new Set(
  Object.values(PAGE_SOURCES).flatMap((source) => [...source.matchAll(/<ChartCard\s[^>]*?id="([^"]+)"/g)].map((match) => match[1])),
);

/** The card on a chat page, with a picker inside it, as the de-aggregation and aid pages have. */
function CardOnChatPage({ id }: { id?: string }) {
  const [picked, setPicked] = useState("Retention");
  return (
    <ChartCard
      id={id}
      load={LOAD}
      controls={
        <Button variant="outline" onClick={() => setPicked("Persistence")}>
          Measure: {picked}
        </Button>
      }
    >
      {() => <p className="text-sm">Chart body</p>}
    </ChartCard>
  );
}

/** Shows what the card registered with the session, so stories can check it without asking the model. */
function SessionProbe() {
  const session = useContext(ChatSessionContext);
  return <output aria-label="Chat origin">{session?.origin?.kind === "card" ? session.origin.cardId : "none"}</output>;
}

/** The card inside the app shell's chat session, with the floating chat it opens. */
function WithSession({ id }: { id?: string }) {
  return (
    <ChatPanelProvider>
      <ChatSessionProvider>
        <div className="flex max-w-xl flex-col gap-4">
          <CardOnChatPage id={id} />
          <SessionProbe />
        </div>
        <FloatingChat />
      </ChatSessionProvider>
    </ChatPanelProvider>
  );
}

const meta = {
  component: WithSession,
  title: "Components/Sandbox/Chart card",
  // The chat is only on its five pages, so the session reads this path.
  parameters: { nextjs: { appDirectory: true, navigation: { pathname: routes.sandboxExecutiveView } } },
} satisfies Meta<typeof WithSession>;
export default meta;
type Story = StoryObj<typeof meta>;

export const NoAskWithoutSession: Story = {
  name: "No Ask button outside the app shell's chat session",
  render: () => <CardOnChatPage id="exec-equity-gaps" />,
  play: async ({ canvas }) => {
    await canvas.findByRole("heading", { name: META.title });
    await expect(canvas.queryByRole("button", { name: /^Ask about/ })).toBeNull();
  },
};

export const NoAskWithoutRegisteredId: Story = {
  name: "No Ask button for a card without questions",
  args: { id: "not-a-registered-card" },
  play: async ({ canvas }) => {
    await canvas.findByRole("heading", { name: META.title });
    await expect(canvas.queryByRole("button", { name: /^Ask about/ })).toBeNull();
  },
};

export const AskOpensWithQuestions: Story = {
  name: "Ask opens the chat with the card's questions and calls no model",
  args: { id: "exec-equity-gaps" },
  play: async ({ canvas, userEvent }) => {
    const requests = spyOn(globalThis, "fetch");
    await userEvent.click(await canvas.findByRole("button", { name: `Ask about ${META.title}` }));

    const chat = within(await within(document.body).findByRole("dialog", { name: "Data chat" }));
    for (const question of chartChatSuggestions["exec-equity-gaps"]) {
      await expect(await chat.findByText(question)).toBeVisible();
    }
    await expect(canvas.getByRole("status", { name: "Chat origin" })).toHaveTextContent("exec-equity-gaps");
    await expect(requests).not.toHaveBeenCalled();
    requests.mockRestore();
  },
};

export const PickerDoesNotOpenChat: Story = {
  name: "A picker inside the card doesn't open the chat",
  args: { id: "exec-equity-gaps" },
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: "Measure: Retention" }));
    await canvas.findByRole("button", { name: "Measure: Persistence" });
    await waitFor(() => expect(within(document.body).queryByRole("dialog", { name: "Data chat" })).toBeNull());
    await expect(canvas.getByRole("status", { name: "Chat origin" })).toHaveTextContent("none");
  },
};

export const EveryRegistryKeyIsACard: Story = {
  name: "Every card with questions is a ChartCard id on a page",
  render: () => <CardOnChatPage />,
  play: async () => {
    // Guards the glob itself: if it read nothing, the check below would pass on an empty set.
    await expect(CARD_IDS.has("exec-equity-gaps")).toBe(true);
    for (const id of Object.keys(chartChatSuggestions)) {
      await expect([...CARD_IDS], `"${id}" in chart-chat-suggestions.ts`).toContain(id);
    }
    for (const questions of Object.values(chartChatSuggestions)) await expect(questions).toHaveLength(3);
  },
};
