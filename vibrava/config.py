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
class Config:
    elevenlabs: ElevenLabsConfig
    library_path: Path
    cache_path: Path
    output_path: Path
    pause_duration: float
    sfx_path: Path


def load(path: Path = Path("config.toml")) -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    el = raw.get("elevenlabs", {})
    api_key = os.environ.get("ELEVENLABS_API_KEY", el.get("api_key", ""))
    if not api_key:
        raise ValueError(
            "ElevenLabs API key is missing. Set ELEVENLABS_API_KEY env var or "
            "add api_key under [elevenlabs] in config.toml."
        )
    return Config(
        elevenlabs=ElevenLabsConfig(
            api_key=api_key,
            default_voice_id=el.get("default_voice_id", "21m00Tcm4TlvDq8ikWAM"),
            model_id=el.get("model_id", "eleven_multilingual_v2"),
        ),
        library_path=Path(raw.get("library", {}).get("path", "res")),
        cache_path=Path(raw.get("cache", {}).get("path", "cache")),
        output_path=Path(raw.get("output", {}).get("path", "output")),
        pause_duration=raw.get("compose", {}).get("pause_duration", 0.3),
        sfx_path=Path(raw.get("sfx", {}).get("path", "sfx")),
    )
