"""Run the finished GAIA CascadeLens app on this computer. Needs only Python 3.

usage: python serve.py [--port 8765] [--no-browser]

Everything is served from the app folder. The browser is told to refuse any request off this computer, so the app works with no internet.
Range support is what makes the measurement inspector work: it reads single pixels out of large rasters.
"""
import argparse
import functools
import http.server
import os
import pathlib
import re
import shutil
import webbrowser

APP = pathlib.Path(__file__).resolve().parent / "app"
if not APP.exists():  # Started from the project folder, where the build is in frontend/dist
    APP = APP.parent.parent / "frontend" / "dist"
CSP = "default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'wasm-unsafe-eval'"


class Handler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # Reuses one connection for many tiles instead of opening a new one for each
    disable_nagle_algorithm = True  # Sends small tiles at once, instead of waiting to fill a packet

    # Windows' registry can map these wrongly, and browsers refuse scripts with the wrong type
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
                      ".json": "application/json", ".geojson": "application/json", ".tif": "image/tiff", ".png": "image/png", ".html": "text/html"}

    def cache_rule(self):
        path = self.path.split("?")[0]
        if path.startswith("/assets/"):
            return "public, max-age=31536000, immutable"  # Their names change whenever their content does
        if path.startswith("/data/") and not path.endswith(".json"):
            return "public, max-age=86400"
        return "no-cache"  # The page and manifests: a new version shows on a normal reload

    def end_headers(self):
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", self.cache_rule())
        super().end_headers()

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.translate_path(self.path)
        match = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
        if not match or not os.path.isfile(path):
            return super().do_GET()
        size = os.path.getsize(path)
        start = int(match[1])
        end = min(int(match[2]) if match[2] else size - 1, size - 1)
        if start >= size or end < start:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        length = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            shutil.copyfileobj(_Limited(f, length), self.wfile)


class _Limited:
    """Reads at most `left` bytes, so a range response never overruns its Content-Length."""

    def __init__(self, f, left):
        self.f, self.left = f, left

    def read(self, n):
        chunk = self.f.read(min(n, self.left))
        self.left -= len(chunk)
        return chunk


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64  # A map opens many connections at once

    def handle_error(self, request, client_address):
        pass  # Browsers drop connections when a tile is no longer needed. That is normal, not a fault


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    if not (APP / "index.html").exists():
        raise SystemExit(f"Cannot find the app at {APP}. Keep serve.py next to the app folder.")
    handler = functools.partial(Handler, directory=str(APP))
    for port in range(a.port, a.port + 20):
        try:
            server = Server(("127.0.0.1", port), handler)
            break
        except OSError:
            continue
    else:
        raise SystemExit("No free port found.")
    url = f"http://localhost:{port}/"
    print(f"GAIA CascadeLens is running.\n\n    {url}\n\nIt should open in your default browser. To use Brave or another browser, paste that address into it.\n"
          "Do not open index.html directly: browsers block that.\nKeep this window open while you use the app. Close it, or press Ctrl+C, to stop.")
    if not a.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
