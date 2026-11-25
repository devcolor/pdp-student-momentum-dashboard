"use client";

import { Menu as MenuPrimitive } from "@base-ui/react/menu";
import { Settings } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useChartPalette, usePalette } from "@/hooks/use-palette";
import { CHART_PALETTES, PALETTES } from "@/lib/theme";
import { cn } from "@/lib/utils";

type ChoiceOption<Value extends string> = { id: Value; label: string; swatches?: readonly string[] };

type ThemeChoiceProps<Value extends string> = {
  label: string;
  value: Value;
  options: readonly ChoiceOption<Value>[];
  onChange: (value: Value) => void;
};

/** A row of small color squares previewing an option. */
function Swatches({ colors }: { colors: readonly string[] }) {
  return (
    <span aria-hidden className="flex overflow-hidden rounded-sm ring-1 ring-foreground/15">
      {colors.map((color) => (
        <span key={color} className="size-3" style={{ backgroundColor: color }} />
      ))}
    </span>
  );
}

/** A sub-menu of options where exactly one is selected. */
function ThemeChoice<Value extends string>({ label, value, options, onChange }: ThemeChoiceProps<Value>) {
  return (
    <DropdownMenuSub>
      <DropdownMenuSubTrigger>{label}</DropdownMenuSubTrigger>
      <DropdownMenuSubContent className="w-44">
        <DropdownMenuRadioGroup value={value} onValueChange={(next) => onChange(next as Value)}>
          {options.map((option) => (
            <DropdownMenuRadioItem key={option.id} value={option.id} className="gap-2">
              {option.swatches && <Swatches colors={option.swatches} />}
              {option.label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}

/** A menu row with a switch that flips dark mode and leaves the menu open. */
function DarkModeSwitch() {
  const { resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  return (
    <MenuPrimitive.CheckboxItem
      checked={isDark}
      onCheckedChange={(checked) => setTheme(checked ? "dark" : "light")}
      className="flex cursor-default items-center gap-2 rounded-md px-1.5 py-1 text-sm outline-hidden select-none focus:bg-accent focus:text-accent-foreground"
    >
      Dark mode
      <span aria-hidden className={cn("ml-auto flex h-4 w-7 items-center rounded-full p-0.5 transition-colors", isDark ? "bg-primary" : "bg-input")}>
        <span className={cn("size-3 rounded-full transition-transform", isDark ? "translate-x-3 bg-primary-foreground" : "bg-background")} />
      </span>
    </MenuPrimitive.CheckboxItem>
  );
}

/** Gear button that opens the app settings: dark mode, UI theme and chart colors. */
export function SettingsMenu() {
  const [palette, setPalette] = usePalette();
  const [chartPalette, setChartPalette] = useChartPalette();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="ghost" size="icon" aria-label="Settings" title="Settings" />}>
        <Settings />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-40">
        <DropdownMenuGroup>
          <DropdownMenuLabel>Settings</DropdownMenuLabel>
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>Theme</DropdownMenuSubTrigger>
            <DropdownMenuSubContent className="w-36">
              <DarkModeSwitch />
              <ThemeChoice label="UI" value={palette} options={PALETTES} onChange={setPalette} />
              <ThemeChoice label="Charts" value={chartPalette} options={CHART_PALETTES} onChange={setChartPalette} />
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
