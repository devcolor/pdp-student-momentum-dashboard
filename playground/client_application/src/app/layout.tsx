import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { ThemeProvider } from "@/components/theme-provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { brand } from "@/content/brand";
import { CHART_PALETTE_STORAGE_KEY, PALETTE_STORAGE_KEY } from "@/lib/theme";
import { cn } from "@/lib/utils";

import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

// Runs before first paint so saved UI and chart themes don't flash the defaults on load.
const APPLY_SAVED_THEMES = `try{var d=document.documentElement.dataset,p=localStorage.getItem("${PALETTE_STORAGE_KEY}"),c=localStorage.getItem("${CHART_PALETTE_STORAGE_KEY}");if(p)d.palette=p;if(c)d.chartPalette=c}catch(e){}`;

export const metadata: Metadata = {
  // Pages set only their own title, e.g. "Sandbox", which becomes "Sandbox · Playground".
  title: { default: brand.name, template: `%s · ${brand.name}` },
  description: brand.tagline,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // next-themes sets the theme class on <html> before React hydrates.
    <html lang="en" className={cn("font-sans antialiased", inter.variable)} suppressHydrationWarning>
      <body>
        <script dangerouslySetInnerHTML={{ __html: APPLY_SAVED_THEMES }} />
        <ThemeProvider>
          <TooltipProvider>{children}</TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
