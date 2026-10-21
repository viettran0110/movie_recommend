import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-hosted on the VPS behind Caddy (ADR-016): minimal server bundle for Docker.
  output: "standalone",
  images: {
    // Optional TMDB posters (ADR-025), served from the TMDB CDN and never stored.
    // `Poster` uses `unoptimized`; this allowlist still applies if optimization is turned on.
    remotePatterns: [new URL("https://image.tmdb.org/t/p/**")],
  },
};

export default nextConfig;
