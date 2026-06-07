# Télécommande TV Launcher (TV Launcher Remote)

Une application web moderne, fluide et optimisée de télécommande et de contrôle pour PC média-center sous Linux branché sur un téléviseur.

---

## ─── CARACTÉRISTIQUES ─────────────────────────────────────────────────────────

*   🚀 **Lanceur d'applications :** Démarre des liens web (dans Firefox Kiosk ou Chrome Fullscreen) ou des commandes système directement depuis l'interface tactile.
*   🖱️ **Contrôle de la souris :**
    *   **Vue Écran (PC) :** Visualise l'écran de la TV en direct avec des captures d'écran fluides et contrôle le curseur par coordonnées absolues en cliquant/bougeant la souris.
    *   **Trackpad (iPad / tactile) :** Zone de touchpad géante avec gestes tactiles (glisser pour bouger la souris, tap pour clic gauche, tap à 2 doigts pour clic droit, glisser à 2 doigts pour défiler).
*   ⌨️ **Clavier Physique :** Saisie en temps réel depuis ton clavier d'ordinateur vers la TV.
*   🔊 **Volume & Zoom :** Ajuste le volume sonore (PulseAudio/PipeWire/ALSA) et le zoom d'affichage de la TV.
*   💡 **Hyperion :** Raccourcis pour démarrer/arrêter et réinitialiser ton serveur de LED Ambilight Hyperion.
*   🔋 **Alimentation & Maintenance :** Extinction, redémarrage du PC TV, et mise à jour automatique de l'application (via Git Pull et rechargement de service).

---

## ─── ARCHITECTURE ────────────────────────────────────────────────────────────

Le projet est minimaliste et performant :
1.  **Backend (Python 3) :** Un serveur HTTP multithread sans framework externe (utilise uniquement la bibliothèque standard Python) pour interagir avec le système Linux via `xdotool`, `amixer`, `pactl`, `scrot` et `systemctl`.
2.  **Frontend (Vanilla JS/CSS) :** Une interface mobile-first et responsive (avec adaptabilité pour les grands écrans PC/tablette) stylisée avec un thème sombre "Glassmorphism" moderne et épuré.

---

## ─── PRÉREQUIS & DÉPENDANCES ──────────────────────────────────────────────────

Sur le PC Linux de la TV :
```bash
sudo apt update
sudo apt install -y xdotool scrot ffmpeg x11-xserver-utils pulseaudio-utils
```

*   `xdotool` : Indispensable pour simuler les touches du clavier, les clics et mouvements de souris.
*   `scrot` / `ffmpeg` : Utilisés pour la capture d'écran en direct.
*   `pactl` / `amixer` : Utilisés pour la gestion du volume sonore.

---

## ─── CONFIGURATION (.env) ────────────────────────────────────────────────────

Créez un fichier nommé `.env` à la racine du projet en copiant `.env.example` :
```env
# Mot de passe sudo de l'utilisateur (pour systemctl poweroff/reboot/service)
SUDO_PASSWORD=mon_mot_de_passe_secret
```

---

## ─── INSTALLATION & CHARGEMENT AUTOMATIQUE ───────────────────────────────────

Pour installer l'application et la configurer comme un service système qui démarre avec la TV :
1.  Exécutez le script d'initialisation :
    ```bash
    sudo python3 init.py
    ```
2.  Ce script va configurer le service de démarrage `tv-remote.service` et lier le port `80` pour écouter sur le réseau local.
3.  Vous pouvez maintenant vous connecter sur le navigateur de votre téléphone/tablette/PC à l'adresse :
    `http://tv.local` (ou l'IP locale de la TV).

---

## ─── APIS & ROUTAGE (TABLE DE RÉFÉRENCE) ──────────────────────────────────────

| Route | Méthode | Paramètres (JSON) | Description |
| :--- | :--- | :--- | :--- |
| `/api/status` | GET | Aucun | Retourne le statut de connexion du serveur |
| `/api/apps` | GET | Aucun | Liste toutes les applications installées (data.json) |
| `/api/apps/launch` | POST | `{ "id": "app_id" }` | Démarre l'application par son ID unique |
| `/api/apps/save` | POST | `{ "apps": [...] }` | Sauvegarde la configuration ou l'ordre des favoris |
| `/api/mouse/move` | POST | `{ "dx": 0, "dy": 0 }` | Déplacement relatif de la souris (pixels) |
| `/api/mouse/move_abs` | POST | `{ "x": 0.5, "y": 0.5 }` | Positionnement absolu sur l'écran (0.0 à 1.0) |
| `/api/mouse/click` | POST | `{ "button": "left"/"right" }`| Simule un clic de souris |
| `/api/mouse/scroll` | POST | `{ "direction": "up"/"down", "clicks": 1 }` | Simule un défilement de molette |
| `/api/keyboard/key`| POST | `{ "key": "...", "modifiers": [] }`| Envoie une touche de clavier avec modificateurs |
| `/api/volume` | POST | `{ "action": "up"/"down"/"mute" }`| Contrôle du volume sonore principal |
| `/api/zoom` | POST | `{ "action": "in"/"out"/"reset" }` | Ajuste le zoom de l'affichage sur la TV |
| `/api/hyperion` | POST | `{ "action": "on"/"off" }` | Active ou désactive le service ambilight Hyperion |
| `/api/fullscreen` | POST | Aucun | Simule la touche F11 (plein écran de la TV) |
| `/api/quit-app` | POST | Aucun | Ferme de façon ciblée la fenêtre active (exclut le lanceur) |
| `/api/system/open-launcher` | POST | Aucun | Relance le navigateur de la TV sur le lanceur local |
| `/api/system/screenshot`| GET | Aucun | Capture l'image actuelle de la TV et la sert en PNG |
| `/api/system/shutdown`| POST | Aucun | Éteint le PC de la TV via sudo |
| `/api/system/reboot`| POST | Aucun | Redémarre le PC de la TV via sudo |
| `/api/system/update`| POST | Aucun | Effectue un `git pull` et relance le service tv-remote |

---

## ─── DÉPANNAGE (FAQ) ─────────────────────────────────────────────────────────

### 🔑 Déconnexion récurrente de Netflix sur Chrome
*   **Problème :** Lorsque vous ouvrez Netflix depuis la télécommande, vous êtes déconnecté.
*   **Cause :** Chrome crypte les cookies avec le trousseau de clés Linux (Gnome Keyring). Lancé en tâche de fond par `systemd`, Chrome n'a pas accès à la session graphique d'origine et ne peut pas déchiffrer les cookies, provoquant une déconnexion.
*   **Résolution :** L'application intègre le drapeau `--password-store=basic` pour le lancement de Chrome afin de bypasser ce verrouillage. N'utilisez pas de commande `pkill` destructrice sur Chrome.

### 🎥 DRM / Widevine ne fonctionne pas sur Chrome / Firefox (Écran Noir)
*   **Résolution :** Assurez-vous que le module de décryptage Widevine CDM est à jour. Dans Chrome, ouvrez `chrome://components` et cliquez sur "Rechercher des mises à jour" dans la section Widevine. Sur Firefox, cochez "Lire le contenu protégé par DRM" dans les préférences.

### 🚫 Erreur DISPLAY : "unable to open display"
*   **Cause :** Le serveur web s'exécute en arrière-plan et a besoin de connaître l'écran X11 actif.
*   **Résolution :** Le projet cherche automatiquement le fichier `.Xauthority` de l'utilisateur actif. Vérifiez que la variable d'environnement `DISPLAY` est bien configurée sur `:0` dans le fichier du service systemd (`/etc/systemd/system/tv-remote.service`).
