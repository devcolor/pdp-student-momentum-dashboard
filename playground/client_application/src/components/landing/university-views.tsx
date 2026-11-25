"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { UniversityToggle, useUniversity } from "@/components/university-toggle";
import { groupByRole, landingSectionsFor, type SandboxExample } from "@/content/sandbox-examples";

const FOCUS_RING = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

/** The university toggle, then the view cards for that pick (one card of every page under dev/color), split by role. */
export function UniversityViews() {
  const [university, chooseUniversity] = useUniversity();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 id="views-heading" className="text-2xl font-semibold tracking-tight">
          Get Started
        </h2>
        <UniversityToggle value={university} onChange={chooseUniversity} itemClassName="min-w-20" />
      </div>
      <ul className="flex flex-col gap-4">
        {landingSectionsFor(university).map((section) => (
          <li
            key={section.heading}
            className="@container flex flex-col gap-4 rounded-2xl border bg-card p-6 transition-colors duration-200 hover:border-primary/60 hover:bg-primary/[0.04]"
          >
            <h3 className="text-lg font-semibold tracking-tight">{section.heading}</h3>
            {groupByRole(section.items).map((group) => (
              <div key={group.label} className="flex flex-col gap-2 border-t pt-4">
                <h4 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{group.label}</h4>
                <ul className="grid gap-x-5 gap-y-2 @md:grid-cols-2">
                  {group.items.map((item) => (
                    <li key={item.href}>
                      <PageLink item={item} />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A link to one page, with its icon and one-line description. Opens in a new tab, like the rest of the landing page. */
function PageLink({ item }: { item: SandboxExample }) {
  return (
    <Link
      href={item.href}
      target="_blank"
      rel="noreferrer"
      className={`group/page -mx-2 flex items-start gap-3 rounded-lg p-2 transition-colors hover:bg-primary/10 ${FOCUS_RING}`}
    >
      <item.icon aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground transition-colors group-hover/page:text-primary" />
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-sm font-medium transition-colors group-hover/page:text-primary">{item.label}</span>
        <span className="text-xs text-muted-foreground">{item.description}</span>
      </span>
      <ArrowRight
        aria-hidden
        className="mt-0.5 size-4 shrink-0 text-primary opacity-0 transition-opacity group-hover/page:opacity-100 group-focus-visible/page:opacity-100"
      />
    </Link>
  );
}
