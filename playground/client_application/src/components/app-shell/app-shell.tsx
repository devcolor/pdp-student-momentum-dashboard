"use client";

import { AppSidebar } from "@/components/app-shell/app-sidebar";
import { AppTopbar } from "@/components/app-shell/app-topbar";
import { ChatPanelProvider } from "@/components/app-shell/chat-panel-provider";
import { BrandWatermark } from "@/components/brand-logo";
import { ChatLauncher, FloatingChat } from "@/components/chat/floating-chat";
import { ChatSessionProvider } from "@/components/chat/shell-chat";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { brand } from "@/content/brand";
import { useChatPanel } from "@/hooks/use-chat-panel";
import { useChatPanelDocks } from "@/hooks/use-chat-panel-docks";
import { useChatSession } from "@/hooks/use-chat-session";

/**
 * The app shell, like an editor: a collapsible sidebar on the left, the page in the middle, and the chat panel on
 * the right. On smaller screens the chat panel slides over the page, and on phones the sidebar does too. The chat
 * panel is empty for now, and a shell style can leave it out (see content/app-shells.ts). The pages with the data
 * chat float it over the page instead (see floating-chat.tsx), and the panel's toggle opens that.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <ChatPanelProvider>
      <ChatSessionProvider>
        <SidebarProvider className="h-svh overflow-hidden">
          <AppSidebar />
          <SidebarInset className="min-w-0 overflow-hidden">
            <AppShellPanels>{children}</AppShellPanels>
          </SidebarInset>
        </SidebarProvider>
        <ChatLauncher />
        <FloatingChat />
      </ChatSessionProvider>
    </ChatPanelProvider>
  );
}

/**
 * The page and the chat panel. The panel group always renders, so the page keeps its place in the tree and doesn't
 * remount (refetching charts, losing filters) when the screen crosses the docking width. Only the chat part switches
 * between a docked panel and a Sheet.
 */
function AppShellPanels({ children }: { children: React.ReactNode }) {
  const chatPanelDocks = useChatPanelDocks();
  const { isChatPanelOpen, setChatPanelOpen } = useChatPanel();
  // On the data chat's pages the toggle opens the floating chat, so the empty panel stays out of the way.
  const showsPanel = !useChatSession().availableHere;

  return (
    <>
      <ResizablePanelGroup orientation="horizontal" id="app-shell">
        <ResizablePanel id="main" minSize="40" className="min-w-0">
          <AppMainArea>{children}</AppMainArea>
        </ResizablePanel>
        {showsPanel && chatPanelDocks && isChatPanelOpen && (
          <>
            <ResizableHandle withHandle />
            <ResizablePanel id="chat" defaultSize="28" minSize="20" maxSize="50">
              <div className="h-full p-2 pl-1">
                <section aria-label="Chat" className="h-full rounded-2xl border bg-card shadow-sm" />
              </div>
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>
      {showsPanel && !chatPanelDocks && (
        <Sheet open={isChatPanelOpen} onOpenChange={setChatPanelOpen}>
          <SheetContent side="right" className="gap-0 p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-md">
            <SheetTitle className="sr-only">Chat</SheetTitle>
            <SheetDescription className="sr-only">The chat panel, empty for now.</SheetDescription>
          </SheetContent>
        </Sheet>
      )}
    </>
  );
}

/** The top bar above the scrolling page, with the brand watermark fixed behind the page. */
function AppMainArea({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex h-full min-w-0 flex-col">
      {brand.logo && <BrandWatermark logos={brand.logo} />}
      <AppTopbar />
      {/* Relative so the page paints above the watermark. */}
      <div className="relative min-h-0 flex-1 overflow-y-auto">{children}</div>
    </div>
  );
}
