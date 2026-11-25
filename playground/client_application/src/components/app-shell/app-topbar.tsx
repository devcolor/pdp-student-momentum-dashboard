"use client";

import { PanelRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { SettingsMenu } from "@/components/settings-menu";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { proofOfConceptItems } from "@/content/sandbox-examples";
import { useChatPanel } from "@/hooks/use-chat-panel";
import { routes } from "@/lib/routes";

/** The current page's place in the sandbox, shown only on proof-of-concept pages. */
function TopbarBreadcrumbs() {
  const pathname = usePathname();
  const page = proofOfConceptItems.find((item) => item.href === pathname);
  if (!page) return null;

  return (
    <>
      <Separator orientation="vertical" className="my-4" />
      <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-sm">
        <Link href={routes.sandbox} className="text-muted-foreground transition-colors hover:text-foreground">
          Sandbox
        </Link>
        <span aria-hidden className="text-muted-foreground">
          /
        </span>
        <span aria-current="page" className="truncate font-medium">
          {page.label}
        </span>
      </nav>
    </>
  );
}

/** Above the page: the sidebar toggle and breadcrumbs on the left; the chat panel toggle and settings menu on the right. */
export function AppTopbar() {
  const { isChatPanelAvailable, isChatPanelOpen, toggleChatPanel } = useChatPanel();

  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b px-3 sm:px-4">
      <SidebarTrigger aria-label="Toggle sidebar (⌘B)" title="Toggle sidebar (⌘B)" />
      <TopbarBreadcrumbs />
      <div className="ml-auto flex items-center gap-1">
        {isChatPanelAvailable && (
          <Button
            variant="ghost"
            size="icon"
            aria-label="Toggle chat panel (⌘J)"
            title="Toggle chat panel (⌘J)"
            aria-pressed={isChatPanelOpen}
            onClick={toggleChatPanel}
          >
            <PanelRight />
          </Button>
        )}
        <SettingsMenu />
      </div>
    </header>
  );
}
