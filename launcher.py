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
        if tag.lower() != "link":
            return
        attr = dict(attrs)
        rel = attr.get("rel", "").lower()
        href = attr.get("href")
        if not href:
            return

        if "apple-touch-icon" in rel:
            self.icons.append((0, href))
        elif "icon" in rel:
            self.icons.append((1, href))

def find_icon_url(page_url):
    try:
        req = urllib.request.Request(
            page_url,
            headers={"User-Agent": "Mozilla/5.0 TVLauncher"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read(200_000).decode("utf-8", errors="ignore")

        parser = IconParser()
        parser.feed(html)

        if parser.icons:
            parser.icons.sort(key=lambda x: x[0])
            icon_href = parser.icons[0][1]
            return urllib.parse.urljoin(page_url, icon_href)
    except Exception:
        pass

    # fallback favicon.ico
    p = urllib.parse.urlparse(page_url)
    return f"{p.scheme}://{p.netloc}/favicon.ico"

def download_icon(icon_url, out_path):
    try:
        req = urllib.request.Request(
            icon_url,
            headers={"User-Agent": "Mozilla/5.0 TVLauncher"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read(300_000)

        if not data:
            return False

        with open(out_path, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False

def ensure_icons(data):
    icons_dir = os.path.join(BASE_DIR, "icons")
    os.makedirs(icons_dir, exist_ok=True)
    changed = False

    for app in data["apps"]:
        if app.get("icon"):
            continue
        if app.get("type") != "url":
            continue

        app_id = app["id"]
        icon_path = f"icons/{app_id}.png"
        full_path = os.path.join(BASE_DIR, icon_path)

        if os.path.exists(full_path):
            app["icon"] = icon_path
            changed = True
            continue

        print(f"[ICON] récupération pour {app_id}")

        icon_url = find_icon_url(app["url"])
        if download_icon(icon_url, full_path):
            app["icon"] = icon_path
            changed = True

    if changed:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

class Launcher(Gtk.Window):
    def __init__(self, data):
        super().__init__(title=data["ui"].get("title", "Launcher"))
        self.set_decorated(False)
        self.fullscreen()
        self.connect("destroy", Gtk.main_quit)


# --- AJOUT CSS ---
        css_provider = Gtk.CssProvider()
        css = b"""
        #close_btn { background: transparent; color: rgba(255,255,255,0.3); border: none; font-size: 20px; font-weight: bold; margin: 15px; }
        #close_btn:hover { color: #ff5555; background: rgba(255,255,255,0.1); border-radius: 50px; }
        """
        css_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        outer_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer_vbox.set_halign(Gtk.Align.CENTER)
        outer_vbox.set_valign(Gtk.Align.CENTER)

        outer_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        outer_hbox.set_halign(Gtk.Align.CENTER)
        outer_hbox.set_valign(Gtk.Align.CENTER)


        overlay = Gtk.Overlay()
        self.add(overlay)
        overlay.add(outer_vbox)

        grid = Gtk.Grid()
        grid.set_row_spacing(30)
        grid.set_column_spacing(30)
        grid.set_halign(Gtk.Align.CENTER)
        grid.set_valign(Gtk.Align.CENTER)

        outer_hbox.pack_start(grid, False, False, 0)
        outer_vbox.pack_start(outer_hbox, True, True, 0)

        cols = data["ui"].get("columns", 4)
        tile_px = data["ui"].get("tile_px", 200)

        for i, app in enumerate(data["apps"]):
            btn = Gtk.Button()
            btn.set_size_request(tile_px, tile_px)
            btn.connect("clicked", lambda _b, a=app: launch_app(a))

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            box.set_halign(Gtk.Align.CENTER)
            box.set_valign(Gtk.Align.CENTER)

            from gi.repository import GdkPixbuf

            # taille fixe en hauteur
            tile_height_cm = 5.0
            pixels_par_cm = 20  # ajuster selon ta TV
            tile_height_px = int(tile_height_cm * pixels_par_cm)

            img = Gtk.Image()
            icon_path = os.path.join(BASE_DIR, app.get("icon", ""))
            if os.path.exists(icon_path):
                # charger l'image avec GdkPixbuf pour redimension proportionnel
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(icon_path)
                # calcul largeur proportionnelle
                w = pixbuf.get_width()
                h = pixbuf.get_height()
                scale = tile_height_px / h
                new_w = max(1, int(w * scale))
                new_h = tile_height_px
                # redimensionner
                pixbuf = pixbuf.scale_simple(new_w, new_h, GdkPixbuf.InterpType.BILINEAR)
                img.set_from_pixbuf(pixbuf)
            else:
                # icône fallback
                img.set_from_icon_name("applications-internet", Gtk.IconSize.DIALOG)


            lbl = Gtk.Label(label=app.get("name", "App"))
            lbl.set_justify(Gtk.Justification.CENTER)

            box.pack_start(img, False, False, 0)
            box.pack_start(lbl, False, False, 0)
            btn.add(box)

            r = i // cols
            c = i % cols
            grid.attach(btn, c, r, 1, 1)

        # --- NOUVEAU BOUTON (Overlay) ---
        close_btn = Gtk.Button(label="✕")
        close_btn.set_name("close_btn") # Lien avec le CSS
        close_btn.set_halign(Gtk.Align.END)   # Droite
        close_btn.set_valign(Gtk.Align.START) # Haut
        close_btn.connect("clicked", lambda w: Gtk.main_quit())
        overlay.add_overlay(close_btn) # On le pose par dessus

        self.show_all()

if __name__ == "__main__":
    data = load_data()
    ensure_icons(data)
    Launcher(data)
    Gtk.main()
