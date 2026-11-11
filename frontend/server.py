#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lightweight Backend Server for Anchor Settings Web Panel.

Serves the frontend static files securely (bound to 127.0.0.1 by default)
and provides the REST API endpoints:
- GET  /api/anchor/settings
- POST /api/anchor/settings

Usage:
    python frontend/server.py [--port 8765] [--host 127.0.0.1]
"""
import sys
import json
import argparse
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

# Setup imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anchor.db.connection import get_all_settings, set_setting

FRONTEND_DIR = Path(__file__).resolve().parent


class AnchorSettingsHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/api/anchor/settings":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            settings = get_all_settings()
            self.wfile.write(json.dumps(settings, ensure_ascii=False).encode("utf-8"))
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/anchor/settings":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body)
                for k, v in data.items():
                    set_setting(k, v)

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def run(host: str = "127.0.0.1", port: int = 8765):
    server_address = (host, port)
    httpd = HTTPServer(server_address, AnchorSettingsHandler)
    print(f"Anchor Settings Web UI securely running at http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Anchor Settings HTTP Server")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
    args = parser.parse_args()
    run(host=args.host, port=args.port)
