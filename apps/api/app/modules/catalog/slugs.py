import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
FALLBACK_SLUG = "untitled"


def slugify(value: str, *, max_length: int = 80) -> str:
    """ASCII, lowercase, hyphen-separated. Slugs are cosmetic: URLs carry the id too."""
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _NON_ALNUM.sub("-", ascii_text.lower()).strip("-")
    slug = slug[:max_length].rstrip("-")
    return slug or FALLBACK_SLUG
