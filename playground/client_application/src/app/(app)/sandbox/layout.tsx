import { notFound } from "next/navigation";

import { KeepHashInView } from "@/components/sandbox/keep-hash-in-view";
import { env } from "@/lib/env";

/** Every page under /sandbox: a 404 in production where the sandbox is off, and the page's width and padding. */
export default function SandboxLayout({ children }: LayoutProps<"/sandbox">) {
  if (!env.sandboxEnabled) notFound();

  // A page opts out of the centered column by putting data-full-width on an element.
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-20 px-6 pt-12 pb-24 sm:px-10 sm:pt-16 has-[[data-full-width]]:max-w-none has-[[data-full-width]]:px-4 sm:has-[[data-full-width]]:px-4">
      {children}
      {/* Links from the home page's view buttons land on a section; keep it in view while charts load. */}
      <KeepHashInView />
    </div>
  );
}
