import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from vibrava.audio.tts import AudioSegment


def _audio_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def generate(
    text: str,
    voice_id: str,
    session_id: str,
    cache_dir: Path,
) -> AudioSegment:
    cache_key = hashlib.md5(f"{text}|{voice_id}|tiktok".encode()).hexdigest()
    audio_path = cache_dir / f"{cache_key}.mp3"
    meta_path = cache_dir / f"{cache_key}.json"

    if audio_path.exists() and meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)
        return AudioSegment(path=audio_path, duration=meta["duration"], words=[])

    cache_dir.mkdir(parents=True, exist_ok=True)

    voice_path = os.environ.get("TIKTOK_VOICE_PATH", "/home/tsny/dev/tiktok-voice")
    if voice_path not in sys.path:
        sys.path.insert(0, voice_path)
    from main import tts as _tiktok_tts  # noqa: PLC0415

    _tiktok_tts(session_id, voice_id, text, str(audio_path))
    duration = _audio_duration(audio_path)

    with open(meta_path, "w") as f:
        json.dump({"duration": duration, "words": []}, f)

    return AudioSegment(path=audio_path, duration=duration, words=[])
