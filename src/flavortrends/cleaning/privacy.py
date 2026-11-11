"""Pseudonymisation des auteurs (RGPD).

On remplace l'identifiant d'un auteur par un HMAC-SHA256 avec un secret (PSEUDONYMIZATION_SALT).
Le même auteur garde le même pseudonyme, ce qui permet de mesurer la concentration des auteurs
(détection des campagnes), sans stocker son nom ni son identifiant dans la couche propre.
"""
from __future__ import annotations

import hashlib
import hmac


def pseudonymize(source_id: str, author_id: str | None, salt: str) -> str | None:
    if not author_id:
        return None
    msg = f"{source_id}:{author_id}".encode("utf-8")
    return hmac.new(salt.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:32]
