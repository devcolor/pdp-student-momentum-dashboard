import Image from "next/image";

import { brand, type Logo, type ProductLogo } from "@/content/brand";
import type { PaletteId } from "@/lib/theme";
import { cn } from "@/lib/utils";

const BADGE_CLASSES: Record<Logo["background"], string> = {
  black: "bg-black ring-1 ring-foreground/10",
  white: "bg-white ring-1 ring-foreground/10",
  none: "",
};

type LogoSize = "header" | "feature";

// header: 24px tall in a top bar, on its badge. feature: fills its column with no badge, as on the landing page.
const SIZE_CLASSES: Record<LogoSize, { badge: string; image: string }> = {
  header: { badge: "h-8 items-center rounded-md px-1.5", image: "h-6 w-auto max-w-none" },
  feature: { badge: "w-full items-center justify-center rounded-2xl", image: "h-auto w-full" },
};

// CSS picks the logo from <html data-palette>, so the right one shows before React loads.
// With nothing saved, <html> has no data-palette and the default theme applies.
const SHOW_FOR_PALETTE: Record<PaletteId, string> = {
  devcolor: "hidden [html:not([data-palette])_&]:flex [html[data-palette=devcolor]_&]:flex",
  "university-1": "hidden [html[data-palette=university-1]_&]:flex",
  "university-2": "hidden [html[data-palette=university-2]_&]:flex",
};

/** How to color a black-on-transparent logo: white on a black header badge, else white only in dark mode. */
function monochromeClass(size: LogoSize, background: Logo["background"]) {
  if (size === "header" && background === "black") return "invert";
  return "dark:invert";
}

type BrandLogoProps = {
  logos: Record<PaletteId, Logo>;
  size?: LogoSize;
  className?: string;
};

/** The brand logo, showing the one picked for the active UI theme. */
export function BrandLogo({ logos, size = "header", className }: BrandLogoProps) {
  const entries = Object.entries(logos) as [PaletteId, Logo][];
  return (
    <span className={cn("flex shrink-0", className)}>
      {entries.map(([paletteId, logo]) => (
        <span
          key={paletteId}
          className={cn(
            SIZE_CLASSES[size].badge,
            // The badge gives a small logo contrast in a colored top bar; a large one doesn't need it.
            size === "header" && BADGE_CLASSES[logo.background],
            SHOW_FOR_PALETTE[paletteId],
          )}
        >
          <Image
            src={logo.src}
            alt={logo.alt}
            width={logo.width}
            height={logo.height}
            className={cn(SIZE_CLASSES[size].image, logo.monochrome && monochromeClass(size, logo.background))}
            loading="eager"
          />
        </span>
      ))}
    </span>
  );
}

/** One single-color layer of the wordmark: the file gives the shape, `color` the paint. */
function WordmarkLayer({ src, color }: { src: string; color: string }) {
  return (
    <span
      className="absolute inset-0"
      style={{
        backgroundColor: color,
        maskImage: `url(${src})`,
        maskSize: "contain",
        maskRepeat: "no-repeat",
        maskPosition: "center",
      }}
    />
  );
}

/** The product's wordmark: its own colors on a plain page, one color on a university's sidebar. */
export function ProductWordmark({ logo, className }: { logo: ProductLogo; className?: string }) {
  return (
    <span
      role="img"
      aria-label={logo.alt}
      className={cn("relative inline-block shrink-0", className)}
      style={{ aspectRatio: `${logo.width} / ${logo.height}` }}
    >
      <WordmarkLayer src={logo.letters} color="var(--product-ink)" />
      <WordmarkLayer src={logo.accent} color="var(--product-accent)" />
    </span>
  );
}

/** Top left of every page: the product's wordmark (or name), a thin rule, then the active theme's logo. */
export function BrandLockup({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      {brand.productLogo ? (
        <ProductWordmark logo={brand.productLogo} className="h-6" />
      ) : (
        <span className="text-sm font-semibold tracking-tight">{brand.name}</span>
      )}
      {brand.logo && (
        <>
          <span aria-hidden className="h-6 w-px bg-current opacity-25" />
          <BrandLogo logos={brand.logo} />
        </>
      )}
    </span>
  );
}

/**
 * A large, faint copy of the active theme's logo at the bottom right of its container.
 * Pass `className="fixed"` to pin it to the window instead.
 */
export function BrandWatermark({ logos, className }: { logos: Record<PaletteId, Logo>; className?: string }) {
  const entries = Object.entries(logos) as [PaletteId, Logo][];
  return (
    <div aria-hidden className={cn("pointer-events-none absolute right-8 bottom-8 w-[min(42vw,30rem)]", className)}>
      {entries.map(([paletteId, { watermark }]) => (
        // The shape comes from the mask; the color is the logo's own, or the theme's primary.
        <div
          key={paletteId}
          className={cn("w-full bg-primary opacity-[0.05] dark:opacity-[0.07]", SHOW_FOR_PALETTE[paletteId])}
          style={{
            backgroundColor: watermark.color,
            aspectRatio: `${watermark.width} / ${watermark.height}`,
            maskImage: `url(${watermark.src})`,
            maskSize: "contain",
            maskRepeat: "no-repeat",
            maskPosition: "bottom right",
          }}
        />
      ))}
    </div>
  );
}
