import { Heart } from "lucide-react";
import Image from "next/image";

import { brand } from "@/content/brand";

/** The product's icon and full name, and who made it. */
export function SiteFooter() {
  return (
    <footer className="px-6 py-8 text-center text-xs text-muted-foreground sm:px-10">
      {brand.productLogo && (
        <Image
          src={brand.productLogo.icon}
          alt=""
          width={16}
          height={16}
          className="mr-1.5 inline size-4 -translate-y-px rounded-[4px]"
        />
      )}
      {brand.name} · {brand.summary}
      {brand.madeBy && (
        <>
          {" "}
          made with{" "}
          <Heart
            className="inline size-3 -translate-y-px fill-foreground text-foreground"
            aria-label="love"
            role="img"
          />{" "}
          by {brand.madeBy}
        </>
      )}
    </footer>
  );
}
