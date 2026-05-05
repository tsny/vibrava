import json
import subprocess
import streamlit as st
from pathlib import Path
from PIL import Image


def pick_folder() -> str | None:
    result = subprocess.run(
        ["osascript", "-e", "POSIX path of (choose folder)"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None  # user cancelled

st.set_page_config(layout="wide", page_title="Vibrava Tagger")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm"}
ALL_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

THUMB_SIZE = 160  # gallery thumbnail square size in pixels


def make_thumbnail(img_path: Path) -> Image.Image:
    """Resize and pad to a square so all gallery tiles are uniform."""
    if img_path.suffix.lower() in VIDEO_EXTENSIONS:
        square = Image.new("RGB", (THUMB_SIZE, THUMB_SIZE), (24, 24, 24))
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(square)
        draw.text((THUMB_SIZE // 2, THUMB_SIZE // 2), "▶", fill=(180, 180, 180), anchor="mm")
        return square
    img = Image.open(img_path).convert("RGB")
    img.thumbnail((THUMB_SIZE, THUMB_SIZE))
    square = Image.new("RGB", (THUMB_SIZE, THUMB_SIZE), (24, 24, 24))
    offset = ((THUMB_SIZE - img.width) // 2, (THUMB_SIZE - img.height) // 2)
    square.paste(img, offset)
    return square

COMMON_TAGS = [
    "food", "grumpy", "surprised", "sleeping", "chaos",
    "judging", "cute", "angry", "sad", "happy", "derp",
    "attack", "scared", "confused", "smug",
    "meme", "smirk", "smile", "cry",
    "eating", "napping", "hiding", "sneaking",
    "thinking", "planning", "watching", "staring",
    "excited", "guilty", "caught",
]

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

GRID_PAGE_SIZE = 28  # 4 rows × 7 cols

def init_state():
    defaults = {
        "folder": None,
        "images": [],
        "index": {"version": "1", "clips": []},
        "current_idx": 0,
        "view": "gallery",  # "gallery" | "detail"
        "grid_page": 0,
        "filter_images": True,
        "filter_videos": True,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ---------------------------------------------------------------------------
# Index helpers
# ---------------------------------------------------------------------------

def index_path() -> Path:
    return Path(st.session_state.folder) / "clip_index.json"

def load_index():
    path = index_path()
    if path.exists():
        with open(path) as f:
            st.session_state.index = json.load(f)
    else:
        st.session_state.index = {"version": "1", "clips": []}

def save_index():
    with open(index_path(), "w") as f:
        json.dump(st.session_state.index, f, indent=2)

def get_clip(filename: str) -> dict | None:
    return next(
        (c for c in st.session_state.index["clips"] if c["file"] == filename),
        None,
    )

def upsert_clip(filename: str, tags: list[str]):
    clips = st.session_state.index["clips"]
    existing = next((c for c in clips if c["file"] == filename), None)
    if existing:
        existing["tags"] = tags
    else:
        clips.append({
            "id": Path(filename).stem,
            "file": filename,
            "tags": tags,
            "type": "image",
            "duration_s": None,
            "loop": False,
            "notes": None,
        })
    save_index()

def current_tags() -> list[str]:
    img = st.session_state.images[st.session_state.current_idx]
    clip = get_clip(img.name)
    return list(clip["tags"]) if clip else []

def add_tag(tag: str):
    tags = current_tags()
    if tag and tag not in tags:
        tags.append(tag)
        img = st.session_state.images[st.session_state.current_idx]
        upsert_clip(img.name, tags)

def remove_tag(tag: str):
    tags = current_tags()
    if tag in tags:
        tags.remove(tag)
        img = st.session_state.images[st.session_state.current_idx]
        upsert_clip(img.name, tags)

def tagged_count() -> int:
    return sum(
        1 for img in st.session_state.images
        if (c := get_clip(img.name)) and c.get("tags")
    )

# ---------------------------------------------------------------------------
# Folder loading
# ---------------------------------------------------------------------------

def open_folder(path_str: str) -> bool:
    path = Path(path_str.strip())
    if not path.exists() or not path.is_dir():
        return False
    st.session_state.folder = str(path)
    st.session_state.images = sorted(
        [f for f in path.iterdir() if f.suffix.lower() in ALL_EXTENSIONS],
        key=lambda f: f.name,
    )
    st.session_state.current_idx = 0
    st.session_state.view = "gallery"
    load_index()
    st.query_params["folder"] = str(path)
    return True


# Restore folder from URL on fresh page load, or default to cwd
if st.session_state.folder is None:
    if "folder" in st.query_params:
        open_folder(st.query_params["folder"])
    else:
        open_folder(str(Path.cwd()))

# ---------------------------------------------------------------------------
# Keyboard shortcut injection (Ctrl+J = next, Ctrl+K = prev)
# Finds Prev/Next buttons in the parent document by their text content.
# ---------------------------------------------------------------------------

KEYBOARD_JS = """
<script>
window.parent.document.addEventListener('keydown', function(e) {
    if (!e.ctrlKey) return;
    let target = null;
    if (e.key === 'j') target = 'Next';
    if (e.key === 'k') target = 'Prev';
    if (!target) return;
    e.preventDefault();
    for (const btn of window.parent.document.querySelectorAll('button')) {
        if (btn.innerText.includes(target) && !btn.disabled) {
            btn.click();
            break;
        }
    }
}, { capture: true });
</script>
"""

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("Vibrava Tagger")

    pick_col, _ = st.columns([1, 0.01])
    with pick_col:
        if st.button("📁 Choose Folder", use_container_width=True):
            picked = pick_folder()
            if picked:
                st.session_state["_folder_input"] = picked

    folder_input = st.text_input(
        "Folder path",
        value=st.session_state.get("_folder_input", st.session_state.folder or ""),
        key="_folder_input",
    )
    if st.button("Open", use_container_width=True):
        if not open_folder(folder_input):
            st.error("Path not found or not a directory.")
        else:
            st.rerun()

    if st.session_state.folder:
        total = len(st.session_state.images)
        tagged = tagged_count()
        st.metric("Tagged", f"{tagged} / {total}")
        st.progress(tagged / total if total else 0)

        if st.session_state.view == "detail":
            st.divider()
            if st.button("← Back to Gallery", use_container_width=True):
                st.session_state.view = "gallery"
                st.rerun()

# ---------------------------------------------------------------------------
# Guard: no folder open
# ---------------------------------------------------------------------------

if not st.session_state.folder:
    st.info("Open a folder using the sidebar to start tagging.")
    st.stop()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

gallery_tab, tags_tab = st.tabs(["Gallery", "All Tags"])

# ── Gallery tab ─────────────────────────────────────────────────────────────

with gallery_tab:

    # ── Detail view ─────────────────────────────────────────────────────────
    if st.session_state.view == "detail":
        st.components.v1.html(KEYBOARD_JS, height=0)

        images = st.session_state.images
        idx = st.session_state.current_idx
        img_path = images[idx]

        # Navigation bar
        nav_left, nav_mid, nav_right = st.columns([1, 6, 1])
        with nav_left:
            if st.button("← Prev", disabled=idx == 0, use_container_width=True):
                st.session_state.current_idx -= 1
                st.rerun()
        with nav_mid:
            st.markdown(
                f"<p style='text-align:center; margin:0; padding-top:6px'>"
                f"<strong>{img_path.name}</strong> &nbsp;·&nbsp; {idx + 1} / {len(images)}"
                f"</p>",
                unsafe_allow_html=True,
            )
        with nav_right:
            if st.button("Next →", disabled=idx == len(images) - 1, use_container_width=True):
                st.session_state.current_idx += 1
                st.rerun()

        # Image
        img_col, tag_col = st.columns([1, 2])
        with img_col:
            if img_path.suffix.lower() in VIDEO_EXTENSIONS:
                st.video(str(img_path))
            else:
                st.image(Image.open(img_path), width=400)

        with tag_col:
            tags = current_tags()

            # Current tags as removable chips
            st.markdown("**Tags**")
            if tags:
                # Render chips in rows of 4
                for i in range(0, len(tags), 4):
                    row = st.columns(min(4, len(tags) - i))
                    for j, tag in enumerate(tags[i:i + 4]):
                        with row[j]:
                            if st.button(f"✕ {tag}", key=f"rm_{tag}_{idx}"):
                                remove_tag(tag)
                                st.rerun()
            else:
                st.caption("No tags yet.")

            st.divider()

            # Add tag input
            with st.form(key=f"add_tag_form_{idx}", clear_on_submit=True):
                new_tag = st.text_input("Add tag", placeholder="type and press Enter", key=f"new_tag_{idx}")
                if st.form_submit_button("+ Add", use_container_width=True) and new_tag.strip():
                    add_tag(new_tag.strip().lower())
                    st.rerun()

            st.components.v1.html("""
<script>
setTimeout(function() {
    const input = window.parent.document.querySelector('input[placeholder="type and press Enter"]');
    if (input) input.focus();
}, 100);
</script>
""", height=0)

            st.divider()

            # Quick tags
            st.markdown("**Quick tags**")
            existing = set(current_tags())
            for i in range(0, len(COMMON_TAGS), 3):
                row = st.columns(3)
                for j, tag in enumerate(COMMON_TAGS[i:i + 3]):
                    with row[j]:
                        if st.button(
                            tag,
                            key=f"quick_{tag}_{idx}",
                            disabled=tag in existing,
                            use_container_width=True,
                        ):
                            add_tag(tag)
                            st.rerun()

    # ── Grid view ───────────────────────────────────────────────────────────
    else:
        all_images = sorted(
            st.session_state.images,
            key=lambda f: bool((c := get_clip(f.name)) and c.get("tags")),
        )
        st.session_state.images = all_images

        # Filter + pagination controls
        ctrl_left, ctrl_right = st.columns([3, 2])
        with ctrl_left:
            cb_cols = st.columns(2)
            with cb_cols[0]:
                show_images = st.checkbox("Images", value=st.session_state.filter_images, key="filter_images")
            with cb_cols[1]:
                show_videos = st.checkbox("Videos", value=st.session_state.filter_videos, key="filter_videos")

        images = [
            f for f in all_images
            if (f.suffix.lower() in IMAGE_EXTENSIONS and show_images)
            or (f.suffix.lower() in VIDEO_EXTENSIONS and show_videos)
        ]

        total_pages = max(1, (len(images) + GRID_PAGE_SIZE - 1) // GRID_PAGE_SIZE)
        page = min(st.session_state.grid_page, total_pages - 1)
        st.session_state.grid_page = page

        with ctrl_right:
            pg_cols = st.columns([1, 2, 1])
            with pg_cols[0]:
                if st.button("←", disabled=page == 0, use_container_width=True, key="pg_prev"):
                    st.session_state.grid_page -= 1
                    st.rerun()
            with pg_cols[1]:
                st.markdown(
                    f"<p style='text-align:center;margin:0;padding-top:6px'>{page + 1} / {total_pages}</p>",
                    unsafe_allow_html=True,
                )
            with pg_cols[2]:
                if st.button("→", disabled=page >= total_pages - 1, use_container_width=True, key="pg_next"):
                    st.session_state.grid_page += 1
                    st.rerun()

        if not images:
            st.info("No images found in this folder.")
        else:
            COLS = 7
            page_images = images[page * GRID_PAGE_SIZE:(page + 1) * GRID_PAGE_SIZE]
            for row_start in range(0, len(page_images), COLS):
                cols = st.columns(COLS)
                for col_idx, img_path in enumerate(page_images[row_start:row_start + COLS]):
                    with cols[col_idx]:
                        clip = get_clip(img_path.name)
                        is_tagged = bool(clip and clip.get("tags"))
                        indicator = "✓" if is_tagged else "○"

                        st.image(make_thumbnail(img_path), use_container_width=True)
                        abs_idx = images.index(img_path)
                        if st.button(
                            f"{indicator} {img_path.name}",
                            key=f"open_{img_path.name}",
                            use_container_width=True,
                        ):
                            st.session_state.current_idx = abs_idx
                            st.session_state.view = "detail"
                            st.rerun()

# ── Tags tab ─────────────────────────────────────────────────────────────────

with tags_tab:
    all_tags: dict[str, int] = {}
    for clip in st.session_state.index.get("clips", []):
        for tag in clip.get("tags", []):
            all_tags[tag] = all_tags.get(tag, 0) + 1

    if not all_tags:
        st.info("No tags yet. Start tagging images in the Gallery tab.")
    else:
        st.markdown(f"**{len(all_tags)} unique tags** across {tagged_count()} images")
        st.divider()

        header = st.columns([3, 1])
        header[0].markdown("**Tag**")
        header[1].markdown("**Count**")

        for tag, count in sorted(all_tags.items(), key=lambda x: -x[1]):
            row = st.columns([3, 1])
            row[0].write(tag)
            row[1].write(count)
