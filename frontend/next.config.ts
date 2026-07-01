import withSerwistInit from "@serwist/next";
import type { NextConfig } from "next";

// @serwist/next's InjectManifest webpack plugin doesn't support Turbopack (Next 16's default
// dev bundler) — disable it in dev so `next dev` keeps using Turbopack untouched, and only
// build the real service worker for `next build` (production), same as Serwist's own guidance.
const withSerwist = withSerwistInit({
  swSrc: "app/sw.ts",
  swDest: "public/sw.js",
  disable: process.env.NODE_ENV !== "production",
});

const nextConfig: NextConfig = {
  // Acknowledges the webpack config Serwist's plugin attaches (a no-op while `disable` is
  // true in dev) so Next 16's Turbopack-vs-webpack mismatch check doesn't error out.
  turbopack: {},
};

export default withSerwist(nextConfig);
