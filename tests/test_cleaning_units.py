from flavortrends.cleaning import language
from flavortrends.cleaning.dedup import from_bytes, minhash, to_bytes
from flavortrends.cleaning.privacy import pseudonymize
from flavortrends.cleaning.sponsored import is_sponsored
from flavortrends.cleaning.text import clean_text, content_hash, normalize_key, strip_html, text_for_analysis


def test_strip_html_and_entities():
    assert strip_html("<p>Yuzu &amp; menthe</p><script>x()</script>").strip() == "Yuzu & menthe"


def test_clean_text_normalizes_spaces_and_controls():
    assert clean_text("  Boisson​  au\n\nyuzu\u0000 ") == "Boisson au yuzu"
    assert clean_text(None) == ""


def test_text_for_analysis_removes_noise():
    out = text_for_analysis("Nouveau #yuzu 🍋", "Voir https://ex.com/a?b=1 avec @marque_officielle")
    assert out == "Nouveau yuzu Voir avec"


def test_content_hash_ignores_case_accents_punctuation():
    assert content_hash("Thé glacé : PÊCHE !") == content_hash("the glace peche")
    assert normalize_key("Fève Tonka") == "feve tonka"


def test_language_from_source_and_detection():
    assert language.resolve("French", "...") == ("fr", "source")
    assert language.resolve("en-US", "...") == ("en", "source")
    text = "Cette boisson pétillante au yuzu est rafraîchissante et peu sucrée, parfaite pour l'été."
    assert language.resolve(None, text) == ("fr", "detected")
    assert language.resolve(None, "ok") == (None, "unknown")


def test_pseudonymize_is_stable_and_salted():
    a = pseudonymize("bluesky", "did:plc:abc", "salt-one-123456789")
    assert a == pseudonymize("bluesky", "did:plc:abc", "salt-one-123456789")
    assert a != pseudonymize("bluesky", "did:plc:abc", "salt-two-123456789")
    assert a != pseudonymize("youtube", "did:plc:abc", "salt-one-123456789")
    assert pseudonymize("bluesky", None, "salt") is None
    assert len(a) == 32


def test_sponsored_detection():
    assert is_sponsored("Ma recette #sponsorisé")
    assert is_sponsored(None, "Utilisez le code promo YUZU10")
    assert is_sponsored("Video in partnership with BrandX")
    assert not is_sponsored("Le yuzu, un agrume japonais qui monte")


def test_minhash_near_duplicates_and_roundtrip():
    a = "Le yuzu s'impose dans les boissons pétillantes peu sucrées vendues en grande surface cette année en France"
    b = "Le yuzu s'impose dans les boissons pétillantes peu sucrées vendues en grande surface cette année en France !"
    c = "La vanille de Madagascar reste l'arôme préféré des yaourts selon une étude publiée mardi par un panel"
    ma, mb, mc = minhash(a), minhash(b), minhash(c)
    assert ma.jaccard(mb) > 0.9
    assert ma.jaccard(mc) < 0.3
    assert from_bytes(to_bytes(ma)).jaccard(ma) == 1.0
    assert minhash("trop court pour un minhash") is None
