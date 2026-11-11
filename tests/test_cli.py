"""Vérifie que toutes les commandes se chargent et lisent leurs options (attrape les erreurs de syntaxe de cli.py)."""
import pytest

from flavortrends.cli import build_parser


@pytest.mark.parametrize("argv", [
    ["init-db"], ["load-taxonomy"], ["collect", "all"], ["collect", "off", "--max-files", "2"],
    ["collect", "wikipedia", "--flavors", "yuzu", "--since", "2024-01-01"], ["import-trends"],
    ["import-off-dump", "--limit", "10"], ["clean", "--retry-errors"], ["run"], ["status"],
    ["freshness", "--json"], ["trends-plan", "--geo", "US", "--lang", "en"],
    ["purge-raw", "--families", "all", "--older-than-days", "3"],
    ["import-pinterest"], ["candidats", "--days", "60"], ["collect", "pinterest"], ["export-orange"],
    ["collect", "google_trends"], ["spike2-build"], ["serve", "--port", "8001"],
])
def test_every_command_parses(argv):
    args = build_parser().parse_args(argv)
    assert callable(args.func)
