import { BrandWatermark } from "@/components/brand-logo";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { brand } from "@/content/brand";
import { cn } from "@/lib/utils";

type PageShellProps = {
  children: React.ReactNode;
  className?: string;
  /** Open the header's links in a new tab, as the landing page does. */
  linksInNewTab?: boolean;
  /** Show the header's "System status" button. */
  showSystemStatus?: boolean;
  /** Show the brand watermark, pinned to the bottom right of the window. */
  showWatermark?: boolean;
};

/** Header, a full-height main area and footer. Every page sits inside one; `className` styles its main. */
export function PageShell({ children, className, linksInNewTab, showSystemStatus, showWatermark }: PageShellProps) {
  return (
    // isolate keeps the watermark's negative z-index above the page background but below the content.
    <div className="isolate flex min-h-svh flex-col">
      {showWatermark && brand.logo && <BrandWatermark logos={brand.logo} className="fixed -z-10" />}
      <SiteHeader linksInNewTab={linksInNewTab} showSystemStatus={showSystemStatus} />
      <main className={cn("flex flex-1 flex-col", className)}>{children}</main>
      <SiteFooter />
    </div>
  );
}
