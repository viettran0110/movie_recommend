import { describe, expect, it } from "vitest";

import { placeholderHue, posterUrl } from "./poster-image";

describe("posterUrl", () => {
  it("builds a TMDB CDN URL when a poster path is set", () => {
    expect(posterUrl("/abc_1-X.jpg")).toBe("https://image.tmdb.org/t/p/w342/abc_1-X.jpg");
    expect(posterUrl("/abc.jpg", "w500")).toBe("https://image.tmdb.org/t/p/w500/abc.jpg");
  });

  it("is null without a poster path, so the placeholder renders", () => {
    expect(posterUrl(null)).toBeNull();
    expect(posterUrl(undefined)).toBeNull();
    expect(posterUrl("")).toBeNull();
  });

  it.each(["https://evil.example/x.jpg", "//evil.example/x.jpg", "/../x.jpg", "/x.gif", "x.jpg"])(
    "rejects unexpected path %s",
    (path) => {
      expect(posterUrl(path)).toBeNull();
    },
  );
});

describe("placeholderHue", () => {
  it("is stable per title and within 0-359", () => {
    for (const id of [1, 2, 19995, 2_147_483_647]) {
      const hue = placeholderHue(id);
      expect(hue).toBe(placeholderHue(id));
      expect(hue).toBeGreaterThanOrEqual(0);
      expect(hue).toBeLessThan(360);
    }
  });

  it("spreads neighbouring ids across colours", () => {
    expect(new Set([1, 2, 3, 4, 5].map(placeholderHue)).size).toBeGreaterThan(1);
  });
});
