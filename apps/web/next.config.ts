import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-hosted on the VPS behind Caddy (ADR-016): minimal server bundle for Docker.
  output: "standalone",
  images: {
    // Posters/backdrops come from the TMDB CDN and are never stored (ADR-013).
    remotePatterns: [new URL("https://image.tmdb.org/t/p/**")],
  },
};

export default nextConfig;
