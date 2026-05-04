# vibrava

Short-form video generator for TikTok/Reels-style cat story content. Assembles narrated slideshows from tagged image libraries using ElevenLabs TTS and MoviePy.

## Setup

```bash
pip install -e .
cp config.toml.example config.toml
```

Fill in `config.toml` with your API keys, or set them as environment variables:

| Env var | Purpose |
|---|---|
| `ELEVENLABS_API_KEY` | Required — TTS audio |
| `ANTHROPIC_API_KEY` | Optional — mood-based tag expansion (Claude Haiku) |
| `GEMINI_API_KEY` | Optional — mood-based tag expansion (Gemini Flash Lite) |

If both `ANTHROPIC_API_KEY` and `GEMINI_API_KEY` are set, Anthropic is used. Override with `MOOD_PROVIDER=gemini`.

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
  "voice_id": "EXAVITQu4vr4xnSDxMaL",
  "caption_style": "word",
  "music": "spooky.mp3",
  "output_filename": "out.mp4",
  "resolution": [1080, 1920],
  "sentences": [
    { "id": "s1", "text": "Once upon a time..." }
  ]
}
```

`caption_style` options: `"word"` (word-by-word highlight), `"line"` (full sentence), `"none"`.

## Script Editor

Browse and edit scripts in a Streamlit UI. For each sentence you can edit the text and pick an image directly from the library.

```bash
streamlit run editor/app.py
```

Reads `library.path` from `config.toml` automatically. Opens scripts from `scripts/`. Saves the `"image"` field on each sentence in the same format as `vibrava resolve`.

## Resolve Images (CLI)

Run image-matching on a script without generating a video. Writes `scripts/foo.resolved.json` with an `"image"` field on every sentence:

```bash
vibrava resolve scripts/cat_story_example.json
```

## Image Library & Tagger

The pipeline matches sentences to images by tag overlap. Images must be tagged using the tagger UI before use.

```bash
pip install -r tagger/requirements.txt
streamlit run tagger/app.py
```

Set `library.path` in `config.toml` to point to a folder containing a `clip_index.json` (written by the tagger).

## Pipeline

```
scripts/*.json
  → vibrava/cli.py
  → vibrava/pipeline.py
  → platforms/cat/story_parser.py   # JSON → CatStoryScript
  → audio/tts.py                    # ElevenLabs → AudioSegment (cached)
  → platforms/cat/matcher.py        # sentence text → image Path via tag overlap
  → compose/editor.py               # MoviePy assembly → output/*.mp4
```
