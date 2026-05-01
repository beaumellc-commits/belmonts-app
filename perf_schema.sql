-- ─────────────────────────────────────────────────────────────────────────────
-- Belmonts CRM — Fonctions PostgreSQL pour ACCÉLÉRER l'app
-- À exécuter UNE SEULE FOIS dans Supabase Studio → SQL Editor
--
-- Ces fonctions RPC remplacent plusieurs requêtes paginées par UNE SEULE
-- requête côté serveur. Gain typique : 750ms → 200ms par appel.
-- ─────────────────────────────────────────────────────────────────────────────

-- 1. Compteurs sidebar (À contacter / Contacté / etc.) — appelé à chaque page load
CREATE OR REPLACE FUNCTION get_status_counts()
RETURNS TABLE(statut TEXT, count BIGINT)
LANGUAGE SQL
STABLE
AS $$
    SELECT statut, COUNT(*)::BIGINT
    FROM leads
    GROUP BY statut;
$$;

GRANT EXECUTE ON FUNCTION get_status_counts() TO anon, authenticated, service_role;


-- 2. Stats globales (page Statistiques) — un seul appel pour tout
CREATE OR REPLACE FUNCTION get_dashboard_stats()
RETURNS json
LANGUAGE SQL
STABLE
AS $$
    SELECT json_build_object(
        'total', COALESCE((SELECT COUNT(*)::int FROM leads), 0),
        'by_statut', COALESCE(
            (SELECT json_object_agg(statut, c)
             FROM (SELECT statut, COUNT(*)::int AS c
                   FROM leads GROUP BY statut) s),
            '{}'::json
        ),
        'by_dept', COALESCE(
            (SELECT json_object_agg(departement, c)
             FROM (SELECT departement, COUNT(*)::int AS c
                   FROM leads GROUP BY departement) d),
            '{}'::json
        ),
        'by_type', COALESCE(
            (SELECT json_object_agg(type, c)
             FROM (SELECT type, COUNT(*)::int AS c
                   FROM leads GROUP BY type) t),
            '{}'::json
        ),
        'by_user', COALESCE(
            (SELECT json_object_agg(contacte_par, c)
             FROM (SELECT contacte_par, COUNT(*)::int AS c
                   FROM leads
                   WHERE contacte_par IS NOT NULL AND contacte_par <> ''
                   GROUP BY contacte_par) u),
            '{}'::json
        )
    );
$$;

GRANT EXECUTE ON FUNCTION get_dashboard_stats() TO anon, authenticated, service_role;


-- 3. Liste distincte des villes (pour le dropdown), super rapide
CREATE OR REPLACE FUNCTION get_distinct_villes(dept TEXT DEFAULT NULL)
RETURNS TABLE(ville TEXT)
LANGUAGE SQL
STABLE
AS $$
    SELECT DISTINCT ville
    FROM leads
    WHERE ville IS NOT NULL AND ville <> ''
      AND (dept IS NULL OR departement = dept)
    ORDER BY ville;
$$;

GRANT EXECUTE ON FUNCTION get_distinct_villes(TEXT) TO anon, authenticated, service_role;
