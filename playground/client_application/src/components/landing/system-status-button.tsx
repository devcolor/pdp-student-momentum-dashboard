"use client";

import { LiveStatusPanel } from "@/components/landing/live-status";
import { PulseDot } from "@/components/landing/pulse-dot";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { useHealthMonitor } from "@/hooks/use-health-monitor";
import { toSystemStatus } from "@/lib/system-status";

/** "System status" button with a live dot; opens the diagram, tracker and sparkline in a dialog. */
export function SystemStatusButton() {
  // Polls here, not in the dialog, so the dot stays live and history builds while it's closed.
  const { history, latest } = useHealthMonitor();
  const status = toSystemStatus(latest);

  return (
    <Dialog>
      <DialogTrigger className={buttonVariants({ variant: "outline", size: "sm" })}>
        <PulseDot state={status.overall} />
        System status
      </DialogTrigger>
      <DialogContent className="sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>System status</DialogTitle>
          <DialogDescription>Live checks from this browser to the server application and its database.</DialogDescription>
        </DialogHeader>
        <LiveStatusPanel history={history} latest={latest} />
      </DialogContent>
    </Dialog>
  );
}
