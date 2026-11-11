-- Verrous de travaux (collecte d'une source, nettoyage) stockés dans une table, avec « battement de cœur ».
-- Remplace les verrous de session PostgreSQL : avec le pooler de Supabase, une session peut survivre au
-- programme qui l'a ouverte (coupure réseau) et garder son verrou indéfiniment.
-- Ici, un verrou sans battement de cœur depuis 15 minutes est considéré comme abandonné et peut être repris.
CREATE TABLE IF NOT EXISTS raw.job_lock (
    lock_name     text PRIMARY KEY,
    holder        text NOT NULL,
    acquired_at   timestamptz NOT NULL DEFAULT now(),
    heartbeat_at  timestamptz NOT NULL DEFAULT now()
);
