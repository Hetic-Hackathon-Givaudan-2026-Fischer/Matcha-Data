-- Couche brute : on stocke les réponses des API telles quelles, sans jamais les modifier.
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.source (
    source_id    text PRIMARY KEY,
    family       text NOT NULL CHECK (family IN ('social', 'search', 'news', 'market', 'science')),
    description  text NOT NULL,
    licence      text,
    url          text
);

INSERT INTO raw.source (source_id, family, description, licence, url) VALUES
  ('wikipedia_pageviews', 'search', 'Vues quotidiennes des articles Wikipédia', 'CC0 (données Wikimedia)', 'https://wikimedia.org/api/rest_v1/'),
  ('open_food_facts',     'market', 'Produits alimentaires (ingrédients, marques, catégories)', 'ODbL', 'https://world.openfoodfacts.org'),
  ('youtube',             'social', 'Vidéos YouTube et statistiques', 'Conditions YouTube API', 'https://developers.google.com/youtube/v3'),
  ('gdelt',               'news',   'Articles de presse mondiale (GDELT DOC 2.0)', 'Libre, citer GDELT', 'https://api.gdeltproject.org'),
  ('rss',                 'news',   'Flux RSS de presse spécialisée', 'Selon chaque éditeur : titre, résumé et lien uniquement', NULL),
  ('google_news',         'news',   'Google News RSS par requête', 'Usage personnel et recherche, vérifier les CGU', 'https://news.google.com'),
  ('bluesky',             'social', 'Posts publics Bluesky (AT Protocol)', 'Conditions Bluesky', 'https://docs.bsky.app'),
  ('google_trends',       'search', 'Exports CSV manuels de Google Trends', 'Conditions Google', 'https://trends.google.com')
ON CONFLICT (source_id) DO UPDATE
  SET family = EXCLUDED.family, description = EXCLUDED.description,
      licence = EXCLUDED.licence, url = EXCLUDED.url;

-- Une ligne par exécution d'un collecteur : sert au suivi et au débogage.
CREATE TABLE IF NOT EXISTS raw.collection_run (
    run_id       bigserial PRIMARY KEY,
    source_id    text NOT NULL REFERENCES raw.source,
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    status       text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'partial', 'failed')),
    params       jsonb NOT NULL DEFAULT '{}'::jsonb,
    n_fetched    integer NOT NULL DEFAULT 0,
    n_inserted   integer NOT NULL DEFAULT 0,
    n_errors     integer NOT NULL DEFAULT 0,
    error        text
);

-- Chaque version distincte d'un document est conservée (ex. : les vues d'une vidéo changent).
-- La contrainte d'unicité sur (source, id externe, hash) rend la collecte idempotente :
-- relancer un collecteur n'insère que ce qui a changé.
CREATE TABLE IF NOT EXISTS raw.raw_document (
    id             bigserial PRIMARY KEY,
    source_id      text NOT NULL REFERENCES raw.source,
    external_id    text NOT NULL,
    run_id         bigint REFERENCES raw.collection_run,
    fetched_at     timestamptz NOT NULL DEFAULT now(),
    query          text,
    flavor_id      text,
    payload        jsonb NOT NULL,
    payload_hash   text NOT NULL,
    processed_at   timestamptz,
    process_error  text,
    UNIQUE (source_id, external_id, payload_hash)
);

CREATE INDEX IF NOT EXISTS raw_document_unprocessed_idx
    ON raw.raw_document (source_id, id) WHERE processed_at IS NULL;
CREATE INDEX IF NOT EXISTS raw_document_fetched_idx ON raw.raw_document (fetched_at);
