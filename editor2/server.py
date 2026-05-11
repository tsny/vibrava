#!/usr/bin/env python3
"""Minimal HTTP server for the Vibrava script editor frontend."""
import base64
import hashlib
import io
import json
import logging
import mimetypes
import os
import sys
import threading
import time
import tomllib
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("vibrava")

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
SCRIPTS_DIR = ROOT.parent / "scripts"
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}


def _http_err_msg(exc: Exception) -> str:
    """Return a readable message from an HTTP API error, extracting JSON body fields where possible."""
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)

    # ElevenLabs ApiError: .body is already deserialized
    raw = getattr(exc, "body", None)

    # requests / httpx style: .response.json() or .response.text
    if raw is None:
        resp = getattr(exc, "response", None)
        if resp is not None:
            status = status or getattr(resp, "status_code", None)
            try:
                raw = resp.json()
            except Exception:
                raw = getattr(resp, "text", None)

    # Try to parse string bodies as JSON
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            pass

    if isinstance(raw, dict):
        detail = (
            raw.get("detail")
            or raw.get("message")
            or raw.get("error")
            or raw.get("msg")
            or raw.get("description")
        )
        body_str = str(detail) if detail else str(raw)
    elif raw is not None:
        body_str = str(raw)
    else:
        body_str = str(exc)

    return f"HTTP {status}: {body_str}" if status else body_str


def load_config() -> dict:
    cfg = ROOT.parent / "config.toml"
    if cfg.exists():
        with open(cfg, "rb") as f:
            return tomllib.load(f)
    return {}


CONFIG = load_config()
LIBRARY_PATH = Path(CONFIG.get("library", {}).get("path", "res")).resolve()

_token_lock = threading.Lock()


def _record_gemini_tokens(input_tokens: int, output_tokens: int) -> None:
    with _token_lock:
        try:
            data = json.loads(_GEMINI_TOKEN_FILE.read_text()) if _GEMINI_TOKEN_FILE.exists() else {}
        except Exception:
            data = {}
        data["input_tokens"] = data.get("input_tokens", 0) + input_tokens
        data["output_tokens"] = data.get("output_tokens", 0) + output_tokens
        data["calls"] = data.get("calls", 0) + 1
        _GEMINI_TOKEN_FILE.write_text(json.dumps(data))
SFX_PATH = Path(CONFIG.get("sfx", {}).get("path", "sfx")).resolve()
CACHE_PATH = Path(CONFIG.get("cache", {}).get("path", "cache")).resolve()
_GEMINI_TOKEN_FILE = CACHE_PATH / "gemini_tokens.json"

_EL_CFG = CONFIG.get("elevenlabs", {})
EL_API_KEY = os.environ.get("ELEVENLABS_API_KEY") or _EL_CFG.get("api_key", "")
EL_MODEL_ID = _EL_CFG.get("model_id", "eleven_multilingual_v2")
EL_DEFAULT_VOICE = _EL_CFG.get("default_voice_id", "")

_GM_CFG = CONFIG.get("gemini", {})
GM_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or _GM_CFG.get("api_key", "")
GM_MODEL = _GM_CFG.get("model", "gemini-2.5-flash-preview-tts")
GM_DEFAULT_VOICE = _GM_CFG.get("default_voice_name", "Aoede")

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int) -> list[str]:
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        test = " ".join(current + [word])
        if dummy.textbbox((0, 0), test, font=font)[2] > max_width and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def render_preview_frame(
    image_path: Path | None,
    text: str,
    caption_style: str,
    overlay_path: Path | None,
    resolution: tuple[int, int],
    overlay_size_frac: float = 1/6,
    preview_width: int = 360,
    caption_font_size: int | None = None,
    caption_y_pct: float = 80.0,
) -> bytes:
    orig_w, orig_h = resolution
    scale = preview_width / orig_w
    width = preview_width
    height = int(orig_h * scale)

    bg = Image.new("RGB", (width, height), (0, 0, 0))
    if image_path and image_path.exists():
        try:
            img = Image.open(image_path).convert("RGB")
            ratio = min(width / img.width, height / img.height) * 0.90
            fw, fh = int(img.width * ratio), int(img.height * ratio)
            img = img.resize((fw, fh), Image.LANCZOS)
            bg.paste(img, ((width - fw) // 2, (height - fh) // 2))
        except Exception:
            pass

    if caption_style != "none" and text.strip():
        if caption_font_size is not None:
            font_size = max(8, int(caption_font_size * scale))
        else:
            font_size = max(18, height // 26)
        font = _load_font(font_size)
        lines = _wrap_text(text, font, int(width * 0.88))
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        line_h = font_size + 8
        y = int(height * caption_y_pct / 100) - (len(lines) * line_h) // 2
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            x = (width - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=font, fill="white", stroke_width=3, stroke_fill="black")
            y += line_h
        bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    if overlay_path and overlay_path.exists():
        try:
            ov = Image.open(overlay_path).convert("RGBA")
            max_dim = max(1, int(width * overlay_size_frac))
            ov_scale = min(max_dim / ov.width, max_dim / ov.height, 1.0)
            ov = ov.resize((int(ov.width * ov_scale), int(ov.height * ov_scale)), Image.LANCZOS)
            pad = max(8, int(20 * scale))
            bg_rgba = bg.convert("RGBA")
            bg_rgba.paste(ov, (pad, height - ov.height - pad), ov)
            bg = bg_rgba.convert("RGB")
        except Exception:
            pass

    buf = io.BytesIO()
    bg.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        t0 = time.monotonic()
        log.info("GET  %s", self.path)
        try:
            self._do_GET()
        except Exception:
            log.error("Unhandled exception in GET %s\n%s", self.path, traceback.format_exc())
            self._err(500, "internal server error")
        else:
            log.debug("GET  %s → %.0fms", self.path, (time.monotonic() - t0) * 1000)

    def _do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._file(ROOT / "index.html", "text/html")
        elif path in ("/app.js", "/style.css"):
            mime = "application/javascript" if path.endswith(".js") else "text/css"
            self._file(ROOT / path[1:], mime)
        elif path == "/api/config":
            self._json({"library_path": str(LIBRARY_PATH), "sfx_path": str(SFX_PATH)})
        elif path == "/api/scripts":
            names = sorted(f.name for f in SCRIPTS_DIR.glob("*.json")) if SCRIPTS_DIR.exists() else []
            self._json(names)
        elif path == "/api/preview":
            name = qs.get("name", [None])[0]
            idx = int(qs.get("idx", ["0"])[0])
            if not name:
                return self._err(400, "missing name")
            p = SCRIPTS_DIR / name
            if not p.exists():
                return self._err(404, "not found")
            with open(p) as f:
                data = json.load(f)
            sentences = data.get("sentences", [])
            if not (0 <= idx < len(sentences)):
                return self._err(400, "idx out of range")
            s = sentences[idx]
            res = data.get("resolution", [1080, 1920])
            images = s.get("images") or ([s["image"]] if s.get("image") else [])
            image_file = images[0] if images else None
            overlay_file = data.get("overlay_image")
            cap_font_str = qs.get("capfont", [None])[0]
            cap_y_str = qs.get("capy", [None])[0]
            caption_font_size = int(cap_font_str) if cap_font_str else None
            caption_y_pct = float(cap_y_str) if cap_y_str else float(data.get("caption_y_pct", 80))
            jpeg = render_preview_frame(
                image_path=(LIBRARY_PATH / image_file) if image_file else None,
                text=s.get("text", ""),
                caption_style=data.get("caption_style", "chunk"),
                overlay_path=(LIBRARY_PATH / overlay_file) if overlay_file else None,
                overlay_size_frac=float(data.get("overlay_image_size", 1/6)),
                resolution=(res[0], res[1]),
                caption_font_size=caption_font_size,
                caption_y_pct=caption_y_pct,
            )
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", len(jpeg))
            self.end_headers()
            self.wfile.write(jpeg)
        elif path == "/api/script":
            name = qs.get("name", [None])[0]
            if not name:
                return self._err(400, "missing name")
            p = SCRIPTS_DIR / name
            if not p.exists():
                return self._err(404, "not found")
            with open(p) as f:
                self._json(json.load(f))
        elif path == "/api/clips":
            idx = LIBRARY_PATH / "clip_index.json"
            if not idx.exists():
                return self._json([])
            with open(idx) as f:
                clips = json.load(f).get("clips", [])
            seen: set[str] = set()
            unique = []
            for c in clips:
                cid = c.get("id", c.get("file", ""))
                if cid not in seen:
                    seen.add(cid)
                    unique.append(c)
            self._json(unique)
        elif path == "/api/sfx":
            files = sorted(f.name for f in SFX_PATH.iterdir() if f.suffix.lower() in AUDIO_EXTENSIONS) if SFX_PATH.exists() else []
            self._json(files)
        elif path == "/api/gemini-tokens":
            if _GEMINI_TOKEN_FILE.exists():
                with open(_GEMINI_TOKEN_FILE) as f:
                    self._json(json.load(f))
            else:
                self._json({"input_tokens": 0, "output_tokens": 0, "calls": 0})
        elif path.startswith("/lib/"):
            self._static(LIBRARY_PATH, unquote(path[5:]))
        elif path.startswith("/sfx/"):
            self._static(SFX_PATH, unquote(path[5:]))
        else:
            self._err(404, "not found")

    def do_POST(self):
        t0 = time.monotonic()
        log.info("POST %s", self.path)
        try:
            self._do_POST()
        except Exception:
            log.error("Unhandled exception in POST %s\n%s", self.path, traceback.format_exc())
            self._err(500, "internal server error")
        else:
            log.debug("POST %s → %.0fms", self.path, (time.monotonic() - t0) * 1000)

    def _do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        if path == "/api/tts":
            text = body.get("text", "").strip()
            provider = body.get("provider", "elevenlabs")
            if not text:
                return self._err(400, "missing text")

            cache_dir = CACHE_PATH / "tts"

            if provider == "tiktok":
                voice_id = body.get("voice_id", "").strip() or "en_us_002"
                session_id = CONFIG.get("tiktok", {}).get("session_id", "") or os.environ.get("TIKTOK_SESSION_ID", "")
                if not session_id:
                    return self._err(503, "tiktok session_id not configured")
                cache_key = hashlib.md5(f"{text}|{voice_id}|tiktok".encode()).hexdigest()
                audio_path = cache_dir / f"{cache_key}.mp3"
                if not audio_path.exists():
                    log.info("TTS  tiktok generating voice=%s text=%r", voice_id, text[:60])
                    try:
                        from tiktok_voice.tts import tts as _tiktok_tts
                        cache_dir.mkdir(parents=True, exist_ok=True)
                        _tiktok_tts(session_id, voice_id, text, str(audio_path))
                    except Exception as e:
                        msg = _http_err_msg(e)
                        log.error("TTS  tiktok failed: %s", msg)
                        return self._err(500, msg)
                else:
                    log.info("TTS  tiktok cache hit voice=%s text=%r", voice_id, text[:60])
            elif provider == "gemini":
                voice_name = body.get("voice_id", "").strip() or GM_DEFAULT_VOICE
                if not GM_API_KEY:
                    return self._err(503, "GEMINI_API_KEY not configured")
                cache_key = hashlib.md5(f"{text}|{voice_name}|{GM_MODEL}|gemini".encode()).hexdigest()
                audio_path = cache_dir / f"{cache_key}.wav"
                if not audio_path.exists():
                    log.info("TTS  gemini generating voice=%s text=%r", voice_name, text[:60])
                    try:
                        import wave
                        from google import genai as _genai
                        from google.genai import types as _gtypes
                        client = _genai.Client(api_key=GM_API_KEY)
                        response = client.models.generate_content(
                            model=GM_MODEL,
                            contents=text,
                            config=_gtypes.GenerateContentConfig(
                                speech_config=_gtypes.SpeechConfig(
                                    voice_config=_gtypes.VoiceConfig(
                                        prebuilt_voice_config=_gtypes.PrebuiltVoiceConfig(voice_name=voice_name)
                                    )
                                ),
                                response_modalities=["AUDIO"],
                            ),
                        )
                        usage = response.usage_metadata
                        log.info("TTS  gemini tokens — input: %s, output: %s, total: %s", usage.prompt_token_count, usage.candidates_token_count, usage.total_token_count)
                        _record_gemini_tokens(usage.prompt_token_count or 0, usage.candidates_token_count or 0)
                        candidate = response.candidates[0] if response.candidates else None
                        if not candidate or not candidate.content or not candidate.content.parts:
                            raise RuntimeError(f"Gemini TTS returned no audio. finish_reason={getattr(candidate, 'finish_reason', None)}, text={text!r}")
                        raw = candidate.content.parts[0].inline_data.data
                        pcm_bytes = raw if isinstance(raw, bytes) else base64.b64decode(raw + "=" * (-len(raw) % 4))
                        cache_dir.mkdir(parents=True, exist_ok=True)
                        with wave.open(str(audio_path), "wb") as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(24000)
                            wf.writeframes(pcm_bytes)
                    except Exception as e:
                        msg = _http_err_msg(e)
                        log.error("TTS  gemini failed: %s", msg)
                        return self._err(500, msg)
                else:
                    log.info("TTS  gemini cache hit voice=%s text=%r", voice_name, text[:60])
            else:
                voice_id = body.get("voice_id", "").strip() or EL_DEFAULT_VOICE
                if not EL_API_KEY:
                    return self._err(503, "ELEVENLABS_API_KEY not configured")
                cache_key = hashlib.md5(f"{text}|{voice_id}|{EL_MODEL_ID}".encode()).hexdigest()
                audio_path = cache_dir / f"{cache_key}.mp3"
                if not audio_path.exists():
                    log.info("TTS  elevenlabs generating voice=%s text=%r", voice_id, text[:60])
                    try:
                        from elevenlabs.client import ElevenLabs
                        client = ElevenLabs(api_key=EL_API_KEY)
                        response = client.text_to_speech.convert_with_timestamps(
                            voice_id=voice_id,
                            text=text,
                            model_id=EL_MODEL_ID,
                        )
                        audio_bytes = base64.b64decode(response.audio_base_64)
                        cache_dir.mkdir(parents=True, exist_ok=True)
                        audio_path.write_bytes(audio_bytes)
                    except Exception as e:
                        msg = _http_err_msg(e)
                        log.error("TTS  elevenlabs failed: %s", msg)
                        return self._err(500, msg)
                else:
                    log.info("TTS  elevenlabs cache hit voice=%s text=%r", voice_id, text[:60])

            pitch_shift = float(body.get("pitch_shift", 0.0))
            speed = float(body.get("speed", 1.0))
            if pitch_shift != 0.0 or speed != 1.0:
                from vibrava.audio.fx import apply as fx_apply
                from vibrava.audio.tts import AudioSegment
                seg = fx_apply(
                    AudioSegment(path=audio_path, duration=0.0, words=[]),
                    pitch_shift=pitch_shift,
                    speed=speed,
                    cache_dir=CACHE_PATH / "fx",
                )
                audio_path = seg.path

            content_type = "audio/wav" if audio_path.suffix == ".wav" else "audio/mpeg"

            audio_data = audio_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(audio_data))
            self.end_headers()
            self.wfile.write(audio_data)
        elif path == "/api/script":
            name = qs.get("name", [None])[0]
            if not name:
                return self._err(400, "missing name")
            SCRIPTS_DIR.mkdir(exist_ok=True)
            with open(SCRIPTS_DIR / name, "w") as f:
                json.dump(body, f, indent=2)
            self._json({"ok": True})
        elif path == "/api/scripts":
            name = body.get("name", "")
            if not name:
                return self._err(400, "missing name")
            if not name.endswith(".json"):
                name += ".json"
            p = SCRIPTS_DIR / name
            if p.exists():
                return self._err(409, "already exists")
            SCRIPTS_DIR.mkdir(exist_ok=True)
            with open(p, "w") as f:
                json.dump({"mode": "cat_story", "voice_id": "nPczCjzI2devNBz1zQrb", "sentences": []}, f, indent=2)
            self._json({"name": name})
        else:
            self._err(404, "not found")

    def _static(self, base: Path, rel: str):
        target = (base / rel).resolve()
        if not str(target).startswith(str(base)):
            return self._err(403, "forbidden")
        self._file(target, mimetypes.guess_type(str(target))[0] or "application/octet-stream", cache=True)

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
        level = logging.ERROR if code >= 500 else logging.WARNING
        log.log(level, "%d  %s", code, msg)
        body = json.dumps({"error": msg}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # suppress default httpd noise; we log manually above


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7654
    server = ThreadingHTTPServer(("localhost", port), Handler)
    print(f"Vibrava editor → http://localhost:{port}")
    server.serve_forever()
