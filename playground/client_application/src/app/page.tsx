import { BrandLogo, ProductWordmark } from "@/components/brand-logo";
import { GetStartedButton } from "@/components/landing/get-started-button";
import { UniversityViews } from "@/components/landing/university-views";
import { PageShell } from "@/components/page-shell";
import { brand } from "@/content/brand";
import { env } from "@/lib/env";

/**
 * Two columns on wide screens: the logo and name in the left third, centered beside the university's views in the
 * rest. Narrower screens stack the columns.
 */
export default function HomePage() {
  return (
    <PageShell className="px-6 pt-2 pb-28 sm:px-10 sm:pt-4 lg:px-[10%]" linksInNewTab showSystemStatus showWatermark>
      {/* items-center lines the logo and name up with the middle of the cards. */}
      <div className="grid w-full items-start gap-16 lg:grid-cols-3 lg:items-center lg:gap-10 xl:gap-16">
        <div className="flex flex-col gap-10">
          {brand.logo && <BrandLogo logos={brand.logo} size="feature" className="w-full max-w-lg" />}

          <section className="flex flex-col gap-4 motion-safe:animate-fade-up">
            <h1 className="text-5xl font-semibold tracking-tighter sm:text-6xl lg:text-5xl 2xl:text-6xl">
              {brand.productLogo ? (
                // Letters fill about 70% of the wordmark's height, so this is near the name's size.
                <ProductWordmark logo={brand.productLogo} className="block h-[1.2em]" />
              ) : (
                brand.name
              )}
            </h1>
            <p className="text-lg font-medium text-balance">{brand.fullName}</p>
            <p className="text-base text-balance text-muted-foreground">{brand.tagline}</p>
            {env.sandboxEnabled && (
              <div className="mt-2">
                <GetStartedButton />
              </div>
            )}
          </section>
        </div>

        {/* The proof-of-concept pages live under /sandbox, so they're hidden when it is. */}
        {env.sandboxEnabled && (
          <section
            aria-labelledby="views-heading"
            className="lg:col-span-2 motion-safe:animate-fade-up motion-safe:[animation-delay:150ms]"
          >
            <UniversityViews />
          </section>
        )}
      </div>
    </PageShell>
  );
}
