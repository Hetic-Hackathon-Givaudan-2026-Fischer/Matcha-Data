-- Pinterest : veille manuelle (CSV) et, si l'accès est accordé, API Trends.
INSERT INTO raw.source (source_id, family, description, licence, url) VALUES
  ('pinterest', 'search', 'Tendances Pinterest : veille manuelle (CSV) ou API Trends (réservée aux partenaires)',
   'Conditions Pinterest ; pas de scraping', 'https://trends.pinterest.com')
ON CONFLICT (source_id) DO NOTHING;

-- Listes de tendances observées sur des plateformes externes (Pinterest aujourd'hui, d'autres demain).
-- Une ligne = un mot-clé en tendance, observé un jour donné, dans un pays donné.
CREATE TABLE IF NOT EXISTS core.external_trend (
    source_id       text NOT NULL REFERENCES raw.source,
    observed_on     date NOT NULL,
    region          text NOT NULL,
    keyword         text NOT NULL,
    trend_type      text NOT NULL DEFAULT '',
    flavor_id       text REFERENCES core.flavor,     -- NULL = mot-clé inconnu de notre liste (candidat à ajouter)
    rank            smallint,
    pct_growth_wow  real,                            -- croissance sur 1 semaine (%)
    pct_growth_mom  real,                            -- sur 1 mois
    pct_growth_yoy  real,                            -- sur 1 an
    note            text,
    url             text,
    raw_id          bigint REFERENCES raw.raw_document(id) ON DELETE SET NULL,
    cleaned_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, observed_on, region, keyword, trend_type)
);
CREATE INDEX IF NOT EXISTS external_trend_flavor_idx ON core.external_trend (flavor_id, observed_on);
CREATE INDEX IF NOT EXISTS external_trend_raw_id_idx ON core.external_trend (raw_id);
