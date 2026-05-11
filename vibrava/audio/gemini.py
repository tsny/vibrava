import base64
import hashlib
import json
import wave
from pathlib import Path

from google import genai
from google.genai import types

from vibrava.audio.tts import AudioSegment


_SAMPLE_RATE = 24000
_CHANNELS = 1
_SAMPLE_WIDTH = 2  # 16-bit PCM

_token_file_name = "gemini_tokens.json"


def _record_tokens(cache_dir: Path, input_tokens: int, output_tokens: int) -> None:
    token_file = cache_dir.parent / _token_file_name
    try:
        data = json.loads(token_file.read_text()) if token_file.exists() else {}
    except Exception:
        data = {}
    data["input_tokens"] = data.get("input_tokens", 0) + input_tokens
    data["output_tokens"] = data.get("output_tokens", 0) + output_tokens
    data["calls"] = data.get("calls", 0) + 1
    token_file.write_text(json.dumps(data))


def _pcm_to_wav(pcm_bytes: bytes, path: Path) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(_CHANNELS)
        wf.setsampwidth(_SAMPLE_WIDTH)
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes(pcm_bytes)


def generate(
    text: str,
    voice_name: str,
    model: str,
    api_key: str,
    cache_dir: Path,
) -> AudioSegment:
    cache_key = hashlib.md5(f"{text}|{voice_name}|{model}|gemini".encode()).hexdigest()
    audio_path = cache_dir / f"{cache_key}.wav"
    meta_path = cache_dir / f"{cache_key}.json"

    if audio_path.exists() and meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)
        return AudioSegment(path=audio_path, duration=meta["duration"], words=[])

    cache_dir.mkdir(parents=True, exist_ok=True)

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=text,
        config=types.GenerateContentConfig(
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
            response_modalities=["AUDIO"],
        ),
    )

    usage = response.usage_metadata
    print(f"[gemini tts] tokens — input: {usage.prompt_token_count}, output: {usage.candidates_token_count}, total: {usage.total_token_count}")
    _record_tokens(cache_dir, usage.prompt_token_count or 0, usage.candidates_token_count or 0)

    candidate = response.candidates[0] if response.candidates else None
    if not candidate or not candidate.content or not candidate.content.parts:
        print(f"[gemini tts] bad response: {response}")
        raise RuntimeError(f"Gemini TTS returned no audio. finish_reason={getattr(candidate, 'finish_reason', None)}")

    raw = candidate.content.parts[0].inline_data.data
    pcm_bytes = raw if isinstance(raw, bytes) else base64.b64decode(raw + "=" * (-len(raw) % 4))
    _pcm_to_wav(pcm_bytes, audio_path)

    n_frames = len(pcm_bytes) // (_CHANNELS * _SAMPLE_WIDTH)
    duration = n_frames / _SAMPLE_RATE

    with open(meta_path, "w") as f:
        json.dump({"duration": duration, "words": []}, f)

    return AudioSegment(path=audio_path, duration=duration, words=[])
