import base64
import hashlib
import json
from pathlib import Path

from elevenlabs.client import ElevenLabs

from vibrava.audio.tts import AudioSegment, WordTimestamp


def _chars_to_words(
    characters: list[str],
    starts: list[float],
    ends: list[float],
) -> list[WordTimestamp]:
    """Convert character-level ElevenLabs alignment to word-level timestamps."""
    words = []
    current_word = ""
    word_start = 0.0

    for char, start, end in zip(characters, starts, ends):
        if char in (" ", "\n"):
            if current_word:
                words.append(WordTimestamp(current_word, word_start, end))
                current_word = ""
        else:
            if not current_word:
                word_start = start
            current_word += char

    if current_word:
        words.append(WordTimestamp(current_word, word_start, ends[-1] if ends else 0.0))

    return words


def generate(
    text: str,
    voice_id: str,
    model_id: str,
    api_key: str,
    cache_dir: Path,
) -> AudioSegment:
    cache_key = hashlib.md5(f"{text}|{voice_id}|{model_id}".encode()).hexdigest()
    audio_path = cache_dir / f"{cache_key}.mp3"
    meta_path = cache_dir / f"{cache_key}.json"

    if audio_path.exists() and meta_path.exists():
        print(f"[tts cache hit] {text[:60]!r}")
        with open(meta_path) as f:
            meta = json.load(f)
        return AudioSegment(
            path=audio_path,
            duration=meta["duration"],
            words=[WordTimestamp(**w) for w in meta["words"]],
        )

    cache_dir.mkdir(parents=True, exist_ok=True)
    client = ElevenLabs(api_key=api_key)

    response = client.text_to_speech.convert_with_timestamps(
        voice_id=voice_id,
        text=text,
        model_id=model_id,
    )

    audio_bytes = base64.b64decode(response.audio_base_64)
    audio_path.write_bytes(audio_bytes)

    alignment = response.alignment
    words = _chars_to_words(
        alignment.characters,
        alignment.character_start_times_seconds,
        alignment.character_end_times_seconds,
    )

    duration = (
        alignment.character_end_times_seconds[-1]
        if alignment.character_end_times_seconds
        else 0.0
    )

    meta = {
        "duration": duration,
        "words": [{"word": w.word, "start": w.start, "end": w.end} for w in words],
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    return AudioSegment(path=audio_path, duration=duration, words=words)
