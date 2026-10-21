import Image from "next/image";

import { placeholderHue, POSTER_SIZES, posterUrl, type PosterSize } from "./poster-image";

type PosterProps = {
  titleId: number;
  title: string;
  year?: number | null;
  posterPath?: string | null;
  size?: PosterSize;
  className?: string;
};

// TMDB poster when `posterPath` is set, otherwise a placeholder with the title and year.
export function Poster({ titleId, title, year, posterPath, size = "w342", className }: PosterProps) {
  const src = posterUrl(posterPath, size);
  const { width, height } = POSTER_SIZES[size];
  const classes = `aspect-[2/3] w-full overflow-hidden rounded-md ${className ?? ""}`;

  if (src) {
    return (
      <Image
        src={src}
        alt={`Poster for ${title}`}
        width={width}
        height={height}
        // TMDB already serves resized images; skip re-optimizing them on our server.
        unoptimized
        className={`${classes} object-cover`}
      />
    );
  }

  const hue = placeholderHue(titleId);
  return (
    <div
      role="img"
      aria-label={`${title}${year ? ` (${year})` : ""}, no poster`}
      className={`${classes} flex flex-col justify-end gap-1 p-3 text-white`}
      style={{ background: `linear-gradient(160deg, hsl(${hue} 45% 38%), hsl(${hue} 50% 18%))` }}
    >
      <span className="line-clamp-3 text-sm font-semibold leading-tight">{title}</span>
      {year ? <span className="text-xs opacity-80">{year}</span> : null}
    </div>
  );
}
