# Tagger2 Plan

Port the Streamlit tagger to the HTML/JS + Python server pattern from editor2.

## Files to Create

- `tagger2/server.py`
- `tagger2/index.html`
- `tagger2/app.js`
- `tagger2/style.css`

---

## Step 1: server.py

Minimal Python HTTP server (same pattern as editor2/server.py).

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | serve index.html |
| GET | `/app.js` | serve app.js |
| GET | `/style.css` | serve style.css |
| GET | `/api/files?folder=<path>` | list image/video files in folder, sorted by name |
| GET | `/api/index?folder=<path>` | return clip_index.json from folder, or empty skeleton |
| POST | `/api/index?folder=<path>` | write clip_index.json to folder |
| GET | `/media?folder=<f>&file=<rel>` | serve file from within folder (path-validated) |
| GET | `/thumb?folder=<f>&file=<rel>&size=160` | PIL square thumbnail (JPEG) |

### Notes
- Path validation on `/media` and `/thumb`: resolved path must start with folder
- Video files in `/thumb` get a dark grey square with a play symbol (same as old tagger)
- Default port 7655 (different from editor2's 7654)
- PIL already available (used by editor2)

---

## Step 2: index.html

Minimal shell, same structure as editor2:

```html
<aside id="sidebar"></aside>
<div id="main"></div>
```

---

## Step 3: style.css

Dark theme matching editor2. Additions needed:
- `.tag-chip` — pill button for current tags (removable)
- `.grid` — 7-column thumbnail grid
- `.thumb-cell` — individual grid cell
- `.tagged-dot` / `.untagged-dot` — status indicator on grid cells
- `.detail-layout` — two-column (image | tags) layout

---

## Step 4: app.js

### State

```js
const S = {
  folder: null,
  files: [],          // [{name, rel}] sorted
  index: {version:'1', clips:[]},
  view: 'gallery',    // 'gallery' | 'detail' | 'tags'
  currentIdx: 0,
  page: 0,
  filterImages: true,
  filterVideos: true,
  search: '',         // filter in gallery by filename/tag
};
```

### API helpers
- `get(path)` / `post(path, body)` — same as editor2
- `thumbUrl(folder, file)` → `/thumb?folder=...&file=...`
- `mediaUrl(folder, file)` → `/media?folder=...&file=...`

### Index helpers
- `getClip(filename)` — find clip entry by filename
- `upsertClip(filename, tags)` — create or update clip entry
- `saveIndex()` — POST current index to server
- `taggedCount()` — count clips with non-empty tags

### Views

**Sidebar** (always visible):
- Folder path text input + "Open" button
- Tagged N / M metric + progress bar
- "← Gallery" button (only in detail/tags view)
- "All Tags" button

**Gallery view** (`view === 'gallery'`):
- Filter checkboxes: Images | Videos
- Search input (filename or tag)
- 7-column grid, PAGE_SIZE=28
- Each cell: thumbnail image, filename label, ✓/○ indicator
- Click cell → open detail view at that index
- Pagination controls

**Detail view** (`view === 'detail'`):
- Nav bar: ← Prev | filename · N/total | Next →
- Two-column layout:
  - Left: image (or `<video>` for video files)
  - Right:
    - Current tags as removable chips (click to remove)
    - Add tag text input (Enter to add)
    - Quick tags grid (COMMON_TAGS, disabled if already tagged)
- Keyboard: `j` → next, `k` → prev, `Escape` → back to gallery
- Auto-save on every tag change

**Tags view** (`view === 'tags'`):
- Header: "N unique tags across M images"
- Sorted list: tag name | count (descending)

### Constants

```js
const COMMON_TAGS = [
  'food','grumpy','surprised','sleeping','chaos',
  'judging','cute','angry','sad','happy','derp',
  'attack','scared','confused','smug',
  'meme','smirk','smile','cry',
  'eating','napping','hiding','sneaking',
  'thinking','planning','watching','staring',
  'excited','guilty','caught',
];

const IMAGE_EXTS = new Set(['.jpg','.jpeg','.png','.gif','.webp']);
const VIDEO_EXTS = new Set(['.mp4','.mov','.avi','.webm']);
const PAGE_SIZE = 28;
const COLS = 7;
```

---

## Execution Order

- [x] Write PLAN.md
- [x] Create tagger2/server.py
- [x] Create tagger2/index.html
- [x] Create tagger2/style.css
- [x] Create tagger2/app.js
- [x] Smoke test: server boots, /api/files and /api/index respond correctly
