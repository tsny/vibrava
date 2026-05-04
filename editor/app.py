import json
import tomllib
from pathlib import Path

import streamlit as st
from PIL import Image

st.set_page_config(layout="wide", page_title="Vibrava Script Editor")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
THUMB_SMALL = 80
THUMB_PICK = 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config_library() -> str:
    cfg = Path("config.toml")
    if cfg.exists():
        with open(cfg, "rb") as f:
            data = tomllib.load(f)
        lib = data.get("library", {}).get("path")
        if lib:
            return lib
    return "res"


def make_thumbnail(img_path: Path, size: int) -> Image.Image:
    img = Image.open(img_path).convert("RGB")
    img.thumbnail((size, size))
    square = Image.new("RGB", (size, size), (24, 24, 24))
    square.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
    return square


def load_clip_index(library_path: str) -> list[dict]:
    idx = Path(library_path) / "clip_index.json"
    if not idx.exists():
        return []
    with open(idx) as f:
        return json.load(f).get("clips", [])


def sentence_image_path(sentence: dict) -> Path | None:
    img = sentence.get("image")
    if not img:
        return None
    p = Path(st.session_state.library_path) / img
    return p if p.exists() and p.suffix.lower() in IMAGE_EXTENSIONS else None


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def init_state():
    defaults: dict = {
        "script_path": None,
        "script_data": None,
        "library_path": load_config_library(),
        "clip_index": [],
        "selected_sentence": None,
        "picker_search": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

if not st.session_state.clip_index:
    st.session_state.clip_index = load_clip_index(st.session_state.library_path)


# ---------------------------------------------------------------------------
# Script I/O
# ---------------------------------------------------------------------------

def open_script(path: Path):
    with open(path) as f:
        st.session_state.script_data = json.load(f)
    st.session_state.script_path = str(path)
    st.session_state.selected_sentence = None


def save_script():
    path = st.session_state.script_path
    data = st.session_state.script_data
    if path and data is not None:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("Script Editor")

    # Library
    lib_val = st.text_input("Library path", value=st.session_state.library_path)
    if lib_val != st.session_state.library_path:
        st.session_state.library_path = lib_val
        st.session_state.clip_index = load_clip_index(lib_val)
        st.rerun()

    st.divider()

    # Script picker
    scripts_dir = Path("scripts")
    script_files = sorted(
        f for f in scripts_dir.glob("*.json") if scripts_dir.exists()
    )

    if script_files:
        names = [f.name for f in script_files]
        current = Path(st.session_state.script_path).name if st.session_state.script_path else names[0]
        idx = names.index(current) if current in names else 0
        chosen = st.selectbox("Script", names, index=idx)
        if st.button("Open", use_container_width=True):
            open_script(scripts_dir / chosen)
            st.rerun()
    else:
        custom = st.text_input("Script path", placeholder="scripts/my_script.json")
        if custom and st.button("Open", use_container_width=True):
            p = Path(custom)
            if p.exists():
                open_script(p)
                st.rerun()
            else:
                st.error("File not found.")

    st.divider()

    # Metadata (only shown when a script is open)
    if st.session_state.script_data:
        d = st.session_state.script_data
        st.markdown("**Settings**")

        d["voice_id"] = st.text_input("Voice ID", value=d.get("voice_id") or "")
        d["caption_style"] = st.selectbox(
            "Caption style",
            ["word", "line", "none"],
            index=["word", "line", "none"].index(d.get("caption_style", "line")),
        )
        d["output_filename"] = st.text_input(
            "Output filename", value=d.get("output_filename") or "output.mp4"
        )
        d["music"] = st.text_input("Music file", value=d.get("music") or "") or None

        st.divider()
        if st.button("💾 Save", use_container_width=True, type="primary"):
            save_script()
            st.success("Saved.")


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------

if not st.session_state.script_data:
    st.info("Open a script using the sidebar.")
    st.stop()


# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

data = st.session_state.script_data
sentences: list[dict] = data.setdefault("sentences", [])

fname = Path(st.session_state.script_path).name
st.markdown(f"### {fname}")
st.caption(f"{len(sentences)} sentences · mode: {data.get('mode', '?')}")

left_col, right_col = st.columns([5, 6])

# ── Left: sentence list ────────────────────────────────────────────────────

with left_col:
    header_cols = st.columns([1, 6, 1, 1])
    header_cols[1].markdown("**Text**")
    header_cols[2].markdown("**Img**")

    for i, sentence in enumerate(sentences):
        is_selected = st.session_state.selected_sentence == i
        img_path = sentence_image_path(sentence)

        border_color = "#4A90E2" if is_selected else "#333"
        st.markdown(
            f"<div style='border:1px solid {border_color}; border-radius:6px; padding:4px 8px; margin-bottom:6px'>",
            unsafe_allow_html=True,
        )

        row = st.columns([1, 6, 1, 1])

        with row[0]:
            st.markdown(
                f"<p style='margin:28px 0 0 0; color:#888; font-size:0.85em'>{i + 1}</p>",
                unsafe_allow_html=True,
            )

        with row[1]:
            new_text = st.text_area(
                "text",
                value=sentence.get("text", ""),
                key=f"text_{i}",
                height=68,
                label_visibility="collapsed",
            )
            if new_text != sentence.get("text", ""):
                sentences[i]["text"] = new_text

        with row[2]:
            if img_path:
                st.image(make_thumbnail(img_path, THUMB_SMALL), use_container_width=True)
            else:
                st.markdown(
                    f"<div style='width:{THUMB_SMALL}px;height:{THUMB_SMALL}px;"
                    "background:#2a2a2a;border-radius:4px;border:1px dashed #555'></div>",
                    unsafe_allow_html=True,
                )

        with row[3]:
            if st.button("🖼", key=f"pick_{i}", help="Pick image", use_container_width=True):
                st.session_state.selected_sentence = None if is_selected else i
                st.rerun()
            if st.button("✕", key=f"del_{i}", help="Remove sentence", use_container_width=True):
                sentences.pop(i)
                if st.session_state.selected_sentence == i:
                    st.session_state.selected_sentence = None
                elif (st.session_state.selected_sentence or 0) > i:
                    st.session_state.selected_sentence -= 1
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    if st.button("＋ Add sentence", use_container_width=True):
        sentences.append({
            "id": f"s{len(sentences) + 1}",
            "text": "",
            "sound_effect": None,
        })
        st.session_state.selected_sentence = len(sentences) - 1
        st.rerun()

# ── Right: image picker ────────────────────────────────────────────────────

with right_col:
    sel = st.session_state.selected_sentence
    if sel is None or sel >= len(sentences):
        st.info("Click 🖼 next to a sentence to pick its image.")
        st.stop()

    sentence = sentences[sel]
    preview = sentence.get("text", "")[:60]
    st.markdown(f"**Sentence {sel + 1}** — _{preview}_")

    img_path = sentence_image_path(sentence)
    if img_path:
        img_col, clear_col = st.columns([3, 1])
        with img_col:
            st.image(Image.open(img_path), width=400)
            st.caption(sentence.get("image", ""))
        with clear_col:
            if st.button("✕ Clear", key="clear_img"):
                sentences[sel]["image"] = None
                st.rerun()
    else:
        st.caption("No image assigned.")

    st.divider()

    search = st.text_input(
        "Filter clips",
        value=st.session_state.picker_search,
        placeholder="tag or filename…",
        key="picker_search",
    )
    terms = [t.strip().lower() for t in search.split() if t.strip()]

    clips = st.session_state.clip_index
    if terms:
        def clip_matches(clip: dict) -> bool:
            haystack = " ".join(clip.get("tags", [])).lower() + " " + clip.get("file", "").lower()
            return all(t in haystack for t in terms)
        clips = [c for c in clips if clip_matches(c)]

    lib = Path(st.session_state.library_path)
    current_image = sentence.get("image")

    COLS = 5
    if not clips:
        st.caption("No clips match." if terms else "No clips in library.")
    else:
        for row_start in range(0, len(clips), COLS):
            cols = st.columns(COLS)
            for col_idx, clip in enumerate(clips[row_start:row_start + COLS]):
                with cols[col_idx]:
                    img_file = lib / clip["file"]
                    if img_file.exists() and img_file.suffix.lower() in IMAGE_EXTENSIONS:
                        st.image(make_thumbnail(img_file, THUMB_PICK), use_container_width=True)

                    is_current = current_image == clip["file"]
                    label = f"✓ {clip['file']}" if is_current else clip["file"]
                    btn_type = "primary" if is_current else "secondary"
                    if st.button(
                        label,
                        key=f"assign_{sel}_{clip['id']}",
                        use_container_width=True,
                        type=btn_type,
                    ):
                        sentences[sel]["image"] = clip["file"]
                        st.rerun()
