import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Sentence:
    id: str
    text: str
    sound_effect: str | None = None
    image: str | None = None  # relative path from library root; skips matching when set


@dataclass
class VideoScript:
    voice_id: str
    output_filename: str
    sentences: list[Sentence]
    caption_style: str = "line"          # "word" | "line" | "none"
    resolution: tuple[int, int] = field(default_factory=lambda: (1080, 1920))
    pause_duration: float | None = None  # overrides config if set
    music: str | None = None             # filename in res/music/, e.g. "lofi.mp3"
    music_volume: float = 0.15
    music_start: float = 0.0            # seconds into the video when music begins
    random_fallback: bool = False        # use a random image when no tag match found
    pause_jitter: float = 0.0            # when > 0, randomize gap to uniform(0.1, pause_jitter); max 1.0
    tts_provider: str = "elevenlabs"    # "elevenlabs" | "tiktok"


def parse(path: Path) -> VideoScript:
    with open(path) as f:
        data = json.load(f)

    if data.get("mode") != "cat_story":
        raise ValueError(f"Expected mode 'cat_story', got '{data.get('mode')}'")

    sentences = [
        Sentence(
            id=s["id"],
            text=s["text"],
            sound_effect=s.get("sound_effect"),
            image=s.get("image"),
        )
        for s in data["sentences"]
    ]

    res = data.get("resolution", [1080, 1920])
    return VideoScript(
        voice_id=data.get("voice_id", "21m00Tcm4TlvDq8ikWAM"),
        output_filename=data.get("output_filename", "output.mp4"),
        sentences=sentences,
        caption_style=data.get("caption_style", "line"),
        resolution=(res[0], res[1]),
        pause_duration=data.get("pause_duration"),
        music=data.get("music"),
        music_volume=data.get("music_volume", 0.15),
        music_start=data.get("music_start", 0.0),
        random_fallback=data.get("random_fallback", False),
        pause_jitter=min(data.get("pause_jitter", 0.0), 1.0),
        tts_provider=data.get("tts_provider", "elevenlabs"),
    )
