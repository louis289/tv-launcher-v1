#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil

def main():
    print("=========================================================")
    print("      TV Launcher & Remote - Script d'installation")
    print("=========================================================")

    # 1. Verification of Root Privileges
    if os.geteuid() != 0:
        print("\n[ERREUR] Ce script doit être exécuté avec les privilèges root (sudo).")
        print("Veuillez relancer avec : sudo python3 init.py\n")
        sys.exit(1)

    # 2. Detect the real non-root user who invoked sudo
    real_user = os.environ.get('SUDO_USER')
    if not real_user or real_user == 'root':
        # Fallback to folder owner
        import stat
        file_stat = os.stat(__file__)
        import pwd
        real_user = pwd.getpwuid(file_stat.st_uid).pw_name

    print(f"[INFO] Utilisateur cible détecté : {real_user}")
    
    # Get user home directory
    import pwd
    user_info = pwd.getpwnam(real_user)
    user_home = user_info.pw_dir
    user_uid = user_info.pw_uid
    user_gid = user_info.pw_gid

    repo_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"[INFO] Répertoire du projet : {repo_dir}")

    # Prompt confirmation
    confirm = input("\nVoulez-vous lancer l'installation ? (O/n) : ")
    if confirm.lower() not in ('', 'o', 'oui', 'y', 'yes'):
        print("Installation annulée.")
        sys.exit(0)

    # 3. Installing System Dependencies
    print("\n>>> Étape 1 : Installation des paquets apt...")
    try:
        subprocess.run(["apt-get", "update"], check=True)
        # Packages: xdotool (simulation), avahi (mDNS tv.local), GTK3 bindings (launcher.py), volume tools
        packages = [
            "xdotool", 
            "avahi-daemon", 
            "python3-gi", 
            "gir1.2-gtk-3.0", 
            "pulseaudio-utils", 
            "alsa-utils"
        ]
        print(f"[INFO] Installation des paquets : {', '.join(packages)}")
        subprocess.run(["apt-get", "install", "-y"] + packages, check=True)
        print("[OK] Dépendances installées avec succès.")
    except subprocess.CalledProcessError as e:
        print(f"[ERREUR] Échec de l'installation des dépendances : {e}")
        sys.exit(1)

    # 4. Hostname configuration for tv.local
    print("\n>>> Étape 2 : Configuration du nom de réseau (DNS local)...")
    net_confirm = input("Voulez-vous renommer ce PC en 'tv' pour y accéder via 'http://tv.local' ? (O/n) : ")
    if net_confirm.lower() in ('', 'o', 'oui', 'y', 'yes'):
        try:
            subprocess.run(["hostnamectl", "set-hostname", "tv"], check=True)
            subprocess.run(["systemctl", "restart", "avahi-daemon"], check=True)
            print("[OK] Machine renommée en 'tv'. L'adresse http://tv.local sera active après redémarrage.")
        except Exception as e:
            print(f"[WARNING] Impossible de renommer la machine : {e}")

    # 5. Create tv-remote.service (Systemd System Service)
    print("\n>>> Étape 3 : Création du service systemd de la Télécommande...")
    remote_service_path = "/etc/systemd/system/tv-remote.service"
    service_content = f"""[Unit]
Description=TV Launcher Remote Web Server
After=network.target

[Service]
Type=simple
User={real_user}
Group={real_user}
WorkingDirectory={repo_dir}
ExecStart=/usr/bin/python3 {repo_dir}/server.py --port 80
Restart=always
RestartSec=5
Environment=DISPLAY=:0
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
"""
    try:
        with open(remote_service_path, "w", encoding="utf-8") as f:
            f.write(service_content)
        
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", "tv-remote.service"], check=True)
        subprocess.run(["systemctl", "restart", "tv-remote.service"], check=True)
        print("[OK] Service tv-remote créé, activé et démarré sur le port 80.")
    except Exception as e:
        print(f"[ERREUR] Échec de configuration du service tv-remote : {e}")
        sys.exit(1)

    # 6. Create hyperion.service (Systemd User Service)
    print("\n>>> Étape 4 : Configuration du service utilisateur Hyperion...")
    user_systemd_dir = os.path.join(user_home, ".config", "systemd", "user")
    os.makedirs(user_systemd_dir, exist_ok=True)
    
    hyperion_service_path = os.path.join(user_systemd_dir, "hyperion.service")
    hyperion_content = """[Unit]
Description=Hyperion Ambient Light Service
After=network.target

[Service]
ExecStart=/bin/hyperiond
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""
    try:
        # Check if hyperion.service already exists to avoid overwriting user scripts
        if not os.path.exists(hyperion_service_path):
            with open(hyperion_service_path, "w", encoding="utf-8") as f:
                f.write(hyperion_content)
            print("[OK] Fichier hyperion.service par défaut créé.")
        else:
            print("[INFO] hyperion.service existe déjà. Conservation du fichier existant.")

        # Enable the service under the user session
        # Using su - <user> to execute systemctl --user command as the target user
        subprocess.run(["su", "-", real_user, "-c", "systemctl --user daemon-reload"], check=True)
        subprocess.run(["su", "-", real_user, "-c", "systemctl --user enable hyperion.service"], check=True)
        print("[OK] Service utilisateur Hyperion configuré et activé.")
    except Exception as e:
        print(f"[WARNING] Impossible de configurer le service utilisateur Hyperion : {e}")

    # 7. Configure Autostart for launcher.py
    print("\n>>> Étape 5 : Configuration du démarrage automatique du Launcher...")
    autostart_dir = os.path.join(user_home, ".config", "autostart")
    os.makedirs(autostart_dir, exist_ok=True)
    
    autostart_desktop_path = os.path.join(autostart_dir, "tv-launcher.desktop")
    autostart_content = f"""[Desktop Entry]
Type=Application
Exec=/usr/bin/python3 {repo_dir}/launcher.py
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=TV Launcher
Comment=Lance le menu TV au démarrage
"""
    try:
        with open(autostart_desktop_path, "w", encoding="utf-8") as f:
            f.write(autostart_content)
        print("[OK] Fichier de démarrage automatique du launcher créé.")
    except Exception as e:
        print(f"[WARNING] Impossible d'ajouter le launcher au démarrage automatique : {e}")

    # 8. Restore correct permissions on user files
    print("\n>>> Étape 6 : Restauration des droits d'accès utilisateur...")
    try:
        # Recursively change ownership of ~/.config directory to user, since we created folders under root
        user_config_dir = os.path.join(user_home, ".config")
        for root, dirs, files in os.walk(user_config_dir):
            for d in dirs:
                os.chown(os.path.join(root, d), user_uid, user_gid)
            for f in files:
                os.chown(os.path.join(root, f), user_uid, user_gid)
        print("[OK] Droits d'accès utilisateur restaurés.")
    except Exception as e:
        print(f"[WARNING] Droits d'accès non restaurés automatiquement : {e}")

    # 9. Installation Complete
    print("\n=========================================================")
    print("                 INSTALLATION TERMINÉE !")
    print("=========================================================")
    print(f" Accès Télécommande : http://tv.local (depuis votre Wi-Fi)")
    print(f" Le launcher GTK démarrera automatiquement avec la session.")
    print("=========================================================\n")

if __name__ == "__main__":
    main()
