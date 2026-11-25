/** Name, wording and logo used across the site. Copies of Playground change them here. */

import type { PaletteId } from "@/lib/theme";

export type Logo = {
  src: string;
  alt: string;
  width: number;
  height: number;
  /** Badge behind the artwork: match the logo file's own background, or "none" for a transparent logo. */
  background: "black" | "white" | "none";
  /** Black artwork on transparent: drawn white on a black badge and in dark mode, black otherwise. */
  monochrome?: boolean;
  /**
   * Single-color copy for the page background: only its shape is used. `color` keeps a school's own
   * color; leave it out to use the theme's primary color.
   */
  watermark: { src: string; width: number; height: number; color?: string };
};

/**
 * The product's own logo. The wordmark is two black-on-transparent layers on the same canvas, the
 * letters and the accent, so each can take a theme color (see --product-ink in globals.css).
 */
export type ProductLogo = {
  alt: string;
  letters: string;
  accent: string;
  width: number;
  height: number;
  /** Square, full-color app icon: the collapsed sidebar and the footer. app/icon.svg is the tab's copy. */
  icon: string;
};

type Brand = {
  name: string;
  /** Drawn in place of the name, beside the university's logo. Set to null to show the name instead. */
  productLogo: ProductLogo | null;
  /** What the name stands for, under it on the landing page. */
  fullName: string;
  /** Under the name on the landing page, and the description search engines show. */
  tagline: string;
  /** Footer: "{name} · {summary} made with ♥ by {madeBy}". */
  summary: string;
  /** Footer credit. Set to null to hide it. */
  madeBy: string | null;
  /** The school's logo, one per UI theme, beside the product's and on the landing page. Null leaves it out. */
  logo: Record<PaletteId, Logo> | null;
};

/**
 * Logos to choose from. To add one: put the file and a white-on-transparent watermark copy in
 * public/brand/, add an entry here with their pixel sizes, then pick it for a theme in `brand.logo`.
 */
export const logos = {
  devcolor: {
    // Vector, so it stays sharp at the landing page's large size.
    src: "/brand/devcolor-logo.svg",
    alt: "dev/color",
    width: 554,
    height: 176,
    background: "black",
    monochrome: true,
    watermark: { src: "/brand/devcolor-watermark.png", width: 251, height: 62 },
  },
  mvsu: {
    src: "/brand/mvsu-logo.png",
    alt: "Mississippi Valley State University",
    width: 898,
    height: 640,
    // White, so the green artwork stays visible on the theme's green sidebar.
    background: "white",
    watermark: { src: "/brand/mvsu-watermark.png", width: 738, height: 521, color: "#00703C" },
  },
  ccac: {
    src: "/brand/ccac-logo.png",
    alt: "Community College of Allegheny County",
    width: 900,
    height: 320,
    // The artwork is already a red block, so it needs no badge.
    background: "none",
    watermark: { src: "/brand/ccac-watermark.png", width: 864, height: 282, color: "#AB182B" },
  },
} satisfies Record<string, Logo>;

export const brand: Brand = {
  name: "SYMPA",
  // The full kit, and how these files were cut from it, is in brand-originals/.
  productLogo: {
    alt: "SYMPA",
    letters: "/brand/sympa-wordmark-letters.svg",
    accent: "/brand/sympa-wordmark-accent.svg",
    width: 1110,
    height: 284,
    icon: "/brand/sympa-icon.svg",
  },
  fullName: "Student Yearly Momentum & Performance Analytics",
  tagline: "Measuring what matters, moving students forward",
  summary: "Student Yearly Momentum & Performance Analytics",
  madeBy: "dev/color",
  // The logo follows the UI theme picked in the settings menu.
  logo: {
    devcolor: logos.devcolor,
    "university-1": logos.mvsu,
    "university-2": logos.ccac,
  },
};
