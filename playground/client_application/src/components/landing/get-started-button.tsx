"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { useUniversity } from "@/components/university-toggle";
import { buttonVariants } from "@/components/ui/button";
import { startPageFor } from "@/content/sandbox-examples";

/** The landing page's main button: opens the top page for the university picked in the toggle, in this tab. */
export function GetStartedButton() {
  const [university] = useUniversity();
  return (
    <Link href={startPageFor(university)} className={buttonVariants({ size: "lg" })}>
      Get started
      <ArrowRight aria-hidden />
    </Link>
  );
}
