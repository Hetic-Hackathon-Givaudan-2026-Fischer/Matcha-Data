-- Permet de supprimer la couche brute après nettoyage (économie d'espace, utile sur Supabase).
-- Les lignes propres gardent leurs données ; seul le lien vers la ligne brute devient vide (NULL).
ALTER TABLE core.document ALTER COLUMN raw_id DROP NOT NULL;
ALTER TABLE core.document DROP CONSTRAINT IF EXISTS document_raw_id_fkey;
ALTER TABLE core.document ADD CONSTRAINT document_raw_id_fkey
    FOREIGN KEY (raw_id) REFERENCES raw.raw_document(id) ON DELETE SET NULL;

ALTER TABLE core.product ALTER COLUMN raw_id DROP NOT NULL;
ALTER TABLE core.product DROP CONSTRAINT IF EXISTS product_raw_id_fkey;
ALTER TABLE core.product ADD CONSTRAINT product_raw_id_fkey
    FOREIGN KEY (raw_id) REFERENCES raw.raw_document(id) ON DELETE SET NULL;

ALTER TABLE core.search_interest ALTER COLUMN raw_id DROP NOT NULL;
ALTER TABLE core.search_interest DROP CONSTRAINT IF EXISTS search_interest_raw_id_fkey;
ALTER TABLE core.search_interest ADD CONSTRAINT search_interest_raw_id_fkey
    FOREIGN KEY (raw_id) REFERENCES raw.raw_document(id) ON DELETE SET NULL;
