#!/usr/bin/env python3
import json
import os
import re
import sys
import glob
import time
import shlex
import threading
import subprocess
import tempfile
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# ─── Compatibilité Python < 3.7 ───────────────────────────────────────────────
try:
    from http.server import ThreadingHTTPServer
except ImportError:
    class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True

# ─── Verrou de concurrence pour data.json ─────────────────────────────────────
DATA_LOCK = threading.Lock()

# ─── Chemins du projet ────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
WEB_DIR    = os.path.join(BASE_DIR, "web")
ICONS_DIR  = os.path.join(BASE_DIR, "icons")
DATA_PATH  = os.path.join(BASE_DIR, "data.json")
ENV_PATH   = os.path.join(BASE_DIR, ".env")

# ─── Chargement du fichier .env ───────────────────────────────────────────────
def load_env(path):
    """Parse un fichier .env simple (KEY=VALUE) et retourne un dict."""
    env = {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, _, val = line.partition('=')
                    env[key.strip()] = val.strip()
    except FileNotFoundError:
        print(f"[ENV] Fichier .env introuvable : {path}", file=sys.stderr)
    except Exception as e:
        print(f"[ENV] Erreur lecture .env : {e}", file=sys.stderr)
    return env

APP_ENV       = load_env(ENV_PATH)
SUDO_PASSWORD = APP_ENV.get('SUDO_PASSWORD', '')

if SUDO_PASSWORD:
    print("[ENV] Mot de passe sudo chargé depuis .env ✓")
else:
    print("[ENV] ATTENTION : SUDO_PASSWORD absent du .env — éteindre/redémarrer nécessite sudo sans mdp",
          file=sys.stderr)


# ─── Récupération d'icônes web ────────────────────────────────────────────────
class IconParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.icons = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "link":
            return
        attr = dict(attrs)
        rel  = attr.get("rel", "").lower()
        href = attr.get("href")
        if not href:
            return
        if "apple-touch-icon" in rel:
            self.icons.append((0, href))
        elif "icon" in rel:
            self.icons.append((1, href))

def find_icon_url(page_url):
    try:
        req = urllib.request.Request(page_url, headers={"User-Agent": "Mozilla/5.0 TVLauncher"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read(200_000).decode("utf-8", errors="ignore")
        parser = IconParser()
        parser.feed(html)
        if parser.icons:
            parser.icons.sort(key=lambda x: x[0])
            return urllib.parse.urljoin(page_url, parser.icons[0][1])
    except Exception:
        pass
    p = urllib.parse.urlparse(page_url)
    return f"{p.scheme}://{p.netloc}/favicon.ico"

def download_icon(icon_url, out_path):
    try:
        req = urllib.request.Request(icon_url, headers={"User-Agent": "Mozilla/5.0 TVLauncher"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read(300_000)
        if not data:
            return False
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False


# ─── Environnement X11 ────────────────────────────────────────────────────────
def find_xauthority():
    """Recherche le fichier .Xauthority dans les emplacements habituels."""
    # 1. Répertoires /home/
    try:
        for username in os.listdir('/home'):
            xauth = f'/home/{username}/.Xauthority'
            if os.path.exists(xauth):
                return xauth
    except Exception:
        pass

    # 2. Répertoires /run/user/ (GDM/LightDM moderne)
    try:
        for uid in os.listdir('/run/user'):
            uid_dir = f'/run/user/{uid}'
            if not os.path.isdir(uid_dir):
                continue
            gdm_xauth = os.path.join(uid_dir, 'gdm', 'Xauthority')
            if os.path.exists(gdm_xauth):
                return gdm_xauth
            for filename in os.listdir(uid_dir):
                if filename.startswith('xauth') or filename == '.Xauthority':
                    xauth_path = os.path.join(uid_dir, filename)
                    if os.path.exists(xauth_path):
                        return xauth_path
    except Exception:
        pass

    return '/home/ghiglione/.Xauthority'

def get_x11_env():
    """Retourne os.environ complété avec DISPLAY et XAUTHORITY."""
    env = os.environ.copy()
    if 'DISPLAY' not in env:
        env['DISPLAY'] = ':0'
    if 'XAUTHORITY' not in env:
        env['XAUTHORITY'] = find_xauthority()
    return env


# ─── Simulation d'entrée via xdotool ──────────────────────────────────────────
def run_xdotool(cmd_args):
    env = get_x11_env()
    try:
        res = subprocess.run(["xdotool"] + cmd_args, capture_output=True, text=True, env=env)
        if res.returncode == 0:
            return True
        print(
            f"[ERROR] Échec xdotool {cmd_args}. code={res.returncode}, "
            f"DISPLAY={env.get('DISPLAY')}, stderr={res.stderr.strip()}",
            file=sys.stderr
        )
        return False
    except FileNotFoundError:
        print("[ERROR] 'xdotool' n'est pas installé. Exécutez : sudo apt install -y xdotool", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERROR] Échec xdotool {cmd_args}: {e}", file=sys.stderr)
        return False


def get_active_window_id():
    """Retourne l'identifiant numérique de la fenêtre active."""
    env = get_x11_env()
    try:
        res = subprocess.run(["xdotool", "getactivewindow"], capture_output=True, text=True, env=env, timeout=2)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return ""


def get_active_window_title():
    """Retourne le titre de la fenêtre active."""
    win_id = get_active_window_id()
    if not win_id:
        return ""
    env = get_x11_env()
    try:
        res = subprocess.run(["xdotool", "getwindowname", win_id], capture_output=True, text=True, env=env, timeout=2)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return ""



# ─── Contrôle du volume (PulseAudio / PipeWire / ALSA) ───────────────────────
def run_volume(action):
    env = get_x11_env()

    # Assurer XDG_RUNTIME_DIR
    if 'XDG_RUNTIME_DIR' not in env:
        uid = "1000"
        try:
            import pwd
            uid = str(pwd.getpwnam('ghiglione').pw_uid)
        except Exception:
            pass
        env['XDG_RUNTIME_DIR'] = f'/run/user/{uid}'

    uid = env['XDG_RUNTIME_DIR'].split('/')[-1]
    pulse_path = f"/run/user/{uid}/pulse"
    if os.path.exists(pulse_path):
        env['PULSE_RUNTIME_PATH'] = pulse_path

    cmds_map = {
        "up":   [["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+5%"],
                 ["amixer", "sset", "Master", "5%+"]],
        "down": [["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-5%"],
                 ["amixer", "sset", "Master", "5%-"]],
        "mute": [["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
                 ["amixer", "sset", "Master", "toggle"]],
    }
    for cmd in cmds_map.get(action, []):
        try:
            res = subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode == 0:
                return True
        except Exception:
            pass

    print("[WARNING] Échec de modification du volume (pactl et amixer ont échoué).", file=sys.stderr)
    return False


# ─── Lancement d'applications ─────────────────────────────────────────────────
def kill_browser(browser_name):
    """Tue le processus navigateur et supprime ses fichiers de verrouillage."""
    for sig in ["-TERM", "-KILL"]:
        try:
            subprocess.run(["pkill", sig, "-f", browser_name],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    time.sleep(0.8)

    if browser_name == "firefox":
        lock_patterns = [
            "/home/ghiglione/.mozilla/firefox/*/.parentlock",
            "/home/ghiglione/.mozilla/firefox/*/lock",
            "/tmp/firefox*",
        ]
        for pattern in lock_patterns:
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                    print(f"[LAUNCH] Supprimé verrou: {f}")
                except Exception as ex:
                    print(f"[WARNING] Impossible de supprimer {f}: {ex}", file=sys.stderr)

def launch_app_by_id(app_id):
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERROR] Impossible de lire data.json: {e}", file=sys.stderr)
        return False

    app = next((a for a in data.get("apps", []) if a.get("id") == app_id), None)
    if not app:
        print(f"[WARNING] Application avec ID '{app_id}' introuvable.", file=sys.stderr)
        return False
    return launch_application(app)

def launch_application(app):
    try:
        env = get_x11_env()
        if app["type"] == "url":
            url = app["url"]
            if app.get("browser") == "chrome":
                # Chrome n'a pas de problème de verrouillage de profil.
                # On N'écrase PAS les sessions Chrome existantes (ex: Netflix).
                # --password-store=basic permet de conserver les cookies cryptés même si le Keyring Gnome est verrouillé.
                cmd = f"google-chrome --new-window --start-fullscreen --password-store=basic {url}"
            else:
                # Firefox : tuer d'abord pour éviter le "already running"
                kill_browser("firefox")
                cmd = f"firefox --new-window --kiosk {url}"
            print(f"[LAUNCH] Ouverture URL: {url} dans {app.get('browser', 'firefox')}")
            subprocess.Popen(shlex.split(cmd), env=env)
            return True
        elif app["type"] == "cmd":
            print(f"[LAUNCH] Exécution commande: {app['cmd']}")
            subprocess.Popen(app["cmd"], shell=True, env=env)
            return True
    except Exception as e:
        print(f"[ERROR] Échec du lancement de l'application: {e}", file=sys.stderr)
    return False



# ─── Gestion du service Hyperion ──────────────────────────────────────────────
def control_hyperion(action):
    env = get_x11_env()

    if 'XDG_RUNTIME_DIR' not in env:
        uid = "1000"
        try:
            import pwd
            uid = str(pwd.getpwnam('ghiglione').pw_uid)
        except Exception:
            pass
        env['XDG_RUNTIME_DIR'] = f'/run/user/{uid}'

    verb = "restart" if action == "on" else "stop"
    cmd  = ["systemctl", "--user", verb, "hyperion.service"]
    print(f"[HYPERION] {action.upper()} via 'systemctl --user {verb} hyperion.service'")

    try:
        res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return True
        print(f"[WARNING] Échec systemctl --user, code={res.returncode}, stderr={res.stderr.strip()}. Repli...",
              file=sys.stderr)
    except Exception as e:
        print(f"[WARNING] Exception systemctl: {e}. Repli...", file=sys.stderr)

    # Repli direct
    if action == "on":
        display = env.get('DISPLAY', ':0')
        xauth   = env.get('XAUTHORITY', '/home/ghiglione/.Xauthority')
        fallback = (
            f"bash -c 'killall hyperiond 2>/dev/null; sleep 0.5; "
            f"env DISPLAY={display} XAUTHORITY={xauth} nohup /bin/hyperiond >/dev/null 2>&1 &'"
        )
        subprocess.Popen(fallback, shell=True, env=env)
        return True
    elif action == "off":
        subprocess.run(["killall", "-9", "hyperiond"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    return False


# ─── Capture d'écran ──────────────────────────────────────────────────────────
def get_screen_resolution():
    try:
        env = get_x11_env()
        res = subprocess.run(["xdotool", "getdisplaygeometry"], env=env, capture_output=True, text=True)
        if res.returncode == 0:
            parts = res.stdout.strip().split()
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return 1920, 1080

def capture_screen():
    """Tente de capturer l'écran avec plusieurs outils (scrot, ffmpeg, xwd, gnome-screenshot, import)."""
    tmp_file = os.path.join(tempfile.gettempdir(), "tv_screen.png")
    env      = get_x11_env()
    display  = env.get('DISPLAY', ':0')
    w, h     = get_screen_resolution()

    # Chaque stratégie : (nom, callable qui retourne la commande subprocess.run)
    def try_scrot():
        return subprocess.run(["scrot", "-z", "-o", tmp_file],
                              env=env, capture_output=True, text=True, timeout=5)

    def try_ffmpeg():
        return subprocess.run([
            "ffmpeg", "-y", "-f", "x11grab",
            "-video_size", f"{w}x{h}", "-i", display,
            "-vframes", "1", "-q:v", "2", tmp_file
        ], env=env, capture_output=True, text=True, timeout=8)

    def try_gnome():
        return subprocess.run(["gnome-screenshot", "-f", tmp_file],
                              env=env, capture_output=True, text=True, timeout=5)

    def try_import():
        return subprocess.run(["import", "-window", "root", tmp_file],
                              env=env, capture_output=True, text=True, timeout=5)

    strategies = [
        ("scrot",              try_scrot),
        ("ffmpeg",             try_ffmpeg),
        ("gnome-screenshot",   try_gnome),
        ("import",             try_import),
    ]

    # xwd + convert nécessite deux processus enchaînés — traité séparément
    for name, fn in strategies:
        try:
            res = fn()
            if res.returncode == 0 and os.path.exists(tmp_file):
                return tmp_file
            print(f"[SCREENSHOT] {name}: code={res.returncode} {res.stderr.strip()[-80:]}", file=sys.stderr)
        except Exception as e:
            print(f"[SCREENSHOT] {name}: {e}", file=sys.stderr)

        # xwd + convert intercalé après ffmpeg
        if name == "ffmpeg":
            try:
                xwd = subprocess.run(["xwd", "-root", "-silent", "-display", display],
                                     env=env, capture_output=True, timeout=5)
                if xwd.returncode == 0 and xwd.stdout:
                    conv = subprocess.run(["convert", "xwd:-", tmp_file],
                                          input=xwd.stdout, capture_output=True, timeout=5)
                    if conv.returncode == 0 and os.path.exists(tmp_file):
                        return tmp_file
                    print(f"[SCREENSHOT] xwd+convert: convert code={conv.returncode}", file=sys.stderr)
                else:
                    print(f"[SCREENSHOT] xwd: code={xwd.returncode}", file=sys.stderr)
            except Exception as e:
                print(f"[SCREENSHOT] xwd+convert: {e}", file=sys.stderr)

    print("[SCREENSHOT] Tous les outils ont échoué. Installez scrot: sudo apt install scrot", file=sys.stderr)
    return None


# ─── Commandes système avec sudo (shutdown / reboot) ──────────────────────────
def run_system_cmd(cmds_with_password, cmds_no_password, label):
    """
    Exécute une liste de commandes sudo, puis sans sudo, jusqu'au premier succès.
    cmds_with_password : liste de tuples (cmd_list, password_str)
    cmds_no_password   : liste de cmd_list
    label              : préfixe de log (ex: "SHUTDOWN", "REBOOT")
    """
    for cmd, password in cmds_with_password:
        try:
            res = subprocess.run(
                cmd,
                input=(password + "\n") if password else "",
                capture_output=True, text=True, timeout=10
            )
            if res.returncode == 0:
                print(f"[SYSTEM] {label} OK via {cmd}", file=sys.stderr)
                return
            print(f"[{label}] {cmd} -> code={res.returncode} {res.stderr.strip()[:80]}", file=sys.stderr)
        except Exception as e:
            print(f"[{label}] {cmd} exception: {e}", file=sys.stderr)

    for cmd in cmds_no_password:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                print(f"[SYSTEM] {label} OK via {cmd}", file=sys.stderr)
                return
            print(f"[{label}] {cmd} -> code={res.returncode} {res.stderr.strip()[:80]}", file=sys.stderr)
        except Exception as e:
            print(f"[{label}] {cmd} exception: {e}", file=sys.stderr)

    print(f"[{label} ERROR] Toutes les méthodes ont échoué !", file=sys.stderr)


# ─── Serveur de fichiers statiques ────────────────────────────────────────────
def safe_serve_file(handler, base_dir, filename, content_type):
    """Sert un fichier statique en vérifiant qu'il reste dans base_dir (anti path-traversal)."""
    filepath = os.path.abspath(os.path.join(base_dir, filename))
    if not filepath.startswith(base_dir):
        handler.send_error(403, "Accès Refusé")
        return
    if not os.path.isfile(filepath):
        handler.send_error(404, "Fichier Non Trouvé")
        return
    try:
        with open(filepath, "rb") as f:
            content = f.read()
        handler.send_response(200)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(content)))
        handler.send_cors_headers()
        handler.end_headers()
        handler.wfile.write(content)
    except Exception as e:
        handler.send_error(500, f"Erreur Interne du Serveur: {e}")


# ─── Gestionnaire de requêtes HTTP ────────────────────────────────────────────
class TVRemoteHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        """Filtre les endpoints bruyants (mousemove, status) des logs console."""
        try:
            log_str = format % args
        except Exception:
            log_str = ""
        if "/api/mouse/move" in log_str or "/api/status" in log_str:
            return
        super().log_message(format, *args)

    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    # ── Routes GET ──────────────────────────────────────────────────────────
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        # Fichiers statiques
        if path in ("/", "/index.html"):
            safe_serve_file(self, WEB_DIR, "index.html", "text/html")
        elif path == "/style.css":
            safe_serve_file(self, WEB_DIR, "style.css", "text/css")
        elif path == "/client.js":
            safe_serve_file(self, WEB_DIR, "client.js", "application/javascript")

        # Icônes
        elif path.startswith("/icons/"):
            filename = path[7:]
            ext = os.path.splitext(filename)[1].lower()
            content_type = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".svg": "image/svg+xml", ".ico": "image/x-icon"
            }.get(ext, "image/png")
            safe_serve_file(self, ICONS_DIR, filename, content_type)

        # API GET
        elif path == "/api/status":
            self.send_json({"status": "ok"})
        elif path == "/api/apps":
            try:
                with open(DATA_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.send_json(data)
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
        elif path == "/api/system/screenshot":
            img_path = capture_screen()
            if img_path and os.path.exists(img_path):
                try:
                    with open(img_path, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(content)))
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(content)
                except Exception as e:
                    self.send_json({"error": str(e)}, status=500)
            else:
                self.send_json({"error": "Impossible de capturer l'écran"}, status=500)
        else:
            self.send_error(404, "Fichier Non Trouvé")

    # ── Routes POST ─────────────────────────────────────────────────────────
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path

        # Lecture du corps JSON
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(content_length).decode('utf-8')
            body = json.loads(raw) if raw else {}
        except Exception as e:
            self.send_json({"success": False, "error": f"JSON invalide: {e}"}, status=400)
            return

        success = False

        # ── Lancement d'applications ───────────────────────────────────────
        if path == "/api/launch":
            success = launch_app_by_id(body.get("id"))

        elif path == "/api/launch-url":
            url = body.get("url")
            if url:
                success = launch_application({"type": "url", "url": url,
                                               "browser": body.get("browser", "firefox")})

        # ── Gestion des apps (CMS) ─────────────────────────────────────────
        elif path == "/api/apps/add":
            name    = body.get("name", "Favori")
            url     = body.get("url")
            browser = body.get("browser", "firefox")
            if url:
                app_id = re.sub(r'[^a-zA-Z0-9]+', '_', name.lower()).strip('_') or "custom_app"
                with DATA_LOCK:
                    try:
                        with open(DATA_PATH, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        temp_id, idx = app_id, 1
                        while any(a.get("id") == temp_id for a in data.get("apps", [])):
                            temp_id = f"{app_id}_{idx}"
                            idx += 1
                        app_id = temp_id
                        icon_relative = f"icons/{app_id}.png"
                        icon_full     = os.path.join(BASE_DIR, icon_relative)
                        download_icon(find_icon_url(url), icon_full)
                        data.setdefault("apps", []).append({
                            "id": app_id, "name": name, "type": "url",
                            "url": url, "browser": browser, "icon": icon_relative
                        })
                        with open(DATA_PATH, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                        success = True
                    except Exception as e:
                        print(f"[ERROR] Ajout app: {e}", file=sys.stderr)

        elif path == "/api/apps/edit":
            app_id = body.get("id")
            if app_id:
                with DATA_LOCK:
                    try:
                        with open(DATA_PATH, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        app = next((a for a in data.get("apps", []) if a.get("id") == app_id), None)
                        if app:
                            if body.get("name"):    app["name"]    = body["name"]
                            if body.get("url"):     app["url"]     = body["url"]
                            if body.get("browser"): app["browser"] = body["browser"]
                            if body.get("url") and app.get("type") == "url":
                                icon_relative = app.get("icon", f"icons/{app_id}.png")
                                download_icon(find_icon_url(body["url"]),
                                              os.path.join(BASE_DIR, icon_relative))
                                app["icon"] = icon_relative
                            with open(DATA_PATH, "w", encoding="utf-8") as f:
                                json.dump(data, f, indent=2, ensure_ascii=False)
                            success = True
                    except Exception as e:
                        print(f"[ERROR] Édition app: {e}", file=sys.stderr)

        elif path == "/api/apps/delete":
            app_id = body.get("id")
            if app_id:
                with DATA_LOCK:
                    try:
                        with open(DATA_PATH, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        apps = data.get("apps", [])
                        app  = next((a for a in apps if a.get("id") == app_id), None)
                        if app:
                            icon_rel = app.get("icon", "")
                            if icon_rel and "icons/" in icon_rel:
                                icon_full = os.path.join(BASE_DIR, icon_rel)
                                try:
                                    if os.path.exists(icon_full):
                                        os.remove(icon_full)
                                except Exception:
                                    pass
                        data["apps"] = [a for a in apps if a.get("id") != app_id]
                        with open(DATA_PATH, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                        success = True
                    except Exception as e:
                        print(f"[ERROR] Suppression app: {e}", file=sys.stderr)

        elif path == "/api/apps/reorder":
            order = body.get("order", [])
            if order:
                with DATA_LOCK:
                    try:
                        with open(DATA_PATH, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        apps_map = {a.get("id"): a for a in data.get("apps", [])}
                        new_apps = [apps_map.pop(aid) for aid in order if aid in apps_map]
                        new_apps.extend(apps_map.values())
                        data["apps"] = new_apps
                        with open(DATA_PATH, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                        success = True
                    except Exception as e:
                        print(f"[ERROR] Réorganisation apps: {e}", file=sys.stderr)

        # ── Contrôle de la souris ──────────────────────────────────────────
        elif path == "/api/mouse/move":
            success = run_xdotool(["mousemove_relative", "--",
                                   str(body.get("dx", 0)), str(body.get("dy", 0))])

        elif path == "/api/mouse/move_abs":
            w, h = get_screen_resolution()
            abs_x = int(body.get("x", 0.5) * w)
            abs_y = int(body.get("y", 0.5) * h)
            success = run_xdotool(["mousemove", str(abs_x), str(abs_y)])

        elif path == "/api/mouse/click":
            btn = "1" if body.get("button", "left") == "left" else "3"
            success = run_xdotool(["click", btn])

        elif path == "/api/mouse/scroll":
            btn_map   = {"up": "4", "down": "5", "left": "6", "right": "7"}
            btn       = btn_map.get(body.get("direction", "down"), "5")
            success   = run_xdotool(["click", "--repeat", str(body.get("clicks", 1)), btn])

        # ── Contrôle du clavier ────────────────────────────────────────────
        elif path == "/api/keyboard/key":
            key  = body.get("key")
            mods = body.get("modifiers", [])
            if key:
                translated_mods = ["super" if m in ("super", "win") else m for m in mods]
                combo   = "+".join(translated_mods) + "+" + key if translated_mods else key
                success = run_xdotool(["key", combo])

        elif path == "/api/keyboard/type":
            text = body.get("text", "")
            if text:
                success = run_xdotool(["type", "--", text])

        # ── Volume, zoom, média, Hyperion, plein écran ─────────────────────
        elif path == "/api/volume":
            success = run_volume(body.get("action"))

        elif path == "/api/zoom":
            action = body.get("action")
            if action == "in":
                run_xdotool(["key", "ctrl+plus"])
                success = run_xdotool(["key", "ctrl+equal"])
            elif action == "out":
                success = run_xdotool(["key", "ctrl+minus"])
            elif action == "reset":
                success = run_xdotool(["key", "ctrl+0"])

        elif path == "/api/media":
            key_map = {"play": "XF86AudioPlay", "next": "XF86AudioNext", "prev": "XF86AudioPrev"}
            action  = body.get("action")
            if action in key_map:
                success = run_xdotool(["key", key_map[action]])

        elif path == "/api/hyperion":
            success = control_hyperion(body.get("action"))

        elif path == "/api/fullscreen":
            success = run_xdotool(["key", "F11"])

        # ── Quitter l'application active ───────────────────────────────────
        elif path == "/api/quit-app":
            title = get_active_window_title().lower()
            print(f"[QUIT] Titre de la fenêtre active : '{title}'", file=sys.stderr)
            if "tv launcher" in title or title == "launcher":
                print("[QUIT] La fenêtre active est le Lanceur TV. Fermeture ignorée.", file=sys.stderr)
                self.send_json({"success": False, "error": "Cannot close launcher itself"})
                return

            win_id = get_active_window_id()
            if win_id:
                print(f"[QUIT] Fermeture ciblée de la fenêtre {win_id} ('{title}')", file=sys.stderr)
                run_xdotool(["windowclose", win_id])
                success = True
            else:
                print("[QUIT] ID de fenêtre active introuvable, envoi de ctrl+q et ctrl+w", file=sys.stderr)
                run_xdotool(["key", "ctrl+q"])
                time.sleep(0.2)
                run_xdotool(["key", "ctrl+w"])
                success = True

        # ── Ouvrir le lanceur sur la TV ─────────────────────────────────────
        elif path == "/api/system/open-launcher":
            env = get_x11_env()
            # 1. Tenter d'activer la fenêtre du lanceur si elle est déjà ouverte
            try:
                res = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", "TV Launcher"],
                                     capture_output=True, text=True, env=env, timeout=2)
                win_ids = res.stdout.strip().split()
                if win_ids:
                    win_id = win_ids[0]
                    print(f"[LAUNCH] Lanceur déjà en cours. Activation de la fenêtre {win_id}", file=sys.stderr)
                    subprocess.run(["xdotool", "windowactivate", win_id], env=env)
                    self.send_json({"success": True, "message": "Lanceur activé"})
                    return
            except Exception as e:
                print(f"[LAUNCH] Erreur lors de la recherche du lanceur: {e}", file=sys.stderr)

            # 2. Si non trouvée, relancer le script launcher.py
            cmd = f"/usr/bin/python3 {os.path.join(BASE_DIR, 'launcher.py')}"
            print(f"[LAUNCH] Lancement du Lanceur GTK: {cmd}", file=sys.stderr)
            subprocess.Popen(shlex.split(cmd), env=env)
            success = True

        # ── Extinction ─────────────────────────────────────────────────────
        elif path == "/api/system/shutdown":
            print("[SYSTEM] Extinction demandée par la télécommande.", file=sys.stderr)
            self.send_json({"success": True})
            def do_shutdown():
                time.sleep(0.3)
                run_system_cmd(
                    cmds_with_password=[
                        (["sudo", "-S", "systemctl", "poweroff"], SUDO_PASSWORD),
                        (["sudo", "-S", "shutdown", "-h", "now"],  SUDO_PASSWORD),
                        (["sudo", "-S", "halt", "-p"],              SUDO_PASSWORD),
                    ],
                    cmds_no_password=[
                        ["systemctl", "poweroff"],
                        ["loginctl",  "poweroff"],
                        ["shutdown",  "-h", "now"],
                    ],
                    label="SHUTDOWN"
                )
            threading.Thread(target=do_shutdown, daemon=True).start()
            return

        # ── Redémarrage ────────────────────────────────────────────────────
        elif path == "/api/system/reboot":
            print("[SYSTEM] Redémarrage demandé par la télécommande.", file=sys.stderr)
            self.send_json({"success": True})
            def do_reboot():
                time.sleep(0.3)
                run_system_cmd(
                    cmds_with_password=[
                        (["sudo", "-S", "systemctl", "reboot"],    SUDO_PASSWORD),
                        (["sudo", "-S", "shutdown",  "-r", "now"], SUDO_PASSWORD),
                        (["sudo", "-S", "reboot"],                  SUDO_PASSWORD),
                    ],
                    cmds_no_password=[
                        ["systemctl", "reboot"],
                        ["loginctl",  "reboot"],
                        ["shutdown",  "-r", "now"],
                    ],
                    label="REBOOT"
                )
            threading.Thread(target=do_reboot, daemon=True).start()
            return

        # ── Mise à jour Git + redémarrage du service ───────────────────────
        elif path == "/api/system/update":
            print("[SYSTEM] Mise à jour demandée par la télécommande.", file=sys.stderr)
            self.send_json({"success": True, "message": "Mise à jour en cours..."})
            def do_update():
                time.sleep(0.5)
                try:
                    res = subprocess.run(["git", "pull"], cwd=BASE_DIR,
                                         capture_output=True, text=True, timeout=60)
                    print(f"[UPDATE] git pull: {(res.stdout + res.stderr).strip()}", file=sys.stderr)
                except Exception as e:
                    print(f"[UPDATE] git pull exception: {e}", file=sys.stderr)
                time.sleep(1)
                restart_cmds = [
                    (["sudo", "-S", "systemctl", "restart", "tv-remote.service"], SUDO_PASSWORD),
                    (["sudo", "-S", "systemctl", "restart", "tv-remote.service"], ""),
                ]
                for cmd, password in restart_cmds:
                    try:
                        res = subprocess.run(
                            cmd, input=(password + "\n") if password else "",
                            capture_output=True, text=True, timeout=30
                        )
                        if res.returncode == 0:
                            print("[UPDATE] Service redémarré OK", file=sys.stderr)
                            return
                        print(f"[UPDATE] {cmd} -> {res.returncode}: {res.stderr.strip()[:80]}", file=sys.stderr)
                    except Exception as e:
                        print(f"[UPDATE] {cmd} exception: {e}", file=sys.stderr)
                print("[UPDATE ERROR] Impossible de redémarrer le service.", file=sys.stderr)
            threading.Thread(target=do_update, daemon=True).start()
            return

        else:
            self.send_error(404, "Route API Non Trouvée")
            return

        self.send_json({"success": success})

    # ── Réponse JSON ────────────────────────────────────────────────────────
    def send_json(self, data, status=200):
        try:
            response = json.dumps(data).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response)))
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(response)
        except Exception as e:
            print(f"[ERROR] Impossible d'envoyer la réponse JSON: {e}", file=sys.stderr)


# ─── Démarrage du serveur ──────────────────────────────────────────────────────
def run_server(host="0.0.0.0", port=8080):
    httpd = ThreadingHTTPServer((host, port), TVRemoteHandler)
    print("=========================================================")
    print("  Serveur de Télécommande TV démarré avec succès !")
    print(f"  Adresse locale : http://localhost:{port}")
    print(f"  Sur le réseau  : http://tv.local:{port} (ou IP de la TV)")
    print("=========================================================")
    print("Appuyez sur Ctrl+C pour arrêter le serveur.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du serveur...")
        httpd.server_close()
        print("Serveur arrêté.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TV Launcher Web Remote Server")
    parser.add_argument("--port", type=int, default=8080, help="Port d'écoute (défaut: 8080)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Adresse IP d'écoute (défaut: 0.0.0.0)")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)
