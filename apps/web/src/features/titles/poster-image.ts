// Poster helpers (ADR-025). The API returns a TMDB `poster_path` only after the poster job ran
// with a TMDB API key; otherwise it is null and the UI renders a generated placeholder.

export const TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p";

// TMDB pre-renders these widths; posters are 2:3.
export const POSTER_SIZES = {
  w185: { width: 185, height: 278 },
  w342: { width: 342, height: 513 },
  w500: { width: 500, height: 750 },
} as const;

export type PosterSize = keyof typeof POSTER_SIZES;

// Same rule as the API client: "/abc_1-X.jpg". Anything else falls back to the placeholder.
const POSTER_PATH = /^\/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png)$/;

export function posterUrl(
  posterPath: string | null | undefined,
  size: PosterSize = "w342",
): string | null {
  if (!posterPath || !POSTER_PATH.test(posterPath)) return null;
  return `${TMDB_IMAGE_BASE_URL}/${size}${posterPath}`;
}

// Stable hue per title, so a placeholder keeps its colour across renders and pages.
export function placeholderHue(titleId: number): number {
  let hash = Math.abs(Math.trunc(titleId));
  hash = Math.imul(hash ^ (hash >>> 16), 0x45d9f3b);
  hash = Math.imul(hash ^ (hash >>> 16), 0x45d9f3b);
  return ((hash ^ (hash >>> 16)) >>> 0) % 360;
}
