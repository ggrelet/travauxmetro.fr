#!/usr/bin/env python3
"""Regenerate index.html from local snapshot data and serve public/ on port 8080.

Usage: uv run python scripts/serve.py
Re-run whenever you change fetch.py to pick up template changes.
"""

import http.server
import json
import socketserver
import threading
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
PUBLIC = ROOT / "public"

import sys as _sys
if str(ROOT) not in _sys.path:
    _sys.path.insert(0, str(ROOT))


def regenerate():
    from scripts.fetch import generate_index, METRO_LINE_COLORS

    snapshot = json.loads((DATA / "snapshot.json").read_text())
    fetched_at = snapshot["fetched_at"]
    disruptions = snapshot["disruptions"]
    dis_by_id = {d["id"]: d for d in disruptions}
    by_line = {k: set(v) for k, v in json.loads((DATA / "by_line.json").read_text()).items()}

    dis_to_stops = {d["id"]: {} for d in disruptions}
    metro_lines = {}
    name_to_id = {}
    for name in METRO_LINE_COLORS:
        fid = f"fake_{name}"
        metro_lines[fid] = {"shortName": name}
        name_to_id[name] = fid

    for d in disruptions:
        for obj in d.get("impactedObjects", []):
            pt = obj.get("pt_object", {})
            if pt.get("embedded_type") == "line":
                code = pt.get("line", {}).get("code", "").upper().replace("BIS", "B")
                if code in name_to_id:
                    lid = name_to_id[code]
                    stops = [sp.get("stop_point", {}).get("name", "") for sp in obj.get("impacted_stops", [])]
                    dis_to_stops[d["id"]].setdefault(lid, []).extend(s for s in stops if s)

    html = generate_index(by_line, dis_by_id, dis_to_stops, metro_lines, fetched_at)
    (PUBLIC / "index.html").write_text(html)
    print("index.html regenerated")


import importlib
import sys

PORT = 8080


class ReloadHandler(http.server.SimpleHTTPRequestHandler):
    """Serve from public/; regenerate index.html on each request to / or /index.html."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            # Reload fetch module so template changes are picked up without restart
            for mod_name in list(sys.modules):
                if "scripts.fetch" in mod_name:
                    del sys.modules[mod_name]
            regenerate()
        super().do_GET()

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")


if __name__ == "__main__":
    import socket

    regenerate()
    local_ip = socket.gethostbyname(socket.gethostname())
    print(f"\nServing on http://localhost:{PORT}  •  http://{local_ip}:{PORT}")
    print("index.html auto-regenerates on each page load (picks up fetch.py changes)\n")
    with socketserver.TCPServer(("", PORT), ReloadHandler) as httpd:
        httpd.allow_reuse_address = True
        httpd.serve_forever()
