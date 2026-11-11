"""Normalisation de texte."""
from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from html.parser import HTMLParser

URL_RE = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)
CTRL_RE = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f​-‍⁠﻿]")
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0001F1E6-\U0001F1FF]")
MENTION_RE = re.compile(r"(?<!\w)@[\w.\-]+")
HASHTAG_RE = re.compile(r"(?<!\w)#(\w+)")
SPACE_RE = re.compile(r"\s+")
NON_ALNUM_RE = re.compile(r"[^0-9a-z]+")
BLOCK_TAGS = {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr", "td"}


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag in BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def strip_html(s: str) -> str:
    if "<" not in s:
        return html.unescape(s)
    p = _Stripper()
    p.feed(s)
    p.close()
    return "".join(p.parts)


def clean_text(s: str | None) -> str:
    """Texte lisible : HTML retiré, Unicode normalisé (NFC), caractères de contrôle supprimés, espaces réduits."""
    if not s:
        return ""
    s = unicodedata.normalize("NFC", strip_html(str(s)))
    s = CTRL_RE.sub("", s)
    return SPACE_RE.sub(" ", s).strip()


def text_for_analysis(*parts: str | None) -> str:
    """Texte destiné à l'analyse : URL, emojis et @mentions retirés, # des hashtags retiré."""
    s = " ".join(p for p in (clean_text(x) for x in parts) if p)
    s = URL_RE.sub(" ", s)
    s = EMOJI_RE.sub(" ", s)
    s = MENTION_RE.sub(" ", s)
    s = HASHTAG_RE.sub(r"\1", s)
    return SPACE_RE.sub(" ", s).strip()


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_key(s: str) -> str:
    """Forme canonique pour comparer : minuscules, sans accents ni ponctuation."""
    return NON_ALNUM_RE.sub(" ", strip_accents(s.casefold())).strip()


def tokens(s: str) -> list[str]:
    return normalize_key(s).split()


def content_hash(s: str) -> str:
    """Empreinte du contenu : deux textes qui ne diffèrent que par la casse, les accents ou la ponctuation ont la même."""
    return hashlib.sha256(normalize_key(s).encode("utf-8")).hexdigest()
