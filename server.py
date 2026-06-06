#!/usr/bin/env python3
import json
import os
import subprocess
import shlex
import urllib.parse
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

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
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

def launch_application(app):
    try:
        env = get_x11_env()
        if app["type"] == "url":
            url = app["url"]
            if app.get("browser") == "chrome":
                cmd = f"google-chrome --new-window --start-fullscreen {url}"
            else:
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
    if action == "on":
        display = env.get('DISPLAY', ':0')
        xauth = env.get('XAUTHORITY', '/home/ghiglione/.Xauthority')
        # Utilise les variables d'environnement détectées dynamiquement au lieu de valeurs en dur
        cmd = f"bash -c 'killall hyperiond; env DISPLAY={display} XAUTHORITY={xauth} nohup /bin/hyperiond > /dev/null 2>&1 &'"
        print(f"[HYPERION] Démarrage du service (DISPLAY={display}, XAUTHORITY={xauth})")
        subprocess.Popen(cmd, shell=True, env=env)
        return True
    elif action == "off":
        print("[HYPERION] Arrêt du service")
        subprocess.run(["killall", "hyperiond"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    return False

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
        request_line = args[0] if len(args) > 0 else ""
        if "/api/mouse/move" in request_line or "/api/status" in request_line:
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
                
        elif path == "/api/mouse/move":
            dx = body.get("dx", 0)
            dy = body.get("dy", 0)
            success = run_xdotool(["mousemove_relative", "--", str(dx), str(dy)])
            
        elif path == "/api/mouse/click":
            btn = body.get("button", "left")
            click_num = "1" if btn == "left" else "3"
            success = run_xdotool(["click", click_num])
            
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
