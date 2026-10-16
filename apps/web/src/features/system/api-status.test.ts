import { describe, expect, it } from "vitest";

import { describeApiStatus, toApiStatus } from "./api-status";

describe("toApiStatus", () => {
  it("is unreachable without a response", () => {
    expect(toApiStatus(undefined)).toEqual({ kind: "unreachable" });
  });

  it("is ok when the API reports ok", () => {
    const status = toApiStatus({
      status: "ok",
      checks: { database: true, redis: true, meilisearch: true },
    });
    expect(status).toEqual({ kind: "ok" });
  });

  it("lists failing checks in sorted order when degraded", () => {
    const status = toApiStatus({
      status: "degraded",
      checks: { redis: false, database: true, meilisearch: false },
    });
    expect(status).toEqual({ kind: "degraded", failing: ["meilisearch", "redis"] });
    expect(describeApiStatus(status)).toBe("Degraded: meilisearch, redis");
  });
});
