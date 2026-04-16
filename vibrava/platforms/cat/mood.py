import hashlib
import json
from pathlib import Path

from anthropic import Anthropic

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


def infer_moods(
    text: str,
    cache_dir: Path,
    client: Anthropic | None = None,
) -> list[str]:
    """Classify the emotional tone of *text* into 1–2 moods from MOODS.

    Results are cached on disk by md5(text) so repeat runs are free.
    Returns [] if the classifier call fails or no valid moods are parsed.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(f"moods|{text}".encode()).hexdigest()
    cache_file = cache_dir / f"{key}.json"

    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)

    if client is None:
        client = Anthropic()

    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=30,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
    )

    raw = next((b.text for b in resp.content if b.type == "text"), "")
    parsed = [m.strip().lower() for m in raw.split(",")]
    moods = [m for m in parsed if m in MOODS][:2]

    with open(cache_file, "w") as f:
        json.dump(moods, f)

    return moods


def mood_tags(moods: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for m in moods:
        for tag in MOOD_TAGS.get(m, []):
            if tag not in seen:
                seen.add(tag)
                result.append(tag)
    return result
