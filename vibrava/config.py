import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ElevenLabsConfig:
    api_key: str
    default_voice_id: str
    model_id: str


@dataclass
class GeminiConfig:
    api_key: str
    default_voice_name: str
    model: str


@dataclass
class Config:
    elevenlabs: ElevenLabsConfig
    gemini: GeminiConfig
    library_path: Path
    cache_path: Path
    output_path: Path
    sfx_path: Path
    on_complete: str | None
    tiktok_session_id: str


def load(path: Path = Path("config.toml")) -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    el = raw.get("elevenlabs", {})
    el_api_key = os.environ.get("ELEVENLABS_API_KEY", el.get("api_key", ""))

    gm = raw.get("gemini", {})
    gm_api_key = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", gm.get("api_key", "")))

    return Config(
        elevenlabs=ElevenLabsConfig(
            api_key=el_api_key,
            default_voice_id=el.get("default_voice_id", "21m00Tcm4TlvDq8ikWAM"),
            model_id=el.get("model_id", "eleven_multilingual_v2"),
        ),
        gemini=GeminiConfig(
            api_key=gm_api_key,
            default_voice_name=gm.get("default_voice_name", "Aoede"),
            model=gm.get("model", "gemini-2.5-flash-preview-tts"),
        ),
        library_path=Path(raw.get("library", {}).get("path", "res")),
        cache_path=Path(raw.get("cache", {}).get("path", "cache")),
        output_path=Path(raw.get("output", {}).get("path", "output")),
        sfx_path=Path(raw.get("sfx", {}).get("path", "sfx")),
        on_complete=raw.get("hooks", {}).get("on_complete", None),
        tiktok_session_id=os.environ.get(
            "TIKTOK_SESSION_ID", raw.get("tiktok", {}).get("session_id", "")
        ),
    )
