# 🏗️ Belmonts — CRM Prospection IDF

App de prospection des **syndics de copropriété** et **agences immobilières
de gestion locative** d'Île-de-France.

```
┌──────────────────────┐    ┌────────────────────┐    ┌─────────────────────┐
│  Ton Mac (Playwright)│───▶│  Supabase          │◀──▶│  App web Streamlit  │
│  scrape_leads.py     │    │  (PG cloud, free)  │    │  (commerciaux)      │
│  → leads.xlsx        │    │                    │    │  statuts + notes    │
└──────────────────────┘    └────────────────────┘    └─────────────────────┘
```

---

## 🗂️ Structure

```
belmonts-app/
├── scrape_leads.py            → Scraper Playwright local (Phase 1)
├── app.py                     → App web Streamlit (Phase 2)
├── db.py                      → Couche Supabase
├── supabase_schema.sql        → SQL à exécuter une fois
├── requirements.txt           → Cloud (sans Playwright)
├── requirements-local.txt     → Local (avec Playwright)
└── .streamlit/
    ├── config.toml            → Thème
    └── secrets.toml.example   → Template
```

---

## 🚀 Mise en route — pas à pas

### 1. Crée la base Supabase (5 min)

1. https://supabase.com → New project (région West EU / Paris).
2. Note ton mot de passe DB (juste sécurité, pas utilisé directement).
3. Onglet **SQL Editor → New query** : colle [supabase_schema.sql](supabase_schema.sql), clique **Run**.
4. **Project Settings → API** : copie ton `Project URL` + `service_role` key.

### 2. Configure tes secrets locaux

```bash
cd ~/Downloads/belmonts-app
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```
Édite `.streamlit/secrets.toml` et remplis tes 2 valeurs Supabase.

### 3. Scrape tes leads (Phase 1)

```bash
source ~/scraper-env/bin/activate
pip3 install -r requirements-local.txt
python3 scrape_leads.py            # toute IDF, ~60 min
```

Tu obtiens `leads_belmonts_YYYYMMDD.xlsx` dans le dossier du projet.

### 4. Teste l'app en local (Phase 2)

```bash
streamlit run app.py
```
Ouvre http://localhost:8501 → login `admin / belmonts1978` →
**⚙️ Import Excel** → upload ton fichier → **🚀 Lancer l'import**.

Tu peux maintenant naviguer dans tes leads, changer leur statut,
ajouter des notes, et tester le workflow.

### 5. Déploie sur Streamlit Cloud (5 min)

1. Pousse le code sur GitHub :
```bash
# Si git pas encore initialisé proprement (à vérifier que ~/.git ne traîne pas)
ls ~/.git    # vérifie ; supprime avec `rm -rf ~/.git` si rien d'important
cd ~/Downloads/belmonts-app
git init && git checkout -b main
git add .
git commit -m "Belmonts CRM v1"
git remote add origin https://github.com/beaumellc-commits/belmonts-app.git
git push -u origin main
```

2. https://share.streamlit.io → **New app** → repo, branche `main`, fichier `app.py`.

3. **Advanced settings → Secrets** : colle le contenu de ton `secrets.toml`.

4. **Deploy** → 2 min plus tard tu as une URL `belmonts-crm.streamlit.app`.

5. Sur l'app live, va dans **⚙️ Import Excel** et importe ton fichier.

6. Envoie l'URL à tes 2 commerciaux avec leurs identifiants.

---

## 🔄 Workflow hebdomadaire

```
LUNDI MATIN
└─ Sur ton Mac :
   python3 scrape_leads.py
   → leads_belmonts_YYYYMMDD.xlsx (~3500 leads)

LUNDI 9H
└─ Sur l'app web (admin) : ⚙️ Import Excel → upload du fichier
   → Nouveaux leads apparaissent avec statut 🆕 À contacter
   → Les leads existants gardent leur statut/notes (pas écrasés)

LUNDI - VENDREDI
└─ Tes commerciaux sur l'app web :
   - Filtrent par département / type
   - Ouvrent un lead → marquent "Contacté" / "À recontacter" / "Client"
   - Ajoutent notes, téléphone alt, date de rappel
```

---

## 👤 Comptes par défaut

| Identifiant   | Mot de passe   | Rôle                              |
|---------------|----------------|-----------------------------------|
| `admin`       | `belmonts1978` | Voit tout + import Excel          |
| `commercial1` | `belmonts2024` | Voit + édite tous les leads       |
| `commercial2` | `belmonts2024` | Voit + édite tous les leads       |

À modifier dans Streamlit Cloud → Secrets → `[auth]`.

---

## 🎯 Statuts d'un lead

| Statut             | Quand l'utiliser                                                  |
|--------------------|-------------------------------------------------------------------|
| 🆕 À contacter     | Statut par défaut, prospect pas encore appelé                     |
| 📞 Contacté        | Conversation engagée, en discussion                               |
| 📅 À recontacter   | Pas dispo / brochure / RDV plus tard — saisis la date de rappel    |
| ✅ Client          | A signé 🎉                                                        |
| ❌ Refus           | Pas intéressé, on ne recontacte pas                               |

---

## 🛠️ Dépannage

- **Connexion Supabase échouée** : vérifie `SUPABASE_URL` et `SUPABASE_KEY`
  dans `.streamlit/secrets.toml` (local) ou dans Streamlit Cloud Settings → Secrets.
- **Import Excel ne charge rien** : vérifie que le fichier vient bien de
  `scrape_leads.py` et a un onglet "Tous les leads" (le 1er onglet).
- **Statut perdu après nouveau scraping** : impossible. La fonction
  `import_from_excel` préserve les champs CRM (statut/notes/etc.) sur les
  leads existants identifiés par leur téléphone.

---

## 🔮 Roadmap V2 (à faire plus tard)

- [ ] **Enrichissement email** via Dropcontact (~50€/mois) → bouton "🔍 Trouver l'email"
- [ ] **Cold emailing** via Lemlist/Brevo → bouton "📧 Ajouter à campagne"
- [ ] **Webhook entrant** : Lemlist → app pour MAJ statut auto sur clic/réponse
- [ ] **Assignation par commercial** (chacun ses leads) si l'équipe grandit
- [ ] **Historique des changements** par lead (timeline)
