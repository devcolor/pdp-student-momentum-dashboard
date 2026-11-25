"use client";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { usePalette } from "@/hooks/use-palette";
import { UNIVERSITIES, type UniversityId, universityForPalette } from "@/lib/theme";

/** The picked university, from the UI theme, and a function that switches both. */
export function useUniversity() {
  const [palette, setPalette] = usePalette();
  const university = universityForPalette(palette);
  const chooseUniversity = (id: UniversityId) => {
    const match = UNIVERSITIES.find((item) => item.id === id);
    if (match) setPalette(match.palette);
  };
  return [university, chooseUniversity] as const;
}

/** dev/color, MVSU or CCAC: picks which views are listed and the app's theme. */
export function UniversityToggle({
  value,
  onChange,
  className,
  itemClassName,
}: {
  value: UniversityId | null;
  onChange: (id: UniversityId) => void;
  className?: string;
  itemClassName?: string;
}) {
  return (
    <ToggleGroup
      aria-label="University"
      variant="outline"
      spacing={0}
      className={className}
      value={value ? [value] : []}
      onValueChange={(values) => {
        const next = values[0] as UniversityId | undefined;
        if (next) onChange(next);
      }}
    >
      {UNIVERSITIES.map((university) => (
        <ToggleGroupItem key={university.id} value={university.id} className={itemClassName}>
          {university.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
