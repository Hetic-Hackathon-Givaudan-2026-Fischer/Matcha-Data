-- Suivi des fichiers « delta » Open Food Facts déjà importés.
-- Open Food Facts publie chaque jour un fichier des produits modifiés dans le monde (14 derniers jours disponibles).
CREATE TABLE IF NOT EXISTS raw.off_delta_file (
    file_name    text PRIMARY KEY,
    run_id       bigint REFERENCES raw.collection_run,
    n_products   integer NOT NULL,
    imported_at  timestamptz NOT NULL DEFAULT now()
);
