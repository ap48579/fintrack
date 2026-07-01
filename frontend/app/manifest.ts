import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "FinTrack",
    short_name: "FinTrack",
    description: "Stock research: price & trends, SEC fundamentals, blue whale holdings, and on-demand deep research.",
    start_url: "/",
    display: "standalone",
    background_color: "#09090b",
    theme_color: "#18181b",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
  };
}
