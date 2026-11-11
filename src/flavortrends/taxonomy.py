"""Taxonomie des arômes : lecture du CSV versionné et synchronisation avec la base."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

import psycopg

from .cleaning.text import normalize_key
from .config import ROOT

DEFAULT_FILE = ROOT / "taxonomy" / "flavors.csv"
REQUIRED = ["flavor_id", "name_fr", "name_en", "family", "wiki_fr", "wiki_en", "aliases_fr", "aliases_en"]


@dataclass(frozen=True)
class Flavor:
    flavor_id: str
    name_fr: str
    name_en: str
    family: str
    wiki_fr: str = ""
    wiki_en: str = ""
    aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def wiki(self, lang: str) -> str:
        return {"fr": self.wiki_fr, "en": self.wiki_en}.get(lang, "")

    def term(self, lang: str) -> str:
        """Terme principal de recherche dans une langue (premier alias, sinon le nom)."""
        al = self.aliases.get(lang)
        if al:
            return al[0]
        return self.name_fr if lang == "fr" else self.name_en


def read_csv(path: Path = DEFAULT_FILE) -> list[Flavor]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path} : colonnes manquantes {missing}")
        flavors, seen = [], set()
        for i, row in enumerate(reader, start=2):
            fid = row["flavor_id"].strip()
            if not fid:
                raise ValueError(f"{path}, ligne {i} : flavor_id vide")
            if fid in seen:
                raise ValueError(f"{path}, ligne {i} : flavor_id « {fid} » en double")
            seen.add(fid)
            aliases = {}
            for lang in ("fr", "en"):
                vals = [a.strip().lower() for a in row[f"aliases_{lang}"].split("|") if a.strip()]
                aliases[lang] = tuple(dict.fromkeys(vals))
            flavors.append(Flavor(fid, row["name_fr"].strip(), row["name_en"].strip(), row["family"].strip(),
                                  row["wiki_fr"].strip(), row["wiki_en"].strip(), aliases))
    return flavors


def sync_to_db(conn: psycopg.Connection, flavors: list[Flavor]) -> int:
    """Insère ou met à jour les arômes ; les arômes absents du CSV passent en statut 'retired'."""
    ids = [f.flavor_id for f in flavors]
    for f in flavors:
        conn.execute(
            """INSERT INTO core.flavor (flavor_id, name_fr, name_en, family, wiki_fr, wiki_en, status, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, 'validated', now())
               ON CONFLICT (flavor_id) DO UPDATE SET name_fr = EXCLUDED.name_fr, name_en = EXCLUDED.name_en,
                 family = EXCLUDED.family, wiki_fr = EXCLUDED.wiki_fr, wiki_en = EXCLUDED.wiki_en,
                 status = 'validated', updated_at = now()""",
            (f.flavor_id, f.name_fr, f.name_en, f.family, f.wiki_fr or None, f.wiki_en or None),
        )
        conn.execute("DELETE FROM core.flavor_alias WHERE flavor_id = %s", (f.flavor_id,))
        for lang, als in f.aliases.items():
            for pos, alias in enumerate(als):
                conn.execute(
                    """INSERT INTO core.flavor_alias (alias, lang, flavor_id, position) VALUES (%s, %s, %s, %s)
                       ON CONFLICT (alias, lang) DO UPDATE SET flavor_id = EXCLUDED.flavor_id, position = EXCLUDED.position""",
                    (alias, lang, f.flavor_id, pos),
                )
    conn.execute("UPDATE core.flavor SET status = 'retired', updated_at = now() "
                 "WHERE NOT (flavor_id = ANY(%s)) AND status <> 'retired'", (ids,))
    conn.commit()
    return len(flavors)


def from_db(conn: psycopg.Connection, only: list[str] | None = None) -> list[Flavor]:
    rows = conn.execute(
        """SELECT f.flavor_id, f.name_fr, f.name_en, f.family, coalesce(f.wiki_fr, '') AS wiki_fr,
                  coalesce(f.wiki_en, '') AS wiki_en,
                  coalesce(json_agg(json_build_array(a.lang, a.alias) ORDER BY a.lang, a.position)
                           FILTER (WHERE a.alias IS NOT NULL), '[]') AS aliases
           FROM core.flavor f LEFT JOIN core.flavor_alias a USING (flavor_id)
           WHERE f.status = 'validated' AND (%s::text[] IS NULL OR f.flavor_id = ANY(%s::text[]))
           GROUP BY f.flavor_id ORDER BY f.flavor_id""",
        (only, only),
    ).fetchall()
    out = []
    for r in rows:
        al: dict[str, list[str]] = {}
        for lang, alias in r["aliases"]:
            al.setdefault(lang, []).append(alias)
        out.append(Flavor(r["flavor_id"], r["name_fr"], r["name_en"], r["family"], r["wiki_fr"], r["wiki_en"],
                          {k: tuple(v) for k, v in al.items()}))
    if only:
        unknown = set(only) - {f.flavor_id for f in out}
        if unknown:
            raise ValueError(f"Arômes inconnus ou retirés : {sorted(unknown)}")
    if not out:
        raise ValueError("Aucun arôme en base. Lancez d'abord : flavortrends load-taxonomy")
    return out


class AliasMatcher:
    """Dit si un texte contient au moins un synonyme d'arôme (mot entier, sans tenir compte des accents).

    Sert de pré-filtre grossier, par exemple pour ne garder que les produits Open Food Facts
    qui mentionnent un de nos arômes. Ce n'est pas l'extraction des arômes (étape 5).
    """

    def __init__(self, flavors: list[Flavor]):
        keys = {normalize_key(a) for f in flavors for als in f.aliases.values() for a in als}
        keys |= {normalize_key(f.name_fr) for f in flavors} | {normalize_key(f.name_en) for f in flavors}
        keys = sorted((k for k in keys if len(k) >= 3), key=len, reverse=True)
        self.pattern = re.compile(r"\b(?:" + "|".join(re.escape(k) for k in keys) + r")\b")

    def matches(self, *texts: str | None) -> bool:
        return bool(self.pattern.search(normalize_key(" ".join(t for t in texts if t))))


class FlavorFinder:
    """Retrouve QUELS arômes sont cités dans un texte (mots entiers, sans accents).
    Exemple : « yuzu lemonade recipe » -> ['yuzu']."""

    def __init__(self, flavors: list[Flavor]):
        self.patterns = []
        for f in flavors:
            keys = {normalize_key(a) for als in f.aliases.values() for a in als}
            keys |= {normalize_key(f.name_fr), normalize_key(f.name_en)}
            keys = sorted((k for k in keys if len(k) >= 3), key=len, reverse=True)
            if keys:
                pattern = re.compile(r"\b(?:" + "|".join(re.escape(k) for k in keys) + r")\b")
                self.patterns.append((f.flavor_id, pattern))

    def find(self, text: str | None) -> list[str]:
        t = normalize_key(text or "")
        return [fid for fid, p in self.patterns if p.search(t)]


def alias_index(conn: psycopg.Connection) -> dict[str, str]:
    """Alias normalisé (minuscules, sans accents) -> flavor_id. Sert à rattacher les termes Google Trends."""
    idx = {}
    for r in conn.execute("SELECT alias, flavor_id FROM core.flavor_alias"):
        idx[normalize_key(r["alias"])] = r["flavor_id"]
    for r in conn.execute("SELECT flavor_id, name_fr, name_en FROM core.flavor"):
        idx.setdefault(normalize_key(r["name_fr"]), r["flavor_id"])
        idx.setdefault(normalize_key(r["name_en"]), r["flavor_id"])
    return idx
