# TODO

* Multi-voice script?
* Sound effects at start or end
* Animations between sentences 
*

---

# Script Editor Plan

Build as a **Textual TUI** (not Streamlit). Streamlit's rerun model fights text editing — widget sync issues, no real keyboard nav. Textual maps naturally to the use case.

## Rationale

- Tagger stays in Streamlit (image-heavy, visual)
- Script editor is fundamentally a text editor with a list — Textual wins here
- Same Python stack, no context switch
- Runs in the terminal alongside `vibrava generate`
- Live streaming output in a split pane

## Entry point

Add a `make scripts` target (or `vibrava edit`) that launches the TUI.

## Features

- File list view — browse `scripts/*.json`, open/new/delete
- Edit view:
  - Metadata fields: voice_id, caption_style, tts_provider, music, music_volume, music_start, pause_duration, pause_jitter, random_fallback, output_filename
  - Sentence list with keyboard-driven add / remove / reorder
  - IDs auto-assigned as s1, s2, ... on save
- Save (ctrl+s)
- Save & Generate — runs `vibrava generate` in a split pane with live output
- Dirty state indicator

## Textual specifics

- `ListView` for the file browser and sentence list
- `Input` / `TextArea` widgets for fields and sentence text
- `Log` or `RichLog` widget for generate output panel
- `DataTable` is an option for sentence list but ListView is simpler
- Run generate via `asyncio.create_subprocess_exec` so output streams live without blocking the UI

## Files to create

- `tagger/scripts_tui.py` — main Textual app
- Add `scripts` target to `Makefile`
