import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-hosted on the VPS behind Caddy (ADR-016): minimal server bundle for Docker.
  output: "standalone",
  // No remote images: v1 has no posters and renders placeholders (ADR-024).
};

export default nextConfig;
