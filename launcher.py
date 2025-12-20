#!/usr/bin/env python3
import urllib.request
import urllib.parse
from html.parser import HTMLParser
import json
import os
import subprocess
import shlex
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data.json")

# --- CONFIGURATION RESOLUTION TV ---
FORCE_WIDTH = 1920
FORCE_HEIGHT = 1080

def load_data():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def launch_app(app):
    try:
        if app["type"] == "url":
            url = app["url"]
            if app.get("browser") == "chrome":
                cmd = f"google-chrome --new-window --start-fullscreen {url}"
            else:
                cmd = f"firefox --new-window --kiosk {url}"
            subprocess.Popen(shlex.split(cmd))
        elif app["type"] == "cmd":
            subprocess.Popen(shlex.split(app["cmd"]))
    except Exception as e:
        print("Erreur lancement:", e)

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
        with open(out_path, "wb") as f: f.write(data)
        return True
    except: return False

def ensure_icons(data):
    icons_dir = os.path.join(BASE_DIR, "icons")
    os.makedirs(icons_dir, exist_ok=True)
    changed = False
    for app in data["apps"]:
        if app.get("icon") or app.get("type") != "url": continue
        app_id = app["id"]
        icon_path = f"icons/{app_id}.png"
        full_path = os.path.join(BASE_DIR, icon_path)
        if os.path.exists(full_path):
            app["icon"] = icon_path
            changed = True
            continue
        print(f"[ICON] récupération pour {app_id}")
        if download_icon(find_icon_url(app["url"]), full_path):
            app["icon"] = icon_path
            changed = True
    if changed:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

def play_sound(name):
    son_dir = os.path.join(BASE_DIR, "son")
    for ext in [".mp3", ".wav", ".ogg"]:
        fpath = os.path.join(son_dir, f"{name}{ext}")
        if os.path.exists(fpath):
            subprocess.Popen(["paplay", fpath], stderr=subprocess.DEVNULL)
            return

class Launcher(Gtk.Window):
    def __init__(self, data):
        super().__init__(title=data["ui"].get("title", "Launcher"))
        self.set_decorated(False)
        
        # --- FORCAGE TAILLE ---
        # On impose la taille trouvée via SSH
        self.set_default_size(FORCE_WIDTH, FORCE_HEIGHT)
        self.set_size_request(FORCE_WIDTH, FORCE_HEIGHT)
        self.fullscreen()
        
        self.connect("destroy", Gtk.main_quit)
        self.boot_finished = False 
        self.first_btn = None

        css_provider = Gtk.CssProvider()
        css = """
        #close_btn { background: transparent; color: rgba(255,255,255,0.2); border: none; font-size: 20px; font-weight: bold; margin: 20px; transition: all 0.3s; }
        #close_btn:hover { color: #ff5555; background: rgba(255,255,255,0.1); border-radius: 50px; }
        #main_overlay { opacity: 0; transition: opacity 1.5s ease-out; }
        #main_overlay.visible { opacity: 1; }
        button { border: 2px solid transparent; border-radius: 10px; background-color: transparent; }
        button:focus { background-color: rgba(255, 255, 255, 0.15); border: 2px solid #ffffff; box-shadow: 0 0 10px rgba(255, 255, 255, 0.5); }
        """
        css_provider.load_from_data(css.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.overlay = Gtk.Overlay()
        self.overlay.set_name("main_overlay")
        self.add(self.overlay)

        outer_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer_vbox.set_halign(Gtk.Align.CENTER)
        outer_vbox.set_valign(Gtk.Align.CENTER)
        self.overlay.add(outer_vbox)

        outer_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        outer_hbox.set_halign(Gtk.Align.CENTER)
        outer_hbox.set_valign(Gtk.Align.CENTER)
        outer_vbox.pack_start(outer_hbox, True, True, 0)

        grid = Gtk.Grid()
        grid.set_row_spacing(30)
        grid.set_column_spacing(30)
        grid.set_halign(Gtk.Align.CENTER)
        grid.set_valign(Gtk.Align.CENTER)
        outer_hbox.pack_start(grid, False, False, 0)

        cols = data["ui"].get("columns", 4)
        tile_px = data["ui"].get("tile_px", 200)
        tile_height_px = int(5.0 * 20) 

        for i, app in enumerate(data["apps"]):
            btn = Gtk.Button()
            btn.set_size_request(tile_px, tile_px)
            btn.connect("clicked", lambda _b, a=app: launch_app(a))
            btn.connect("focus-in-event", self.on_app_focus)
            if i == 0: self.first_btn = btn

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            box.set_halign(Gtk.Align.CENTER)
            box.set_valign(Gtk.Align.CENTER)

            img = Gtk.Image()
            icon_path = os.path.join(BASE_DIR, app.get("icon", ""))
            if os.path.exists(icon_path):
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(icon_path)
                    w, h = pixbuf.get_width(), pixbuf.get_height()
                    scale = tile_height_px / h
                    pixbuf = pixbuf.scale_simple(max(1, int(w*scale)), tile_height_px, GdkPixbuf.InterpType.BILINEAR)
                    img.set_from_pixbuf(pixbuf)
                except: img.set_from_icon_name("image-missing", Gtk.IconSize.DIALOG)
            else: img.set_from_icon_name("applications-internet", Gtk.IconSize.DIALOG)

            lbl = Gtk.Label(label=app.get("name", "App"))
            lbl.set_justify(Gtk.Justification.CENTER)
            lbl.set_max_width_chars(15)
            lbl.set_ellipsize(3)
            box.pack_start(img, False, False, 0)
            box.pack_start(lbl, False, False, 0)
            btn.add(box)
            grid.attach(btn, i % cols, i // cols, 1, 1)

        close_btn = Gtk.Button(label="✕")
        close_btn.set_name("close_btn")
        close_btn.set_halign(Gtk.Align.END)
        close_btn.set_valign(Gtk.Align.START)
        close_btn.connect("clicked", lambda w: Gtk.main_quit())
        self.overlay.add_overlay(close_btn)
        
        self.show_all()
        if self.first_btn: self.first_btn.grab_focus()
        play_sound("intro")
        GLib.timeout_add(100, self.start_animation)

    def start_animation(self):
        self.overlay.get_style_context().add_class("visible")
        GLib.timeout_add(500, self.enable_sounds)
        return False

    def enable_sounds(self):
        self.boot_finished = True
        return False

    def on_app_focus(self, widget, event):
        if self.boot_finished: play_sound("mouv")
        return False

if __name__ == "__main__":
    data = load_data()
    ensure_icons(data)
    Launcher(data)
    Gtk.main()
