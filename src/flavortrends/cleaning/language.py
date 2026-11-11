"""Langue d'un document : celle déclarée par la source si elle existe, sinon détectée."""
from __future__ import annotations

from langdetect import DetectorFactory, LangDetectException, detect_langs

DetectorFactory.seed = 0  # résultats reproductibles

LANG_NAMES = {
    "french": "fr", "english": "en", "spanish": "es", "german": "de", "italian": "it",
    "portuguese": "pt", "dutch": "nl", "japanese": "ja", "korean": "ko", "chinese": "zh",
}
MIN_CHARS = 25
MIN_PROB = 0.80


def normalize_code(value: str | None) -> str | None:
    """'fr-FR' -> 'fr', 'French' -> 'fr', 'zxx' / '' -> None."""
    if not value:
        return None
    v = str(value).strip().lower().replace("_", "-")
    if v in LANG_NAMES:
        return LANG_NAMES[v]
    code = v.split("-")[0]
    if len(code) == 2 and code.isalpha():
        return code
    return None


def detect(text: str) -> tuple[str | None, float]:
    if len(text) < MIN_CHARS:
        return None, 0.0
    try:
        best = detect_langs(text)[0]
    except LangDetectException:
        return None, 0.0
    if best.prob < MIN_PROB:
        return None, best.prob
    return best.lang.split("-")[0], best.prob


def resolve(source_lang: str | None, text: str) -> tuple[str | None, str]:
    """Retourne (code langue, origine) avec origine dans 'source', 'detected', 'unknown'."""
    code = normalize_code(source_lang)
    if code:
        return code, "source"
    code, _ = detect(text)
    if code:
        return code, "detected"
    return None, "unknown"
