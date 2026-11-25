import Link from "next/link";

import { BrandLockup } from "@/components/brand-logo";
import { SystemStatusButton } from "@/components/landing/system-status-button";
import { SettingsMenu } from "@/components/settings-menu";
import { brand } from "@/content/brand";
import { env } from "@/lib/env";
import { routes } from "@/lib/routes";

type SiteHeaderProps = {
  linksInNewTab?: boolean;
  /** Show the "System status" button, as the landing page does. */
  showSystemStatus?: boolean;
};

/** Product and university logos (link home), Sandbox link, environment badge, optional status button and settings menu. */
export function SiteHeader({ linksInNewTab = false, showSystemStatus = false }: SiteHeaderProps) {
  const newTab = linksInNewTab ? { target: "_blank", rel: "noreferrer" } : {};
  return (
    <header className="flex items-center justify-between px-6 py-5 sm:px-10">
      <Link href={routes.home} {...newTab} aria-label={`${brand.name} home`}>
        <BrandLockup />
      </Link>
      <div className="flex items-center gap-3">
        {env.sandboxEnabled && (
          <Link href={routes.sandbox} {...newTab} className="text-sm font-medium underline-offset-4 hover:underline">
            Sandbox
          </Link>
        )}
        <span className="hidden rounded-full border px-2.5 py-0.5 text-[11px] tracking-widest text-muted-foreground uppercase sm:inline">
          {env.appEnv}
        </span>
        {showSystemStatus && <SystemStatusButton />}
        <SettingsMenu />
      </div>
    </header>
  );
}
