import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Sentence:
    id: str
    text: str
    sound_effect: str | None = None
    sfx_offset: float = 0.0       # seconds from start of sentence when sfx plays
    sfx_duration: float | None = None  # seconds to play; None = play to end
    image: str | None = None   # relative path from library root; skips matching when set
    image2: str | None = None  # shown at the halfway point of the sentence
    voice_id: str | None = None  # overrides top-level voice_id when set
    pause_duration: float | None = None  # overrides script/config pause when set
    overlay_image: str | None = None   # per-sentence overlay image (relative to library root)
    overlay_opacity: float = 1.0       # 0.0–1.0; alpha ramps up to this over the first half of the sentence
    overlay_size: float = 1/3          # fraction of video width


@dataclass
class VideoScript:
    voice_id: str | None
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
    overlay_image: str | None = None    # path relative to library root; composited bottom-left over entire video
    overlay_image_size: float = 1/6    # fraction of video width (0.0–1.0)
    caption_font_size: int | None = None  # px at original resolution; None = auto (height // 26)
    caption_y_pct: float = 80.0           # vertical position as % of frame height (0 = top, 100 = bottom)


def _next_sentence_id(raw_sentences: list[dict]) -> str:
    used = {str(s.get("id", "")) for s in raw_sentences}
    numeric_ids = [
        int(sentence_id[1:])
        for sentence_id in used
        if sentence_id.startswith("s") and sentence_id[1:].isdigit()
    ]
    next_num = max(numeric_ids, default=0) + 1
    while f"s{next_num}" in used:
        next_num += 1
    return f"s{next_num}"


def _ensure_sentence_ids(raw_sentences: list[dict]):
    for sentence in raw_sentences:
        if not sentence.get("id"):
            sentence["id"] = _next_sentence_id(raw_sentences)


def parse(path: Path) -> VideoScript:
    with open(path) as f:
        data = json.load(f)

    if data.get("mode") != "cat_story":
        raise ValueError(f"Expected mode 'cat_story', got '{data.get('mode')}'")

    _ensure_sentence_ids(data["sentences"])
    sentences = [
        Sentence(
            id=s["id"],
            text=s["text"],
            sound_effect=s.get("sound_effect"),
            sfx_offset=float(s.get("sfx_offset", 0.0)),
            sfx_duration=float(s["sfx_duration"]) if s.get("sfx_duration") is not None else None,
            image=s.get("image"),
            image2=s.get("image2"),
            voice_id=s.get("voice_id") or None,
            pause_duration=float(s["pause_duration"]) if s.get("pause_duration") is not None else None,
            overlay_image=s.get("overlay_image"),
            overlay_opacity=float(s.get("overlay_opacity", 1.0)),
            overlay_size=float(s.get("overlay_size", 1/3)),
        )
        for s in data["sentences"]
    ]

    res = data.get("resolution", [1080, 1920])
    return VideoScript(
        voice_id=data.get("voice_id") or None,
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
        overlay_image=data.get("overlay_image"),
        overlay_image_size=float(data.get("overlay_image_size", 1/6)),
        caption_font_size=data.get("caption_font_size") or None,
        caption_y_pct=float(data.get("caption_y_pct", 80.0)),
    )
