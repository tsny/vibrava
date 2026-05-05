import json
import tomllib
from collections import Counter
from pathlib import Path

import imageio
import streamlit as st
from PIL import Image

st.set_page_config(layout="wide", page_title="Vibrava Script Editor")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}

TYPE_FILTER_OPTIONS = ["all", "jpg/png", "gif", "mp4"]
TYPE_FILTER_EXTS: dict[str, set[str]] = {
    "jpg/png": {".jpg", ".jpeg", ".png", ".webp"},
    "gif": {".gif"},
    "mp4": {".mp4", ".mov", ".webm"},
}
THUMB_SMALL = 80
THUMB_PICK = 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    cfg = Path("config.toml")
    if cfg.exists():
        with open(cfg, "rb") as f:
            return tomllib.load(f)
    return {}


def load_config_library() -> str:
    lib = _load_config().get("library", {}).get("path")
    return lib or "res"


def load_config_sfx() -> str:
    path = _load_config().get("sfx", {}).get("path")
    return path or "sfx"


def load_sfx_files(sfx_path: str) -> list[str]:
    p = Path(sfx_path)
    if not p.exists():
        return []
    return sorted(f.name for f in p.iterdir() if f.suffix.lower() in AUDIO_EXTENSIONS)


@st.cache_data
def make_video_thumbnail(video_path: Path, size: int) -> Image.Image | None:
    try:
        reader = imageio.get_reader(str(video_path))
        frame = reader.get_data(0)
        reader.close()
        img = Image.fromarray(frame).convert("RGB")
        img.thumbnail((size, size))
        square = Image.new("RGB", (size, size), (24, 24, 24))
        square.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
        return square
    except Exception:
        return None


@st.cache_data
def make_thumbnail(img_path: Path, size: int) -> Image.Image:
    img = Image.open(img_path).convert("RGB")
    img.thumbnail((size, size))
    square = Image.new("RGB", (size, size), (24, 24, 24))
    square.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
    return square


@st.cache_data
def open_image(img_path: Path) -> Image.Image:
    return Image.open(img_path).convert("RGB")


def load_clip_index(library_path: str) -> list[dict]:
    idx = Path(library_path) / "clip_index.json"
    if not idx.exists():
        return []
    with open(idx) as f:
        clips = json.load(f).get("clips", [])
    seen: set[str] = set()
    unique = []
    for c in clips:
        cid = c.get("id", c.get("file", ""))
        if cid not in seen:
            seen.add(cid)
            unique.append(c)
    return unique


def sentence_image_path(sentence: dict, key: str = "image") -> Path | None:
    img = sentence.get(key)
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
        "script_version": 0,
        "library_path": load_config_library(),
        "clip_index": [],
        "sfx_path": load_config_sfx(),
        "sfx_files": [],
        "selected_sentence": None,
        "picker_slot": "image",  # "image" | "image2"
        "picker_search": "",
        "picker_type_filter": "all",
        "picker_page": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

if not st.session_state.clip_index:
    st.session_state.clip_index = load_clip_index(st.session_state.library_path)

if not st.session_state.sfx_files:
    st.session_state.sfx_files = load_sfx_files(st.session_state.sfx_path)


# ---------------------------------------------------------------------------
# Script I/O
# ---------------------------------------------------------------------------

def open_script(path: Path):
    with open(path) as f:
        st.session_state.script_data = json.load(f)
    st.session_state.script_path = str(path)
    st.session_state.script_version += 1
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

    sfx_val = st.text_input("Sound effects path", value=st.session_state.sfx_path)
    if sfx_val != st.session_state.sfx_path:
        st.session_state.sfx_path = sfx_val
        st.session_state.sfx_files = load_sfx_files(sfx_val)
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

    new_name = st.text_input("New script name", placeholder="my_script")
    if st.button("＋ New script", use_container_width=True):
        if new_name:
            scripts_dir.mkdir(exist_ok=True)
            stem = new_name if new_name.endswith(".json") else f"{new_name}.json"
            new_path = scripts_dir / stem
            if new_path.exists():
                st.error(f"{stem} already exists.")
            else:
                blank = {"mode": "cat_story", "sentences": []}
                with open(new_path, "w") as f:
                    json.dump(blank, f, indent=2)
                open_script(new_path)
                st.rerun()
        else:
            st.error("Enter a script name.")

    st.divider()

    # Metadata (only shown when a script is open)
    if st.session_state.script_data:
        d = st.session_state.script_data
        st.markdown("**Settings**")

        providers = ["elevenlabs", "tiktok"]
        cur_provider = d.get("tts_provider", "elevenlabs")
        d["tts_provider"] = st.selectbox(
            "TTS provider",
            providers,
            index=providers.index(cur_provider) if cur_provider in providers else 0,
        )
        voice_hint = "e.g. en_us_002" if d["tts_provider"] == "tiktok" else "e.g. 21m00Tcm4TlvDq8ikWAM"
        d["voice_id"] = st.text_input("Voice ID", value=d.get("voice_id") or "", placeholder=voice_hint) or None
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
    header_cols = st.columns([1, 6, 1, 1, 1])
    header_cols[1].markdown("**Text**")
    header_cols[2].markdown("**Img 1**")
    header_cols[3].markdown("**Img 2**")

    sv = st.session_state.script_version
    for i, sentence in enumerate(sentences):
        is_selected = st.session_state.selected_sentence == i
        img_path = sentence_image_path(sentence, "image")
        img2_path = sentence_image_path(sentence, "image2")

        border_color = "#4A90E2" if is_selected else "#333"
        st.markdown(
            f"<div style='border:1px solid {border_color}; border-radius:6px; padding:4px 8px; margin-bottom:6px'>",
            unsafe_allow_html=True,
        )

        row = st.columns([1, 6, 1, 1, 1])

        with row[0]:
            st.markdown(
                f"<p style='margin:28px 0 0 0; color:#888; font-size:0.85em'>{i + 1}</p>",
                unsafe_allow_html=True,
            )

        with row[1]:
            new_text = st.text_area(
                "text",
                value=sentence.get("text", ""),
                key=f"text_{sv}_{i}",
                height=68,
                label_visibility="collapsed",
            )
            if new_text != sentence.get("text", ""):
                sentences[i]["text"] = new_text
            sfx_files = st.session_state.sfx_files
            sfx_options = ["(none)"] + sfx_files
            current_sfx = sentence.get("sound_effect") or "(none)"
            sfx_idx = sfx_options.index(current_sfx) if current_sfx in sfx_options else 0
            chosen_sfx = st.selectbox(
                "sound_effect",
                sfx_options,
                index=sfx_idx,
                key=f"sfx_{sv}_{i}",
                label_visibility="collapsed",
            )
            new_sfx_val = None if chosen_sfx == "(none)" else chosen_sfx
            if new_sfx_val != sentence.get("sound_effect"):
                sentences[i]["sound_effect"] = new_sfx_val
            if new_sfx_val:
                new_offset = st.number_input(
                    "sfx_offset",
                    value=float(sentence.get("sfx_offset") or 0.0),
                    min_value=0.0,
                    step=0.1,
                    format="%.1f",
                    key=f"sfx_offset_{sv}_{i}",
                    label_visibility="collapsed",
                    help="Seconds from sentence start when sfx plays",
                )
                if new_offset != sentence.get("sfx_offset", 0.0):
                    sentences[i]["sfx_offset"] = new_offset

        for slot, col, path in [("image", row[2], img_path), ("image2", row[3], img2_path)]:
            with col:
                if path:
                    st.image(make_thumbnail(path, THUMB_SMALL), use_container_width=True)
                else:
                    st.markdown(
                        f"<div style='width:{THUMB_SMALL}px;height:{THUMB_SMALL}px;"
                        "background:#2a2a2a;border-radius:4px;border:1px dashed #555'></div>",
                        unsafe_allow_html=True,
                    )
                active = is_selected and st.session_state.picker_slot == slot
                btn_type = "primary" if active else "secondary"
                label = "1️⃣" if slot == "image" else "2️⃣"
                if st.button(label, key=f"pick_{slot}_{sv}_{i}", use_container_width=True, type=btn_type):
                    if active:
                        st.session_state.selected_sentence = None
                    else:
                        st.session_state.selected_sentence = i
                        st.session_state.picker_slot = slot
                    st.rerun()

        with row[4]:
            st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
            if st.button("✕", key=f"del_{sv}_{i}", help="Remove sentence", use_container_width=True):
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
    slot = st.session_state.picker_slot  # "image" | "image2"
    preview = sentence.get("text", "")[:60]
    slot_label = "Image 1" if slot == "image" else "Image 2 (½ way)"
    st.markdown(f"**Sentence {sel + 1}** — _{preview}_ · picking **{slot_label}**")

    # Show both current images side by side
    img_path = sentence_image_path(sentence, "image")
    img2_path = sentence_image_path(sentence, "image2")
    thumb_col1, thumb_col2 = st.columns(2)
    for col, key, path, lbl in [
        (thumb_col1, "image", img_path, "Image 1"),
        (thumb_col2, "image2", img2_path, "Image 2"),
    ]:
        with col:
            st.caption(lbl)
            if path:
                st.image(open_image(path), width=120)
                st.caption(sentence.get(key, ""))
                if st.button(f"✕ Clear {lbl}", key=f"clear_{key}"):
                    sentences[sel][key] = None
                    st.rerun()
            else:
                st.caption("None")

    st.divider()

    def _reset_page():
        st.session_state.picker_page = 0

    # Top tags quick-select
    tag_counts = Counter(
        tag for clip in st.session_state.clip_index for tag in clip.get("tags", [])
    )
    top_tags = [tag for tag, _ in tag_counts.most_common(20)]
    if top_tags:
        active_terms = {t.strip().lower() for t in st.session_state.picker_search.split() if t.strip()}
        tag_rows = [top_tags[:10], top_tags[10:]]
        for row_tags in tag_rows:
            cols = st.columns(len(row_tags))
            for col, tag in zip(cols, row_tags):
                with col:
                    is_active = tag.lower() in active_terms
                    if st.button(
                        tag,
                        key=f"qtag_{tag}",
                        type="primary" if is_active else "secondary",
                        use_container_width=True,
                    ):
                        terms_set = {t.strip().lower() for t in st.session_state.picker_search.split() if t.strip()}
                        if tag.lower() in terms_set:
                            terms_set.discard(tag.lower())
                        else:
                            terms_set.add(tag.lower())
                        st.session_state.picker_search = " ".join(sorted(terms_set))
                        st.session_state.picker_page = 0
                        st.rerun()

    search = st.text_input(
        "Filter clips",
        value=st.session_state.picker_search,
        placeholder="tag or filename…",
        key="picker_search",
        on_change=_reset_page,
    )
    type_filter = st.radio(
        "Type",
        TYPE_FILTER_OPTIONS,
        index=TYPE_FILTER_OPTIONS.index(st.session_state.picker_type_filter),
        horizontal=True,
        key="picker_type_filter",
        on_change=_reset_page,
    )
    terms = [t.strip().lower() for t in search.split() if t.strip()]

    clips = st.session_state.clip_index
    if type_filter != "all":
        allowed_exts = TYPE_FILTER_EXTS[type_filter]
        clips = [c for c in clips if Path(c.get("file", "")).suffix.lower() in allowed_exts]
    if terms:
        def clip_matches(clip: dict) -> bool:
            haystack = " ".join(clip.get("tags", [])).lower() + " " + clip.get("file", "").lower()
            return all(t in haystack for t in terms)
        clips = [c for c in clips if clip_matches(c)]

    lib = Path(st.session_state.library_path)
    current_image = sentence.get(slot)

    COLS = 5
    PAGE_SIZE = 50

    if not clips:
        st.caption("No clips match." if terms else "No clips in library.")
    else:
        total_pages = max(1, (len(clips) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(st.session_state.picker_page, total_pages - 1)
        st.session_state.picker_page = page
        page_clips = clips[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

        for row_start in range(0, len(page_clips), COLS):
            cols = st.columns(COLS)
            for col_idx, clip in enumerate(page_clips[row_start:row_start + COLS]):
                with cols[col_idx]:
                    img_file = lib / clip["file"]
                    if img_file.exists() and img_file.suffix.lower() in IMAGE_EXTENSIONS:
                        st.image(make_thumbnail(img_file, THUMB_PICK), use_container_width=True)
                    elif img_file.exists() and img_file.suffix.lower() in VIDEO_EXTENSIONS:
                        thumb = make_video_thumbnail(img_file, THUMB_PICK)
                        if thumb:
                            st.image(thumb, use_container_width=True)
                        else:
                            st.markdown(
                                f"<div style='width:{THUMB_PICK}px;height:{THUMB_PICK}px;"
                                "background:#1a1a2e;border-radius:4px;border:1px solid #555;"
                                "display:flex;align-items:center;justify-content:center;"
                                "font-size:1.6em'>▶️</div>",
                                unsafe_allow_html=True,
                            )

                    is_current = current_image == clip["file"]
                    label = f"✓ {clip['file']}" if is_current else clip["file"]
                    btn_type = "primary" if is_current else "secondary"
                    if st.button(
                        label,
                        key=f"assign_{sel}_{slot}_{clip['id']}",
                        use_container_width=True,
                        type=btn_type,
                    ):
                        sentences[sel][slot] = clip["file"]
                        st.rerun()

        if total_pages > 1:
            nav_cols = st.columns([1, 2, 1])
            with nav_cols[0]:
                if st.button("← Prev", disabled=page == 0, use_container_width=True):
                    st.session_state.picker_page -= 1
                    st.rerun()
            with nav_cols[1]:
                st.caption(f"Page {page + 1} of {total_pages} · {len(clips)} clips")
            with nav_cols[2]:
                if st.button("Next →", disabled=page >= total_pages - 1, use_container_width=True):
                    st.session_state.picker_page += 1
                    st.rerun()
