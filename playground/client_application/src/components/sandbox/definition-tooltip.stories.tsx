import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, waitFor } from "storybook/test";

import { ChatPanelProvider } from "@/components/app-shell/chat-panel-provider";
import { KeywordChatProvider } from "@/components/chat/keyword-chat";
import { ChatSessionProvider } from "@/components/chat/shell-chat";
import { DefinitionTooltip } from "@/components/sandbox/definition-tooltip";
import { KeywordButton } from "@/components/sandbox/keyword-button";
import { KpiGrid } from "@/components/sandbox/kpi-grid";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { KeywordContext } from "@/services/data-chat";

// The measure's own note, as the server sends it in meta.definitions. Synthetic data.
const RETENTION =
  "Students in the cohort who were enrolled again in the next academic year, or earned a " +
  "credential by then. Spring starters have less time to return than fall starters.";

const KEYWORD: KeywordContext = {
  kind: "measure",
  measure: "Retention",
  cohort: "2024-25",
  rate: 37.9,
  group: null,
  gap_pts: null,
  n: null,
  filtered: false,
  view: "executive-view",
};

/** What the app shell puts above a page: the tooltip context, and the chat a keyword opens. */
function ShellProviders({ children }: { children: React.ReactNode }) {
  return (
    <TooltipProvider>
      <ChatPanelProvider>
        <ChatSessionProvider>
          <KeywordChatProvider scopeOf={(keyword) => keyword.measure ?? ""} suggestionsFor={() => []}>
            {children}
          </KeywordChatProvider>
        </ChatSessionProvider>
      </ChatPanelProvider>
    </TooltipProvider>
  );
}

/** The open tooltip, which renders in a portal on the document rather than inside the story. */
async function openTooltip() {
  return waitFor(() => {
    const popup = document.querySelector('[data-slot="tooltip-content"][data-open]');
    if (!popup) throw new Error("no tooltip is open");
    return popup;
  });
}

/** A measure name as the executive view draws it: explained on hover, chat on click. */
function MeasureName() {
  return (
    <ShellProviders>
      <p className="p-8 text-sm">
        <DefinitionTooltip definition={RETENTION}>
          <KeywordButton keyword={KEYWORD} label="Retention">
            Retention
          </KeywordButton>
        </DefinitionTooltip>
      </p>
    </ShellProviders>
  );
}

const meta = {
  component: MeasureName,
  title: "Components/Sandbox/Definition tooltip",
} satisfies Meta<typeof MeasureName>;
export default meta;
type Story = StoryObj<typeof meta>;

export const ExplainsOnHover: Story = {
  name: "Hovering a measure explains it",
  play: async ({ canvas, userEvent }) => {
    // Nothing is shown until someone asks, so the page still reads as a report.
    await expect(document.querySelector('[data-slot="tooltip-content"]')).toBeNull();

    await userEvent.hover(canvas.getByRole("button", { name: "Ask about Retention" }));

    await expect(await openTooltip()).toHaveTextContent(RETENTION);
  },
};

export const ReachableByKeyboard: Story = {
  name: "Focus explains it too",
  play: async ({ canvas, userEvent }) => {
    await userEvent.tab();

    await expect(canvas.getByRole("button", { name: "Ask about Retention" })).toHaveFocus();
    await expect(await openTooltip()).toHaveTextContent(RETENTION);
  },
};

export const ShowsAPointer: Story = {
  name: "The pointer says it is clickable",
  play: async ({ canvas }) => {
    const name = canvas.getByRole("button", { name: "Ask about Retention" });

    // Tailwind v4's preflight sets button { cursor: default }, so this has to be asked for.
    await expect(getComputedStyle(name).cursor).toBe("pointer");
  },
};

// The KPI grid draws a tile's label through renderLabel, which is where the wiring was missed.
const KPI_RESPONSE = {
  meta: {
    title: "Headline measures",
    description: "Synthetic data.",
    takeaway: null,
    fields_used: ["Retention"],
    filters: [],
    definitions: { Retention: RETENTION },
    source: "synthetic" as const,
    specs: [],
  },
  items: [
    {
      id: "retention",
      label: "Retention",
      unit: "percent" as const,
      value: 37.9,
      secondary_value: null,
      detail: "989 of 2,612 students returned",
      trend: null,
    },
  ],
};

/** A tile drawn by KpiGrid, as the executive view draws it. */
function TileFromTheGrid() {
  return (
    <ShellProviders>
      <div className="p-8">
        <KpiGrid
          load={async () => KPI_RESPONSE}
          placeholderCount={1}
          labelOnTop
          renderLabel={(kpi, kpiMeta) => (
            <DefinitionTooltip definition={kpiMeta.definitions?.[kpi.label]}>
              <KeywordButton keyword={KEYWORD} label={kpi.label}>
                {kpi.label}
              </KeywordButton>
            </DefinitionTooltip>
          )}
        />
      </div>
    </ShellProviders>
  );
}

export const OnAKpiTile: Story = {
  name: "A KPI tile's label explains itself",
  render: () => <TileFromTheGrid />,
  play: async ({ canvas, userEvent }) => {
    await userEvent.hover(await canvas.findByRole("button", { name: "Ask about Retention" }));

    await expect(await openTooltip()).toHaveTextContent(RETENTION);
  },
};
