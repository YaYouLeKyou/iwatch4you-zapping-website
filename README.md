# ⏱️ iWatch4u

> **Le meilleur du zapping web, heure par heure.**
> Agrégateur 100 % automatisé de vidéos virales — scraping RSS + IA Groq (Llama 3) + GitHub Actions.

## 🗂️ Structure du projet

```
iWatch4u/
├── .github/workflows/cron.yml   # Automatisation GitHub Actions
├── data/videos.json             # Base de données des vidéos (programmation)
├── scraper.py                   # Récupération RSS / conversion embed
├── groq_processor.py            # Génération titres/descriptions/tags via Groq
├── main.py                      # Pipeline complet (scrape → IA → planification)
├── index.html                   # Frontend
├── style.css                    # Thème sombre moderne
├── app.js                       # Logique d'affichage « 1 vidéo / heure »
└── requirements.txt
```

## ⚙️ Fonctionnement

1. **GitHub Actions** lance `main.py` toutes les 2 heures.
2. Le **scraper** inspecte les flux RSS (Koreus, chaînes YouTube…) et convertit les liens en URLs d'embed officielles (YouTube-nocookie, Dailymotion, Vimeo). Aucun MP4 n'est téléchargé.
3. **Groq AI** réécrit chaque titre en français accrocheur + description + tags.
4. Chaque vidéo reçoit un `publish_at` = dernière vidéo programmée + 1 h → file d'attente à raison d'**une vidéo par heure**.
5. Le frontend n'affiche que les vidéos dont `publish_at <= Date.now()` et affiche un compte à rebours jusqu'à la prochaine.

## 🚀 Déploiement pas à pas

### 1. Créer le dépôt GitHub
Poussez ce dossier vers un dépôt public (requis pour GitHub Pages gratuit).

### 2. Configurer le secret Groq
1. Sur GitHub : **Settings → Secrets and variables → Actions**.
2. Cliquez **New repository secret**.
3. Name : `GROQ_API_KEY` — Secret : votre clé Groq (https://console.groq.com/keys).

### 3. Activer GitHub Pages
1. **Settings → Pages**.
2. Source : **Deploy from a branch** → branche `main`, dossier `/ (root)` → **Save**.
3. Le site sera disponible sur `https://<votre-user>.github.io/<nom-du-repo>/`.

### 4. Premier lancement
Onglet **Actions → "Mise à jour automatique iWatch4u" → Run workflow** pour remplir immédiatement la file d'attente sans attendre le cron.

## 💻 Développement local

```bash
pip install -r requirements.txt
set GROQ_API_KEY=VotreCle          # Windows
export GROQ_API_KEY=VotreCle       # Linux/Mac

python main.py --max-items 3       # cycle complet
python main.py --dry-run           # test sans écriture
python -m http.server 8000         # serve le site sur http://localhost:8000
```

## 🔧 Personnalisation

- **Sources** : modifiez la liste `FEEDS` dans `scraper.py`.
- **Rythme du cron** : ligne `cron:` dans `.github/workflows/cron.yml`.
- **Vidéos ajoutées par exécution** : argument `--max-items` ou variable `MAX_ITEMS`.
- **Modèle IA** : variable d'environnement `GROQ_MODEL` (défaut : `llama-3.3-70b-versatile`).

## ⚖️ Légal

Les vidéos sont intégrées via leurs lecteurs officiels (embed) et restent la propriété de leurs auteurs respectifs.
