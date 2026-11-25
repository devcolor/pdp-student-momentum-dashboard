"use client";

import { Collapsible } from "@base-ui/react/collapsible";
import { ChevronRight, House, PanelsTopLeft } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { BrandLockup } from "@/components/brand-logo";
import { PulseDot } from "@/components/landing/pulse-dot";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import { UniversityToggle, useUniversity } from "@/components/university-toggle";
import { brand } from "@/content/brand";
import { SANDBOX_EXAMPLES_HEADING, type SandboxExample, sandboxNavItems, viewSectionsFor } from "@/content/sandbox-examples";
import { useHealthMonitor } from "@/hooks/use-health-monitor";
import { routes } from "@/lib/routes";
import { toSystemStatus } from "@/lib/system-status";

// The dot only needs to be roughly current, so it checks far less often than the landing page's tracker.
const STATUS_DOT_INTERVAL_MS = 30_000;

const workbenchItems: SandboxExample[] = [
  { label: "AR Workbench", description: "The AR Workbench.", href: routes.workbench, icon: PanelsTopLeft },
];

/** The left navigation. Collapses to icons with ⌘B or its edge; on a phone it slides over the page. */
export function AppSidebar() {
  const pathname = usePathname();
  const { isMobile, setOpenMobile } = useSidebar();
  // On a phone the sidebar covers the page: close it once a link is chosen.
  const closeSidebarOnMobile = () => isMobile && setOpenMobile(false);
  // The university follows the UI theme, so picking a theme in settings also switches the sidebar.
  const [university, chooseUniversity] = useUniversity();

  return (
    <Sidebar variant="floating" collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              size="lg"
              className="group-data-[collapsible=icon]:justify-center"
              tooltip={brand.name}
              aria-label={`${brand.name} home`}
              render={<Link href={routes.home} onClick={closeSidebarOnMobile} />}
            >
              <BrandLockup className="group-data-[collapsible=icon]:hidden" />
              {/* The logos are too wide for the collapsed sidebar, so it shows the square app icon instead. */}
              {brand.productLogo ? (
                <Image
                  src={brand.productLogo.icon}
                  alt=""
                  width={32}
                  height={32}
                  className="hidden size-8 rounded-md group-data-[collapsible=icon]:block"
                />
              ) : (
                <House className="hidden group-data-[collapsible=icon]:block" />
              )}
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        {/* Hidden when collapsed to icons. Same colors as the selected page link; dev/color has no --sidebar-active, so it falls back. */}
        <div className="px-2 pt-2 group-data-[collapsible=icon]:hidden">
          <UniversityToggle
            value={university}
            onChange={chooseUniversity}
            className="w-full"
            itemClassName="flex-1 aria-pressed:bg-[var(--sidebar-active,var(--sidebar-primary))] aria-pressed:text-[var(--sidebar-active-foreground,var(--sidebar-primary-foreground))]"
          />
        </div>
        {viewSectionsFor(university).map((section) => (
          <NavSection
            key={section.heading}
            heading={section.heading}
            defaultOpen={section.defaultOpen}
            items={section.items}
            pathname={pathname}
            onNavigate={closeSidebarOnMobile}
          />
        ))}
        <NavSection heading="Workbench" items={workbenchItems} pathname={pathname} onNavigate={closeSidebarOnMobile} />
        <NavSection
          heading={SANDBOX_EXAMPLES_HEADING}
          items={sandboxNavItems}
          pathname={pathname}
          onNavigate={closeSidebarOnMobile}
        />
      </SidebarContent>

      <SidebarFooter>
        <ApiConnectionStatus />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}

/** A sidebar section that opens and closes, closed unless defaultOpen is set. */
function NavSection({
  heading,
  defaultOpen = false,
  items,
  pathname,
  onNavigate,
}: {
  heading: string;
  defaultOpen?: boolean;
  items: SandboxExample[];
  pathname: string;
  onNavigate: () => void;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const { state } = useSidebar();
  // Collapsed to icons there is no heading to click, so every section's icons stay visible.
  const isOpen = open || state === "collapsed";

  return (
    <Collapsible.Root open={isOpen} onOpenChange={setOpen}>
      <SidebarGroup>
        <SidebarGroupLabel
          className="cursor-pointer text-sm font-semibold hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
          render={<Collapsible.Trigger />}
        >
          <span className="flex-1 text-left">{heading}</span>
          <ChevronRight className={`transition-transform ${open ? "rotate-90" : ""}`} />
        </SidebarGroupLabel>
        <Collapsible.Panel>
          <SidebarMenu className="gap-1">
            {items.map((item) => (
              <SidebarMenuItem key={item.href}>
                <SidebarMenuButton
                  className="h-10 rounded-xl"
                  isActive={isActiveRoute(pathname, item.href)}
                  tooltip={item.label}
                  render={<Link href={item.href} onClick={onNavigate} />}
                >
                  <item.icon />
                  <span>{item.label}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </Collapsible.Panel>
      </SidebarGroup>
    </Collapsible.Root>
  );
}

/** True on the link's page; the Workbench link also stays lit on its sub-pages. */
function isActiveRoute(pathname: string, href: string): boolean {
  if (href === routes.workbench) return pathname === href || pathname.startsWith(`${href}/`);
  return pathname === href;
}

/** "All systems connected", from polling the server's /health. */
function ApiConnectionStatus() {
  const { latest } = useHealthMonitor({ intervalMs: STATUS_DOT_INTERVAL_MS, historySize: 1 });
  const systemStatus = toSystemStatus(latest);
  return (
    <div className="flex items-center gap-2.5 px-2 py-1.5 text-xs text-muted-foreground" title={systemStatus.label}>
      <PulseDot state={systemStatus.overall} className="ml-0.75" />
      <span className="truncate group-data-[collapsible=icon]:hidden">{systemStatus.label}</span>
    </div>
  );
}
