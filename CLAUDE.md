# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running Things

**Tagger UI:**
```bash
pip install -r tagger/requirements.txt
streamlit run tagger/app.py
```

**Video pipeline:**
```bash
pip install -e .
cp config.toml.example config.toml  # then fill in API keys
vibrava generate scripts/cat_story_example.json
```

## Architecture Docs

Read these before adding new modules — they define the intended structure:
- **`ARCHITECTURE.md`** — voiceover mode (meme clips) and comment_reveal mode (Reddit/YouTube threads)
- **`ARCHITECTURE_CAT.md`** — cat story mode and tagger UI

## Pipeline Flow (`cat_story` mode)

```
scripts/*.json
  → vibrava/cli.py
  → vibrava/pipeline.py          # branches on "mode"
  → platforms/cat/story_parser.py  # JSON → CatStoryScript
  → audio/tts.py                 # ElevenLabs → AudioSegment (cached)
  → platforms/cat/matcher.py     # sentence text → image Path via tag overlap
  → compose/editor.py            # MoviePy assembly → output/*.mp4
```

## Key Modules

**`vibrava/clips/index.py`** — `ClipIndex.load(path)` reads `clip_index.json`. `find_by_tags(tags)` scores clips by tag overlap and returns sorted results. `resolve_path(entry)` returns the absolute path to the image file.

**`vibrava/audio/tts.py`** — Calls `client.text_to_speech.convert_with_timestamps()`. Returns `AudioSegment` with `duration` and `words: list[WordTimestamp]`. Caches both the `.mp3` and a `.json` sidecar by `md5(text|voice_id|model_id)` in `cache/tts/`.

**`vibrava/platforms/cat/matcher.py`** — `extract_tags(text)` strips stop words from sentence text, then `match(text, index)` returns the best-matching image `Path` or `None`.

**`vibrava/compose/editor.py`** — `build()` assembles the final video. Each segment: blurred-background image frame + TTS audio + caption overlay, then `pause_duration` seconds of silence. Caption styles: `"line"` (full sentence shown), `"word"` (word-by-word highlight in yellow), `"none"`.

## Tagger (`tagger/app.py`)

Single-file Streamlit app. Key design points:
- State: `folder`, `images`, `index`, `current_idx`, `view` (`"gallery"` | `"detail"`) in `st.session_state`
- Folder persists across refresh via `st.query_params["folder"]`
- `clip_index.json` is written into whichever folder is open (not a fixed path)
- Folder picker uses `osascript` (macOS-only)
- Ctrl+J/K navigation via JS injected into parent document with `st.components.v1.html`

## clip_index.json Schema

```json
{
  "version": "1",
  "clips": [
    {
      "id": "filename_stem",
      "file": "filename.jpg",
      "tags": ["tag1", "tag2"],
      "type": "image",
      "duration_s": null,
      "loop": false,
      "notes": null
    }
  ]
}
```

`file` is relative to the folder containing `clip_index.json`. The tagger and pipeline both use this same file — `library_path` in `config.toml` must point to the tagged folder.

## Config

Copy `config.toml.example` → `config.toml`. API key can also be set via `ELEVENLABS_API_KEY` env var (takes precedence over the file).

## Not Yet Built

- `voiceover` and `comment_reveal` pipeline modes
- Reddit/YouTube scrapers (PRAW, YouTube Data API)
- Playwright comment section rendering
- Sound effects overlay
- GIPHY fallback
