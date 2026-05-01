"""
Belmonts CRM — App Streamlit de prospection.
Pipeline : À contacter → Contacté → À recontacter → Client / Refus.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import date, datetime

import pandas as pd
import streamlit as st

from db import (
    STATUTS, STATUTS_COLOR, fetch_lead, fetch_leads, fetch_villes,
    get_counts, get_stats, import_from_excel, update_lead,
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Belmonts — CRM",
    page_icon="🏗️",
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
        if st.button("Actualiser", key=f"refresh_{statut}", use_container_width=True):
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

    # Affichage compact en lignes cliquables
    for _, row in page_df.iterrows():
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 1.5, 1])
            with c1:
                st.markdown(f"**{row['nom']}**")
                st.caption(f"{row['type']} — {row.get('ville') or '?'} ({row.get('departement') or '?'})")
            with c2:
                tel = row.get("telephone") or ""
                tel_alt = row.get("telephone_alt") or ""
                st.markdown(f"📞 {tel or '—'}")
                if tel_alt:
                    st.caption(f"📞 alt : {tel_alt}")
            with c3:
                email = row.get("email") or ""
                if email:
                    st.markdown(f"✉️ {email}")
                else:
                    st.caption("Pas d'email")
            with c4:
                statut_label = STATUTS.get(row.get("statut") or "a_contacter", "")
                st.markdown(f"<span class='stat-pill' style='background:#f5f5f3; color:#0d1f38;'>{statut_label}</span>",
                            unsafe_allow_html=True)
            with c5:
                if st.button("Ouvrir →", key=f"open_{row['id']}", use_container_width=True):
                    st.session_state["selected_lead"] = int(row["id"])
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
            if st.button("✕ Fermer", key="close_detail"):
                st.session_state.pop("selected_lead", None)
                st.rerun()

        # Coordonnées
        st.markdown("**📞 Coordonnées**")
        cc1, cc2 = st.columns(2)
        with cc1:
            st.markdown(f"**Téléphone principal** : `{lead.get('telephone') or '—'}`")
            st.markdown(f"**Adresse** : {lead.get('adresse') or '—'}")
        with cc2:
            tel_alt = st.text_input("Téléphone alternatif",
                                    value=lead.get("telephone_alt") or "",
                                    placeholder="06 12 34 56 78",
                                    key=f"telalt_{lead_id}")
            email = st.text_input("Email",
                                  value=lead.get("email") or "",
                                  placeholder="contact@entreprise.fr",
                                  key=f"email_{lead_id}")

        # Suivi commercial
        st.markdown("**🎯 Suivi commercial**")
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

        notes = st.text_area("📝 Notes",
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
                st.caption(f"📅 Dernier contact : **{ts:%d/%m/%Y %H:%M}** par **{last_user or '—'}**")
            except Exception:
                st.caption(f"📅 Dernier contact : {last_contact} par {last_user or '—'}")

        # Actions
        ac1, ac2, ac3, ac4 = st.columns(4)
        with ac1:
            if st.button("💾 Enregistrer", key=f"save_{lead_id}", use_container_width=True):
                update_lead(lead_id, {
                    "telephone_alt": tel_alt,
                    "email": email,
                    "statut": new_statut,
                    "notes": notes,
                    "date_recontact": date_recontact.isoformat() if date_recontact else None,
                }, user)
                st.success("✅ Enregistré")
                st.rerun()
        with ac2:
            if st.button("📞 Marquer contacté", key=f"contact_{lead_id}", use_container_width=True):
                update_lead(lead_id, {"statut": "contacte", "notes": notes,
                                      "telephone_alt": tel_alt, "email": email}, user)
                st.session_state.pop("selected_lead", None)
                st.rerun()
        with ac3:
            if st.button("✅ Client", key=f"client_{lead_id}", use_container_width=True):
                update_lead(lead_id, {"statut": "client", "notes": notes,
                                      "telephone_alt": tel_alt, "email": email}, user)
                st.session_state.pop("selected_lead", None)
                st.rerun()
        with ac4:
            if st.button("❌ Refus", key=f"refus_{lead_id}", use_container_width=True):
                update_lead(lead_id, {"statut": "refus", "notes": notes,
                                      "telephone_alt": tel_alt, "email": email}, user)
                st.session_state.pop("selected_lead", None)
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
    except Exception as e:
        st.error(f"Lecture impossible : {e}")
        return

    st.markdown(f"📊 **{len(df)} lignes** détectées dans le premier onglet.")
    with st.expander("Aperçu (10 premières lignes)"):
        st.dataframe(df.head(10), use_container_width=True, hide_index=True)

    if st.button("🚀 Lancer l'import"):
        with st.spinner("Import en cours…"):
            try:
                new, updated, skipped = import_from_excel(df)
                st.success(
                    f"✅ Import terminé — **{new}** nouveaux, "
                    f"**{updated}** mis à jour, **{skipped}** ignorés."
                )
                st.balloons()
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
    elif page == "stats":
        page_stats()
    elif page == "import":
        page_import()


main()
