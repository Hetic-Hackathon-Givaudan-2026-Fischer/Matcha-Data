-- Couche propre : données nettoyées, typées, dédoublonnées et pseudonymisées.
CREATE SCHEMA IF NOT EXISTS core;

-- Taxonomie des arômes (chargée depuis taxonomy/flavors.csv)
CREATE TABLE IF NOT EXISTS core.flavor (
    flavor_id    text PRIMARY KEY,
    name_fr      text NOT NULL,
    name_en      text NOT NULL,
    family       text NOT NULL,
    wiki_fr      text,
    wiki_en      text,
    status       text NOT NULL DEFAULT 'validated' CHECK (status IN ('validated', 'candidate', 'retired')),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.flavor_alias (
    alias        text NOT NULL,
    lang         text NOT NULL,
    flavor_id    text NOT NULL REFERENCES core.flavor ON DELETE CASCADE,
    position     smallint NOT NULL DEFAULT 0,   -- 0 = terme principal, utilisé pour les recherches
    PRIMARY KEY (alias, lang)
);

-- Documents texte : vidéos, posts, articles.
CREATE TABLE IF NOT EXISTS core.document (
    doc_id          bigserial PRIMARY KEY,
    source_id       text NOT NULL REFERENCES raw.source,
    external_id     text NOT NULL,
    raw_id          bigint NOT NULL REFERENCES raw.raw_document(id),
    doc_type        text NOT NULL CHECK (doc_type IN ('video', 'post', 'article')),
    published_at    timestamptz NOT NULL,
    lang            text,
    lang_source     text CHECK (lang_source IN ('source', 'detected', 'unknown')),
    country         text,
    title           text,
    body            text,
    text_clean      text NOT NULL,
    url             text,
    author_hash     text,
    engagement      jsonb NOT NULL DEFAULT '{}'::jsonb,
    query           text,
    flavor_hint     text,
    content_hash    text NOT NULL,
    minhash         bytea,
    dup_of          bigint REFERENCES core.document(doc_id),
    dup_method      text CHECK (dup_method IN ('exact', 'near')),
    is_sponsored    boolean NOT NULL DEFAULT false,
    quality_flags   text[] NOT NULL DEFAULT '{}',
    cleaned_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, external_id)
);
CREATE INDEX IF NOT EXISTS document_published_idx ON core.document (published_at);
CREATE INDEX IF NOT EXISTS document_content_hash_idx ON core.document (content_hash);
CREATE INDEX IF NOT EXISTS document_canonical_idx ON core.document (published_at) WHERE dup_of IS NULL;

-- Produits Open Food Facts
CREATE TABLE IF NOT EXISTS core.product (
    code              text PRIMARY KEY,
    raw_id            bigint NOT NULL REFERENCES raw.raw_document(id),
    name              text,
    generic_name      text,
    brands            text[] NOT NULL DEFAULT '{}',
    brand_main        text,
    categories        text[] NOT NULL DEFAULT '{}',
    ingredients_text  text,
    ingredients_tags  text[] NOT NULL DEFAULT '{}',
    countries         text[] NOT NULL DEFAULT '{}',
    lang              text,
    added_at          timestamptz,           -- date d'ajout dans Open Food Facts (pas la date de lancement)
    last_modified_at  timestamptz,
    quality_flags     text[] NOT NULL DEFAULT '{}',
    cleaned_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS product_added_idx ON core.product (added_at);

-- Séries d'intérêt : vues Wikipédia, Google Trends.
-- batch_id distingue les exports Google Trends : leurs valeurs (0-100) ne sont comparables qu'à l'intérieur d'un même export.
CREATE TABLE IF NOT EXISTS core.search_interest (
    source_id     text NOT NULL REFERENCES raw.source,
    term          text NOT NULL,
    geo           text NOT NULL,
    day           date NOT NULL,
    batch_id      text NOT NULL DEFAULT '',
    flavor_id     text REFERENCES core.flavor,
    value         real NOT NULL,
    granularity   text NOT NULL CHECK (granularity IN ('day', 'week', 'month')),
    is_censored   boolean NOT NULL DEFAULT false,   -- Google Trends « <1 »
    raw_id        bigint NOT NULL REFERENCES raw.raw_document(id),
    cleaned_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, term, geo, day, batch_id)
);
CREATE INDEX IF NOT EXISTS search_interest_flavor_idx ON core.search_interest (flavor_id, day);
