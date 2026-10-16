import { describeApiStatus, toApiStatus } from "@/features/system/api-status";
import { createServerApiClient } from "@/lib/api/client";

// Placeholder home page for the Phase 0 skeleton; replaced by explore content in Phase 1.
export const dynamic = "force-dynamic";

async function loadApiStatus() {
  try {
    const { data, error } = await createServerApiClient().GET("/api/v1/health", {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    // A degraded API answers 503 with the same body shape; openapi-fetch exposes it as `error`.
    return toApiStatus(data ?? error);
  } catch {
    return toApiStatus(undefined);
  }
}

export default async function Home() {
  const status = await loadApiStatus();

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-4 px-4">
      <h1 className="text-3xl font-semibold tracking-tight">Movie Platform</h1>
      <p className="text-zinc-600 dark:text-zinc-400">
        Search, track, and get recommendations for movies. Under construction.
      </p>
      <p className="text-sm" data-status={status.kind}>
        {describeApiStatus(status)}
      </p>
    </main>
  );
}
