import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useContext, useEffect, useRef, useState } from "react";
import { expect, mocked, spyOn, waitFor, within } from "storybook/test";

import { ChatPanelProvider } from "@/components/app-shell/chat-panel-provider";
import { Button } from "@/components/ui/button";
import { useChatAvailable } from "@/hooks/use-chat-available";
import { useChatPanel } from "@/hooks/use-chat-panel";
import { ChatSessionContext } from "@/hooks/use-chat-session";
import { useOriginCardVisibility } from "@/hooks/use-origin-card-visibility";
import { routes } from "@/lib/routes";
import type { DataChatAnswer, DataChatPageContext } from "@/services/data-chat";

import { ChatPageContext, specsChars } from "./chat-page-context";
import { ChatLauncher, FloatingChat } from "./floating-chat";
import { ChatSessionProvider } from "./shell-chat";

// Synthetic figures from the shared model; nothing here is a finding about real students.
const ANSWER: DataChatAnswer = {
  message: "Asian women retain at 81.0%, 2.4 points above everyone else. Built on synthetic data.",
  definitions: null,
  query: null,
  results: null,
  tools_used: ["query_results"],
  links: [{ page: "deaggregation", label: "De-aggregation: Asian women", params: { race: "Asian", gender: "F" } }],
  source: "synthetic",
};

// The SQL the server sends with a query_results answer, as mcp/pdp_mcp/results.py spec_sql writes it.
const RESULTS_SQL = [
  "-- Published results (python -m measures.publish): sqlite3 measures/output/success_measures.sqlite",
  "-- Chat shows at most 200 rows.",
  "SELECT group_values, status, numerator, denominator, metric_rate, note",
  "FROM success_measures",
  "WHERE measure = 'retention' AND cohort = 'all' AND group_dimensions = 'gender x race'",
  "ORDER BY group_values;",
].join("\n");

const ANSWER_WITH_RESULTS: DataChatAnswer = {
  ...ANSWER,
  results: {
    tool: "query_results",
    input: { measure: "retention", cohort: "all", group_by: ["race", "gender"] },
    output: { row_count: 1, source: "synthetic" },
    is_error: false,
    sql: RESULTS_SQL,
  },
};

const DEAGGREGATION_SPEC = {
  measure: "retention",
  cohort: "all",
  group_by: ["race", "gender"],
  where: { race: "Asian", gender: "F" },
};

const DEAGGREGATION_PAGE: DataChatPageContext = {
  title: "Outcomes for Asian women",
  filters: ["Race: Asian", "Gender: Female"],
  specs: [DEAGGREGATION_SPEC],
};

// Seventeen specs, one over the server's cap of sixteen, so the server would refuse the question.
const TOO_MANY_SPECS: DataChatPageContext = { ...DEAGGREGATION_PAGE, specs: Array(17).fill(DEAGGREGATION_SPEC) };

// Specs whose size the server measured with spec_json: 119 + 96 + 48 characters.
const SERVER_MEASURED_SPECS: Parameters<typeof specsChars>[0] = [
  { measure: "retention", cohort: "all", group_by: ["race", "gender"], where: { race: "Asian <é>", gender: "F" } },
  { measure: "x", cohort: "c", group_by: ["race"], include: ["rates", "gaps"], min_denominator: 50 },
  { measure: "x", cohort: "c", group_by: ["race"], include: ["rates"], where: {} },
];

const SIZE_STORAGE_KEY = "data-chat-size";

const CARD_A_QUESTIONS = ["How is retention defined on this chart?", "Which group is furthest behind here?"];
const CARD_B_QUESTIONS = ["How is headcount counted on this chart?"];
const CARD_A_PAGE: DataChatPageContext = { title: "Retention by group", filters: ["Cohort: Fall 2024"], specs: [] };
const CARD_B_PAGE: DataChatPageContext = { title: "Headcount by term", filters: [], specs: [] };

/** The shell's launcher and floating chat around a page, as the app shell mounts them on a chat page. */
function ChatShell({ children }: { children: React.ReactNode }) {
  return (
    <ChatPanelProvider>
      <ChatSessionProvider>
        {children}
        <ChatLauncher />
        <FloatingChat />
      </ChatSessionProvider>
    </ChatPanelProvider>
  );
}

/** A stand-in for the page an answer links to: it registers its context with the shell's chat, as c1 does. */
function DeaggregationPage({ page }: { page: DataChatPageContext }) {
  return (
    <section aria-label="De-aggregation page" className="text-sm">
      <h2 className="font-semibold">Outcomes for Asian women</h2>
      <ChatPageContext page={page} />
    </section>
  );
}

/** A stand-in for the page the conversation starts on. */
function ExecutivePage() {
  return (
    <section aria-label="Executive view page" className="text-sm">
      <h2 className="font-semibold">Executive view</h2>
    </section>
  );
}

/** One chat session above a page that changes, as the app shell holds it across route changes. */
function ChatAcrossPages({ page = DEAGGREGATION_PAGE }: { page?: DataChatPageContext }) {
  const [onDeaggregation, setOnDeaggregation] = useState(false);
  return (
    <ChatShell>
      <div className="flex h-[40rem] flex-col gap-4">
        <div>
          <Button variant="outline" onClick={() => setOnDeaggregation(true)}>
            Go to De-aggregation
          </Button>
        </div>
        {/* Keyed, so the page child unmounts and a new one mounts, as on a route change. */}
        {onDeaggregation ? <DeaggregationPage key="deaggregation" page={page} /> : <ExecutivePage key="executive" />}
      </div>
    </ChatShell>
  );
}

/** A stand-in for a chart card with an Ask button: it registers its context and reports when it scrolls away. */
function AskCard({ id, title, questions, page }: { id: string; title: string; questions: string[]; page: DataChatPageContext }) {
  const session = useContext(ChatSessionContext);
  const ref = useRef<HTMLElement>(null);
  useOriginCardVisibility(id, ref);
  const setCardContext = session?.setCardContext;

  useEffect(() => {
    if (!setCardContext) return;
    setCardContext(id, page);
    return () => setCardContext(id, null);
  }, [setCardContext, id, page]);

  return (
    <article ref={ref} id={id} aria-label={title} className="flex h-64 flex-col gap-2 rounded-xl border p-4 text-sm">
      <h2 className="font-semibold">{title}</h2>
      <div>
        <Button
          variant="outline"
          onClick={(event) => session?.openCard(id, title, questions, event.currentTarget)}
        >
          Ask about {title}
        </Button>
      </div>
    </article>
  );
}

/** A stand-in for the topbar's chat toggle (app-topbar.tsx), with its accessible name. */
function TopbarToggle() {
  const { toggleChatPanel } = useChatPanel();
  return (
    <Button variant="outline" aria-label="Toggle chat panel (⌘J)" onClick={toggleChatPanel}>
      Topbar chat toggle
    </Button>
  );
}

/** A page that scrolls inside the shell's main area, with two cards near its top and a long page under them. */
function ScrollingPage() {
  return (
    <ChatShell>
      <div className="flex h-[40rem] flex-col gap-2">
        <div className="flex gap-2">
          <Button variant="outline">Somewhere else on the page</Button>
          <TopbarToggle />
        </div>
        <div data-testid="page-scroller" className="min-h-0 flex-1 overflow-y-auto">
          {/* Clear of the topbar and filter bar band the chat treats as out of view. */}
          <div className="h-40" />
          <div className="flex flex-col gap-4">
            <AskCard id="card-a" title="Retention by group" questions={CARD_A_QUESTIONS} page={CARD_A_PAGE} />
            <AskCard id="card-b" title="Headcount by term" questions={CARD_B_QUESTIONS} page={CARD_B_PAGE} />
          </div>
          <div className="h-[200rem]" />
        </div>
      </div>
    </ChatShell>
  );
}

const meta = {
  component: ChatAcrossPages,
  title: "Components/Chat/Floating chat",
  // The floating chat shows only on the chat pages, and floats as a window from 640px up.
  parameters: { nextjs: { appDirectory: true, navigation: { pathname: routes.sandboxExecutiveView } } },
  globals: { viewport: { value: "tablet", isRotated: false } },
  beforeEach() {
    // Each story starts at the default size.
    localStorage.removeItem(SIZE_STORAGE_KEY);
  },
} satisfies Meta<typeof ChatAcrossPages>;
export default meta;
type Story = StoryObj<typeof meta>;

export const LauncherOpensAndCloses: Story = {
  name: "The launcher opens and closes the chat, and closing puts focus back on it",
  play: async ({ canvas, userEvent }) => {
    const launcher = canvas.getByRole("button", { name: "Open data chat (⌘J)" });
    await expect(launcher).toHaveAttribute("aria-expanded", "false");
    await expect(canvas.queryByRole("dialog", { name: "Data chat" })).not.toBeInTheDocument();

    await userEvent.click(launcher);
    const chat = await canvas.findByRole("dialog", { name: "Data chat" });
    await expect(launcher).toHaveAttribute("aria-expanded", "true");
    await expect(launcher).toHaveAttribute("aria-controls", chat.id);
    // Focus moved into the chat, so a keyboard user can type straight away.
    await waitFor(() => expect(chat).toHaveFocus());

    await userEvent.click(within(chat).getByRole("button", { name: "Minimize chat (⌘J to reopen)" }));
    await expect(canvas.queryByRole("dialog", { name: "Data chat" })).not.toBeInTheDocument();
    await expect(launcher).toHaveFocus();

    // A second click on the launcher closes it too.
    await userEvent.click(launcher);
    await canvas.findByRole("dialog", { name: "Data chat" });
    await userEvent.click(launcher);
    await expect(canvas.queryByRole("dialog", { name: "Data chat" })).not.toBeInTheDocument();
  },
};

export const KeyboardResize: Story = {
  name: "Arrow keys on the grip resize the chat, and the size is kept for next time",
  play: async ({ canvas, userEvent }) => {
    const launcher = canvas.getByRole("button", { name: "Open data chat (⌘J)" });
    await userEvent.click(launcher);
    const chat = await canvas.findByRole("dialog", { name: "Data chat" });
    await expect(chat.style.width).toBe("448px");
    await expect(chat.style.height).toBe("576px");

    // The grip is at the top-left corner, so left and up grow the window.
    within(chat).getByRole("button", { name: "Resize chat" }).focus();
    await userEvent.keyboard("{ArrowLeft}{ArrowLeft}{ArrowUp}");
    await expect(chat.style.width).toBe("480px");
    await expect(chat.style.height).toBe("592px");
    await expect(JSON.parse(localStorage.getItem(SIZE_STORAGE_KEY) ?? "null")).toEqual({ width: 480, height: 592 });

    // Closing unmounts the window, so reopening reads the saved size back.
    await userEvent.click(launcher);
    await userEvent.click(launcher);
    const reopened = await canvas.findByRole("dialog", { name: "Data chat" });
    await expect(reopened.style.width).toBe("480px");
    await expect(reopened.style.height).toBe("592px");
  },
};

export const PhoneSheet: Story = {
  name: "On a phone the chat is a bottom sheet without a resize grip",
  globals: { viewport: { value: "mobile1", isRotated: false } },
  play: async ({ canvas, canvasElement, userEvent }) => {
    await userEvent.click(canvas.getByRole("button", { name: "Open data chat (⌘J)" }));
    const chat = await canvas.findByRole("dialog", { name: "Data chat" });
    await expect(within(chat).queryByRole("button", { name: "Resize chat" })).not.toBeInTheDocument();

    // Full width and on the bottom edge.
    const box = chat.getBoundingClientRect();
    const view = canvasElement.ownerDocument.defaultView!;
    await expect(Math.round(box.width)).toBe(view.innerWidth);
    await expect(Math.round(box.bottom)).toBe(view.innerHeight);
  },
};

export const LinksKeepTheConversation: Story = {
  name: "An answer links to its page, and the conversation survives the page change",
  play: async ({ canvas, userEvent }) => {
    const requests = spyOn(globalThis, "fetch").mockImplementation(async () => Response.json(ANSWER));

    await userEvent.click(canvas.getByRole("button", { name: "Open data chat (⌘J)" }));
    const chat = within(await canvas.findByRole("dialog", { name: "Data chat" }));
    await userEvent.type(chat.getByRole("textbox", { name: "Your question" }), "Retention for Asian women?{Enter}");

    // The server names the page and its picks; the client builds the address, same tab.
    const link = await chat.findByRole("link", { name: "De-aggregation: Asian women" });
    await expect(link).toHaveAttribute("href", "/sandbox/deaggregation?race=Asian&gender=F");
    await expect(link).not.toHaveAttribute("target");

    await userEvent.click(canvas.getByRole("button", { name: "Go to De-aggregation" }));
    await canvas.findByRole("region", { name: "De-aggregation page" });

    // The turns live above the page, so the new page shows the same conversation.
    await expect(chat.getByText("Retention for Asian women?")).toBeVisible();
    await expect(chat.getByText(/Asian women retain at 81.0%/)).toBeVisible();

    // A follow-up asked on the new page sends the earlier turns and that page's context.
    await userEvent.type(chat.getByRole("textbox", { name: "Your question" }), "And by term?{Enter}");
    await waitFor(() => expect(requests).toHaveBeenCalledTimes(2));
    const body = JSON.parse(String(requests.mock.calls[1][1]?.body));
    await expect(body.page).toEqual(DEAGGREGATION_PAGE);
    await expect(body.turns).toHaveLength(2);
    requests.mockRestore();
  },
};

export const ResultsShowTheirSql: Story = {
  name: "A published-results answer shows the builder's SQL, with a button to copy it",
  play: async ({ canvas, userEvent }) => {
    const requests = spyOn(globalThis, "fetch").mockImplementation(async () => Response.json(ANSWER_WITH_RESULTS));
    const writeText = spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);

    await userEvent.click(canvas.getByRole("button", { name: "Open data chat (⌘J)" }));
    const chat = within(await canvas.findByRole("dialog", { name: "Data chat" }));
    await userEvent.type(chat.getByRole("textbox", { name: "Your question" }), "Retention for Asian women?{Enter}");

    await userEvent.click(await chat.findByText("Published results: query_results"));
    await expect(chat.getByText(/FROM success_measures/)).toBeVisible();
    await expect(chat.getByText(/sqlite3 measures\/output\/success_measures\.sqlite/)).toBeVisible();

    await userEvent.click(chat.getByRole("button", { name: "Copy SQL" }));
    await expect(writeText).toHaveBeenCalledWith(RESULTS_SQL);
    await expect(await chat.findByRole("button", { name: "Copied" })).toBeVisible();
    writeText.mockRestore();
    requests.mockRestore();
  },
};

export const OversizedSpecsAreLeftOut: Story = {
  name: "Specs over the server's caps are left out, so the question still goes",
  args: { page: TOO_MANY_SPECS },
  play: async ({ canvas, userEvent }) => {
    // The client measures specs as the server does, escapes included.
    await expect(specsChars(SERVER_MEASURED_SPECS)).toBe(119 + 96 + 48);

    const requests = spyOn(globalThis, "fetch").mockImplementation(async () => Response.json(ANSWER));
    await userEvent.click(canvas.getByRole("button", { name: "Go to De-aggregation" }));
    await userEvent.click(canvas.getByRole("button", { name: "Open data chat (⌘J)" }));
    const chat = within(await canvas.findByRole("dialog", { name: "Data chat" }));
    await userEvent.type(chat.getByRole("textbox", { name: "Your question" }), "What is on this page?{Enter}");

    await waitFor(() => expect(requests).toHaveBeenCalledTimes(1));
    const body = JSON.parse(String(requests.mock.calls[0][1]?.body));
    await expect(body.page).toEqual({ ...TOO_MANY_SPECS, specs: [] });
    requests.mockRestore();
  },
};

export const HidesWithItsCard: Story = {
  name: "A chat opened from a card hides while the card is scrolled away, and the launcher brings it back",
  render: () => <ScrollingPage />,
  play: async ({ canvas, userEvent }) => {
    const requests = spyOn(globalThis, "fetch").mockImplementation(async () => Response.json(ANSWER));
    const scroller = canvas.getByTestId("page-scroller");
    const launcher = canvas.getByRole("button", { name: "Open data chat (⌘J)" });

    await userEvent.click(canvas.getByRole("button", { name: "Ask about Retention by group" }));
    const dialog = await canvas.findByRole("dialog", { name: "Data chat" });
    const chat = within(dialog);
    await userEvent.type(chat.getByRole("textbox", { name: "Your question" }), "Retention for Asian women?{Enter}");
    await chat.findByText(/Asian women retain at 81.0%/);
    // The question went with the card's own context.
    const body = JSON.parse(String(requests.mock.calls[0][1]?.body));
    await expect(body.page).toEqual(CARD_A_PAGE);

    // It hides even with a half-typed question in it, and focus moves to the launcher rather than being lost.
    const textbox = chat.getByRole("textbox", { name: "Your question" });
    await userEvent.type(textbox, "And by gend");
    await expect(textbox).toHaveFocus();
    scroller.scrollTop = scroller.scrollHeight;
    await waitFor(() => expect(dialog).not.toBeVisible());
    await expect(launcher).toHaveFocus();
    await expect(launcher).toHaveAttribute("aria-expanded", "false");
    await expect(launcher).toHaveAttribute("title", expect.stringMatching(/hidden/));

    // Scrolled back, it returns with the same conversation and the draft.
    scroller.scrollTop = 0;
    await waitFor(() => expect(dialog).toBeVisible());
    await expect(chat.getByText("Retention for Asian women?")).toBeVisible();
    await expect(textbox).toHaveValue("And by gend");

    // The launcher shows a hidden chat and pins it: scrolling away no longer hides it.
    scroller.scrollTop = scroller.scrollHeight;
    await waitFor(() => expect(dialog).not.toBeVisible());
    await userEvent.click(launcher);
    await waitFor(() => expect(dialog).toBeVisible());
    await waitFor(() => expect(dialog).toHaveFocus());
    await userEvent.click(canvas.getByRole("button", { name: "Somewhere else on the page" }));
    scroller.scrollTop = 0;
    scroller.scrollTop = scroller.scrollHeight;
    await new Promise((resolve) => setTimeout(resolve, 400));
    await expect(dialog).toBeVisible();
    requests.mockRestore();
  },
};

export const AnotherCardCarriesOn: Story = {
  name: "Ask on another card carries on the conversation, pointed at the new card",
  render: () => <ScrollingPage />,
  play: async ({ canvas, userEvent }) => {
    const requests = spyOn(globalThis, "fetch").mockImplementation(async () => Response.json(ANSWER));

    await userEvent.click(canvas.getByRole("button", { name: "Ask about Retention by group" }));
    const chat = within(await canvas.findByRole("dialog", { name: "Data chat" }));
    for (const question of CARD_A_QUESTIONS) await expect(chat.getByRole("button", { name: question })).toBeVisible();
    await userEvent.type(chat.getByRole("textbox", { name: "Your question" }), "Retention for Asian women?{Enter}");
    await chat.findByText(/Asian women retain at 81.0%/);

    // The first card's questions went away once a question was sent.
    await expect(chat.queryByRole("button", { name: CARD_A_QUESTIONS[0] })).not.toBeInTheDocument();

    await userEvent.click(canvas.getByRole("button", { name: "Ask about Headcount by term" }));
    // Same turns, the new card's scope line and questions, and its context goes with the next question.
    await expect(chat.getByText("Retention for Asian women?")).toBeVisible();
    await expect(chat.getByText("Headcount by term")).toBeVisible();
    for (const question of CARD_B_QUESTIONS) await expect(chat.getByRole("button", { name: question })).toBeVisible();
    await userEvent.type(chat.getByRole("textbox", { name: "Your question" }), "And by term?{Enter}");
    await waitFor(() => expect(requests).toHaveBeenCalledTimes(2));
    // Sending a question puts the suggestions away until the next card click.
    await chat.findAllByText(/Asian women retain at 81.0%/).then((answers) => expect(answers).toHaveLength(2));
    await expect(chat.queryByRole("button", { name: CARD_B_QUESTIONS[0] })).not.toBeInTheDocument();
    const body = JSON.parse(String(requests.mock.calls[1][1]?.body));
    await expect(body.page).toEqual(CARD_B_PAGE);
    await expect(body.turns).toHaveLength(2);
    requests.mockRestore();
  },
};

export const TopbarShowsHiddenChat: Story = {
  name: "The topbar toggle shows a hidden chat instead of closing it unseen",
  render: () => <ScrollingPage />,
  play: async ({ canvas, userEvent }) => {
    const scroller = canvas.getByTestId("page-scroller");
    await userEvent.click(canvas.getByRole("button", { name: "Ask about Retention by group" }));
    const dialog = await canvas.findByRole("dialog", { name: "Data chat" });

    scroller.scrollTop = scroller.scrollHeight;
    await waitFor(() => expect(dialog).not.toBeVisible());
    await userEvent.click(canvas.getByRole("button", { name: "Toggle chat panel (⌘J)" }));
    // Shown and pinned, not closed: still the same mounted window, and it stays on further scrolling.
    await waitFor(() => expect(dialog).toBeVisible());
    scroller.scrollTop = 0;
    scroller.scrollTop = scroller.scrollHeight;
    await new Promise((resolve) => setTimeout(resolve, 400));
    await expect(dialog).toBeVisible();

    // Shown, the toggle closes it as before.
    await userEvent.click(canvas.getByRole("button", { name: "Toggle chat panel (⌘J)" }));
    await expect(canvas.queryByRole("dialog", { name: "Data chat" })).not.toBeInTheDocument();
  },
};

export const ShortcutCloseReturnsFocus: Story = {
  name: "Closing with ⌘J puts focus back on what opened the chat",
  render: () => <ScrollingPage />,
  play: async ({ canvas, userEvent }) => {
    const ask = canvas.getByRole("button", { name: "Ask about Retention by group" });
    await userEvent.click(ask);
    const chat = within(await canvas.findByRole("dialog", { name: "Data chat" }));
    await userEvent.click(chat.getByRole("textbox", { name: "Your question" }));

    await userEvent.keyboard("{Control>}j{/Control}");
    await expect(canvas.queryByRole("dialog", { name: "Data chat" })).not.toBeInTheDocument();
    await expect(ask).toHaveFocus();
  },
};

export const ChatOff: Story = {
  name: "With the server's AI chat off, the chat says how to turn it on and has no input",
  beforeEach() {
    // As /health reports when the server has no ANTHROPIC_API_KEY.
    mocked(useChatAvailable).mockReturnValue(false);
  },
  play: async ({ canvas, userEvent }) => {
    const requests = spyOn(globalThis, "fetch");

    await userEvent.click(canvas.getByRole("button", { name: "Open data chat (⌘J)" }));
    const chat = within(await canvas.findByRole("dialog", { name: "Data chat" }));

    await expect(chat.getByText("AI chat is off")).toBeVisible();
    await expect(chat.getByText(/add ANTHROPIC_API_KEY to playground\/server_application\/.env.development.local/)).toBeVisible();
    // Nothing to send from, so nothing can reach the model routes.
    await expect(chat.queryByRole("textbox", { name: "Your question" })).not.toBeInTheDocument();
    await expect(requests).not.toHaveBeenCalled();
    requests.mockRestore();
  },
};
