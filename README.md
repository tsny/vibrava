# vibrava

Short-form video generator for TikTok/Reels-style cat story content. Assembles narrated slideshows from tagged image libraries using ElevenLabs, Gemini, or TikTok TTS and MoviePy.

## Setup

**With uv (recommended):**

```bash
uv sync
cp config.toml.example config.toml
```

**With pip:**

```bash
pip install -e .
cp config.toml.example config.toml
```

Fill in `config.toml` with your API keys, or set them as environment variables:

| Env var | Purpose |
|---|---|
| `ELEVENLABS_API_KEY` | ElevenLabs TTS |
| `GEMINI_API_KEY` | Gemini TTS and/or mood-based tag expansion |
| `TIKTOK_SESSION_ID` | TikTok TTS |
| `ANTHROPIC_API_KEY` | Optional — mood-based tag expansion (Claude Haiku) |

If both `ANTHROPIC_API_KEY` and `GEMINI_API_KEY` are set, Anthropic is used for tag expansion. Override with `MOOD_PROVIDER=gemini`.

## Generate a Video

```bash
vibrava generate scripts/cat_story_example.json
```

Output lands in the `output/` folder. TTS responses are cached in `cache/tts/` by content hash.

## Script Format

Scripts are JSON files in `scripts/`. Example (`cat_story` mode):

```json
{
  "mode": "cat_story",
  "tts_provider": "elevenlabs",
  "voice_id": "EXAVITQu4vr4xnSDxMaL",
  "caption_style": "chunk",
  "caption_y_pct": 80,
  "music": "spooky.mp3",
  "music_volume": 0.15,
  "output_filename": "out.mp4",
  "resolution": [1080, 1920],
  "speed": 1.0,
  "pitch_shift": 0,
  "sfx_volume": 1.0,
  "sentences": [
    {
      "id": "s1",
      "text": "Once upon a time...",
      "images": ["cat_sitting.jpg", "cat_window.jpg"],
      "sound_effect": "whoosh.mp3",
      "sfx_offset": 0.0,
      "sfx_duration": null,
      "sfx_volume": 0.8,
      "pause_duration": 0.5,
      "voice_id": null,
      "speed": null,
      "pitch_shift": null
    }
  ]
}
```

Each sentence can have multiple `images` — they are shown in sequence during playback. Per-sentence fields override the top-level defaults when set (non-null).

`tts_provider` options: `"elevenlabs"` (default), `"gemini"`, `"tiktok"`.

`caption_style` options:

| Value | Description |
|---|---|
| `"chunk"` | 5–8 words at a time, punctuation-aware (default) |
| `"flash"` | One word at a time |
| `"word"` | Word-by-word highlight in yellow |
| `"line"` | Full sentence shown at once |
| `"none"` | No captions |

## Encoder

The pipeline auto-selects the best available H.264 encoder at render time: `h264_nvenc` (NVIDIA) → `h264_videotoolbox` (Apple) → `libx264` (CPU fallback). No configuration needed.

## Script Editor

A web UI for editing scripts and assigning images sentence by sentence.

```bash
python editor2/server.py
```

Opens at `http://localhost:7654`.

Features:
- Edit sentence text, voice, TTS provider, speed, pitch, pause, sound effects
- Assign multiple images per sentence from the tagged library
- Filter the image picker by tag, filename, or file type (jpg/png/gif/mp4)
- Preview a sentence frame (image + caption overlay) without rendering the full video
- TTS preview — play back synthesized audio for any sentence directly
- **TTS Cache browser** (🔊 button) — list, play, and delete cached audio files
- ElevenLabs character usage and Gemini token usage shown in the sidebar
- Compact / spacious density toggle

Reads `library.path` from `config.toml`. Scripts are loaded from and saved to `scripts/`.

## Resolve Images (CLI)

Run image-matching on a script without generating a video. Writes `scripts/foo.resolved.json` with an `images` field on every sentence:

```bash
vibrava resolve scripts/cat_story_example.json
```

## Image Library & Tagger

The pipeline matches sentences to images by tag overlap. Images must be tagged using the tagger UI before use.

```bash
python tagger2/server.py
```

Opens at `http://localhost:7655`. Set `library.path` in `config.toml` to point to a folder containing a `clip_index.json` (written by the tagger).

## Pipeline

```
scripts/*.json
  → vibrava/cli.py
  → vibrava/pipeline.py
  → platforms/cat/story_parser.py   # JSON → CatStoryScript
  → audio/tts.py                    # TTS → AudioSegment (cached)
  → platforms/cat/matcher.py        # sentence text → image Path via tag overlap
  → compose/editor.py               # MoviePy assembly → output/*.mp4
```
