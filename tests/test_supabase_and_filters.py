"""Compatibilité Supabase et filtre « produits qui citent un de nos arômes »."""
import pytest

from flavortrends.collectors.openfoodfacts import keep
from flavortrends.config import ConfigError
from flavortrends.db import connection_options
from flavortrends.taxonomy import AliasMatcher, read_csv


def test_supabase_session_pooler_gets_ssl():
    url = "postgresql://postgres.abcd:secret@aws-0-eu-west-3.pooler.supabase.com:5432/postgres"
    opts = connection_options(url)
    assert opts["sslmode"] == "require" and opts["prepare_threshold"] is None


def test_supabase_transaction_pooler_is_refused():
    with pytest.raises(ConfigError, match="Session pooler"):
        connection_options("postgresql://postgres.abcd:secret@aws-0-eu-west-3.pooler.supabase.com:6543/postgres")


def test_local_database_has_no_forced_ssl():
    assert "sslmode" not in connection_options("postgresql://data:x@localhost:5432/flavors")


def test_alias_matcher_whole_words_without_accents():
    m = AliasMatcher(read_csv())
    assert m.matches("Thé glacé saveur YUZU")
    assert m.matches(None, "eau, sucre, arôme naturel de fève tonka")
    assert m.matches("Kimchi chips")
    assert not m.matches("Eau minérale naturelle")
    assert not m.matches("Pain complet aux céréales")


def test_off_keep_with_matcher():
    m = AliasMatcher(read_csv())
    p_yes = {"code": "1", "product_name": "Pocky matcha", "countries_tags": ["en:japan"]}
    p_no = {"code": "2", "product_name": "Eau de source", "countries_tags": ["en:france"]}
    assert keep(p_yes, [], [], m) and not keep(p_no, [], [], m)
    assert keep(p_no, [], [], None)          # sans filtre : tout produit utilisable est gardé
