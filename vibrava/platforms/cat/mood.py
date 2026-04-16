import hashlib
import json
from pathlib import Path

MOODS = [
    "sad",
    "horror",
    "angry",
    "happy",
    "playful",
    "tense",
    "peaceful",
    "smug",
]

MOOD_TAGS: dict[str, list[str]] = {
    "sad": ["sad", "upset", "quiet", "staring", "alone", "floor"],
    "horror": ["scared", "dark", "hiding", "wide", "eyes", "alert", "intense"],
    "angry": ["angry", "grumpy", "hissing", "ears", "intense", "staring"],
    "happy": ["happy", "content", "purring", "cozy", "playful"],
    "playful": ["playful", "zoomies", "toy", "energetic", "jumping", "chase"],
    "tense": ["alert", "focused", "staring", "crouching", "sneaky", "hunting"],
    "peaceful": ["calm", "cozy", "sleeping", "relaxed", "loaf", "sunny"],
    "smug": ["smug", "sitting", "unbothered", "winning", "calm", "ignoring"],
}

_SYSTEM_PROMPT = (
    "You classify the emotional tone of a single sentence from a short story. "
    "Pick 1 or 2 moods from this list that best match the sentence's feeling: "
    f"{', '.join(MOODS)}. "
    "Return ONLY the mood names, comma-separated, lowercase. "
    "No punctuation, no explanation, no other words."
)

ANTHROPIC_MODEL = "claude-haiku-4-5"
GEMINI_MODEL = "gemini-2.5-flash-lite"


def infer_moods(
    text: str,
    cache_dir: Path,
    provider: str,
) -> list[str]:
    """Classify the emotional tone of *text* into 1–2 moods from MOODS.

    *provider* must be "anthropic" or "gemini". Results are cached on disk by
    md5(provider|text) so repeat runs are free and each provider gets its own
    cache namespace.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(f"moods|{provider}|{text}".encode()).hexdigest()
    cache_file = cache_dir / f"{key}.json"

    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)

    if provider == "anthropic":
        raw = _call_anthropic(text)
    elif provider == "gemini":
        raw = _call_gemini(text)
    else:
        raise ValueError(f"Unknown mood provider: {provider!r}")

    parsed = [m.strip().lower() for m in raw.split(",")]
    moods = [m for m in parsed if m in MOODS][:2]

    with open(cache_file, "w") as f:
        json.dump(moods, f)

    return moods


def _call_anthropic(text: str) -> str:
    from anthropic import Anthropic

    client = Anthropic()
    resp = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=30,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
    )
    return next((b.text for b in resp.content if b.type == "text"), "")


def _call_gemini(text: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client()
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=text,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            max_output_tokens=30,
        ),
    )
    return resp.text or ""


def mood_tags(moods: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for m in moods:
        for tag in MOOD_TAGS.get(m, []):
            if tag not in seen:
                seen.add(tag)
                result.append(tag)
    return result
