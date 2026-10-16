import createClient from "openapi-fetch";

import type { paths } from "./schema";

/**
 * Server-side API client. Server Components call the API over the internal network
 * (API_INTERNAL_URL); browser calls go through Caddy on the same origin under /api.
 */
export function createServerApiClient() {
  const baseUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
  return createClient<paths>({ baseUrl });
}
