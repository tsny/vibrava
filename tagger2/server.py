#!/usr/bin/env python3
"""Minimal HTTP server for the Vibrava tagger frontend."""
import io
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm"}
ALL_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

THUMB_SIZE = 160

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _load_font(size: int):
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def make_thumbnail(file_path: Path, size: int = THUMB_SIZE) -> bytes:
    square = Image.new("RGB", (size, size), (24, 24, 24))
    if file_path.suffix.lower() in VIDEO_EXTENSIONS:
        draw = ImageDraw.Draw(square)
        font = _load_font(size // 4)
        draw.text((size // 2, size // 2), "▶", fill=(180, 180, 180), anchor="mm", font=font)
    else:
        try:
            img = Image.open(file_path).convert("RGB")
            img.thumbnail((size, size))
            offset = ((size - img.width) // 2, (size - img.height) // 2)
            square.paste(img, offset)
        except Exception:
            pass
    buf = io.BytesIO()
    square.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def validate_path(folder: str, rel: str) -> Path | None:
    """Return absolute path only if it's inside folder."""
    base = Path(folder).resolve()
    target = (base / rel).resolve()
    if str(target).startswith(str(base) + "/") or target == base:
        return target
    return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._file(ROOT / "index.html", "text/html")
        elif path in ("/app.js", "/style.css"):
            mime = "application/javascript" if path.endswith(".js") else "text/css"
            self._file(ROOT / path[1:], mime)

        elif path == "/api/files":
            folder = qs.get("folder", [None])[0]
            if not folder:
                return self._err(400, "missing folder")
            p = Path(folder)
            if not p.exists() or not p.is_dir():
                return self._err(400, "not a directory")
            files = sorted(
                f.name for f in p.iterdir()
                if f.suffix.lower() in ALL_EXTENSIONS
            )
            self._json({"files": files, "folder": str(p.resolve())})

        elif path == "/api/index":
            folder = qs.get("folder", [None])[0]
            if not folder:
                return self._err(400, "missing folder")
            idx = Path(folder) / "clip_index.json"
            if idx.exists():
                with open(idx) as f:
                    self._json(json.load(f))
            else:
                self._json({"version": "1", "clips": []})

        elif path == "/media":
            folder = qs.get("folder", [None])[0]
            rel = unquote(qs.get("file", [None])[0] or "")
            if not folder or not rel:
                return self._err(400, "missing params")
            target = validate_path(folder, rel)
            if not target:
                return self._err(403, "forbidden")
            mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            self._file(target, mime, cache=True)

        elif path == "/thumb":
            folder = qs.get("folder", [None])[0]
            rel = unquote(qs.get("file", [None])[0] or "")
            size = int(qs.get("size", [str(THUMB_SIZE)])[0])
            if not folder or not rel:
                return self._err(400, "missing params")
            target = validate_path(folder, rel)
            if not target:
                return self._err(403, "forbidden")
            if not target.exists():
                return self._err(404, "not found")
            data = make_thumbnail(target, size)
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", len(data))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(data)

        else:
            self._err(404, "not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        if path == "/api/index":
            folder = qs.get("folder", [None])[0]
            if not folder:
                return self._err(400, "missing folder")
            p = Path(folder)
            if not p.exists() or not p.is_dir():
                return self._err(400, "not a directory")
            with open(p / "clip_index.json", "w") as f:
                json.dump(body, f, indent=2)
            self._json({"ok": True})
        else:
            self._err(404, "not found")

    def _file(self, p: Path, mime: str, cache: bool = False):
        if not p.exists():
            return self._err(404, "not found")
        data = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", len(data))
        if cache:
            self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, code: int, msg: str):
        body = json.dumps({"error": msg}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7655
    server = ThreadingHTTPServer(("localhost", port), Handler)
    print(f"Vibrava tagger → http://localhost:{port}")
    server.serve_forever()
