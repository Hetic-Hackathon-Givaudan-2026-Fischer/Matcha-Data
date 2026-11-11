"""Repérage des contenus sponsorisés ou promotionnels."""
from __future__ import annotations

import re

from .text import strip_accents

PATTERNS = [
    r"#(ad|ads|sponsored|sponsor|sponsorise|pub|publicite|partenariat|partnership|collab|gifted|affiliate)\b",
    r"\b(code promo|promo code|discount code|use code|utilise(z)? (le )?code)\b",
    r"\b(en partenariat avec|in partnership with|sponsorise par|sponsored by|paid partnership|partenariat remunere)\b",
    r"\b(lien affilie|liens affilies|affiliate link|affiliate links|lien d'affiliation)\b",
    r"\b(offert par|gifted by|produit offert)\b",
]
SPONSORED_RE = re.compile("|".join(PATTERNS), re.IGNORECASE)


def is_sponsored(*texts: str | None) -> bool:
    joined = strip_accents(" ".join(t for t in texts if t).lower())
    return bool(SPONSORED_RE.search(joined))
