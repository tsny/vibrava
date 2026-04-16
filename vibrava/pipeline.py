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
    image_map = {}

    mood_enabled = bool(os.environ.get("ANTHROPIC_API_KEY"))
    mood_cache_dir = config.cache_path / "moods"
    print(
        f"[mood]  {'enabled (claude-haiku-4-5)' if mood_enabled else 'disabled (no ANTHROPIC_API_KEY)'}"
    )

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

        if mood_enabled:
            moods = mood.infer_moods(sentence.text, cache_dir=mood_cache_dir)
            if moods:
                print(f"[mood]  {', '.join(moods)}")
                img_path = matcher.match_with_tags(
                    sentence.text, index, mood.mood_tags(moods)
                )
            else:
                img_path = matcher.match(sentence.text, index)
        else:
            img_path = matcher.match(sentence.text, index)
        if img_path is None and script.random_fallback and index._clips:
            entry = random.choice(index._clips)
            img_path = index.resolve_path(entry)
            label = f"{img_path.name} (random fallback)"
        elif img_path:
            label = img_path.name
        else:
            label = "no match"
        image_map[sentence.id] = img_path
        print(f"[match] {label}")

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


def run(script_path: Path, config: Config) -> None:
    with open(script_path) as f:
        mode = json.load(f).get("mode")

    if mode == "cat_story":
        _run_video_script(script_path, config)
    else:
        raise ValueError(f"Unsupported mode: '{mode}'")
