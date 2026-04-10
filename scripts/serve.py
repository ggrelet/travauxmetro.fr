#!/usr/bin/env python3
"""Regenerate the site from data/snapshot.json and serve public/ on port 8080.

Usage: uv run python scripts/serve.py
Re-run whenever you change fetch.py to pick up template changes.
"""

import http.server
import socket
import socketserver
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PUBLIC = ROOT / "public"
SNAPSHOT = ROOT / "data" / "snapshot.json"

PORT = 8080


def regenerate() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "fetch.py"), "--fixture", str(SNAPSHOT), "--force"],
        check=True,
    )


class ReloadHandler(http.server.SimpleHTTPRequestHandler):
    """Serve from public/; regenerate on each request to / or /index.html."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            regenerate()
        super().do_GET()

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")


if __name__ == "__main__":
    regenerate()
    local_ip = socket.gethostbyname(socket.gethostname())
    print(f"\nServing on http://localhost:{PORT}  •  http://{local_ip}:{PORT}")
    print("index.html auto-regenerates on each page load (picks up fetch.py changes)\n")
    with socketserver.TCPServer(("", PORT), ReloadHandler) as httpd:
        httpd.allow_reuse_address = True
        httpd.serve_forever()
