-- ─────────────────────────────────────────────────────────────────────────────
-- Belmonts CRM — Schéma Supabase
-- À exécuter UNE SEULE FOIS dans Supabase Studio → SQL Editor
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS leads (
    id BIGSERIAL PRIMARY KEY,

    -- Données issues du scraping (mises à jour au prochain import)
    nom         TEXT        NOT NULL,
    type        TEXT        NOT NULL CHECK (type IN ('Syndic', 'Agence')),
    telephone   TEXT        DEFAULT '',
    email       TEXT        DEFAULT '',
    adresse     TEXT        DEFAULT '',
    ville       TEXT        DEFAULT '',
    departement TEXT        DEFAULT '',
    source      TEXT        DEFAULT '',

    -- Champs CRM édités par les commerciaux (PRÉSERVÉS au prochain import)
    telephone_alt TEXT      DEFAULT '',
    statut        TEXT      DEFAULT 'a_contacter' CHECK (statut IN (
                              'a_contacter', 'contacte', 'a_recontacter', 'client', 'refus'
                            )),
    notes         TEXT      DEFAULT '',
    date_recontact DATE,
    contacte_par   TEXT     DEFAULT '',
    date_dernier_contact TIMESTAMPTZ,

    -- Tracking
    date_ajout         TIMESTAMPTZ DEFAULT NOW(),
    date_modification  TIMESTAMPTZ DEFAULT NOW()
);

-- Dédup par téléphone : un tél = un bureau physique unique.
-- L'index est PARTIEL : ne s'applique que quand telephone est non vide,
-- ce qui permet d'avoir plusieurs leads sans téléphone.
CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_unique_tel
    ON leads(telephone)
    WHERE telephone IS NOT NULL AND telephone <> '';

-- Index de performance pour les filtres courants
CREATE INDEX IF NOT EXISTS idx_leads_statut       ON leads(statut);
CREATE INDEX IF NOT EXISTS idx_leads_dept         ON leads(departement);
CREATE INDEX IF NOT EXISTS idx_leads_type         ON leads(type);
CREATE INDEX IF NOT EXISTS idx_leads_modification ON leads(date_modification DESC);

-- Trigger : met à jour automatiquement date_modification à chaque UPDATE
CREATE OR REPLACE FUNCTION trigger_set_modification()
RETURNS TRIGGER AS $$
BEGIN
    NEW.date_modification = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS leads_set_modification ON leads;
CREATE TRIGGER leads_set_modification
    BEFORE UPDATE ON leads
    FOR EACH ROW
    EXECUTE FUNCTION trigger_set_modification();

-- Row Level Security (RLS) activée. La clé service_role bypass automatiquement
-- RLS et c'est elle qu'on utilise côté serveur Streamlit (jamais exposée au navigateur).
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
