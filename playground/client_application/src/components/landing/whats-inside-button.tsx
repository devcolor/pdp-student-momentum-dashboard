"use client";

import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export const WHATS_INSIDE_TITLE = "What's inside";

/** "What's inside" button that opens the stack overview in a dialog. The page passes the overview as children. */
export function WhatsInsideButton({ children }: { children: React.ReactNode }) {
  return (
    <Dialog>
      <DialogTrigger className={buttonVariants({ variant: "outline", size: "lg" })}>{WHATS_INSIDE_TITLE}</DialogTrigger>
      <DialogContent className="sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold tracking-tight">{WHATS_INSIDE_TITLE}</DialogTitle>
          <DialogDescription>Two applications that deploy on their own and talk only over HTTP.</DialogDescription>
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  );
}
