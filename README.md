# FlavorTrends · collecte, stockage brut et nettoyage

Ce dépôt couvre les quatre premières étapes du pipeline Data :

```
Sources ──► Collecte ──► Stockage brut (schéma raw) ──► Nettoyage (schéma core)
```

Les étapes suivantes (extraction des arômes, scoring, API) liront le schéma `core`.

## Ce que fait chaque étape

| Étape | Ce qui se passe | Où |
|---|---|---|
| **Sources** | 9 sources gratuites : Wikipédia, Open Food Facts, Google Trends (automatique), YouTube, Bluesky, Google News, flux RSS, GDELT, Pinterest (veille manuelle) | `src/flavortrends/collectors/` |
| **Collecte** | Un collecteur par source : respect des quotas, reprises automatiques en cas d'erreur, collecte incrémentale, journal de chaque exécution | `src/flavortrends/collectors/` |
| **Stockage brut** | La réponse de l'API est gardée telle quelle (JSONB). Chaque version distincte est conservée une seule fois : relancer une collecte n'insère que ce qui a changé | `raw.raw_document`, `raw.collection_run` |
| **Nettoyage** | HTML retiré, Unicode normalisé, dates en UTC, langue (déclarée ou détectée), auteurs pseudonymisés, contenus sponsorisés repérés, doublons exacts et quasi-doublons marqués, documents inutilisables écartés avec leur raison | `src/flavortrends/cleaning/` → `core.document`, `core.product`, `core.search_interest` |

## Installation

Prérequis : Python 3.11 ou plus, et une base PostgreSQL. **L'équipe utilise Supabase** (base en ligne partagée) : mettez son adresse « Session pooler » (port 5432, pas 6543) dans `DATABASE_URL`.

```bash
# 1. Base de données
#    Supabase : créer le projet et copier l'adresse « Session pooler » dans DATABASE_URL
#    ou en local : un PostgreSQL 16 installé sur le PC

# 2. Environnement Python
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS / Linux : source .venv/bin/activate)
pip install -e ".[dev]"

# 3. Configuration
copy .env.example .env            # macOS / Linux : cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
#   -> collez le résultat dans PSEUDONYMIZATION_SALT du fichier .env
#   -> optionnel : YOUTUBE_API_KEY, BLUESKY_HANDLE, BLUESKY_APP_PASSWORD

# 4. Création des tables et chargement des 102 arômes
flavortrends init-db
```

Sans Docker : installez PostgreSQL 16, créez une base `flavors`, puis mettez son adresse dans `DATABASE_URL`.

## Utilisation

```bash
flavortrends collect wikipedia            # 1er passage : historique depuis 2016 (quelques minutes)
flavortrends import-off-dump              # UNE SEULE FOIS : export complet Open Food Facts (≈4 M produits, 30-60 min)
flavortrends collect off                  # chaque jour : produits modifiés dans le monde (fichiers delta officiels)
flavortrends collect rss
flavortrends collect google_news
flavortrends collect gdelt                # lent exprès : 8 s entre deux requêtes
flavortrends collect youtube              # si YOUTUBE_API_KEY est renseignée
flavortrends collect bluesky              # si le compte Bluesky est renseigné
flavortrends import-trends                # lit data/manual/google_trends/*.csv
flavortrends import-pinterest            # lit data/manual/pinterest/*.csv (veille hebdomadaire)
flavortrends candidats                   # mots-clés en tendance absents de notre liste d'arômes
flavortrends export-orange               # fichiers CSV pour Orange Data Mining (data/exports/)
flavortrends collect google_trends       # Google Trends automatique (pytrends), une fois par semaine
flavortrends spike2-build                # SPIKE-2 : cas de référence réels, modèle V1, fiches MiroFish (data/sample/)
flavortrends serve                       # API Data pour l'équipe Tech : http://localhost:8000/docs

flavortrends clean                        # nettoie tout ce qui n'a pas encore été traité
flavortrends status                       # état par source
```

Options utiles : `--flavors yuzu,matcha` pour cibler quelques arômes, `--langs fr`, `--days 3`, `-v` pour un journal détaillé.

**Commande quotidienne** (toutes les sources puis nettoyage) : `flavortrends run`.

## Planification automatique (Windows)

Une fois la base lancée et le fichier `.env` rempli :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\install_tasks.ps1
```

Cela crée trois tâches dans le Planificateur de tâches (dossier « FlavorTrends ») :

| Tâche | Heures | Ce qu'elle fait |
|---|---|---|
| Collecte quotidienne | 03:00 | Toutes les sources, puis nettoyage |
| Presse toutes les 4 h | 07:00, 11:00, 15:00, 19:00, 23:00 | Flux RSS + Google News, puis nettoyage (les flux ne gardent que leurs 10 à 30 derniers articles) |
| Contrôle de fraîcheur | 08:30 | Écrit le bilan dans `logs\freshness_latest.log` |

- Si le PC est éteint à l'heure prévue, la tâche se lance dès qu'il redémarre.
- Les tâches tournent quand vous êtes connecté à votre session Windows.
- Deux collectes de la même source, ou deux nettoyages, ne tournent jamais en même temps : la seconde est ignorée.
- Journaux : `logs\` (30 jours conservés). Dans le Planificateur, « Résultat de la dernière exécution » vaut 0x1 si le contrôle de fraîcheur a trouvé une alerte.
- Supprimer les tâches : ajoutez `-Uninstall` à la commande ci-dessus.

Sur macOS ou Linux, planifiez `flavortrends run` avec cron.

## Contrôle de fraîcheur

```bash
flavortrends freshness          # tableau lisible ; code de sortie 1 s'il y a une alerte
flavortrends freshness --json   # même chose en JSON, pour le dashboard (« Dernière mise à jour »)
```

```
OK         wikipedia_pageviews  à jour (il y a 0 h 36 min)  données jusqu'au 2026-11-09
ATTENTION  gdelt                à jour, mais la dernière collecte était partielle (il y a 0 h 9 min)
INFO       youtube              non configurée (clé ou compte absent dans .env)
ALERTE     rss                  en retard : dernière collecte réussie il y a 7 h 2 min (attendu : toutes les 4 h)
```

Délais tolérés : 6 h pour RSS et Google News, 30 h pour les sources quotidiennes, 8 jours pour Google Trends.

## Exports Google Trends (à faire une fois, puis chaque semaine)

```bash
flavortrends trends-plan               # France, en français
flavortrends trends-plan --geo US --lang en
```

La commande découpe les 102 arômes en 26 comparaisons de 4 termes, plus « vanille » comme terme d'ancrage commun, et donne le lien de chacune. Ouvrez chaque lien, téléchargez le CSV « Intérêt au fil du temps » dans `data/manual/google_trends/`, puis lancez `flavortrends import-trends`.

## Quota YouTube

Le budget par défaut (`YOUTUBE_UNIT_BUDGET=9000`) permet 89 recherches par jour. Avec 102 arômes × 2 langues = 204 recherches, une rotation quotidienne s'active : chaque arôme est couvert **une fois tous les 3 jours**. Pour couvrir tous les arômes chaque jour, demandez une hausse de quota gratuite à Google (console Google Cloud > YouTube Data API v3 > Quotas), ou ne gardez qu'une langue pour YouTube.

## Espace disque (Supabase)

L'offre gratuite de Supabase est limitée à 500 Mo. Les réglages `OFF_ONLY_FLAVOR_MATCHES`, `WIKIPEDIA_START`, `RAW_RETENTION_DAYS`, `BLUESKY_MAX_PAGES` et `DB_SIZE_LIMIT_MB` du `.env` permettent de tenir dans cette limite. `flavortrends status` affiche la taille de la base, et `flavortrends freshness` prévient à 80 % et 95 %.

## Périmètre

Tous les aliments, monde entier : `OFF_CATEGORIES` et `OFF_COUNTRIES` sont vides dans `.env`. Pour restreindre, mettez par exemple `OFF_CATEGORIES=en:beverages` ou `OFF_COUNTRIES=en:france`. Les vidéos YouTube arrivent dans toutes les langues (coréen, japonais…) : la langue de chaque document est détectée au nettoyage.

### Exemple de `flavortrends status`

```
source_id            family  raw_rows  pending  skipped  errors  clean_rows duplicates sponsored last_status
open_food_facts      market  300       0        5        0       295        0          0         success
gdelt                news    14        0        0        0       14         3          0         partial
google_news          news    86        0        0        0       86         0          1         success
rss                  news    250       0        0        0       250        0          0         success
wikipedia_pageviews  search  32016     0        0        0       32016      0          0         success
```

- `pending` : lignes brutes pas encore nettoyées.
- `skipped` : lignes écartées volontairement (raison dans `raw.raw_document.process_error`).
- `errors` : lignes en erreur. Après correction du code : `flavortrends clean --retry-errors`.
- `partial` : la collecte a fonctionné, mais certaines requêtes ont échoué ou le quota a été atteint.

## Tables produites (ce que lisent les étapes suivantes)

| Table | Une ligne = | Champs clés |
|---|---|---|
| `core.document` | une vidéo, un post ou un article | `published_at` (UTC), `lang`, `text_clean`, `engagement`, `flavor_hint` (arôme recherché), `dup_of` (NULL = document de référence), `is_sponsored`, `author_hash` |
| `core.product` | un produit Open Food Facts | `name`, `brands`, `ingredients_text`, `ingredients_tags`, `categories`, `added_at` |
| `core.search_interest` | un point de série (terme × zone × jour) | `source_id`, `term`, `geo`, `day`, `value`, `flavor_id`, `batch_id` |
| `core.flavor`, `core.flavor_alias` | un arôme et ses synonymes FR/EN | chargés depuis `taxonomy/flavors.csv` |

**Règle pour compter les mentions** : ne gardez que `dup_of IS NULL`, et pondérez `is_sponsored` à la baisse.

```sql
-- Exemple : documents de référence par source et par semaine
SELECT source_id, date_trunc('week', published_at) AS week, count(*)
FROM core.document WHERE dup_of IS NULL
GROUP BY 1, 2 ORDER BY 2 DESC;
```

## Modifier la liste des arômes

Éditez `taxonomy/flavors.csv` puis lancez `flavortrends load-taxonomy`.
Le premier alias de chaque langue sert de terme de recherche. Un arôme retiré du fichier passe en statut `retired` sans être supprimé.

## Tests

```bash
pytest                       # tests unitaires et collecteurs (réponses d'API simulées)
```

Pour inclure le test de bout en bout sur PostgreSQL, créez une base `flavors_test` puis :

```bash
set TEST_DATABASE_URL=postgresql://data:change-me@localhost:5432/flavors_test   # Windows (cmd)
pytest
```

## RGPD et bonnes pratiques

- Les auteurs sont pseudonymisés en couche propre (HMAC-SHA256 avec `PSEUDONYMIZATION_SALT`). Ne changez plus ce secret une fois choisi.
- Les posts Bluesky n'ont ni URL ni pseudo en couche propre.
- La couche brute contient des données personnelles (posts sociaux). Purgez-la régulièrement :
  `flavortrends purge-raw --older-than-days 180 --families social`
- Les clés d'API ne sont jamais écrites dans le journal ni dans la base.
- `.env` est ignoré par Git : ne le commitez jamais.
