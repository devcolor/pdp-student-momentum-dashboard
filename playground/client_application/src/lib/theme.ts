export const PALETTE_STORAGE_KEY = "palette";
export const CHART_PALETTE_STORAGE_KEY = "chart-palette";

/** UI themes in the settings menu. Each id other than dev/color has a block in globals.css. */
export const PALETTES = [
  { id: "devcolor", label: "dev/color", swatches: ["#171717", "#737373", "#E5E5E5"] },
  { id: "university-1", label: "MVSU", swatches: ["#003B24", "#00713D", "#F6AB00"] },
  { id: "university-2", label: "CCAC", swatches: ["#A6192E", "#FFFFFF", "#003057"] },
] as const;

/** The options in the university toggle, each tied to its UI theme. dev/color shows every university's views. */
export const UNIVERSITIES = [
  { id: "devcolor", label: "dev/color", palette: "devcolor" },
  { id: "mvsu", label: "MVSU", palette: "university-1" },
  { id: "ccac", label: "CCAC", palette: "university-2" },
] as const;

export type UniversityId = (typeof UNIVERSITIES)[number]["id"];

/** Chart color options in the settings menu. They apply under every UI theme. */
export const CHART_PALETTES = [
  { id: "color", label: "Color", swatches: ["#256ABF", "#EB6834", "#1BAF7A"] },
  { id: "grayscale", label: "Grayscale", swatches: ["#0A0A0A", "#5B5B5B", "#ABABAB"] },
  { id: "okabe-ito", label: "Okabe-Ito", swatches: ["#E69F00", "#56B4E9", "#009E73"] },
  { id: "ibm", label: "IBM", swatches: ["#648FFF", "#785EF0", "#DC0067"] },
  { id: "paul-tol", label: "Paul Tol Muted", swatches: ["#CC6677", "#332288", "#DDCC77"] },
  { id: "paul-tol-vibrant", label: "Paul Tol Vibrant", swatches: ["#0077BB", "#33BBEE", "#009988"] },
  { id: "paul-tol-light", label: "Paul Tol Light", swatches: ["#77AADD", "#EE8866", "#44BB99"] },
  { id: "wong", label: "Wong", swatches: ["#E69F00", "#56B4E9", "#009E73"] },
  { id: "microbiome", label: "Microbiome", swatches: ["#003F5C", "#FF7C43", "#665191"] },
  { id: "dark-high-contrast", label: "Dark High-Contrast", swatches: ["#00F5D4", "#FFB703", "#7B2CBF"] },
] as const;

export type PaletteId = (typeof PALETTES)[number]["id"];
export type ChartPaletteId = (typeof CHART_PALETTES)[number]["id"];

export const DEFAULT_PALETTE: PaletteId = "devcolor";
export const DEFAULT_CHART_PALETTE: ChartPaletteId = "color";

/** A known UI theme id, or the default for a missing or stale saved value. */
export function toPaletteId(value: string | null | undefined): PaletteId {
  const match = PALETTES.find((palette) => palette.id === value);
  return match ? match.id : DEFAULT_PALETTE;
}

/** The university whose theme is active, or null under a theme no university uses. */
export function universityForPalette(palette: PaletteId): UniversityId | null {
  const match = UNIVERSITIES.find((university) => university.palette === palette);
  return match ? match.id : null;
}

/** A known chart option id, or the default for a missing or stale saved value. */
export function toChartPaletteId(value: string | null | undefined): ChartPaletteId {
  const match = CHART_PALETTES.find((palette) => palette.id === value);
  return match ? match.id : DEFAULT_CHART_PALETTE;
}
