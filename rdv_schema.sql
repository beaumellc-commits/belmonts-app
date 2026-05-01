-- ─────────────────────────────────────────────────────────────────────────────
-- Belmonts CRM — Module Rendez-vous (RDV terrain ↔ bureau)
-- À exécuter UNE SEULE FOIS dans Supabase Studio → SQL Editor
-- (après supabase_schema.sql qui crée la table `leads`)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS rendez_vous (
    id BIGSERIAL PRIMARY KEY,

    -- Lien vers le lead concerné (cascade : supprimer un lead supprime ses RDV)
    lead_id     BIGINT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,

    -- Planification
    date_rdv    TIMESTAMPTZ NOT NULL,
    duree_min   INT     DEFAULT 60,
    type        TEXT    DEFAULT 'physique'
                        CHECK (type IN ('physique', 'visio', 'telephone')),
    lieu        TEXT    DEFAULT '',
    assigne_a   TEXT    DEFAULT '',  -- username du commercial assigné

    -- Statut
    statut      TEXT    DEFAULT 'a_venir'
                        CHECK (statut IN ('a_venir', 'termine', 'annule', 'reporte')),

    -- Contenu
    briefing      TEXT  DEFAULT '',  -- préparation par le bureau
    compte_rendu  TEXT  DEFAULT '',  -- rapport après le RDV par le terrain
    resultat      TEXT  DEFAULT '',  -- ex: "devis demandé", "pas intéressé"

    -- Audit
    cree_par     TEXT          NOT NULL,
    cree_le      TIMESTAMPTZ   DEFAULT NOW(),
    modifie_le   TIMESTAMPTZ   DEFAULT NOW()
);

-- Index pour les requêtes courantes
CREATE INDEX IF NOT EXISTS idx_rdv_lead     ON rendez_vous(lead_id);
CREATE INDEX IF NOT EXISTS idx_rdv_date     ON rendez_vous(date_rdv);
CREATE INDEX IF NOT EXISTS idx_rdv_assigne  ON rendez_vous(assigne_a);
CREATE INDEX IF NOT EXISTS idx_rdv_statut   ON rendez_vous(statut);

-- Trigger : maj auto de modifie_le à chaque UPDATE
-- (fonction dédiée car la table `leads` a 'date_modification' mais ici c'est 'modifie_le')
CREATE OR REPLACE FUNCTION trigger_set_modifie_le()
RETURNS TRIGGER AS $$
BEGIN
    NEW.modifie_le = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS rdv_set_modification ON rendez_vous;
CREATE TRIGGER rdv_set_modification
    BEFORE UPDATE ON rendez_vous
    FOR EACH ROW
    EXECUTE FUNCTION trigger_set_modifie_le();

-- RLS activée. La clé service_role bypass automatiquement.
ALTER TABLE rendez_vous ENABLE ROW LEVEL SECURITY;


-- ─────────────────────────────────────────────────────────────────────────────
-- Table des CONTACTS rencontrés pendant un RDV
-- (un RDV peut avoir plusieurs contacts : directeur, comptable, gestionnaire…)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rdv_contacts (
    id          BIGSERIAL PRIMARY KEY,
    rdv_id      BIGINT      NOT NULL REFERENCES rendez_vous(id) ON DELETE CASCADE,

    nom         TEXT        NOT NULL,
    poste       TEXT        DEFAULT '',  -- ex : Directeur, Comptable, Gardien
    telephone   TEXT        DEFAULT '',
    email       TEXT        DEFAULT '',
    notes       TEXT        DEFAULT '',  -- ex : Décisionnaire, à recontacter pour devis

    cree_le     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rdv_contacts_rdv ON rdv_contacts(rdv_id);

ALTER TABLE rdv_contacts ENABLE ROW LEVEL SECURITY;
