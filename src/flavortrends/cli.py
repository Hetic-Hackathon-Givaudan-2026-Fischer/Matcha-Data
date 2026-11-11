"""Ligne de commande : flavortrends <commande> [options]. Lancez `flavortrends -h` pour l'aide."""
from __future__ import annotations

import argparse
import glob
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from . import taxonomy
from .cleaning.pipeline import retry_errors, run_cleaning
from .collectors import (Bluesky, Gdelt, GoogleNews, GoogleTrendsAuto, GoogleTrendsImport, OpenFoodFacts, OpenFoodFactsDelta,
                         OpenFoodFactsDump, PinterestManualImport, PinterestTrendsApi, RssFeeds,
                         WikipediaPageviews, YouTube)
from .collectors.base import RunResult
from .collectors.google_trends import build_plan, explore_url
from .exports import DEFAULT_DIR as EXPORT_DIR, export_orange
from .freshness import check as check_freshness
from .config import ROOT, ConfigError, Settings, load_settings
from .db import connect, connection_options, migrate
from .maintenance import ALL_FAMILIES, compact_raw, database_size_mb, purge_raw, status, table_sizes

log = logging.getLogger("flavortrends")

SOURCES = ["wikipedia", "off", "off-api", "gdelt", "rss", "google_news", "youtube", "bluesky", "pinterest",
           "google_trends"]
DAILY = ["wikipedia", "off", "gdelt", "rss", "google_news", "youtube", "bluesky", "pinterest", "google_trends"]


def _setup_logging(verbose: bool) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    # httpx journalise les URL complètes, clés d'API comprises : on le fait taire.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def collect_one(conn, settings: Settings, name: str, args: argparse.Namespace) -> RunResult | None:
    langs = args.langs.split(",") if getattr(args, "langs", None) else settings.langs
    only = args.flavors.split(",") if getattr(args, "flavors", None) else None
    needs_flavors = name in ("wikipedia", "gdelt", "google_news", "youtube", "bluesky", "google_trends")
    flavors = taxonomy.from_db(conn, only) if needs_flavors else None
    days = getattr(args, "days", None)

    if name == "wikipedia":
        since = date.fromisoformat(args.since) if getattr(args, "since", None) else None
        return WikipediaPageviews(conn, settings).run(flavors=flavors, langs=langs, since=since,
                                                      first_start=date.fromisoformat(settings.wikipedia_start))
    if name == "off":
        return OpenFoodFactsDelta(conn, settings).run(categories=settings.off_categories,
                                                      countries=settings.off_countries,
                                                      max_files=getattr(args, "max_files", None) or 14,
                                                      matcher=_off_matcher(conn, settings))
    if name == "off-api":
        return OpenFoodFacts(conn, settings).run(categories=settings.off_categories, countries=settings.off_countries,
                                                 max_pages=getattr(args, "max_pages", None) or 20,
                                                 full=getattr(args, "full", False),
                                                 matcher=_off_matcher(conn, settings))
    if name == "gdelt":
        return Gdelt(conn, settings).run(flavors=flavors, langs=langs, timespan=f"{days or 3}d")
    if name == "rss":
        return RssFeeds(conn, settings).run()
    if name == "google_news":
        return GoogleNews(conn, settings).run(flavors=flavors, langs=langs, days=days or 7)
    if name == "youtube":
        if not settings.youtube_api_key:
            log.warning("YouTube ignoré : YOUTUBE_API_KEY est vide dans .env")
            return None
        return YouTube(conn, settings).run(flavors=flavors, langs=langs, days=days or 7)
    if name == "bluesky":
        if not (settings.bluesky_handle and settings.bluesky_app_password):
            log.warning("Bluesky ignoré : BLUESKY_HANDLE / BLUESKY_APP_PASSWORD vides dans .env")
            return None
        return Bluesky(conn, settings).run(flavors=flavors, langs=langs, days=days or 2,
                                           max_pages=settings.bluesky_max_pages)
    if name == "google_trends":
        # Une fois par semaine : le collecteur ne fait rien si la dernière collecte auto a moins de 6 jours.
        popularity = {r["flavor_id"]: float(r["v"]) for r in conn.execute(
            """SELECT flavor_id, sum(value) AS v FROM core.search_interest WHERE source_id = 'wikipedia_pageviews'
               AND flavor_id IS NOT NULL AND day > current_date - 365 GROUP BY flavor_id""")}
        return GoogleTrendsAuto(conn, settings).run(flavors=flavors, zones=list(settings.google_trends_zones),
                                                    popularity=popularity, force=getattr(args, "full", False))
    if name == "pinterest":
        if not settings.pinterest_access_token:
            log.info("Pinterest API ignorée : pas de PINTEREST_ACCESS_TOKEN (accès réservé aux partenaires). "
                     "La veille manuelle passe par : flavortrends import-pinterest")
            return None
        return PinterestTrendsApi(conn, settings).run(regions=list(settings.pinterest_regions),
                                                      trend_types=list(settings.pinterest_trend_types),
                                                      interests=list(settings.pinterest_interests))
    raise ValueError(f"source inconnue : {name}")


def _off_matcher(conn, settings: Settings):
    """Filtre « produits qui citent un de nos arômes » si OFF_ONLY_FLAVOR_MATCHES=true, sinon aucun filtre."""
    if not settings.off_only_flavor_matches:
        return None
    return taxonomy.AliasMatcher(taxonomy.from_db(conn))


def cmd_init_db(args, settings):
    with connect(settings) as conn:
        done = migrate(conn)
        print(f"Migrations appliquées : {', '.join(done) if done else 'aucune (base déjà à jour)'}")
        n = taxonomy.sync_to_db(conn, taxonomy.read_csv(Path(args.taxonomy)))
        print(f"Taxonomie chargée : {n} arômes")


def cmd_load_taxonomy(args, settings):
    with connect(settings) as conn:
        n = taxonomy.sync_to_db(conn, taxonomy.read_csv(Path(args.file)))
        print(f"Taxonomie chargée : {n} arômes")


def cmd_collect(args, settings):
    names = DAILY if args.source == "all" else [args.source]
    results = []
    with connect(settings) as conn:
        for name in names:
            try:
                res = collect_one(conn, settings, name, args)
            except ConfigError as exc:
                log.warning("%s : %s", name, exc)
                continue
            if res:
                results.append(res)
    _print_runs(results)
    return 1 if any(r.status == "failed" for r in results) else 0


def cmd_import_trends(args, settings):
    paths = sorted({Path(p) for pattern in args.files for p in glob.glob(pattern)})
    if not paths:
        print("Aucun fichier trouvé. Déposez les exports CSV dans data/manual/google_trends/.")
        return 1
    with connect(settings) as conn:
        res = GoogleTrendsImport(conn, settings).run(paths=paths)
    _print_runs([res])
    return 0 if res.status != "failed" else 1


def cmd_import_pinterest(args, settings):
    paths = sorted({Path(p) for pattern in args.files for p in glob.glob(pattern)})
    if not paths:
        print("Aucun fichier trouvé. Déposez la veille Pinterest (CSV) dans data/manual/pinterest/.")
        return 1
    with connect(settings) as conn:
        res = PinterestManualImport(conn, settings).run(paths=paths)
    _print_runs([res])
    print("Étape suivante : flavortrends clean, puis flavortrends candidats")
    return 0 if res.status != "failed" else 1


def cmd_candidats(args, settings):
    """Mots-clés en tendance (Pinterest…) qui ne correspondent à aucun de nos arômes : à examiner pour la liste."""
    with connect(settings) as conn:
        rows = conn.execute(
            """SELECT keyword, string_agg(DISTINCT region, ',') AS regions, count(*) AS fois,
                      max(observed_on) AS derniere_fois, max(pct_growth_mom) AS croissance_mois_max
               FROM core.external_trend
               WHERE flavor_id IS NULL AND observed_on >= current_date - %s
               GROUP BY keyword ORDER BY fois DESC, derniere_fois DESC LIMIT 50""",
            (args.days,),
        ).fetchall()
    if not rows:
        print("Aucun mot-clé inconnu : tout ce qui a été vu correspond déjà à un arôme de la liste.")
        return 0
    print(f"Mots-clés en tendance absents de taxonomy/flavors.csv ({args.days} derniers jours) :")
    print("Si c'est un arôme, ajoutez-le au fichier puis lancez : flavortrends load-taxonomy\n")
    for r in rows:
        growth = f"  +{r['croissance_mois_max']:.0f} %/mois" if r["croissance_mois_max"] is not None else ""
        print(f"  {r['keyword']:<35} vu {r['fois']} fois ({r['regions']}), dernière fois {r['derniere_fois']}{growth}")
    return 0


def cmd_export_orange(args, settings):
    with connect(settings) as conn:
        counts = export_orange(conn, Path(args.out))
    print(f"Fichiers pour Orange Data Mining, dans {args.out} :")
    for name, n in counts.items():
        print(f"  {name:<32} {n} lignes")
    print("Dans Orange : widget « File » > ouvrir le fichier.")
    return 0


def cmd_spike2_build(args, settings):
    from .spike2 import OUT_DIR, build
    with connect(settings) as conn:
        res = build(conn, Path(args.out) if args.out else OUT_DIR)
    m = res["model"]
    print(f"Cas de référence réels : {res['cases']}  (pérennes : {m.get('n_perenne')}, buzz : {m.get('n_buzz')}, "
          f"arômes : {m.get('n_flavors')})")
    if "accuracy" in m:
        print(f"Modèle V2 ({m['validation']}) :")
        print(f"  {'':<28}{'accuracy':>9}{'équilibrée':>11}{'buzz détectés':>15}")
        print(f"  {'V2 (régression logistique)':<28}{m['accuracy']:>9.0%}{m['balanced_accuracy']:>11.0%}{m['buzz_detectes']:>15.0%}"
              f"   (F1 pérenne {m['f1_perenne']:.2f}, ROC AUC {m['roc_auc']:.2f})")
        for name, v in m["baselines"].items():
            print(f"  {name:<28}{v['accuracy']:>9.0%}{v['balanced_accuracy']:>11.0%}{v['buzz_detectes']:>15.0%}")
    else:
        print("Modèle V2 :", m.get("warning"))
    print(f"Fiches MiroFish : {res['packets_ok']}/{res['trends']} valides | données API : data/sample/trends_scored.json")
    return 0


def cmd_serve(args, settings):
    import uvicorn
    print(f"API sur http://localhost:{args.port}/docs  (Ctrl+C pour arrêter)")
    uvicorn.run("flavortrends.api:app", host=args.host, port=args.port)
    return 0


def cmd_import_off_dump(args, settings):
    with connect(settings) as conn:
        res = OpenFoodFactsDump(conn, settings).run(categories=settings.off_categories,
                                                    countries=settings.off_countries,
                                                    path=Path(args.file) if args.file else None, limit=args.limit,
                                                    matcher=_off_matcher(conn, settings))
    _print_runs([res])
    print("Étape suivante : flavortrends clean --source open_food_facts")
    return 0 if res.status != "failed" else 1


def cmd_clean(args, settings):
    with connect(settings) as conn:
        if args.retry_errors:
            print(f"{retry_errors(conn, args.source)} lignes en erreur remises en file")
        stats = run_cleaning(conn, settings, source=args.source, batch_size=args.batch_size)
    if stats.get("locked"):
        print("Un nettoyage est déjà en cours : rien à faire.")
        return 0
    if not stats:
        print("Rien à nettoyer : toutes les données brutes sont déjà traitées.")
        return 0
    print("Nettoyage terminé :")
    for k in ["raw_read", "documents", "products", "interest_points", "external_trends", "skipped", "errors",
              "exact_duplicates", "near_duplicates"]:
        print(f"  {k:<18} {stats.get(k, 0)}")
    return 0


def cmd_run(args, settings):
    """Collecte quotidienne complète puis nettoyage : c'est la commande à planifier."""
    args.source = "all"
    code = cmd_collect(args, settings)
    args.source, args.retry_errors, args.batch_size = None, False, 2000
    cmd_clean(args, settings)
    if settings.raw_retention_days > 0:
        with connect(settings) as conn:
            n = purge_raw(conn, settings.raw_retention_days, ALL_FAMILIES)
        print(f"Couche brute : {n} lignes nettoyées depuis plus de {settings.raw_retention_days} jours supprimées")
    # Rafraîchit l'échantillon SPIKE-2 et les données de l'API avec les données du jour
    try:
        cmd_spike2_build(argparse.Namespace(out=None), settings)
    except Exception as exc:   # ne doit jamais faire échouer la collecte quotidienne
        log.warning("SPIKE-2 non reconstruit : %s", exc)
    return code


def cmd_status(args, settings):
    with connect(settings) as conn:
        rows = status(conn)
        size, tables = database_size_mb(conn), table_sizes(conn)
    cols = [("source_id", 20), ("family", 7), ("raw_rows", 9), ("pending", 8), ("skipped", 8), ("errors", 7),
            ("clean_rows", 10), ("duplicates", 10), ("sponsored", 9), ("last_status", 11), ("last_run_at", 16)]
    print(" ".join(f"{c:<{w}}" for c, w in cols))
    for r in rows:
        vals = []
        for c, w in cols:
            v = r[c]
            if c == "last_run_at" and v:
                v = v.strftime("%Y-%m-%d %H:%M")
            vals.append(f"{'' if v is None else v!s:<{w}}")
        print(" ".join(vals))
    limit = ""
    if settings.db_size_limit_mb:
        limit = f" sur {settings.db_size_limit_mb} Mo autorisés ({size / settings.db_size_limit_mb:.0%})"
    print(f"\nTaille de la base : {size:.0f} Mo{limit}")
    print("  " + " | ".join(f"{t['table_name']} {t['mb']} Mo" for t in tables[:5]))


LEVEL_LABEL = {"ok": "OK", "info": "INFO", "warning": "ATTENTION", "alert": "ALERTE"}


def cmd_freshness(args, settings):
    """Code de sortie 1 s'il y a au moins une alerte : le Planificateur de tâches l'affiche comme un échec."""
    with connect(settings) as conn:
        items = check_freshness(conn, settings)
    if args.json:
        print(json.dumps({"checked_at": datetime.now(timezone.utc).isoformat(), "sources": items},
                         ensure_ascii=False, indent=2))
    else:
        for it in items:
            until = f"  données jusqu'au {it['data_until'][:10]}" if it["data_until"] else ""
            print(f"{LEVEL_LABEL[it['level']]:<10} {it['source_id']:<20} {it['message']}{until}")
        n_alert = sum(it["level"] == "alert" for it in items)
        print(f"\n{n_alert} alerte(s)." if n_alert else "\nAucune alerte.")
    return 1 if any(it["level"] == "alert" for it in items) else 0


def cmd_trends_plan(args, settings):
    with connect(settings) as conn:
        flavors = taxonomy.from_db(conn)
    plan = build_plan(flavors, args.lang, args.anchor)
    anchor_term = next(f.term(args.lang) for f in flavors if f.flavor_id == args.anchor)
    print(f"{len(plan)} exports à faire (zone {args.geo}, 5 ans, terme d'ancrage « {anchor_term} » dans chacun).")
    print("Pour chaque lien : ouvrir, vérifier la période « 5 dernières années », puis télécharger le CSV")
    print("« Intérêt au fil du temps » dans data/manual/google_trends/. Ensuite : flavortrends import-trends\n")
    for i, terms in enumerate(plan, 1):
        print(f"{i:>2}. {', '.join(terms)}\n    {explore_url(terms, args.geo, args.lang)}")


def cmd_purge_raw(args, settings):
    with connect(settings) as conn:
        families = ALL_FAMILIES if args.families == "all" else args.families.split(",")
        deleted = purge_raw(conn, args.older_than_days, families)
    print(f"Couche brute : {deleted} lignes déjà nettoyées supprimées ({', '.join(families)})")
    if args.vacuum_full:
        print("Compactage de la table brute (VACUUM FULL)…")
        compact_raw(settings.database_url, {k: v for k, v in connection_options(settings.database_url).items()
                                            if k != "row_factory"})
        with connect(settings) as conn:
            print(f"Taille de la base après compactage : {database_size_mb(conn):.0f} Mo")


def _print_runs(results: list[RunResult]) -> None:
    if not results:
        return
    print("\nRésumé de la collecte :")
    for r in results:
        line = f"  {r.source_id:<20} {r.status:<8} reçus={r.n_fetched:<7} nouveaux={r.n_inserted:<7} erreurs={r.n_errors}"
        print(line + (f"  ({r.error})" if r.error else ""))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="flavortrends", description="Collecte et nettoyage des signaux de tendances aromatiques")
    p.add_argument("-v", "--verbose", action="store_true", help="journal détaillé")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init-db", help="crée les tables et charge la taxonomie")
    s.add_argument("--taxonomy", default=str(taxonomy.DEFAULT_FILE))
    s.set_defaults(func=cmd_init_db)

    s = sub.add_parser("load-taxonomy", help="recharge taxonomy/flavors.csv en base")
    s.add_argument("--file", default=str(taxonomy.DEFAULT_FILE))
    s.set_defaults(func=cmd_load_taxonomy)

    def common(sp):
        sp.add_argument("--flavors", help="liste d'arômes, ex. yuzu,matcha (défaut : tous)")
        sp.add_argument("--langs", help="langues, ex. fr,en (défaut : LANGS du .env)")
        sp.add_argument("--days", type=int, help="fenêtre de collecte en jours (gdelt, google_news, youtube, bluesky)")
        sp.add_argument("--since", help="wikipedia : date de début AAAA-MM-JJ (défaut : reprise automatique)")
        sp.add_argument("--max-files", type=int, help="off : nombre maximum de fichiers delta à importer (défaut 14)")
        sp.add_argument("--max-pages", type=int, help="off-api : nombre maximum de pages de 100 produits")
        sp.add_argument("--full", action="store_true", help="off-api : ignore la reprise et repart du plus récent")

    s = sub.add_parser("collect", help="lance un collecteur")
    s.add_argument("source", choices=SOURCES + ["all"])
    common(s)
    s.set_defaults(func=cmd_collect)

    s = sub.add_parser("import-trends", help="importe des exports CSV Google Trends")
    s.add_argument("files", nargs="*", default=[str(ROOT / "data" / "manual" / "google_trends" / "*.csv")])
    s.set_defaults(func=cmd_import_trends)

    s = sub.add_parser("import-pinterest", help="importe la veille Pinterest (CSV dans data/manual/pinterest/)")
    s.add_argument("files", nargs="*", default=[str(ROOT / "data" / "manual" / "pinterest" / "*.csv")])
    s.set_defaults(func=cmd_import_pinterest)

    s = sub.add_parser("candidats", help="mots-clés en tendance qui ne sont pas encore dans la liste des arômes")
    s.add_argument("--days", type=int, default=30)
    s.set_defaults(func=cmd_candidats)

    s = sub.add_parser("export-orange", help="exporte les données en CSV pour Orange Data Mining")
    s.add_argument("--out", default=str(EXPORT_DIR))
    s.set_defaults(func=cmd_export_orange)

    s = sub.add_parser("spike2-build", help="SPIKE-2 : cas de référence réels, modèles V1/V2, fiches MiroFish, données API")
    s.add_argument("--out", help="dossier de sortie (défaut : data/sample)")
    s.set_defaults(func=cmd_spike2_build)

    s = sub.add_parser("serve", help="lance l'API Data (FastAPI) pour l'équipe Tech")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("import-off-dump", help="import unique de l'export complet Open Food Facts (historique)")
    s.add_argument("--file", help="fichier .csv.gz déjà téléchargé (défaut : téléchargement en continu)")
    s.add_argument("--limit", type=int, help="nombre maximum de produits (pour un essai)")
    s.set_defaults(func=cmd_import_off_dump)

    s = sub.add_parser("clean", help="nettoie les données brutes non traitées")
    s.add_argument("--source", choices=["wikipedia_pageviews", "open_food_facts", "gdelt", "rss", "google_news",
                                        "youtube", "bluesky", "google_trends"])
    s.add_argument("--retry-errors", action="store_true", help="retraite les lignes en erreur")
    s.add_argument("--batch-size", type=int, default=2000)
    s.set_defaults(func=cmd_clean)

    s = sub.add_parser("run", help="collecte quotidienne de toutes les sources puis nettoyage")
    common(s)
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("status", help="état des données par source")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("freshness", help="vérifie que chaque source est à jour (code 1 si alerte)")
    s.add_argument("--json", action="store_true", help="sortie JSON (pour le dashboard ou une supervision)")
    s.set_defaults(func=cmd_freshness)

    s = sub.add_parser("trends-plan", help="liste les exports Google Trends à faire, avec les liens")
    s.add_argument("--geo", default="FR", help="zone Google Trends, ex. FR, US, GB")
    s.add_argument("--lang", default="fr", choices=["fr", "en"])
    s.add_argument("--anchor", default="vanilla", help="arôme d'ancrage présent dans chaque export")
    s.set_defaults(func=cmd_trends_plan)

    s = sub.add_parser("purge-raw", help="purge RGPD de la couche brute")
    s.add_argument("--older-than-days", type=int, default=180)
    s.add_argument("--families", default="social", help="familles concernées, ex. social,news, ou all")
    s.add_argument("--vacuum-full", action="store_true",
                   help="rend la place au disque après la purge (utile sur Supabase, où la taille est comptée)")
    s.set_defaults(func=cmd_purge_raw)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    try:
        return args.func(args, load_settings()) or 0
    except ConfigError as exc:
        print(f"Configuration : {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
