"""
Belmonts CRM — App Streamlit de prospection.
Pipeline : À contacter → Contacté → À recontacter → Client / Refus.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import date, datetime, time as dtime, timedelta

import pandas as pd
import streamlit as st

from db import (
    STATUTS, STATUTS_COLOR, STATUTS_RDV, TYPES_RDV,
    add_rdv_contact, create_rdv, delete_lead, delete_rdv, delete_rdv_contact,
    fetch_contacts_for_rdv, fetch_lead, fetch_leads, fetch_rdvs,
    fetch_rdvs_for_lead, fetch_villes, get_counts, get_stats,
    import_from_excel, update_lead, update_rdv, update_rdv_contact,
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Belmonts — CRM",
    page_icon="⬢",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─── PERSISTANCE DE SESSION (token signé dans l'URL) ──────────────────────────
# Approche simple sans dépendance : on met un token HMAC-signé dans `?t=…` de
# l'URL après login. Au refresh, l'URL est conservée par le navigateur, on lit
# le token, on vérifie la signature, et on restaure la session.
URL_TOKEN_PARAM = "t"


def _auth_secret() -> str:
    """Clé secrète pour signer les tokens. À surcharger via env var AUTH_SECRET."""
    return os.environ.get("AUTH_SECRET", "belmonts-default-secret-please-change-me")


def _make_session_token(user: str) -> str:
    """Génère un token URL-safe : `user.signature_hmac`."""
    sig = hmac.new(_auth_secret().encode(), user.encode(), hashlib.sha256).hexdigest()
    return f"{user}.{sig}"


def _verify_session_token(token: str) -> str | None:
    """Vérifie le token, retourne le user si valide, None sinon."""
    if not token or "." not in token:
        return None
    user, sig = token.rsplit(".", 1)
    expected = hmac.new(_auth_secret().encode(), user.encode(), hashlib.sha256).hexdigest()
    if hmac.compare_digest(expected, sig):
        return user
    return None


def _restore_session_from_url() -> None:
    """Restaure st.session_state['user'] depuis le token URL si valide."""
    if "user" in st.session_state:
        return
    try:
        token = st.query_params.get(URL_TOKEN_PARAM)
    except Exception:
        return
    if not token:
        return
    user = _verify_session_token(token)
    if user and user in get_users():
        st.session_state["user"] = user
        st.session_state.setdefault("page", "a_contacter")


def _persist_login(user: str) -> None:
    """Pose le token signé dans l'URL après connexion."""
    try:
        st.query_params[URL_TOKEN_PARAM] = _make_session_token(user)
    except Exception:
        pass


def _clear_login_token() -> None:
    """Retire le token de l'URL au logout."""
    try:
        if URL_TOKEN_PARAM in st.query_params:
            del st.query_params[URL_TOKEN_PARAM]
    except Exception:
        pass


def get_users() -> dict[str, str]:
    """
    Lit les credentials :
    1. Render / autres → variables d'env AUTH_ADMIN, AUTH_COMMERCIAL1, AUTH_COMMERCIAL2
    2. Streamlit Cloud → section [auth] de secrets.toml
    3. Fallback → valeurs par défaut Belmonts (à changer en prod)
    """
    env_users = {
        k[len("AUTH_"):].lower(): v
        for k, v in os.environ.items()
        if k.startswith("AUTH_") and v
    }
    if env_users:
        return env_users

    try:
        auth = st.secrets.get("auth")
        if auth:
            return dict(auth)
    except Exception:
        pass

    return {
        "admin":       "belmonts1978",
        "commercial1": "belmonts2024",
        "commercial2": "belmonts2024",
    }


# ─── STYLE ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* Masque les éléments Streamlit en anglais (menu, footer, statut, etc.) */
#MainMenu, footer, header { visibility: hidden !important; height: 0 !important; }
[data-testid="stToolbar"], [data-testid="stStatusWidget"], [data-testid="stDecoration"],
[data-testid="stHeader"], [data-testid="stMainMenu"], [data-testid="stDeployButton"]
{ display: none !important; }

[data-testid="stSidebar"] {
    background: #0d1f38 !important;
    border-right: none !important;
    padding-top: 1.5rem !important;
}
[data-testid="stSidebar"] * { color: rgba(255,255,255,0.75); }

/* Section labels (LEADS, OUTILS) */
[data-testid="stSidebar"] .sb-section {
    font-size: 10px !important;
    font-weight: 600 !important;
    letter-spacing: 2px !important;
    color: rgba(255,255,255,0.35) !important;
    margin: 1.5rem 0 0.75rem 0.5rem !important;
    text-transform: uppercase;
}

/* Boutons de navigation — design pro */
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    color: rgba(255,255,255,0.78) !important;
    border: none !important;
    border-left: 2px solid transparent !important;
    border-radius: 0 6px 6px 0 !important;
    text-align: left !important;
    font-weight: 400 !important;
    font-size: 13px !important;
    padding: 0.55rem 0.9rem !important;
    margin: 0 0 2px 0 !important;
    transition: all 0.15s ease !important;
    width: 100% !important;
    justify-content: flex-start !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.05) !important;
    color: #fff !important;
    border-left-color: rgba(255,255,255,0.3) !important;
}
[data-testid="stSidebar"] .stButton > button:focus {
    box-shadow: none !important;
    outline: none !important;
}

/* Bouton déconnexion en bas — discret */
[data-testid="stSidebar"] .sb-logout .stButton > button {
    background: transparent !important;
    color: rgba(255,255,255,0.4) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 6px !important;
    text-align: center !important;
    justify-content: center !important;
    font-size: 12px !important;
}
[data-testid="stSidebar"] .sb-logout .stButton > button:hover {
    background: rgba(204,32,32,0.12) !important;
    border-color: rgba(204,32,32,0.5) !important;
    color: #fff !important;
}

.main .block-container { padding: 1.5rem 2.5rem; max-width: 100%; }

[data-testid="metric-container"] {
    background: #fff; border: 1px solid #e8e8e4; border-radius: 8px;
    padding: 1rem 1.25rem; border-left: 3px solid #cc2020;
}
[data-testid="metric-container"] label { font-size: 11px !important; color: #999 !important; }
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-size: 26px !important; font-weight: 500 !important; color: #0d1f38 !important;
}

.main .stButton > button {
    background: #cc2020 !important; color: #fff !important; border: none !important;
    border-radius: 6px !important; font-weight: 500 !important;
    padding: 0.5rem 1.25rem !important;
}
.main .stButton > button:hover { background: #aa1818 !important; }

/* Bouton icône (↻) — taille compacte, symbole bien centré */
.main .stButton > button[kind="secondary"]:has(p:only-child),
.main .stButton > button:has(div:only-child p:contains("↻")) {
    font-size: 18px !important;
    line-height: 1 !important;
    padding: 0.45rem 0 !important;
}

.belmonts-header {
    display: flex; align-items: baseline; gap: 12px;
    margin-bottom: 1.25rem; border-bottom: 1px solid #e8e8e4;
    padding-bottom: 0.75rem;
}
.belmonts-title { font-size: 22px; font-weight: 500; color: #0d1f38; }
.belmonts-sub   { font-size: 13px; color: #999; }

div[data-testid="stExpander"] {
    border: 1px solid #e8e8e4 !important;
    border-radius: 8px !important;
    background: #fff !important;
}

.stat-pill {
    display: inline-block; padding: 2px 10px; font-size: 11px;
    border-radius: 12px; font-weight: 500;
}
</style>
""", unsafe_allow_html=True)


# ─── COMPOSANTS ───────────────────────────────────────────────────────────────
def header(title: str, subtitle: str = "") -> None:
    st.markdown(f"""
    <div class="belmonts-header">
        <div class="belmonts-title">{title}</div>
        <div class="belmonts-sub">{subtitle}</div>
    </div>
    """, unsafe_allow_html=True)


def login() -> None:
    st.markdown("""
    <div style="text-align:center; margin-top: 60px; margin-bottom: 2rem;">
        <div style="font-size:26px; font-weight:500; color:#0d1f38; letter-spacing:5px;">
            BELMON<span style="color:#cc2020;">T</span>S
        </div>
        <div style="height:1px; background:linear-gradient(90deg,transparent,#cc2020,transparent);
                    width:140px; margin:8px auto;"></div>
        <div style="font-size:9px; color:#aaa; letter-spacing:3px;">DEPUIS 1978</div>
        <div style="font-size:14px; color:#999; margin-top:1.5rem;">CRM Prospection — Île-de-France</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.form("login_form"):
            u = st.text_input("Identifiant")
            p = st.text_input("Mot de passe", type="password")
            if st.form_submit_button("Se connecter", use_container_width=True):
                users = get_users()
                if u in users and users[u] == p:
                    st.session_state["user"] = u
                    st.session_state["page"] = "a_contacter"
                    _persist_login(u)
                    st.rerun()
                else:
                    st.error("Identifiants invalides.")


def sidebar() -> str:
    with st.sidebar:
        # Logo
        st.markdown("""
        <div style="margin: 0 0 2rem 0;">
            <div style="font-size:17px; font-weight:500; color:#fff; letter-spacing:5px;">
                BELMON<span style="color:#cc2020;">T</span>S
            </div>
            <div style="height:1px; background:linear-gradient(90deg,#cc2020,transparent); margin:6px 0 4px; width:80%;"></div>
            <div style="font-size:8px; color:rgba(255,255,255,0.35); letter-spacing:3px;">DEPUIS 1978</div>
        </div>
        """, unsafe_allow_html=True)

        # Connexion BD
        try:
            counts = get_counts()
            db_ok = True
        except Exception:
            counts = {k: 0 for k in STATUTS}
            db_ok = False

        if not db_ok:
            st.markdown("""
            <div style="background:rgba(204,32,32,0.12); border-left:2px solid #cc2020;
                        padding:0.6rem 0.8rem; margin-bottom:1rem; border-radius:0 4px 4px 0;
                        font-size:11px; color:rgba(255,255,255,0.85);">
                Base de données indisponible.
            </div>
            """, unsafe_allow_html=True)

        # Section LEADS
        st.markdown('<div class="sb-section">Leads</div>', unsafe_allow_html=True)

        for key, label in STATUTS.items():
            count = counts.get(key, 0)
            color = STATUTS_COLOR.get(key, "#6b7280")
            # Bouton invisible Streamlit (pour le clic) + label HTML stylé au-dessus
            cols = st.columns([1])
            with cols[0]:
                btn_label = f"{label}  ·  {count}"
                if st.button(btn_label, key=f"nav_{key}", use_container_width=True):
                    st.session_state["page"] = key
                    st.session_state.pop("selected_lead", None)
                    st.session_state.pop(f"page_num_{key}", None)
                    st.rerun()

        # Section OUTILS
        st.markdown('<div class="sb-section">Outils</div>', unsafe_allow_html=True)

        if st.button("Rendez-vous", key="nav_rdv", use_container_width=True):
            st.session_state["page"] = "rdv"
            st.session_state.pop("selected_lead", None)
            st.rerun()
        if st.button("Statistiques", key="nav_stats", use_container_width=True):
            st.session_state["page"] = "stats"
            st.rerun()
        if st.session_state.get("user") == "admin":
            if st.button("Importer des leads", key="nav_import", use_container_width=True):
                st.session_state["page"] = "import"
                st.rerun()

        # Pied de sidebar — utilisateur + déconnexion
        st.markdown(f"""
        <div style="margin-top:2.5rem; padding-top:1rem; border-top:1px solid rgba(255,255,255,0.08);
                    font-size:11px; color:rgba(255,255,255,0.4);">
            Connecté en tant que<br/>
            <span style="color:rgba(255,255,255,0.85); font-weight:500; font-size:13px;">
                {st.session_state.get('user', '')}
            </span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="sb-logout">', unsafe_allow_html=True)
        if st.button("Se déconnecter", key="logout", use_container_width=True):
            _clear_login_token()
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    return st.session_state.get("page", "a_contacter")


# ─── PAGE: LISTE DE LEADS ─────────────────────────────────────────────────────
PAGE_TITLES = {
    "a_contacter":   ("Leads à contacter", "Prospects pas encore appelés"),
    "contacte":      ("Contactés en cours", "Discussion engagée"),
    "a_recontacter": ("À recontacter",       "Rappel programmé"),
    "client":        ("Clients",             "Ils ont signé 🎉"),
    "refus":         ("Refus",               "Pas intéressés"),
}


def page_leads(statut: str) -> None:
    title, sub = PAGE_TITLES.get(statut, ("Leads", ""))
    header(title, sub)

    # Filtres
    c1, c2, c3, c4, c5 = st.columns([1.4, 1.8, 1.2, 2.4, 0.9])
    with c1:
        depts = ["Tous", "75", "92", "93", "94", "78", "77", "91", "95"]
        dept = st.selectbox("Département", depts, key=f"dept_{statut}")
    with c2:
        ville_options = ["Toutes"] + fetch_villes(
            departement=dept if dept != "Tous" else None
        )
        ville = st.selectbox(
            "Ville / arrondissement",
            ville_options,
            key=f"ville_{statut}_{dept}",  # reset auto si dept change
        )
    with c3:
        type_p = st.selectbox("Type", ["Tous", "Syndic", "Agence"], key=f"type_{statut}")
    with c4:
        search = st.text_input("Recherche par nom",
                               placeholder="ex: Foncia",
                               key=f"search_{statut}")
    with c5:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("↻", key=f"refresh_{statut}",
                     help="Actualiser la liste",
                     use_container_width=True):
            st.rerun()

    df = fetch_leads(
        statut=statut,
        departement=dept if dept != "Tous" else None,
        ville=ville if ville != "Toutes" else None,
        type_prospect=type_p if type_p != "Tous" else None,
        search=search if search else None,
    )

    st.markdown(
        f"<div style='font-size:13px; color:#666; margin: 0.75rem 0 1rem;'>"
        f"<strong>{len(df)}</strong> lead(s) trouvé(s)</div>",
        unsafe_allow_html=True,
    )

    if df.empty:
        st.info("Aucun lead avec ces filtres.")
        return

    # Panneau de détail au-dessus si un lead est sélectionné
    if st.session_state.get("selected_lead"):
        render_lead_detail(st.session_state["selected_lead"])
        st.markdown("---")

    # Pagination simple (25 par page)
    PAGE_SIZE = 25
    page_key = f"page_num_{statut}"
    if page_key not in st.session_state:
        st.session_state[page_key] = 0
    total_pages = max(1, (len(df) - 1) // PAGE_SIZE + 1)
    st.session_state[page_key] = min(st.session_state[page_key], total_pages - 1)

    pc1, pc2, pc3 = st.columns([1, 2, 1])
    with pc1:
        if st.button("← Précédent", key=f"prev_{statut}",
                     disabled=st.session_state[page_key] == 0,
                     use_container_width=True):
            st.session_state[page_key] -= 1
            st.rerun()
    with pc2:
        st.markdown(
            f"<div style='text-align:center; padding-top:8px; color:#666; font-size:13px;'>"
            f"Page <strong>{st.session_state[page_key] + 1}</strong> / {total_pages}</div>",
            unsafe_allow_html=True,
        )
    with pc3:
        if st.button("Suivant →", key=f"next_{statut}",
                     disabled=st.session_state[page_key] >= total_pages - 1,
                     use_container_width=True):
            st.session_state[page_key] += 1
            st.rerun()

    start = st.session_state[page_key] * PAGE_SIZE
    end = start + PAGE_SIZE
    page_df = df.iloc[start:end]

    # Affichage compact avec changement de statut inline (auto-save)
    user = st.session_state.get("user", "")
    statut_keys = list(STATUTS.keys())

    for _, row in page_df.iterrows():
        lead_id = int(row["id"])
        current_statut = row.get("statut") or "a_contacter"
        if current_statut not in statut_keys:
            current_statut = "a_contacter"

        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3.2, 2.2, 2.4, 1])

            with c1:
                st.markdown(f"**{row['nom']}**")
                st.caption(
                    f"{row['type']} — {row.get('ville') or '?'} "
                    f"({row.get('departement') or '?'})"
                )

            with c2:
                tel = row.get("telephone") or ""
                tel_alt = row.get("telephone_alt") or ""
                st.markdown(f"{tel or '—'}")
                if tel_alt:
                    st.caption(f"alt : {tel_alt}")

            with c3:
                # Selectbox inline → changement de statut auto-save
                new_statut = st.selectbox(
                    "Statut",
                    statut_keys,
                    index=statut_keys.index(current_statut),
                    format_func=lambda k: STATUTS[k],
                    key=f"row_statut_{lead_id}",
                    label_visibility="collapsed",
                )
                if new_statut != current_statut:
                    payload: dict = {"statut": new_statut}
                    # Pour "À recontacter", on pré-remplit la date à +14 jours
                    # (modifiable ensuite dans la fiche détaillée).
                    if new_statut == "a_recontacter":
                        payload["date_recontact"] = (
                            date.today() + timedelta(days=14)
                        ).isoformat()
                    update_lead(lead_id, payload, user)
                    st.toast(
                        f"« {row['nom']} » → {STATUTS[new_statut]}",
                        icon="✅",
                    )
                    st.rerun()

            with c4:
                if st.button("Ouvrir →", key=f"open_{lead_id}", use_container_width=True):
                    st.session_state["selected_lead"] = lead_id
                    st.rerun()

    # Pagination en BAS de la liste (utile quand on a scrollé jusqu'en bas)
    if total_pages > 1:
        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        bp1, bp2, bp3 = st.columns([1, 2, 1])
        with bp1:
            if st.button("← Précédent", key=f"prev_bottom_{statut}",
                         disabled=st.session_state[page_key] == 0,
                         use_container_width=True):
                st.session_state[page_key] -= 1
                st.rerun()
        with bp2:
            st.markdown(
                f"<div style='text-align:center; padding-top:8px; color:#666; font-size:13px;'>"
                f"Page <strong>{st.session_state[page_key] + 1}</strong> / {total_pages}</div>",
                unsafe_allow_html=True,
            )
        with bp3:
            if st.button("Suivant →", key=f"next_bottom_{statut}",
                         disabled=st.session_state[page_key] >= total_pages - 1,
                         use_container_width=True):
                st.session_state[page_key] += 1
                st.rerun()


# ─── DÉTAIL D'UN LEAD ─────────────────────────────────────────────────────────
def render_lead_detail(lead_id: int) -> None:
    lead = fetch_lead(lead_id)
    if not lead:
        st.error("Lead introuvable.")
        st.session_state.pop("selected_lead", None)
        return

    user = st.session_state.get("user", "")

    with st.container(border=True):
        # En-tête
        c_h1, c_h2 = st.columns([5, 1])
        with c_h1:
            st.markdown(f"### {lead['nom']}")
            st.caption(f"{lead['type']} — {lead.get('ville') or '?'} "
                       f"({lead.get('departement') or '?'})")
        with c_h2:
            if st.button("Fermer", key="close_detail"):
                st.session_state.pop("selected_lead", None)
                st.rerun()

        # Coordonnées (toutes éditables — info client ou changement organisationnel)
        st.markdown("**Coordonnées**")
        cc1, cc2 = st.columns(2)
        with cc1:
            nom_edit = st.text_input("Nom de l'entreprise",
                                     value=lead.get("nom") or "",
                                     key=f"nom_{lead_id}")
            tel_edit = st.text_input("Téléphone principal",
                                     value=lead.get("telephone") or "",
                                     placeholder="01 23 45 67 89",
                                     key=f"tel_{lead_id}")
            tel_alt = st.text_input("Téléphone alternatif",
                                    value=lead.get("telephone_alt") or "",
                                    placeholder="06 12 34 56 78",
                                    key=f"telalt_{lead_id}")
            email = st.text_input("Email",
                                  value=lead.get("email") or "",
                                  placeholder="contact@entreprise.fr",
                                  key=f"email_{lead_id}")
        with cc2:
            adresse_edit = st.text_input("Adresse",
                                         value=lead.get("adresse") or "",
                                         key=f"adr_{lead_id}")
            tcc1, tcc2 = st.columns(2)
            with tcc1:
                ville_edit = st.text_input("Ville",
                                           value=lead.get("ville") or "",
                                           key=f"ville_{lead_id}")
            with tcc2:
                dept_edit = st.text_input("Département",
                                          value=lead.get("departement") or "",
                                          placeholder="ex: 75",
                                          key=f"dept_{lead_id}")
            type_keys = ["Syndic", "Agence"]
            cur_type = lead.get("type") or "Syndic"
            type_edit = st.selectbox("Type de prospect",
                                     type_keys,
                                     index=type_keys.index(cur_type) if cur_type in type_keys else 0,
                                     key=f"type_edit_{lead_id}")

        # Suivi commercial
        st.markdown("**Suivi commercial**")
        sc1, sc2 = st.columns(2)
        with sc1:
            statut_keys = list(STATUTS.keys())
            current = lead.get("statut") or "a_contacter"
            idx = statut_keys.index(current) if current in statut_keys else 0
            new_statut = st.selectbox("Statut",
                                      statut_keys,
                                      index=idx,
                                      format_func=lambda k: STATUTS[k],
                                      key=f"statut_{lead_id}")
        with sc2:
            current_recontact = lead.get("date_recontact")
            recontact_value: date | None = None
            if current_recontact:
                try:
                    recontact_value = (date.fromisoformat(current_recontact[:10])
                                       if isinstance(current_recontact, str)
                                       else current_recontact)
                except Exception:
                    recontact_value = None
            date_recontact = st.date_input("Date à recontacter",
                                           value=recontact_value,
                                           key=f"recontact_{lead_id}")

        notes = st.text_area("Notes",
                             value=lead.get("notes") or "",
                             height=120,
                             placeholder="ex: RDV jeudi 14h avec M. Durand. Demande devis ravalement.",
                             key=f"notes_{lead_id}")

        # Historique
        last_contact = lead.get("date_dernier_contact")
        last_user = lead.get("contacte_par")
        if last_contact:
            try:
                ts = datetime.fromisoformat(str(last_contact).replace("Z", "+00:00"))
                st.caption(f"Dernier contact : **{ts:%d/%m/%Y %H:%M}** par **{last_user or '—'}**")
            except Exception:
                st.caption(f"Dernier contact : {last_contact} par {last_user or '—'}")

        # Section Rendez-vous (briefing bureau ↔ compte-rendu terrain)
        st.markdown("---")
        _render_rdv_section(lead_id, lead, user)
        st.markdown("---")

        # Payload commun (tous les champs éditables sont sauvegardés à chaque action)
        full_payload: dict = {
            "nom": (nom_edit or "").strip() or lead.get("nom"),
            "type": type_edit,
            "telephone": (tel_edit or "").strip(),
            "telephone_alt": tel_alt,
            "email": email,
            "adresse": adresse_edit,
            "ville": ville_edit,
            "departement": dept_edit,
            "notes": notes,
            "date_recontact": date_recontact.isoformat() if date_recontact else None,
        }

        # Actions
        ac1, ac2, ac3, ac4 = st.columns(4)
        with ac1:
            if st.button("Enregistrer", key=f"save_{lead_id}", use_container_width=True):
                update_lead(lead_id, {**full_payload, "statut": new_statut}, user)
                st.success("Enregistré")
                st.rerun()
        with ac2:
            if st.button("Marquer contacté", key=f"contact_{lead_id}", use_container_width=True):
                update_lead(lead_id, {**full_payload, "statut": "contacte"}, user)
                st.session_state.pop("selected_lead", None)
                st.rerun()
        with ac3:
            if st.button("Client", key=f"client_{lead_id}", use_container_width=True):
                update_lead(lead_id, {**full_payload, "statut": "client"}, user)
                st.session_state.pop("selected_lead", None)
                st.rerun()
        with ac4:
            if st.button("Refus", key=f"refus_{lead_id}", use_container_width=True):
                update_lead(lead_id, {**full_payload, "statut": "refus"}, user)
                st.session_state.pop("selected_lead", None)
                st.rerun()

        # Suppression (zone "danger" en bas, avec confirmation à 2 clics)
        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        confirm_key = f"confirm_del_{lead_id}"
        if not st.session_state.get(confirm_key):
            if st.button("Supprimer ce lead", key=f"del_lead_{lead_id}",
                         help="Supprime définitivement ce lead et tous ses RDV"):
                st.session_state[confirm_key] = True
                st.rerun()
        else:
            st.warning(
                f"Confirmer la suppression de **{lead.get('nom')}** ? "
                "Cette action supprimera aussi tous ses rendez-vous et est irréversible."
            )
            cc_d1, cc_d2 = st.columns(2)
            with cc_d1:
                if st.button("Confirmer la suppression",
                             key=f"confirm_del_btn_{lead_id}",
                             use_container_width=True):
                    delete_lead(lead_id)
                    st.session_state.pop(confirm_key, None)
                    st.session_state.pop("selected_lead", None)
                    st.toast(f"Lead « {lead.get('nom')} » supprimé")
                    st.rerun()
            with cc_d2:
                if st.button("Annuler",
                             key=f"cancel_del_btn_{lead_id}",
                             use_container_width=True):
                    st.session_state.pop(confirm_key, None)
                    st.rerun()


# ─── SECTION RDV (dans la fiche d'un lead) ───────────────────────────────────
def _parse_rdv_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _render_rdv_section(lead_id: int, lead: dict, user: str) -> None:
    rdvs = fetch_rdvs_for_lead(lead_id)
    upcoming = [r for r in rdvs if r.get("statut") == "a_venir"]
    history = [r for r in rdvs if r.get("statut") != "a_venir"]
    n_upcoming = len(upcoming)

    label = f"**Rendez-vous** ({len(rdvs)})"
    if n_upcoming:
        label += f"   ·  {n_upcoming} à venir"
    st.markdown(label)

    # Form de création
    with st.expander("Planifier un nouveau rendez-vous", expanded=(len(rdvs) == 0)):
        with st.form(f"create_rdv_{lead_id}", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                d = st.date_input("Date du RDV",
                                  value=date.today() + timedelta(days=7),
                                  key=f"new_rdv_d_{lead_id}")
                h = st.time_input("Heure",
                                  value=dtime(14, 0),
                                  key=f"new_rdv_h_{lead_id}",
                                  step=timedelta(minutes=15))
                duree = st.selectbox("Durée prévue",
                                     [30, 45, 60, 90, 120],
                                     index=2,
                                     format_func=lambda m: f"{m} min",
                                     key=f"new_rdv_duree_{lead_id}")
            with c2:
                type_keys = list(TYPES_RDV.keys())
                type_rdv = st.selectbox("Type",
                                        type_keys,
                                        format_func=lambda k: TYPES_RDV[k],
                                        key=f"new_rdv_type_{lead_id}")
                users_list = list(get_users().keys())
                default_idx = users_list.index(user) if user in users_list else 0
                assigne = st.selectbox("Assigné à (commercial terrain)",
                                       users_list,
                                       index=default_idx,
                                       key=f"new_rdv_assigne_{lead_id}")
            lieu = st.text_input("Lieu",
                                 value=lead.get("adresse") or "",
                                 placeholder="Adresse du RDV",
                                 key=f"new_rdv_lieu_{lead_id}")
            briefing = st.text_area(
                "Briefing pour le commercial terrain",
                placeholder="Contexte du syndic, contact à demander, "
                            "points clés à aborder, attentes du client...",
                height=120,
                key=f"new_rdv_brief_{lead_id}",
            )
            submitted = st.form_submit_button("Créer le rendez-vous",
                                              use_container_width=False)
            if submitted:
                dt = datetime.combine(d, h)
                created = create_rdv(lead_id, {
                    "date_rdv":  dt.isoformat(),
                    "duree_min": int(duree),
                    "type":      type_rdv,
                    "lieu":      lieu,
                    "assigne_a": assigne,
                    "briefing":  briefing,
                }, user)
                if created:
                    st.success(f"RDV créé pour le {dt:%d/%m/%Y à %H:%M}")
                    st.rerun()
                else:
                    st.error("Erreur à la création du RDV.")

    if not rdvs:
        return

    # RDVs à venir
    if upcoming:
        st.markdown("##### À venir")
        for rdv in upcoming:
            _render_rdv_card(rdv, user, expanded=True)

    # Historique (terminé / annulé / reporté)
    if history:
        st.markdown("##### Historique")
        for rdv in history:
            _render_rdv_card(rdv, user, expanded=False)


def _render_rdv_card(rdv: dict, user: str, expanded: bool = False) -> None:
    rdv_id = int(rdv["id"])
    dt = _parse_rdv_dt(rdv.get("date_rdv"))
    statut_key = rdv.get("statut") or "a_venir"
    type_label = TYPES_RDV.get(rdv.get("type") or "physique", rdv.get("type", ""))

    # Indicateur de statut sobre (Unicode minimal, pas d'emoji)
    statut_marker = {
        "a_venir":  "•",
        "termine":  "✓",
        "annule":   "×",
        "reporte":  "○",
    }.get(statut_key, "·")

    when = f"{dt:%a %d/%m %H:%M}" if dt else "?"
    title = (
        f"{statut_marker}  **{when}**  ·  {type_label}  ·  "
        f"Assigné à **{rdv.get('assigne_a') or '—'}**  "
        f"·  *{STATUTS_RDV.get(statut_key, statut_key)}*"
    )

    with st.expander(title, expanded=expanded):
        # Briefing (préparation par le bureau)
        briefing = st.text_area(
            "Briefing (rédigé par le bureau)",
            value=rdv.get("briefing") or "",
            key=f"brief_{rdv_id}",
            height=100,
        )

        # Compte-rendu (rempli par le terrain après le RDV)
        compte_rendu = st.text_area(
            "Compte-rendu (à remplir après le RDV)",
            value=rdv.get("compte_rendu") or "",
            placeholder="Notes, contacts rencontrés, accord obtenu, "
                        "points en suspens, prochaine étape...",
            key=f"cr_{rdv_id}",
            height=140,
        )

        resultat = st.text_input(
            "Résultat / suite à donner",
            value=rdv.get("resultat") or "",
            placeholder="ex : devis demandé, refus, à rappeler dans 1 mois",
            key=f"res_{rdv_id}",
        )

        # Lieu (modifiable)
        lieu = st.text_input("Lieu",
                             value=rdv.get("lieu") or "",
                             key=f"lieu_{rdv_id}")

        # Contacts rencontrés sur place (sous-CRM mini)
        _render_contacts_section(rdv_id, statut_key)

        # Métadonnées
        cree_par = rdv.get("cree_par", "")
        cree_le = _parse_rdv_dt(rdv.get("cree_le"))
        if cree_par or cree_le:
            cap = "Créé"
            if cree_par:
                cap += f" par **{cree_par}**"
            if cree_le:
                cap += f" le {cree_le:%d/%m/%Y à %H:%M}"
            st.caption(cap)

        # Actions selon le statut
        if statut_key == "a_venir":
            b1, b2, b3, b4, b5 = st.columns(5)
            with b1:
                if st.button("Enregistrer", key=f"save_rdv_{rdv_id}",
                             use_container_width=True):
                    update_rdv(rdv_id, {
                        "briefing": briefing,
                        "compte_rendu": compte_rendu,
                        "resultat": resultat,
                        "lieu": lieu,
                    })
                    st.success("Sauvegardé")
                    st.rerun()
            with b2:
                if st.button("Marquer terminé", key=f"done_rdv_{rdv_id}",
                             use_container_width=True):
                    update_rdv(rdv_id, {
                        "statut": "termine",
                        "briefing": briefing,
                        "compte_rendu": compte_rendu,
                        "resultat": resultat,
                        "lieu": lieu,
                    })
                    st.toast("RDV marqué terminé")
                    st.rerun()
            with b3:
                if st.button("Reporter", key=f"postpone_rdv_{rdv_id}",
                             use_container_width=True):
                    update_rdv(rdv_id, {"statut": "reporte"})
                    st.rerun()
            with b4:
                if st.button("Annuler", key=f"cancel_rdv_{rdv_id}",
                             use_container_width=True):
                    update_rdv(rdv_id, {"statut": "annule"})
                    st.rerun()
            with b5:
                if st.button("Supprimer", key=f"del_rdv_{rdv_id}",
                             use_container_width=True):
                    delete_rdv(rdv_id)
                    st.rerun()
        else:
            b1, b2 = st.columns([1, 1])
            with b1:
                if st.button("Sauvegarder le compte-rendu",
                             key=f"save_rdv_{rdv_id}",
                             use_container_width=True):
                    update_rdv(rdv_id, {
                        "compte_rendu": compte_rendu,
                        "resultat": resultat,
                    })
                    st.success("Compte-rendu sauvegardé")
                    st.rerun()
            with b2:
                if st.button("Réactiver",
                             key=f"reopen_rdv_{rdv_id}",
                             use_container_width=True):
                    update_rdv(rdv_id, {"statut": "a_venir"})
                    st.rerun()


# ─── CONTACTS RENCONTRÉS (sous-section d'un RDV) ─────────────────────────────
def _render_contacts_section(rdv_id: int, statut_key: str) -> None:
    contacts = fetch_contacts_for_rdv(rdv_id)
    n = len(contacts)

    st.markdown(f"##### Contacts rencontrés ({n})")

    # Liste des contacts existants (chaque contact = container éditable)
    for ct in contacts:
        ct_id = int(ct["id"])
        with st.container(border=True):
            cc1, cc2 = st.columns([6, 1])
            with cc1:
                cn1, cn2 = st.columns(2)
                with cn1:
                    nom = st.text_input(
                        "Nom",
                        value=ct.get("nom", ""),
                        key=f"ct_nom_{ct_id}",
                        placeholder="ex : M. Dupont",
                    )
                    poste = st.text_input(
                        "Poste / fonction",
                        value=ct.get("poste", ""),
                        key=f"ct_poste_{ct_id}",
                        placeholder="ex : Directeur, Comptable, Gardien",
                    )
                with cn2:
                    tel = st.text_input(
                        "Téléphone",
                        value=ct.get("telephone", ""),
                        key=f"ct_tel_{ct_id}",
                        placeholder="06 12 34 56 78",
                    )
                    email = st.text_input(
                        "Email",
                        value=ct.get("email", ""),
                        key=f"ct_email_{ct_id}",
                        placeholder="contact@entreprise.fr",
                    )
                notes = st.text_input(
                    "Notes",
                    value=ct.get("notes", ""),
                    key=f"ct_notes_{ct_id}",
                    placeholder="ex : Décisionnaire, à recontacter pour devis",
                )
            with cc2:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("✓", key=f"save_ct_{ct_id}",
                             help="Enregistrer ce contact",
                             use_container_width=True):
                    update_rdv_contact(ct_id, {
                        "nom": nom, "poste": poste, "telephone": tel,
                        "email": email, "notes": notes,
                    })
                    st.toast("Contact mis à jour")
                    st.rerun()
                if st.button("×", key=f"del_ct_{ct_id}",
                             help="Supprimer ce contact",
                             use_container_width=True):
                    delete_rdv_contact(ct_id)
                    st.rerun()

    if not contacts:
        st.caption("Aucun contact rencontré enregistré pour ce RDV.")

    # Formulaire pour ajouter un nouveau contact
    with st.form(f"new_contact_form_{rdv_id}", clear_on_submit=True):
        st.markdown("**Ajouter un contact rencontré**")
        nc1, nc2 = st.columns(2)
        with nc1:
            new_nom = st.text_input("Nom *", key=f"new_ct_nom_{rdv_id}",
                                    placeholder="ex : Mme Martin")
            new_poste = st.text_input(
                "Poste / fonction",
                key=f"new_ct_poste_{rdv_id}",
                placeholder="ex : Directrice, Gestionnaire de patrimoine",
            )
        with nc2:
            new_tel = st.text_input("Téléphone", key=f"new_ct_tel_{rdv_id}",
                                    placeholder="06 12 34 56 78")
            new_email = st.text_input("Email", key=f"new_ct_email_{rdv_id}",
                                      placeholder="contact@entreprise.fr")
        new_notes = st.text_input(
            "Notes (optionnel)",
            key=f"new_ct_notes_{rdv_id}",
            placeholder="ex : Décisionnaire, demande devis ravalement façade",
        )
        if st.form_submit_button("Ajouter ce contact"):
            if not (new_nom or "").strip():
                st.error("Le nom du contact est requis.")
            else:
                add_rdv_contact(rdv_id, {
                    "nom": new_nom, "poste": new_poste,
                    "telephone": new_tel, "email": new_email,
                    "notes": new_notes,
                })
                st.toast("Contact ajouté")
                st.rerun()


# ─── PAGE: RENDEZ-VOUS (vue globale) ─────────────────────────────────────────
def page_rdv() -> None:
    header("Rendez-vous", "Suivi des RDV terrain")

    user = st.session_state.get("user", "")

    # Filtres
    f1, f2, f3, f4 = st.columns([1.5, 1.5, 1.5, 1])
    with f1:
        scope = st.selectbox("Visibilité", ["Mes RDV", "Tous les RDV"],
                             key="rdv_scope")
    with f2:
        statut_keys = ["Tous"] + list(STATUTS_RDV.keys())
        statut_f = st.selectbox(
            "Statut",
            statut_keys,
            format_func=lambda k: STATUTS_RDV.get(k, "Tous"),
            key="rdv_statut_filter",
        )
    with f3:
        period = st.selectbox(
            "Période",
            ["À venir (7 jours)", "Aujourd'hui", "Cette semaine",
             "Ce mois", "Tout"],
            key="rdv_period",
        )
    with f4:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("↻", key="rdv_refresh",
                     help="Actualiser la liste",
                     use_container_width=True):
            st.rerun()

    # Calcule les bornes de date selon la période
    today = date.today()
    date_min: str | None = None
    date_max: str | None = None
    if period == "Aujourd'hui":
        date_min = today.isoformat()
        date_max = (today + timedelta(days=1)).isoformat()
    elif period == "Cette semaine":
        start_w = today - timedelta(days=today.weekday())
        end_w = start_w + timedelta(days=7)
        date_min = start_w.isoformat()
        date_max = end_w.isoformat()
    elif period == "Ce mois":
        first = today.replace(day=1)
        if first.month == 12:
            next_first = first.replace(year=first.year + 1, month=1)
        else:
            next_first = first.replace(month=first.month + 1)
        date_min = first.isoformat()
        date_max = next_first.isoformat()
    elif period == "À venir (7 jours)":
        date_min = today.isoformat()
        date_max = (today + timedelta(days=7)).isoformat()

    rdvs = fetch_rdvs(
        assigne_a=user if scope == "Mes RDV" else None,
        statut=statut_f if statut_f != "Tous" else None,
        date_min=date_min,
        date_max=date_max,
    )

    st.markdown(
        f"<div style='font-size:13px; color:#666; margin: 0.75rem 0 1rem;'>"
        f"<strong>{len(rdvs)}</strong> rendez-vous</div>",
        unsafe_allow_html=True,
    )

    if not rdvs:
        st.info("Aucun rendez-vous avec ces filtres.")
        return

    for rdv in rdvs:
        lead_data = rdv.get("leads") or {}
        dt = _parse_rdv_dt(rdv.get("date_rdv"))
        statut_key = rdv.get("statut") or "a_venir"
        # Point coloré CSS selon le statut (vert / gris / rouge / orange)
        statut_color = {
            "a_venir": "#10b981", "termine": "#6b7280",
            "annule":  "#cc2020", "reporte": "#f59e0b",
        }.get(statut_key, "#6b7280")
        statut_dot_html = (
            f"<span style='color:{statut_color}; font-size:14px; "
            f"line-height:1; vertical-align:middle;'>●</span>"
        )
        type_label = TYPES_RDV.get(rdv.get("type") or "physique", "")

        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3.2, 2.8, 2, 1])

            with c1:
                st.markdown(f"**{lead_data.get('nom') or '—'}**")
                st.caption(
                    f"{lead_data.get('type') or ''} — "
                    f"{lead_data.get('ville') or '?'} "
                    f"({lead_data.get('departement') or '?'})"
                )
                if lead_data.get("adresse"):
                    st.caption(lead_data['adresse'])

            with c2:
                if dt:
                    st.markdown(
                        f"{statut_dot_html} **{dt:%a %d/%m %H:%M}**",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(f"{statut_dot_html} ?", unsafe_allow_html=True)
                st.caption(f"{type_label} · {rdv.get('duree_min', 60)} min")
                if rdv.get("lieu"):
                    st.caption(rdv['lieu'])

            with c3:
                st.markdown(
                    f"Assigné à : **{rdv.get('assigne_a') or '—'}**"
                )
                if lead_data.get("telephone"):
                    st.caption(lead_data['telephone'])

            with c4:
                if st.button("Ouvrir →", key=f"go_lead_{rdv['id']}",
                             use_container_width=True):
                    st.session_state["page"] = "a_contacter"
                    st.session_state["selected_lead"] = int(rdv["lead_id"])
                    st.rerun()


# ─── PAGE: STATISTIQUES ───────────────────────────────────────────────────────
def page_stats() -> None:
    header("Statistiques", "Vue d'ensemble du pipeline")

    stats = get_stats()
    if stats["total"] == 0:
        st.info("Pas encore de données. Importe ton fichier Excel via ⚙️ Import Excel.")
        return

    cols = st.columns(5)
    for i, (key, label) in enumerate(STATUTS.items()):
        cols[i].metric(label, stats["by_statut"].get(key, 0))

    st.markdown("---")
    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown("**Par département**")
        if stats["by_dept"]:
            df = (pd.DataFrame(list(stats["by_dept"].items()),
                               columns=["Département", "Total"])
                  .sort_values("Total", ascending=False))
            st.bar_chart(df.set_index("Département"))
        else:
            st.caption("—")
    with cc2:
        st.markdown("**Par type**")
        if stats["by_type"]:
            df = pd.DataFrame(list(stats["by_type"].items()), columns=["Type", "Total"])
            st.bar_chart(df.set_index("Type"))
        else:
            st.caption("—")

    st.markdown("---")
    st.markdown("**Activité par commercial** (leads contactés)")
    if stats["by_user"]:
        df = pd.DataFrame(list(stats["by_user"].items()),
                          columns=["Commercial", "Leads contactés"])
        st.bar_chart(df.set_index("Commercial"))
    else:
        st.caption("Pas encore d'activité enregistrée.")


# ─── PAGE: IMPORT ─────────────────────────────────────────────────────────────
def page_import() -> None:
    header("Import de leads", "Réservé à l'administrateur")

    st.markdown("""
Upload un fichier Excel de leads. Le fichier doit contenir au minimum les
colonnes **Entreprise**, **Type** (Syndic ou Agence) et **Téléphone**. Les
colonnes **Email**, **Adresse**, **Ville**, **Département** et **Source** sont
prises en compte si présentes.

**Comportement** :
- Les nouveaux leads sont ajoutés avec le statut **🆕 À contacter**.
- Les leads existants (identifiés par leur téléphone) voient leurs
  coordonnées mises à jour, mais leur **statut, notes, téléphone alternatif
  et historique sont préservés**.
""")

    uploaded = st.file_uploader("Fichier Excel (.xlsx)", type="xlsx")
    if not uploaded:
        return

    try:
        df = pd.read_excel(uploaded, sheet_name=0)
        # Détection auto : si les fichiers générés par scrape_leads.py ont un
        # bandeau "BELMONTS" en ligne 1, les vrais en-têtes sont en ligne 2.
        expected = {"Entreprise", "Nom", "nom", "Téléphone", "telephone"}
        if not (set(df.columns) & expected):
            df = pd.read_excel(uploaded, sheet_name=0, header=1)
    except Exception as e:
        st.error(f"Lecture impossible : {e}")
        return

    st.markdown(f"**{len(df)} lignes** détectées dans le premier onglet.")
    with st.expander("Aperçu (10 premières lignes)"):
        st.dataframe(df.head(10), use_container_width=True, hide_index=True)

    if st.button("Lancer l'import"):
        with st.spinner("Import en cours…"):
            try:
                new, updated, skipped = import_from_excel(df)
                st.success(
                    f"Import terminé — **{new}** nouveaux, "
                    f"**{updated}** mis à jour, **{skipped}** ignorés."
                )
            except Exception as e:
                st.error(f"Échec de l'import : {e}")


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────
def main() -> None:
    # Tente de restaurer la session depuis le token URL (survit au refresh)
    _restore_session_from_url()

    if "user" not in st.session_state:
        login()
        return

    page = sidebar()
    if page in STATUTS:
        page_leads(page)
    elif page == "rdv":
        page_rdv()
    elif page == "stats":
        page_stats()
    elif page == "import":
        page_import()


main()
