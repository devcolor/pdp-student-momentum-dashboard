import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, mocked, spyOn } from "storybook/test";

import { ChatPanelProvider } from "@/components/app-shell/chat-panel-provider";
import { KeywordButton } from "@/components/sandbox/keyword-button";
import { useChatAvailable } from "@/hooks/use-chat-available";
import { routes } from "@/lib/routes";
import type { KeywordContext } from "@/services/data-chat";

import { FloatingChat } from "./floating-chat";
import { KeywordChatProvider } from "./keyword-chat";
import { ChatSessionProvider } from "./shell-chat";

// Synthetic figures from the shared model; nothing here is a finding about real students.
const RETENTION_GAP: KeywordContext = {
  kind: "group",
  measure: "Retention",
  group: "Part-time students",
  cohort: "2024-25",
  rate: 43.2,
  gap_pts: -15.5,
  n: 6040,
  filtered: false,
  view: "executive-view",
};

const SUGGESTIONS = [
  "How does Retention for Part-time students compare with the other groups on the same breakdown?",
  "Is the Retention gap for Part-time students larger than the gaps by race or by gender?",
  "What are the other published measures for Part-time students?",
  "Which other groups are behind on Retention?",
];

const scopeOf = (keyword: KeywordContext) => `${keyword.measure} · ${keyword.group} · Fall 2024 entry`;
const suggestionsFor = () => SUGGESTIONS;

/** A page with one clickable number on it, under the app shell's floating chat, which opens on a click. */
function PageWithAKeyword() {
  return (
    <ChatPanelProvider>
      <ChatSessionProvider>
        <div className="h-[40rem]">
          <KeywordChatProvider scopeOf={scopeOf} suggestionsFor={suggestionsFor}>
            <p className="text-sm">
              Retention for{" "}
              <KeywordButton keyword={RETENTION_GAP} label="Retention for Part-time students">
                Part-time students
              </KeywordButton>{" "}
              is 43.2%.
            </p>
          </KeywordChatProvider>
        </div>
        <FloatingChat />
      </ChatSessionProvider>
    </ChatPanelProvider>
  );
}

const meta = {
  component: PageWithAKeyword,
  title: "Components/Chat/Keyword chat",
  // The floating chat shows only on the chat pages, and floats as a window from 640px up.
  parameters: { nextjs: { appDirectory: true, navigation: { pathname: routes.sandboxExecutiveView } } },
  globals: { viewport: { value: "tablet", isRotated: false } },
} satisfies Meta<typeof PageWithAKeyword>;
export default meta;
type Story = StoryObj<typeof meta>;

export const OpensWithSuggestions: Story = {
  name: "A click opens the chat with suggestions, and calls no model",
  play: async ({ canvas, userEvent }) => {
    // Watched, not replaced, so a request would still go through and be visible here.
    const requests = spyOn(globalThis, "fetch");
    // Closed until something is clicked, so a page that includes it costs nothing.
    await expect(canvas.queryByRole("dialog", { name: "Data chat" })).not.toBeInTheDocument();

    await userEvent.click(canvas.getByRole("button", { name: "Ask about Retention for Part-time students" }));

    const panel = await canvas.findByRole("dialog", { name: "Data chat" });
    await expect(panel).toBeVisible();
    // The chat says what it is scoped to, so the question is not floating free of the page.
    await expect(canvas.getByText("Retention · Part-time students · Fall 2024 entry")).toBeVisible();
    for (const suggestion of SUGGESTIONS) {
      await expect(canvas.getByRole("button", { name: suggestion })).toBeVisible();
    }
    // The suggestions come from a lookup table, so opening the chat asks the model nothing.
    await expect(requests).not.toHaveBeenCalled();
    requests.mockRestore();
  },
};

export const ClosesAgain: Story = {
  name: "Close puts the page back",
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(canvas.getByRole("button", { name: "Ask about Retention for Part-time students" }));
    await canvas.findByRole("dialog", { name: "Data chat" });

    await userEvent.click(canvas.getByRole("button", { name: "Minimize chat (⌘J to reopen)" }));

    await expect(canvas.queryByRole("dialog", { name: "Data chat" })).not.toBeInTheDocument();
  },
};

export const EscapeCloses: Story = {
  name: "Escape closes it, and a click opens it again",
  play: async ({ canvas, userEvent }) => {
    const keyword = canvas.getByRole("button", { name: "Ask about Retention for Part-time students" });
    await userEvent.click(keyword);
    await canvas.findByRole("dialog", { name: "Data chat" });

    // The click moved focus into the chat, so Escape reaches it without another click.
    await userEvent.keyboard("{Escape}");
    await expect(canvas.queryByRole("dialog", { name: "Data chat" })).not.toBeInTheDocument();

    await userEvent.click(keyword);
    await canvas.findByRole("dialog", { name: "Data chat" });
    await expect(canvas.getByText("Retention · Part-time students · Fall 2024 entry")).toBeVisible();
  },
};

export const CloseReturnsFocus: Story = {
  name: "Closing puts focus back on the keyword that opened it",
  play: async ({ canvas, userEvent }) => {
    const keyword = canvas.getByRole("button", { name: "Ask about Retention for Part-time students" });
    await userEvent.click(keyword);
    await canvas.findByRole("dialog", { name: "Data chat" });

    await userEvent.click(canvas.getByRole("button", { name: "Minimize chat (⌘J to reopen)" }));
    await expect(keyword).toHaveFocus();

    await userEvent.click(keyword);
    await canvas.findByRole("dialog", { name: "Data chat" });
    await userEvent.keyboard("{Escape}");
    await expect(keyword).toHaveFocus();
  },
};

export const HeaderButtonsDoNotOverlap: Story = {
  name: "Close sits beside Start over, and neither sits on the resize grip",
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(canvas.getByRole("button", { name: "Ask about Retention for Part-time students" }));
    await canvas.findByRole("dialog", { name: "Data chat" });

    const close = canvas.getByRole("button", { name: "Minimize chat (⌘J to reopen)" }).getBoundingClientRect();
    const startOver = canvas.getByRole("button", { name: "Start over" }).getBoundingClientRect();
    const grip = canvas.getByRole("button", { name: "Resize chat" }).getBoundingClientRect();

    // All are really on screen, so an overlap would be a real one and not zero-size boxes.
    for (const box of [close, startOver, grip]) await expect(box.width).toBeGreaterThan(0);
    await expect(overlaps(close, startOver)).toBe(false);
    await expect(overlaps(grip, close)).toBe(false);
    await expect(overlaps(grip, startOver)).toBe(false);
  },
};

/** Whether two boxes on screen share any area. */
function overlaps(a: DOMRect, b: DOMRect): boolean {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}

export const ChatOff: Story = {
  name: "With the server's AI chat off, a click opens the off notice instead of suggestions",
  beforeEach() {
    // As /health reports when the server has no ANTHROPIC_API_KEY.
    mocked(useChatAvailable).mockReturnValue(false);
  },
  play: async ({ canvas, userEvent }) => {
    const requests = spyOn(globalThis, "fetch");

    await userEvent.click(canvas.getByRole("button", { name: "Ask about Retention for Part-time students" }));

    await canvas.findByRole("dialog", { name: "Data chat" });
    await expect(canvas.getByText("AI chat is off")).toBeVisible();
    // No suggestion or input to click, so the model is never asked.
    await expect(canvas.queryByRole("button", { name: SUGGESTIONS[0] })).not.toBeInTheDocument();
    await expect(canvas.queryByRole("textbox", { name: "Your question" })).not.toBeInTheDocument();
    await expect(requests).not.toHaveBeenCalled();
    requests.mockRestore();
  },
};
