# Brand originals

The logo files as they were received, kept so the web copies can be remade. The site doesn't serve
this folder; it serves the copies in `public/brand/`, which `src/content/brand.ts` lists.

| Original | Web copies in `public/brand/` | How they were made |
| --- | --- | --- |
| `mvsu-logo-gradient.png` (1500×1500, transparent) | `mvsu-logo.png`, `mvsu-watermark.png` | Cropped to the artwork and scaled to 640 px tall. The watermark keeps only the green, as a white-on-transparent shape. |
| `ccac-logo-on-red.jpg` (1200×630 social banner) | `ccac-logo.png`, `ccac-watermark.png` | Cropped to the white-bordered box. The watermark keeps only the white lettering and border. |
| `devcolor-logo-on-white.png` (554×554, black on white) | `devcolor-logo.svg` | Cropped to the artwork, scaled up 4×, traced to vector paths with potrace, black on transparent. `monochrome` in `brand.ts` turns it white on the header's black badge and in dark mode. The watermark, `devcolor-watermark.png`, came with the earlier logo. |

The SYMPA kit is the product's own logo, which sits beside the school's. Use these files for slides and
documents too: `sympa-primary.svg` on light backgrounds, `sympa-reversed.svg` on dark ones, and the
`sympa-lockup*.svg` versions when the full name should show under it.

| Original | Web copies | How they were made |
| --- | --- | --- |
| `sympa-icon.svg` | `public/brand/sympa-icon.svg`, `src/app/icon.svg` | Copied as is. The second is the browser tab's icon. |
| `sympa-mono-black.svg` | `sympa-wordmark-letters.svg`, `sympa-wordmark-accent.svg` | Split in two: the letters, and the arrow with its line. The page uses each as a mask and fills it with `--product-ink` or `--product-accent` from `globals.css`, so the wordmark can be navy and green on a page and one color on a school's sidebar. |
| `sympa-primary.svg`, `sympa-reversed.svg`, `sympa-lockup.svg`, `sympa-lockup-reversed.svg` | None | Not used by the site. |

A watermark file's color doesn't matter: the page uses it as a mask and fills it with the color set in
`brand.ts` (`watermark.color`), or the theme's primary color when none is set.

To add or swap a school: add its original here, make the two web copies, then add an entry to `logos` in
`src/content/brand.ts` and pick it for a theme in `brand.logo`.
