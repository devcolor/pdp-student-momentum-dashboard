import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  // On Vercel, the site and API run as two services, and /_next/image answers 404 there.
  // The only images are the brand logos in public/brand/, already sized for the web, so serve them as they are.
  images: { unoptimized: true },
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
