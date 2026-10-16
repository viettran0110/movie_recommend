import type { components } from "@/lib/api/schema";

type HealthResponse = components["schemas"]["HealthResponse"];

export type ApiStatus =
  | { kind: "ok" }
  | { kind: "degraded"; failing: string[] }
  | { kind: "unreachable" };

export function toApiStatus(health: HealthResponse | undefined): ApiStatus {
  if (!health) return { kind: "unreachable" };
  if (health.status === "ok") return { kind: "ok" };
  const failing = Object.entries(health.checks)
    .filter(([, healthy]) => !healthy)
    .map(([name]) => name)
    .sort();
  return { kind: "degraded", failing };
}

export function describeApiStatus(status: ApiStatus): string {
  switch (status.kind) {
    case "ok":
      return "All services operational";
    case "degraded":
      return `Degraded: ${status.failing.join(", ")}`;
    case "unreachable":
      return "API unreachable";
  }
}
