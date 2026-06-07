#!/usr/bin/env python3
import json
import os
import subprocess
import shlex
import urllib.parse
import sys
import re
import threading
import urllib.request
from html.parser import HTMLParser
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# Lock for data.json concurrency safety
DATA_LOCK = threading.Lock()

# ---------------------------------------------------------
# Dual-compatibility Threading Server
# Works on python < 3.7 and >= 3.7
# ---------------------------------------------------------
try:
    from http.server import ThreadingHTTPServer
except ImportError:
    class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True

# Paths Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
ICONS_DIR = os.path.join(BASE_DIR, "icons")
DATA_PATH = os.path.join(BASE_DIR, "data.json")
ENV_PATH = os.path.join(BASE_DIR, ".env")

# ---------------------------------------------------------
# Load .env file (SUDO_PASSWORD, etc.)
# ---------------------------------------------------------
def load_env(path):
    """Parse a simple KEY=VALUE .env file into a dict."""
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

APP_ENV = load_env(ENV_PATH)
SUDO_PASSWORD = APP_ENV.get('SUDO_PASSWORD', '')

if SUDO_PASSWORD:
    print(f"[ENV] Mot de passe sudo chargé depuis .env ✓")
else:
    print(f"[ENV] ATTENTION : SUDO_PASSWORD absent du .env — éteindre/redémarrer nécessite sudo sans mdp", file=sys.stderr)


# ---------------------------------------------------------
# Web Icons Fetching Utilities
# ---------------------------------------------------------
class IconParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.icons = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() != "link": return
        attr = dict(attrs)
        rel = attr.get("rel", "").lower()
        href = attr.get("href")
        if not href: return
        if "apple-touch-icon" in rel: self.icons.append((0, href))
        elif "icon" in rel: self.icons.append((1, href))

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
    except: pass
    p = urllib.parse.urlparse(page_url)
    return f"{p.scheme}://{p.netloc}/favicon.ico"

def download_icon(icon_url, out_path):
    try:
        req = urllib.request.Request(icon_url, headers={"User-Agent": "Mozilla/5.0 TVLauncher"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read(300_000)
        if not data: return False
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f: f.write(data)
        return True
    except: return False

# ---------------------------------------------------------
# X11 Display Environment Detection
# ---------------------------------------------------------
def find_xauthority():
    # 1. Check standard /home paths
    try:
        if os.path.exists('/home'):
            for username in os.listdir('/home'):
                xauth = os.path.join('/home', username, '.Xauthority')
                if os.path.exists(xauth):
                    return xauth
    except Exception:
        pass
        
    # 2. Check /run/user paths (common in modern Ubuntu/GDM/LightDM)
    try:
        if os.path.exists('/run/user'):
            for uid in os.listdir('/run/user'):
                uid_dir = os.path.join('/run/user', uid)
                if os.path.isdir(uid_dir):
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
        
    # 3. Fallback standard path
    return '/home/ghiglione/.Xauthority'

def get_x11_env():
    env = os.environ.copy()
    
    # Default display to :0 if not present
    if 'DISPLAY' not in env:
        env['DISPLAY'] = ':0'
        
    if 'XAUTHORITY' not in env:
        env['XAUTHORITY'] = find_xauthority()
            
    return env

# ---------------------------------------------------------
# Input Simulation via xdotool
# ---------------------------------------------------------
def run_xdotool(cmd_args):
    env = get_x11_env()
    full_cmd = ["xdotool"] + cmd_args
    try:
        res = subprocess.run(full_cmd, capture_output=True, text=True, env=env)
        if res.returncode == 0:
            return True
        else:
            print(f"[ERROR] Échec xdotool {cmd_args}. code={res.returncode}, env={dict(DISPLAY=env.get('DISPLAY'), XAUTHORITY=env.get('XAUTHORITY'))}, stderr={res.stderr.strip()}", file=sys.stderr)
            return False
    except FileNotFoundError:
        print("[ERROR] 'xdotool' n'est pas installé sur le système Ubuntu.", file=sys.stderr)
        print("[TUTO] Installez-le en exécutant : sudo apt install -y xdotool", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERROR] Échec de l'exécution xdotool {cmd_args}: {e}", file=sys.stderr)
        return False

# ---------------------------------------------------------
# Sound Controls (PulseAudio / PipeWire / ALSA)
# ---------------------------------------------------------
def run_volume(action):
    env = get_x11_env()
    
    # Assurer que XDG_RUNTIME_DIR est présent
    if 'XDG_RUNTIME_DIR' not in env:
        uid = "1000"
        try:
            import pwd
            uid = str(pwd.getpwnam('ghiglione').pw_uid)
        except Exception:
            pass
        env['XDG_RUNTIME_DIR'] = f'/run/user/{uid}'
        
    # Injecter PULSE_RUNTIME_PATH si le dossier pulse de l'utilisateur existe
    uid = env['XDG_RUNTIME_DIR'].split('/')[-1]
    pulse_path = f"/run/user/{uid}/pulse"
    if os.path.exists(pulse_path):
        env['PULSE_RUNTIME_PATH'] = pulse_path

    # Define volume steps or commands
    cmds = []
    if action == "up":
        cmds = [
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+5%"],
            ["amixer", "sset", "Master", "5%+"]
        ]
    elif action == "down":
        cmds = [
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-5%"],
            ["amixer", "sset", "Master", "5%-"]
        ]
    elif action == "mute":
        cmds = [
            ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
            ["amixer", "sset", "Master", "toggle"]
        ]
        
    for cmd in cmds:
        try:
            # We try commands in sequence; if one returns 0, we exit successfully
            res = subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode == 0:
                return True
        except Exception:
            pass
    print("[WARNING] Échec de modification du volume (pactl et amixer ont échoué).", file=sys.stderr)
    return False

# ---------------------------------------------------------
# App Launching Controls
# ---------------------------------------------------------
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

def kill_browser(browser_name):
    """Kill browser process and clean up profile lock files to prevent 'already running' errors."""
    import glob, time
    
    # 1. Kill process
    for sig in ["-TERM", "-KILL"]:
        try:
            subprocess.run(["pkill", sig, "-f", browser_name],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    
    # 2. Wait briefly for process to actually die
    time.sleep(0.8)
    
    # 3. Remove Firefox profile lock files
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

def launch_application(app):
    try:
        env = get_x11_env()
        if app["type"] == "url":
            url = app["url"]
            if app.get("browser") == "chrome":
                # Kill Chrome first to avoid "already running" issues
                kill_browser("google-chrome")
                cmd = f"google-chrome --new-window --start-fullscreen {url}"
            else:
                # Kill Firefox first and remove lock files
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
    return False

# ---------------------------------------------------------
# Hyperion Service Management
# ---------------------------------------------------------
def control_hyperion(action):
    env = get_x11_env()
    
    # S'assurer que XDG_RUNTIME_DIR est présent
    if 'XDG_RUNTIME_DIR' not in env:
        uid = "1000"
        try:
            import pwd
            uid = str(pwd.getpwnam('ghiglione').pw_uid)
        except Exception:
            pass
        env['XDG_RUNTIME_DIR'] = f'/run/user/{uid}'

    # ON = restart (pour relancer même si déjà en cours mais bloqué)
    # OFF = stop
    verb = "restart" if action == "on" else "stop"
    cmd = ["systemctl", "--user", verb, "hyperion.service"]
    print(f"[HYPERION] {action.upper()} via 'systemctl --user {verb} hyperion.service'")
    
    try:
        res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return True
        else:
            print(f"[WARNING] Échec systemctl --user, code={res.returncode}, stderr={res.stderr.strip()}. Tentative de repli direct...", file=sys.stderr)
    except Exception as e:
        print(f"[WARNING] Exception systemctl: {e}. Tentative de repli direct...", file=sys.stderr)
        
    # Repli direct en lançant le binaire (fallback)
    if action == "on":
        display = env.get('DISPLAY', ':0')
        xauth = env.get('XAUTHORITY', '/home/ghiglione/.Xauthority')
        fallback_cmd = f"bash -c 'killall hyperiond 2>/dev/null; sleep 0.5; env DISPLAY={display} XAUTHORITY={xauth} nohup /bin/hyperiond > /dev/null 2>&1 &'"
        subprocess.Popen(fallback_cmd, shell=True, env=env)
        return True
    elif action == "off":
        subprocess.run(["killall", "-9", "hyperiond"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    return False

# ---------------------------------------------------------
# Screen Capture & Display Geometry Helpers
# ---------------------------------------------------------
def capture_screen():
    import tempfile
    tmp_file = os.path.join(tempfile.gettempdir(), "tv_screen.png")
    env = get_x11_env()
    display = env.get('DISPLAY', ':0')
    
    # 1. scrot (rapide, silencieux)
    try:
        res = subprocess.run(["scrot", "-z", "-o", tmp_file], env=env, capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and os.path.exists(tmp_file):
            return tmp_file
        print(f"[SCREENSHOT] scrot: code={res.returncode} {res.stderr.strip()[:60]}", file=sys.stderr)
    except Exception as e:
        print(f"[SCREENSHOT] scrot: {e}", file=sys.stderr)

    # 2. ffmpeg x11grab (très commun sur Ubuntu)
    try:
        w, h = get_screen_resolution()
        res = subprocess.run([
            "ffmpeg", "-y",
            "-f", "x11grab",
            "-video_size", f"{w}x{h}",
            "-i", display,
            "-vframes", "1",
            "-q:v", "2",
            tmp_file
        ], env=env, capture_output=True, text=True, timeout=8)
        if res.returncode == 0 and os.path.exists(tmp_file):
            return tmp_file
        print(f"[SCREENSHOT] ffmpeg: code={res.returncode} {res.stderr.strip()[-120:]}", file=sys.stderr)
    except Exception as e:
        print(f"[SCREENSHOT] ffmpeg: {e}", file=sys.stderr)

    # 3. xwd + convert (x11-apps + imagemagick)
    try:
        xwd_proc = subprocess.run(
            ["xwd", "-root", "-silent", "-display", display],
            env=env, capture_output=True, timeout=5
        )
        if xwd_proc.returncode == 0 and xwd_proc.stdout:
            conv = subprocess.run(
                ["convert", "xwd:-", tmp_file],
                input=xwd_proc.stdout, capture_output=True, timeout=5
            )
            if conv.returncode == 0 and os.path.exists(tmp_file):
                return tmp_file
            print(f"[SCREENSHOT] xwd+convert: convert code={conv.returncode}", file=sys.stderr)
        else:
            print(f"[SCREENSHOT] xwd: code={xwd_proc.returncode}", file=sys.stderr)
    except Exception as e:
        print(f"[SCREENSHOT] xwd+convert: {e}", file=sys.stderr)

    # 4. gnome-screenshot
    try:
        res = subprocess.run(["gnome-screenshot", "-f", tmp_file], env=env, capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and os.path.exists(tmp_file):
            return tmp_file
        print(f"[SCREENSHOT] gnome-screenshot: code={res.returncode}", file=sys.stderr)
    except Exception as e:
        print(f"[SCREENSHOT] gnome-screenshot: {e}", file=sys.stderr)

    # 5. import (ImageMagick)
    try:
        res = subprocess.run(["import", "-window", "root", tmp_file], env=env, capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and os.path.exists(tmp_file):
            return tmp_file
        print(f"[SCREENSHOT] import: code={res.returncode}", file=sys.stderr)
    except Exception as e:
        print(f"[SCREENSHOT] import: {e}", file=sys.stderr)

    print("[SCREENSHOT] Tous les outils ont échoué. Installez scrot: sudo apt install scrot", file=sys.stderr)
    return None

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
    return 1920, 1080 # Fallback

# ---------------------------------------------------------
# Safe Static File Serving
# ---------------------------------------------------------
def safe_serve_file(handler, base_dir, filename, content_type):
    # Prevent path traversal vulnerabilities
    filepath = os.path.abspath(os.path.join(base_dir, filename))
    if not filepath.startswith(base_dir):
        handler.send_error(403, "Accès Refusé")
        return
        
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
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

# ---------------------------------------------------------
# HTTP Request Handler Class
# ---------------------------------------------------------
class TVRemoteHandler(BaseHTTPRequestHandler):
    
    # Mute log console output for frequent mouse moves and state checks
    def log_message(self, format, *args):
        # Filter out noisy endpoints from printing to CLI stdout
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
        
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        
        # Static files mapping
        if path in ("/", "/index.html"):
            safe_serve_file(self, WEB_DIR, "index.html", "text/html")
        elif path == "/style.css":
            safe_serve_file(self, WEB_DIR, "style.css", "text/css")
        elif path == "/client.js":
            safe_serve_file(self, WEB_DIR, "client.js", "application/javascript")
            
        # Serve icons from local icons/ folder
        elif path.startswith("/icons/"):
            filename = path[7:] # strip '/icons/'
            # Map common icon formats
            ext = os.path.splitext(filename)[1].lower()
            content_type = "image/png"
            if ext in (".jpg", ".jpeg"): content_type = "image/jpeg"
            elif ext == ".svg": content_type = "image/svg+xml"
            elif ext == ".ico": content_type = "image/x-icon"
            
            safe_serve_file(self, ICONS_DIR, filename, content_type)
            
        # API GET Requests
        elif path == "/api/status":
            self.send_json({"status": "ok"})
        elif path == "/api/apps":
            # Load list of apps from data.json file
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
            
    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        
        # Read body contents
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            body = json.loads(post_data) if post_data else {}
        except Exception as e:
            self.send_json({"success": False, "error": f"JSON invalide: {e}"}, status=400)
            return
            
        success = False
        
        # API Routes dispatching
        if path == "/api/launch":
            app_id = body.get("id")
            success = launch_app_by_id(app_id)
            
        elif path == "/api/launch-url":
            url = body.get("url")
            browser = body.get("browser", "firefox")
            if url:
                success = launch_application({"type": "url", "url": url, "browser": browser})
                
        elif path == "/api/apps/add":
            name = body.get("name", "Favori")
            url = body.get("url")
            browser = body.get("browser", "firefox")
            if url:
                app_id = re.sub(r'[^a-zA-Z0-9]+', '_', name.lower()).strip('_')
                if not app_id: app_id = "custom_app"
                
                with DATA_LOCK:
                    try:
                        with open(DATA_PATH, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            
                        temp_id = app_id
                        idx = 1
                        while any(a.get("id") == temp_id for a in data.get("apps", [])):
                            temp_id = f"{app_id}_{idx}"
                            idx += 1
                        app_id = temp_id
                        
                        icon_relative = f"icons/{app_id}.png"
                        icon_full = os.path.join(BASE_DIR, icon_relative)
                        
                        icon_url = find_icon_url(url)
                        download_icon(icon_url, icon_full)
                        
                        new_app = {
                            "id": app_id,
                            "name": name,
                            "type": "url",
                            "url": url,
                            "browser": browser,
                            "icon": icon_relative
                        }
                        
                        data.setdefault("apps", []).append(new_app)
                        with open(DATA_PATH, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                        success = True
                    except Exception as e:
                        print(f"Error adding app: {e}", file=sys.stderr)

        elif path == "/api/apps/edit":
            app_id = body.get("id")
            name = body.get("name")
            url = body.get("url")
            browser = body.get("browser")
            if app_id:
                with DATA_LOCK:
                    try:
                        with open(DATA_PATH, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            
                        app = next((a for a in data.get("apps", []) if a.get("id") == app_id), None)
                        if app:
                            if name: app["name"] = name
                            if url: app["url"] = url
                            if browser: app["browser"] = browser
                            if url and app.get("type") == "url":
                                icon_relative = app.get("icon", f"icons/{app_id}.png")
                                icon_full = os.path.join(BASE_DIR, icon_relative)
                                icon_url = find_icon_url(url)
                                download_icon(icon_url, icon_full)
                                app["icon"] = icon_relative
                            
                            with open(DATA_PATH, "w", encoding="utf-8") as f:
                                json.dump(data, f, indent=2, ensure_ascii=False)
                            success = True
                    except Exception as e:
                        print(f"Error editing app: {e}", file=sys.stderr)

        elif path == "/api/apps/delete":
            app_id = body.get("id")
            if app_id:
                with DATA_LOCK:
                    try:
                        with open(DATA_PATH, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            
                        apps = data.get("apps", [])
                        app = next((a for a in apps if a.get("id") == app_id), None)
                        if app:
                            icon_relative = app.get("icon", "")
                            if icon_relative:
                                icon_full = os.path.join(BASE_DIR, icon_relative)
                                if os.path.exists(icon_full) and "icons/" in icon_relative:
                                    try: os.remove(icon_full)
                                    except: pass
                                    
                        data["apps"] = [a for a in apps if a.get("id") != app_id]
                        with open(DATA_PATH, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                        success = True
                    except Exception as e:
                        print(f"Error deleting app: {e}", file=sys.stderr)

        elif path == "/api/apps/reorder":
            order = body.get("order", [])
            if order:
                with DATA_LOCK:
                    try:
                        with open(DATA_PATH, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            
                        apps = data.get("apps", [])
                        apps_map = {a.get("id"): a for a in apps}
                        
                        new_apps = []
                        for aid in order:
                            if aid in apps_map:
                                new_apps.append(apps_map[aid])
                                del apps_map[aid]
                        new_apps.extend(apps_map.values())
                        
                        data["apps"] = new_apps
                        with open(DATA_PATH, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                        success = True
                    except Exception as e:
                        print(f"Error reordering apps: {e}", file=sys.stderr)
                
        elif path == "/api/mouse/move":
            dx = body.get("dx", 0)
            dy = body.get("dy", 0)
            success = run_xdotool(["mousemove_relative", "--", str(dx), str(dy)])
            
        elif path == "/api/mouse/move_abs":
            x = body.get("x", 0.5)
            y = body.get("y", 0.5)
            w, h = get_screen_resolution()
            abs_x = int(x * w)
            abs_y = int(y * h)
            success = run_xdotool(["mousemove", str(abs_x), str(abs_y)])
            
        elif path == "/api/mouse/click":
            btn = body.get("button", "left")
            click_num = "1" if btn == "left" else "3"
            success = run_xdotool(["click", click_num])
            
        elif path == "/api/mouse/scroll":
            direction = body.get("direction", "down")
            clicks = body.get("clicks", 1)
            btn_map = {"up": "4", "down": "5", "left": "6", "right": "7"}
            btn = btn_map.get(direction, "5")
            success = run_xdotool(["click", "--repeat", str(clicks), btn])
            
        elif path == "/api/keyboard/key":
            key = body.get("key")
            mods = body.get("modifiers", [])
            if key:
                # Compile modifiers if any
                translated_mods = ["super" if m in ("super", "win") else m for m in mods]
                combo = "+".join(translated_mods) + "+" + key if translated_mods else key
                success = run_xdotool(["key", combo])
                
        elif path == "/api/keyboard/type":
            text = body.get("text", "")
            if text:
                success = run_xdotool(["type", "--", text])
                
        elif path == "/api/volume":
            action = body.get("action")
            success = run_volume(action)
            
        elif path == "/api/zoom":
            action = body.get("action")
            if action == "in":
                # Send both options (plus / equal) to support french / international keyboards
                run_xdotool(["key", "ctrl+plus"])
                success = run_xdotool(["key", "ctrl+equal"])
            elif action == "out":
                success = run_xdotool(["key", "ctrl+minus"])
            elif action == "reset":
                success = run_xdotool(["key", "ctrl+0"])
                
        elif path == "/api/media":
            action = body.get("action")
            key_map = {"play": "XF86AudioPlay", "next": "XF86AudioNext", "prev": "XF86AudioPrev"}
            if action in key_map:
                success = run_xdotool(["key", key_map[action]])
                
        elif path == "/api/hyperion":
            action = body.get("action")
            success = control_hyperion(action)
            
        elif path == "/api/fullscreen":
            success = run_xdotool(["key", "F11"])

        elif path == "/api/quit-app":
            import time
            # 1. Try Ctrl+Q (Firefox, most apps)
            run_xdotool(["key", "ctrl+q"])
            time.sleep(0.4)
            # 2. Try Ctrl+W (Chrome: close tab / window)
            run_xdotool(["key", "ctrl+w"])
            time.sleep(0.3)
            # 3. Try Alt+F4 (universal window close on Linux)
            run_xdotool(["key", "alt+F4"])
            time.sleep(0.3)
            # 4. Last resort: pkill browsers
            env = get_x11_env()
            for proc_name in ["google-chrome", "chromium-browser", "chromium", "firefox"]:
                subprocess.run(["pkill", "-f", proc_name],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            success = True
            
        elif path == "/api/system/shutdown":
            print("[SYSTEM] Shutdown initiated by remote.", file=sys.stderr)
            # Send success FIRST so client receives it before machine cuts power
            self.send_json({"success": True})

            def do_shutdown():
                import time
                time.sleep(0.3)  # Small delay to ensure response is sent
                pwd = SUDO_PASSWORD
                # Commands to try in order
                cmds_with_password = [
                    (["sudo", "-S", "systemctl", "poweroff"], pwd),
                    (["sudo", "-S", "shutdown", "-h", "now"], pwd),
                    (["sudo", "-S", "halt", "-p"], pwd),
                ]
                cmds_no_password = [
                    ["systemctl", "poweroff"],
                    ["loginctl", "poweroff"],
                    ["shutdown", "-h", "now"],
                ]
                for cmd, password in cmds_with_password:
                    try:
                        res = subprocess.run(
                            cmd,
                            input=(password + "\n") if password else "",
                            capture_output=True, text=True, timeout=10
                        )
                        if res.returncode == 0:
                            print(f"[SYSTEM] Shutdown OK via {cmd}", file=sys.stderr)
                            return
                        print(f"[SHUTDOWN] {cmd} -> code={res.returncode} {res.stderr.strip()[:80]}", file=sys.stderr)
                    except Exception as e:
                        print(f"[SHUTDOWN] {cmd} exception: {e}", file=sys.stderr)
                for cmd in cmds_no_password:
                    try:
                        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                        if res.returncode == 0:
                            print(f"[SYSTEM] Shutdown OK via {cmd}", file=sys.stderr)
                            return
                        print(f"[SHUTDOWN] {cmd} -> code={res.returncode} {res.stderr.strip()[:80]}", file=sys.stderr)
                    except Exception as e:
                        print(f"[SHUTDOWN] {cmd} exception: {e}", file=sys.stderr)
                print("[SHUTDOWN ERROR] All methods failed!", file=sys.stderr)

            threading.Thread(target=do_shutdown, daemon=True).start()
            return

        elif path == "/api/system/reboot":
            print("[SYSTEM] Reboot initiated by remote.", file=sys.stderr)
            self.send_json({"success": True})

            def do_reboot():
                import time
                time.sleep(0.3)
                pwd = SUDO_PASSWORD
                cmds_with_password = [
                    (["sudo", "-S", "systemctl", "reboot"], pwd),
                    (["sudo", "-S", "shutdown", "-r", "now"], pwd),
                    (["sudo", "-S", "reboot"], pwd),
                ]
                cmds_no_password = [
                    ["systemctl", "reboot"],
                    ["loginctl", "reboot"],
                    ["shutdown", "-r", "now"],
                ]
                for cmd, password in cmds_with_password:
                    try:
                        res = subprocess.run(
                            cmd,
                            input=(password + "\n") if password else "",
                            capture_output=True, text=True, timeout=10
                        )
                        if res.returncode == 0:
                            print(f"[SYSTEM] Reboot OK via {cmd}", file=sys.stderr)
                            return
                        print(f"[REBOOT] {cmd} -> code={res.returncode} {res.stderr.strip()[:80]}", file=sys.stderr)
                    except Exception as e:
                        print(f"[REBOOT] {cmd} exception: {e}", file=sys.stderr)
                for cmd in cmds_no_password:
                    try:
                        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                        if res.returncode == 0:
                            print(f"[SYSTEM] Reboot OK via {cmd}", file=sys.stderr)
                            return
                        print(f"[REBOOT] {cmd} -> code={res.returncode} {res.stderr.strip()[:80]}", file=sys.stderr)
                    except Exception as e:
                        print(f"[REBOOT] {cmd} exception: {e}", file=sys.stderr)
                print("[REBOOT ERROR] All methods failed!", file=sys.stderr)

            threading.Thread(target=do_reboot, daemon=True).start()
            return

        elif path == "/api/system/update":
            print("[SYSTEM] Update requested by remote.", file=sys.stderr)
            self.send_json({"success": True, "message": "Mise à jour en cours..."})

            def do_update():
                import time
                time.sleep(0.5)
                # 1. git pull
                try:
                    res = subprocess.run(
                        ["git", "pull"],
                        cwd=BASE_DIR,
                        capture_output=True, text=True, timeout=60
                    )
                    out = res.stdout.strip() + " " + res.stderr.strip()
                    print(f"[UPDATE] git pull: {out.strip()}", file=sys.stderr)
                except Exception as e:
                    print(f"[UPDATE] git pull exception: {e}", file=sys.stderr)

                time.sleep(1)
                # 2. Restart service (client will reconnect automatically)
                pwd = SUDO_PASSWORD
                restart_cmds = [
                    (["sudo", "-S", "systemctl", "restart", "tv-remote.service"], pwd),
                    (["sudo", "-S", "systemctl", "restart", "tv-remote.service"], ""),
                ]
                for cmd, password in restart_cmds:
                    try:
                        res = subprocess.run(
                            cmd,
                            input=(password + "\n") if password else "",
                            capture_output=True, text=True, timeout=30
                        )
                        if res.returncode == 0:
                            print(f"[UPDATE] Service redémarré OK", file=sys.stderr)
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

# ---------------------------------------------------------
# Run server
# ---------------------------------------------------------
def run_server(host="0.0.0.0", port=8080):
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, TVRemoteHandler)
    print(f"=========================================================")
    print(f"  Serveur de Télécommande TV démarré avec succès !")
    print(f"  Adresse locale : http://localhost:{port}")
    print(f"  Sur le réseau  : http://tv.local:{port} (ou IP de la TV)")
    print(f"=========================================================")
    print(f"Appuyez sur Ctrl+C pour arrêter le serveur.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du serveur...")
        httpd.server_close()
        print("Serveur arrêté.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TV Launcher Web Remote Server")
    parser.add_argument("--port", type=int, default=8080, help="Port d'écoute (defaut: 8080)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Adresse IP d'écoute (defaut: 0.0.0.0)")
    args = parser.parse_args()
    
    run_server(host=args.host, port=args.port)
