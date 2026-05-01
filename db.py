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
@st.cache_data(ttl=30, show_spinner=False)
def fetch_leads(
    statut: str | None = None,
    departement: str | None = None,
    ville: str | None = None,
    type_prospect: str | None = None,
    search: str | None = None,
    limit: int = 5000,
) -> pd.DataFrame:
    sb = _client()
    q = sb.table("leads").select("*")
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
    res = q.order("date_modification", desc=True).limit(limit).execute()
    return pd.DataFrame(res.data or [])


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
    q = sb.table("leads").select("ville,departement")
    if departement:
        q = q.eq("departement", departement)
    res = q.limit(50000).execute()
    villes = {r["ville"] for r in (res.data or []) if r.get("ville")}
    return sorted(villes, key=_ville_sort_key)


def fetch_lead(lead_id: int) -> dict[str, Any] | None:
    """Pas de cache : on veut toujours la version la plus fraîche pour l'édition."""
    sb = _client()
    res = sb.table("leads").select("*").eq("id", lead_id).execute()
    return res.data[0] if res.data else None


@st.cache_data(ttl=20, show_spinner=False)
def get_counts() -> dict[str, int]:
    """Compte les leads par statut. Affiché dans la sidebar."""
    sb = _client()
    res = sb.table("leads").select("statut").limit(50000).execute()
    counts = {k: 0 for k in STATUTS}
    for row in (res.data or []):
        s = row.get("statut") or "a_contacter"
        if s in counts:
            counts[s] += 1
    counts["total"] = sum(counts.values())
    return counts


@st.cache_data(ttl=60, show_spinner=False)
def get_stats() -> dict[str, Any]:
    sb = _client()
    res = sb.table("leads").select(
        "statut,type,departement,contacte_par,date_dernier_contact"
    ).limit(50000).execute()
    df = pd.DataFrame(res.data or [])
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

    # Récupère les téléphones existants en 1 requête (pour éviter N round-trips)
    res = sb.table("leads").select("id,telephone").limit(50000).execute()
    existing_tels = {r["telephone"]: r["id"] for r in (res.data or []) if r.get("telephone")}

    inserts: list[dict] = []
    updates: list[tuple[int, dict]] = []
    skip = 0

    for _, row in df.iterrows():
        nom = str(row.get("nom", "") or "").strip()
        if not nom:
            skip += 1
            continue

        tel = str(row.get("telephone", "") or "").strip()
        type_ = str(row.get("type", "Syndic") or "Syndic").strip()
        if type_ not in {"Syndic", "Agence"}:
            type_ = "Syndic"

        payload = {
            "nom": nom, "type": type_, "telephone": tel,
            "email":       str(row.get("email", "") or "").strip(),
            "adresse":     str(row.get("adresse", "") or "").strip(),
            "ville":       str(row.get("ville", "") or "").strip(),
            "departement": str(row.get("departement", "") or "").strip(),
            "source":      str(row.get("source", "") or "").strip(),
        }

        if tel and tel in existing_tels:
            updates.append((existing_tels[tel], payload))
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
