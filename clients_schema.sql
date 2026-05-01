-- ─────────────────────────────────────────────────────────────────────────────
-- Belmonts CRM — Module Clients (portefeuille MBS + Belmonts)
-- À exécuter UNE SEULE FOIS dans Supabase Studio → SQL Editor
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS clients (
    id BIGSERIAL PRIMARY KEY,

    -- Identification
    nom         TEXT        NOT NULL,
    siret       TEXT        DEFAULT '',
    code        TEXT        DEFAULT '',  -- code interne (Code dans le CSV)

    -- Coordonnées
    adresse     TEXT        DEFAULT '',
    adresse2    TEXT        DEFAULT '',
    cp          TEXT        DEFAULT '',
    ville       TEXT        DEFAULT '',
    tel         TEXT        DEFAULT '',
    tel2        TEXT        DEFAULT '',
    email       TEXT        DEFAULT '',
    dirigeant   TEXT        DEFAULT '',

    -- Indicateurs entreprise — un client peut être chez MBS, Belmonts, ou les deux
    client_mbs       BOOLEAN DEFAULT FALSE,
    client_belmonts  BOOLEAN DEFAULT FALSE,

    -- Suivi commercial
    observations    TEXT    DEFAULT '',  -- venant du CSV (Observations facture)
    tags            TEXT    DEFAULT '',
    notes           TEXT    DEFAULT '',  -- notes internes commerciaux
    bloque          BOOLEAN DEFAULT FALSE,

    -- Tracking
    date_ajout         TIMESTAMPTZ DEFAULT NOW(),
    date_modification  TIMESTAMPTZ DEFAULT NOW()
);

-- Dédup forte : SIRET unique quand renseigné
CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_unique_siret
    ON clients(siret)
    WHERE siret IS NOT NULL AND siret <> '';

-- Index de performance pour les filtres courants
CREATE INDEX IF NOT EXISTS idx_clients_mbs        ON clients(client_mbs);
CREATE INDEX IF NOT EXISTS idx_clients_belm       ON clients(client_belmonts);
CREATE INDEX IF NOT EXISTS idx_clients_nom_lower  ON clients(LOWER(nom));
CREATE INDEX IF NOT EXISTS idx_clients_modif      ON clients(date_modification DESC);

-- Trigger date_modification (réutilise la fonction existante créée par leads)
DROP TRIGGER IF EXISTS clients_set_modification ON clients;
CREATE TRIGGER clients_set_modification
    BEFORE UPDATE ON clients
    FOR EACH ROW
    EXECUTE FUNCTION trigger_set_modification();

ALTER TABLE clients ENABLE ROW LEVEL SECURITY;


-- ─────────────────────────────────────────────────────────────────────────────
-- Fonctions RPC pour stats clients (perf)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION get_clients_counts()
RETURNS json LANGUAGE SQL STABLE AS $$
    SELECT json_build_object(
        'total',     (SELECT COUNT(*)::int FROM clients),
        'mbs',       (SELECT COUNT(*)::int FROM clients WHERE client_mbs = TRUE),
        'belmonts',  (SELECT COUNT(*)::int FROM clients WHERE client_belmonts = TRUE),
        'communs',   (SELECT COUNT(*)::int FROM clients
                      WHERE client_mbs = TRUE AND client_belmonts = TRUE)
    );
$$;
GRANT EXECUTE ON FUNCTION get_clients_counts() TO anon, authenticated, service_role;
