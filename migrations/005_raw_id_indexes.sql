-- Index sur raw_id : quand une ligne brute est supprimée (purge), PostgreSQL doit retrouver
-- la ligne propre qui la référence pour vider son lien. Sans index, il parcourt toute la table
-- à chaque suppression, et une purge de 200 000 lignes dépasse le délai maximal de Supabase.
CREATE INDEX IF NOT EXISTS document_raw_id_idx ON core.document (raw_id);
CREATE INDEX IF NOT EXISTS product_raw_id_idx ON core.product (raw_id);
CREATE INDEX IF NOT EXISTS search_interest_raw_id_idx ON core.search_interest (raw_id);
