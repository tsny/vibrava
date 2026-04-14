import json
from pathlib import Path

from vibrava.audio.tts import generate as tts_generate
from vibrava.clips.index import ClipIndex
from vibrava.compose import editor
from vibrava.config import Config
from vibrava.platforms.cat import matcher
from vibrava.platforms.cat.story_parser import parse as parse_cat_story


def _run_cat_story(script_path: Path, config: Config) -> None:
    script = parse_cat_story(script_path)

    index = ClipIndex.load(config.library_path / "clip_index.json")
    cache_dir = config.cache_path / "tts"
    voice_id = script.voice_id or config.elevenlabs.default_voice_id

    audio_map = {}
    image_map = {}

    for sentence in script.sentences:
        print(f"[tts]   {sentence.text[:60]}{'...' if len(sentence.text) > 60 else ''}")
        seg = tts_generate(
            text=sentence.text,
            voice_id=voice_id,
            model_id=config.elevenlabs.model_id,
            api_key=config.elevenlabs.api_key,
            cache_dir=cache_dir,
        )
        audio_map[sentence.id] = seg

        img_path = matcher.match(sentence.text, index)
        image_map[sentence.id] = img_path
        label = img_path.name if img_path else "no match"
        print(f"[match] {label}")

    pause = (
        script.pause_duration
        if script.pause_duration is not None
        else config.pause_duration
    )
    output_path = config.output_path / script.output_filename

    print(f"[compose] → {output_path}")
    editor.build(
        sentences=script.sentences,
        audio_map=audio_map,
        image_map=image_map,
        output_path=output_path,
        resolution=script.resolution,
        pause_duration=pause,
        caption_style=script.caption_style,
    )
    print(f"[done] {output_path}")


def run(script_path: Path, config: Config) -> None:
    with open(script_path) as f:
        mode = json.load(f).get("mode")

    if mode == "cat_story":
        _run_cat_story(script_path, config)
    else:
        raise ValueError(f"Unsupported mode: '{mode}'")
