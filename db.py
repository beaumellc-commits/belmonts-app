"""
Couche d'accès Supabase pour Belmonts CRM.
Toutes les opérations sur la table `leads` passent par ce module.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

# Mapping statut → libellé affiché (utilisé partout dans l'UI)
STATUTS: dict[str, str] = {
    "a_contacter":   "À contacter",
    "contacte":      "Contacté",
    "a_recontacter": "À recontacter",
    "client":        "Client",
    "refus":         "Refus",
}

# Couleur d'accent par statut — utilisée dans la sidebar et les pills
STATUTS_COLOR: dict[str, str] = {
    "a_contacter":   "#cc2020",  # rouge Belmonts (action prioritaire)
    "contacte":      "#3b82f6",  # bleu (en cours)
    "a_recontacter": "#f59e0b",  # ambre (à suivre)
    "client":        "#10b981",  # vert (gagné)
    "refus":         "#6b7280",  # gris (perdu, désaccentué)
}

# Statuts RDV
STATUTS_RDV: dict[str, str] = {
    "a_venir":  "À venir",
    "termine":  "Terminé",
    "reporte":  "Reporté",
    "annule":   "Annulé",
}

TYPES_RDV: dict[str, str] = {
    "physique":  "Physique (sur place)",
    "visio":     "Visio",
    "telephone": "Téléphone",
}


def _get_secret(key: str) -> str | None:
    """Lit un secret. Priorité env vars (Render) puis st.secrets (Streamlit Cloud)."""
    val = os.environ.get(key)
    if val:
        return val
    try:
        return st.secrets.get(key)
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def _client():
    """Singleton du client Supabase. Cache géré par Streamlit."""
    from supabase import create_client
    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Variables SUPABASE_URL et SUPABASE_KEY introuvables. "
            "Configure-les dans .streamlit/secrets.toml (local) "
            "ou dans les variables d'environnement (Render)."
        )
    return create_client(url, key)


# ─── LECTURE ──────────────────────────────────────────────────────────────────
# Note : Supabase/PostgREST renvoie max 1000 lignes par requête. On pagine via
# `.range(start, end)` pour récupérer plus de 1000 leads.
PAGE_SIZE = 1000


def _build_leads_query(
    statut: str | None,
    departement: str | None,
    ville: str | None,
    type_prospect: str | None,
    search: str | None,
    columns: str,
):
    sb = _client()
    q = sb.table("leads").select(columns)
    if statut:
        q = q.eq("statut", statut)
    if departement:
        q = q.eq("departement", departement)
    if ville:
        q = q.eq("ville", ville)
    if type_prospect:
        q = q.eq("type", type_prospect)
    if search and search.strip():
        q = q.ilike("nom", f"%{search.strip()}%")
    return q


@st.cache_data(ttl=30, show_spinner=False)
def fetch_leads(
    statut: str | None = None,
    departement: str | None = None,
    ville: str | None = None,
    type_prospect: str | None = None,
    search: str | None = None,
    limit: int = 50000,
) -> pd.DataFrame:
    """Récupère tous les leads (paginé). Limit max conseillée : 50 000."""
    all_rows: list[dict] = []
    start = 0
    while len(all_rows) < limit:
        q = _build_leads_query(statut, departement, ville, type_prospect, search, "*")
        end = min(start + PAGE_SIZE - 1, limit - 1)
        res = q.order("date_modification", desc=True).range(start, end).execute()
        rows = res.data or []
        all_rows.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return pd.DataFrame(all_rows)


def _ville_sort_key(v: str) -> tuple[int, Any]:
    """Trie 'Paris 1' à 'Paris 20' numériquement, le reste alphabétiquement."""
    m = re.match(r"^Paris\s+(\d+)$", (v or "").strip(), re.IGNORECASE)
    if m:
        return (0, int(m.group(1)))
    return (1, (v or "").lower())


@st.cache_data(ttl=120, show_spinner=False)
def fetch_villes(departement: str | None = None) -> list[str]:
    """
    Retourne la liste triée des villes/arrondissements présents en BD,
    optionnellement filtrés par département.

    Pour Paris (75) : Paris 1, Paris 2, …, Paris 20 (ordre numérique).
    Pour les autres dpt : ordre alphabétique des villes.
    """
    sb = _client()
    villes: set[str] = set()
    start = 0
    while True:
        q = sb.table("leads").select("ville,departement")
        if departement:
            q = q.eq("departement", departement)
        res = q.range(start, start + PAGE_SIZE - 1).execute()
        rows = res.data or []
        for r in rows:
            if r.get("ville"):
                villes.add(r["ville"])
        if len(rows) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return sorted(villes, key=_ville_sort_key)


def fetch_lead(lead_id: int) -> dict[str, Any] | None:
    """Pas de cache : on veut toujours la version la plus fraîche pour l'édition."""
    sb = _client()
    res = sb.table("leads").select("*").eq("id", lead_id).execute()
    return res.data[0] if res.data else None


@st.cache_data(ttl=20, show_spinner=False)
def get_counts() -> dict[str, int]:
    """Compte les leads par statut. Paginé pour aller au-delà de 1000."""
    sb = _client()
    counts = {k: 0 for k in STATUTS}
    start = 0
    while True:
        res = sb.table("leads").select("statut").range(start, start + PAGE_SIZE - 1).execute()
        rows = res.data or []
        for row in rows:
            s = row.get("statut") or "a_contacter"
            if s in counts:
                counts[s] += 1
        if len(rows) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    counts["total"] = sum(counts.values())
    return counts


@st.cache_data(ttl=60, show_spinner=False)
def get_stats() -> dict[str, Any]:
    sb = _client()
    all_rows: list[dict] = []
    start = 0
    while True:
        res = sb.table("leads").select(
            "statut,type,departement,contacte_par,date_dernier_contact"
        ).range(start, start + PAGE_SIZE - 1).execute()
        rows = res.data or []
        all_rows.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    df = pd.DataFrame(all_rows)
    if df.empty:
        return {
            "total": 0, "by_statut": {}, "by_dept": {},
            "by_type": {}, "by_user": {},
        }
    return {
        "total": len(df),
        "by_statut": df.groupby("statut").size().to_dict(),
        "by_dept":   df.groupby("departement").size().to_dict(),
        "by_type":   df.groupby("type").size().to_dict(),
        "by_user":   df[df["contacte_par"].fillna("") != ""]
                       .groupby("contacte_par").size().to_dict(),
    }


def invalidate_cache() -> None:
    """Vide les caches de lecture après un write. À appeler post-update/import."""
    fetch_leads.clear()
    fetch_villes.clear()
    get_counts.clear()
    get_stats.clear()


# ─── ÉCRITURE ─────────────────────────────────────────────────────────────────
def update_lead(lead_id: int, updates: dict[str, Any], user: str) -> None:
    sb = _client()
    payload = {k: v for k, v in updates.items() if k not in {"id", "date_ajout", "date_modification"}}

    # Si le statut bascule "à autre chose que à_contacter", on log le contact
    if "statut" in payload and payload["statut"] != "a_contacter":
        payload["date_dernier_contact"] = datetime.now().isoformat()
        payload["contacte_par"] = user

    sb.table("leads").update(payload).eq("id", lead_id).execute()
    invalidate_cache()


def _clean_str(v: Any) -> str:
    """Convertit en chaîne propre. Gère les NaN / None / '<NA>' que pandas
    peut produire à la lecture d'un Excel."""
    if v is None:
        return ""
    # Test NaN sans importer numpy
    if isinstance(v, float) and v != v:
        return ""
    s = str(v).strip()
    if s.lower() in {"nan", "none", "null", "<na>", "na"}:
        return ""
    return s


def import_from_excel(df: pd.DataFrame) -> tuple[int, int, int]:
    """
    Upsert depuis un DataFrame Excel généré par scrape_leads.py.

    Comportement :
    - Si un lead avec ce téléphone existe : on met à jour ses coordonnées
      mais on PRÉSERVE statut, notes, telephone_alt, etc.
    - Sinon : insertion d'un nouveau lead avec statut 'a_contacter' par défaut.

    Retourne (nouveaux, mis_a_jour, ignorés).
    """
    sb = _client()

    # Le fichier Excel a des colonnes en français — on les remappe
    col_map = {
        "Entreprise": "nom",       "Type": "type",
        "Téléphone":  "telephone", "Email": "email",
        "Adresse":    "adresse",   "Ville": "ville",
        "Département": "departement", "Source": "source",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # Récupère TOUS les leads existants (paginé) pour détecter les doublons
    # à la fois par téléphone ET par (nom + ville) pour ceux sans tél.
    existing_tels: dict[str, int] = {}
    existing_nv: dict[tuple[str, str], int] = {}  # (nom_lower, ville_lower) -> id
    start = 0
    while True:
        res = sb.table("leads").select("id,telephone,nom,ville").range(
            start, start + PAGE_SIZE - 1
        ).execute()
        rows = res.data or []
        for r in rows:
            t = (r.get("telephone") or "").strip()
            if t:
                existing_tels[t] = r["id"]
            nom_l = (r.get("nom") or "").strip().lower()
            ville_l = (r.get("ville") or "").strip().lower()
            if nom_l:
                existing_nv[(nom_l, ville_l)] = r["id"]
        if len(rows) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    inserts: list[dict] = []
    updates: list[tuple[int, dict]] = []
    skip = 0
    seen_tels_in_batch: set[str] = set()
    seen_nv_in_batch: set[tuple[str, str]] = set()

    for _, row in df.iterrows():
        nom = _clean_str(row.get("nom"))
        if not nom:
            skip += 1
            continue

        tel = _clean_str(row.get("telephone"))
        ville = _clean_str(row.get("ville"))
        type_ = _clean_str(row.get("type")) or "Syndic"
        if type_ not in {"Syndic", "Agence"}:
            type_ = "Syndic"

        payload = {
            "nom": nom, "type": type_, "telephone": tel,
            "email":       _clean_str(row.get("email")),
            "adresse":     _clean_str(row.get("adresse")),
            "ville":       ville,
            "departement": _clean_str(row.get("departement")),
            "source":      _clean_str(row.get("source")),
        }

        nv_key = (nom.lower(), ville.lower())

        # 1. Si on a un tél, c'est notre clé primaire de dédup
        if tel:
            # a. Doublon dans le fichier importé lui-même → skip
            if tel in seen_tels_in_batch:
                skip += 1
                continue
            seen_tels_in_batch.add(tel)
            seen_nv_in_batch.add(nv_key)

            # b. Existe déjà en BD → update (préserve les champs CRM)
            if tel in existing_tels:
                updates.append((existing_tels[tel], payload))
            else:
                inserts.append(payload)
            continue

        # 2. Pas de tél → dédup par (nom + ville)
        if nv_key in seen_nv_in_batch:
            skip += 1
            continue
        seen_nv_in_batch.add(nv_key)

        if nv_key in existing_nv:
            updates.append((existing_nv[nv_key], payload))
        else:
            inserts.append(payload)

    new_count = 0
    update_count = 0

    # Inserts en batch (Supabase tient ~500 par requête)
    BATCH = 500
    for i in range(0, len(inserts), BATCH):
        batch = inserts[i:i + BATCH]
        sb.table("leads").insert(batch).execute()
        new_count += len(batch)

    # Updates un par un (préserve les champs CRM)
    for lead_id, payload in updates:
        sb.table("leads").update(payload).eq("id", lead_id).execute()
        update_count += 1

    invalidate_cache()
    return new_count, update_count, skip


# ─── RENDEZ-VOUS ──────────────────────────────────────────────────────────────
def _invalidate_rdv_cache() -> None:
    fetch_rdvs_for_lead.clear()
    fetch_rdvs.clear()


@st.cache_data(ttl=20, show_spinner=False)
def fetch_rdvs_for_lead(lead_id: int) -> list[dict[str, Any]]:
    """Tous les RDV d'un lead, du plus récent au plus ancien."""
    sb = _client()
    res = (sb.table("rendez_vous").select("*")
             .eq("lead_id", lead_id)
             .order("date_rdv", desc=True)
             .execute())
    return res.data or []


@st.cache_data(ttl=20, show_spinner=False)
def fetch_rdvs(
    assigne_a: str | None = None,
    statut: str | None = None,
    date_min: str | None = None,
    date_max: str | None = None,
) -> list[dict[str, Any]]:
    """
    Liste des RDV avec leur lead joint (nom, tél, ville, adresse).
    Triée par date croissante (les prochains en premier).
    """
    sb = _client()
    all_rows: list[dict] = []
    start = 0
    while True:
        q = sb.table("rendez_vous").select(
            "*, leads(nom, telephone, ville, departement, adresse, type)"
        )
        if assigne_a:
            q = q.eq("assigne_a", assigne_a)
        if statut:
            q = q.eq("statut", statut)
        if date_min:
            q = q.gte("date_rdv", date_min)
        if date_max:
            q = q.lte("date_rdv", date_max)
        res = q.order("date_rdv").range(start, start + PAGE_SIZE - 1).execute()
        rows = res.data or []
        all_rows.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return all_rows


def create_rdv(lead_id: int, data: dict[str, Any], user: str) -> dict | None:
    sb = _client()
    payload = {
        "lead_id":   lead_id,
        "date_rdv":  data["date_rdv"],
        "duree_min": data.get("duree_min", 60),
        "type":      data.get("type", "physique"),
        "lieu":      data.get("lieu", ""),
        "assigne_a": data.get("assigne_a", user),
        "briefing":  data.get("briefing", ""),
        "statut":    "a_venir",
        "cree_par":  user,
    }
    res = sb.table("rendez_vous").insert(payload).execute()
    _invalidate_rdv_cache()
    return res.data[0] if res.data else None


def update_rdv(rdv_id: int, updates: dict[str, Any]) -> None:
    sb = _client()
    forbidden = {"id", "lead_id", "cree_par", "cree_le", "modifie_le"}
    payload = {k: v for k, v in updates.items() if k not in forbidden}
    sb.table("rendez_vous").update(payload).eq("id", rdv_id).execute()
    _invalidate_rdv_cache()


def delete_rdv(rdv_id: int) -> None:
    sb = _client()
    sb.table("rendez_vous").delete().eq("id", rdv_id).execute()
    _invalidate_rdv_cache()


# ─── CONTACTS RENCONTRÉS PENDANT UN RDV ───────────────────────────────────────
@st.cache_data(ttl=20, show_spinner=False)
def fetch_contacts_for_rdv(rdv_id: int) -> list[dict[str, Any]]:
    """Liste les contacts rencontrés pendant un RDV donné, par ordre d'ajout."""
    sb = _client()
    res = (sb.table("rdv_contacts").select("*")
             .eq("rdv_id", rdv_id)
             .order("cree_le")
             .execute())
    return res.data or []


def add_rdv_contact(rdv_id: int, data: dict[str, Any]) -> dict | None:
    sb = _client()
    payload = {
        "rdv_id":    rdv_id,
        "nom":       (data.get("nom") or "").strip(),
        "poste":     (data.get("poste") or "").strip(),
        "telephone": (data.get("telephone") or "").strip(),
        "email":     (data.get("email") or "").strip(),
        "notes":     (data.get("notes") or "").strip(),
    }
    if not payload["nom"]:
        return None
    res = sb.table("rdv_contacts").insert(payload).execute()
    fetch_contacts_for_rdv.clear()
    return res.data[0] if res.data else None


def update_rdv_contact(contact_id: int, updates: dict[str, Any]) -> None:
    sb = _client()
    forbidden = {"id", "rdv_id", "cree_le"}
    payload = {k: v for k, v in updates.items() if k not in forbidden}
    sb.table("rdv_contacts").update(payload).eq("id", contact_id).execute()
    fetch_contacts_for_rdv.clear()


def delete_rdv_contact(contact_id: int) -> None:
    sb = _client()
    sb.table("rdv_contacts").delete().eq("id", contact_id).execute()
    fetch_contacts_for_rdv.clear()
