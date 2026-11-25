import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect } from "storybook/test";

import type { HomeStateRow } from "./data";
import { stateLabel } from "./home-state-map";

// Shaped like the endpoint's rows. Synthetic data, not real students.
const ROWS: { name: string; row: HomeStateRow | undefined }[] = [
  { name: "Illinois", row: { state: "IL", n: 2247, share: 86 } },
  { name: "Indiana", row: { state: "IN", n: 71, share: 2.7 } },
  { name: "Arizona", row: { state: "AZ", n: null, share: null } },
  { name: "Alaska", row: undefined },
];

/** The hover text for each kind of state, which the map puts in a <title>. */
function StateHoverText() {
  return (
    <ul className="p-8 text-sm">
      {ROWS.map(({ name, row }) => (
        <li key={name}>{stateLabel(name, row)}</li>
      ))}
    </ul>
  );
}

const meta = {
  component: StateHoverText,
  title: "Components/Sandbox/Home state hover",
} satisfies Meta<typeof StateHoverText>;
export default meta;
type Story = StoryObj<typeof meta>;

export const ShowsTheShare: Story = {
  name: "Hover gives the share, since the map already prints the count",
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Illinois: 86% of students")).toBeVisible();
    await expect(canvas.getByText("Indiana: 2.7% of students")).toBeVisible();
    // The count is on the state itself, so repeating it in the hover said nothing new.
    await expect(canvas.queryByText(/2,247 students/)).not.toBeInTheDocument();
  },
};

export const SaysWhenAStateIsHidden: Story = {
  name: "A hidden state says so instead of a share",
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Arizona: hidden to protect small counts")).toBeVisible();
    await expect(canvas.getByText("Alaska: no students")).toBeVisible();
  },
};
