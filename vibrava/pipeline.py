import json
import os
import random
from datetime import datetime
from pathlib import Path

from vibrava.audio import elevenlabs as tts_elevenlabs
from vibrava.audio import tiktok as tts_tiktok
from vibrava.clips.index import ClipIndex
from vibrava.compose import editor
from vibrava.config import Config
from vibrava.platforms.cat import matcher, mood
from vibrava.platforms.cat.story_parser import parse as parse_video_script


def _resolve_mood_provider() -> str | None:
    """Pick a mood-inference provider, or None if no keys are set.

    ``MOOD_PROVIDER`` env var wins when set (must be "anthropic" or "gemini").
    Otherwise, auto-detect: prefer Anthropic if its key is present, fall back
    to Gemini if only its key is present.
    """
    explicit = os.environ.get("MOOD_PROVIDER", "").strip().lower()
    if explicit:
        if explicit not in ("anthropic", "gemini"):
            raise ValueError(
                f"MOOD_PROVIDER must be 'anthropic' or 'gemini', got {explicit!r}"
            )
        return explicit
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
    return None


def _run_video_script(script_path: Path, config: Config) -> None:
    script = parse_video_script(script_path)

    index = ClipIndex.load(config.library_path / "clip_index.json")
    cache_dir = config.cache_path / "tts"

    use_tiktok = script.tts_provider == "tiktok"
    provider_name = "tiktok" if use_tiktok else "elevenlabs"
    print(f"[tts]   provider={provider_name}")
    if use_tiktok:
        tiktok_session_id = os.environ.get("TIKTOK_SESSION_ID", "")
        if not tiktok_session_id:
            raise ValueError("TIKTOK_SESSION_ID env var is required for tts_provider=tiktok")
        voice_id = script.voice_id or os.environ.get("TIKTOK_VOICE_ID", "en_us_002")
    else:
        voice_id = script.voice_id or config.elevenlabs.default_voice_id

    pause = (
        script.pause_duration
        if script.pause_duration is not None
        else config.pause_duration
    )

    audio_map = {}
    image_map: dict[str, list[Path | None]] = {}
    sfx_map: dict[str, tuple[Path, float] | None] = {}

    mood_provider = _resolve_mood_provider()
    mood_enabled = mood_provider is not None
    mood_cache_dir = config.cache_path / "moods"
    if mood_enabled:
        model = mood.ANTHROPIC_MODEL if mood_provider == "anthropic" else mood.GEMINI_MODEL
        print(f"[mood]  enabled (provider={mood_provider}, model={model})")
    else:
        print("[mood]  disabled (no ANTHROPIC_API_KEY or GEMINI_API_KEY)")

    for sentence in script.sentences:
        preview = sentence.text[:60] + ("..." if len(sentence.text) > 60 else "")
        print(f"[tts]   {preview}  (pause={pause}s)")
        if use_tiktok:
            seg = tts_tiktok.generate(
                text=sentence.text,
                voice_id=voice_id,
                session_id=tiktok_session_id,
                cache_dir=cache_dir,
            )
        else:
            seg = tts_elevenlabs.generate(
                text=sentence.text,
                voice_id=voice_id,
                model_id=config.elevenlabs.model_id,
                api_key=config.elevenlabs.api_key,
                cache_dir=cache_dir,
            )
        audio_map[sentence.id] = seg

        if sentence.image:
            img_path = index.library_dir / sentence.image
            label = f"{Path(sentence.image).name} (pinned)"
        else:
            img_path = matcher.match(sentence.text, index)
            if img_path is None and mood_enabled:
                moods = mood.infer_moods(
                    sentence.text,
                    cache_dir=mood_cache_dir,
                    provider=mood_provider,
                )
                if moods:
                    print(f"[mood]  {', '.join(moods)}")
                    img_path = matcher.match_with_tags(
                        sentence.text, index, mood.mood_tags(moods)
                    )
            if img_path is None and script.random_fallback and index._clips:
                entry = random.choice(index._clips)
                img_path = index.resolve_path(entry)
                label = f"{img_path.name} (random fallback)"
            elif img_path:
                label = img_path.name
            else:
                label = "no match"

        img2_path = (index.library_dir / sentence.image2) if sentence.image2 else None
        image_map[sentence.id] = [img_path, img2_path]
        if img2_path:
            print(f"[match] {label} + {img2_path.name}")
        else:
            print(f"[match] {label}")

        if sentence.sound_effect:
            sfx_path = config.sfx_path / sentence.sound_effect
            if sfx_path.exists():
                sfx_map[sentence.id] = (sfx_path, sentence.sfx_offset)
            else:
                print(f"[warn]  sfx not found: {sfx_path}")
                sfx_map[sentence.id] = None
        else:
            sfx_map[sentence.id] = None

    ts = datetime.now().strftime("%m%d-%H%M")
    stem = Path(script.output_filename).stem
    output_path = config.output_path / f"{stem}_{ts}.mp4"

    music_path = None
    if script.music:
        music_path = config.library_path / "music" / script.music
        if not music_path.exists():
            print(f"[warn] music file not found: {music_path}")
            music_path = None

    print(f"[compose] → {output_path}")
    editor.build(
        sentences=script.sentences,
        audio_map=audio_map,
        image_map=image_map,
        sfx_map=sfx_map,
        output_path=output_path,
        resolution=script.resolution,
        pause_duration=pause,
        caption_style=script.caption_style,
        music_path=music_path,
        music_volume=script.music_volume,
        music_start=script.music_start,
        pause_jitter=script.pause_jitter,
    )
    print(f"[done] {output_path}")


def _resolve_video_script(script_path: Path, config: Config) -> None:
    with open(script_path) as f:
        raw = json.load(f)

    script = parse_video_script(script_path)
    index = ClipIndex.load(config.library_path / "clip_index.json")

    mood_provider = _resolve_mood_provider()
    mood_enabled = mood_provider is not None
    mood_cache_dir = config.cache_path / "moods"
    if mood_enabled:
        model = mood.ANTHROPIC_MODEL if mood_provider == "anthropic" else mood.GEMINI_MODEL
        print(f"[mood]  enabled (provider={mood_provider}, model={model})")
    else:
        print("[mood]  disabled (no ANTHROPIC_API_KEY or GEMINI_API_KEY)")

    resolved_images: list[str | None] = []
    for sentence in script.sentences:
        if sentence.image:
            image_val = sentence.image
            label = f"{Path(sentence.image).name} (pinned)"
        else:
            img_path = matcher.match(sentence.text, index)
            if img_path is None and mood_enabled:
                moods = mood.infer_moods(
                    sentence.text,
                    cache_dir=mood_cache_dir,
                    provider=mood_provider,
                )
                if moods:
                    print(f"[mood]  {', '.join(moods)}")
                    img_path = matcher.match_with_tags(
                        sentence.text, index, mood.mood_tags(moods)
                    )
            if img_path is None and script.random_fallback and index._clips:
                entry = random.choice(index._clips)
                img_path = index.resolve_path(entry)
                label = f"{img_path.name} (random fallback)"
            elif img_path:
                label = img_path.name
            else:
                label = "no match"
            image_val = str(img_path.relative_to(index.library_dir)) if img_path else None

        resolved_images.append(image_val)
        preview = sentence.text[:60] + ("..." if len(sentence.text) > 60 else "")
        print(f"[match] {preview} → {label}")

    for sentence_data, image_val in zip(raw["sentences"], resolved_images):
        sentence_data["image"] = image_val
        sentence_data.setdefault("image2", None)

    out_path = script_path.with_stem(script_path.stem + ".resolved")
    with open(out_path, "w") as f:
        json.dump(raw, f, indent=2)
    print(f"[done]  {out_path}")


def run(script_path: Path, config: Config) -> None:
    with open(script_path) as f:
        mode = json.load(f).get("mode")

    if mode == "cat_story":
        _run_video_script(script_path, config)
    else:
        raise ValueError(f"Unsupported mode: '{mode}'")


def resolve(script_path: Path, config: Config) -> None:
    with open(script_path) as f:
        mode = json.load(f).get("mode")

    if mode == "cat_story":
        _resolve_video_script(script_path, config)
    else:
        raise ValueError(f"Unsupported mode: '{mode}'")
