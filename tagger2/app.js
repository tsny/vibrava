'use strict';

// ─── Constants ───────────────────────────────────────────────────────────────

const IMAGE_EXTS = new Set(['.jpg', '.jpeg', '.png', '.gif', '.webp']);
const VIDEO_EXTS = new Set(['.mp4', '.mov', '.avi', '.webm']);
const PAGE_SIZE = 28;
const COLS = 7;

const COMMON_TAGS = [
  'food', 'grumpy', 'surprised', 'sleeping', 'chaos',
  'judging', 'cute', 'angry', 'sad', 'happy', 'derp',
  'attack', 'scared', 'confused', 'smug',
  'meme', 'smirk', 'smile', 'cry',
  'eating', 'napping', 'hiding', 'sneaking',
  'thinking', 'planning', 'watching', 'staring',
  'excited', 'guilty', 'caught',
];

// ─── State ────────────────────────────────────────────────────────────────────

const S = {
  folder: null,
  files: [],
  index: { version: '1', clips: [] },
  view: 'gallery',   // 'gallery' | 'detail' | 'tags'
  currentIdx: 0,
  page: 0,
  filterImages: true,
  filterVideos: true,
  filterUntagged: false,
  search: '',
};

// ─── API ─────────────────────────────────────────────────────────────────────

async function get(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}`);
  return r.json();
}

async function post(path, body) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`POST ${path} → ${r.status}`);
  return r.json();
}

// ─── Utils ────────────────────────────────────────────────────────────────────

const esc = s => String(s ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const ext = f => { const d = (f || '').lastIndexOf('.'); return d >= 0 ? f.slice(d).toLowerCase() : ''; };
const isVideo = f => VIDEO_EXTS.has(ext(f));

function thumbUrl(file) {
  return `/thumb?folder=${encodeURIComponent(S.folder)}&file=${encodeURIComponent(file)}`;
}

function mediaUrl(file) {
  return `/media?folder=${encodeURIComponent(S.folder)}&file=${encodeURIComponent(file)}`;
}

// ─── Index helpers ────────────────────────────────────────────────────────────

function getClip(filename) {
  return S.index.clips.find(c => c.file === filename) ?? null;
}

function upsertClip(filename, tags) {
  const existing = S.index.clips.find(c => c.file === filename);
  if (existing) {
    existing.tags = tags;
  } else {
    S.index.clips.push({
      id: filename.replace(/\.[^.]+$/, ''),
      file: filename,
      tags,
      type: isVideo(filename) ? 'video' : 'image',
      duration_s: null,
      loop: false,
      notes: null,
    });
  }
  saveIndex();
}

async function saveIndex() {
  try {
    await post(`/api/index?folder=${encodeURIComponent(S.folder)}`, S.index);
  } catch (e) {
    console.error('Save failed:', e);
  }
}

function currentTags() {
  const file = S.files[S.currentIdx];
  if (!file) return [];
  const clip = getClip(file);
  return clip ? [...clip.tags] : [];
}

function taggedCount() {
  return S.files.filter(f => {
    const c = getClip(f);
    return c && c.tags && c.tags.length > 0;
  }).length;
}

function allTagCounts() {
  const counts = new Map();
  for (const clip of S.index.clips) {
    for (const tag of (clip.tags || [])) {
      counts.set(tag, (counts.get(tag) || 0) + 1);
    }
  }
  return counts;
}

// ─── Filtered files ───────────────────────────────────────────────────────────

function isUntagged(f) {
  const c = getClip(f);
  return !c || !c.tags || c.tags.length === 0;
}

function filteredFiles() {
  return S.files.filter(f => {
    const isImg = IMAGE_EXTS.has(ext(f));
    const isVid = VIDEO_EXTS.has(ext(f));
    if (isImg && !S.filterImages) return false;
    if (isVid && !S.filterVideos) return false;
    if (S.filterUntagged && !isUntagged(f)) return false;
    if (S.search) {
      const needle = S.search.toLowerCase();
      const clip = getClip(f);
      const tags = clip ? clip.tags.join(' ') : '';
      if (!f.toLowerCase().includes(needle) && !tags.includes(needle)) return false;
    }
    return true;
  }).sort((a, b) => isUntagged(b) - isUntagged(a));
}

function findNextUntaggedIdx(from) {
  for (let i = from + 1; i < S.files.length; i++) {
    if (isUntagged(S.files[i])) return i;
  }
  return -1;
}

function findPrevUntaggedIdx(from) {
  for (let i = from - 1; i >= 0; i--) {
    if (isUntagged(S.files[i])) return i;
  }
  return -1;
}

// ─── Folder loading ───────────────────────────────────────────────────────────

async function openFolder(folderPath) {
  const { files, folder } = await get(`/api/files?folder=${encodeURIComponent(folderPath)}`);
  S.folder = folder;
  S.files = files;
  S.index = await get(`/api/index?folder=${encodeURIComponent(folder)}`);
  S.view = 'gallery';
  S.currentIdx = 0;
  S.page = 0;
  S.search = '';
  const url = new URL(location.href);
  url.searchParams.set('folder', folder);
  history.replaceState(null, '', url);
  render();
}

// ─── Sidebar ─────────────────────────────────────────────────────────────────

function renderSidebar() {
  const total = S.files.length;
  const tagged = S.folder ? taggedCount() : 0;
  const pct = total ? tagged / total : 0;

  document.getElementById('sidebar').innerHTML = `
    <h2 class="sidebar-title">Vibrava Tagger</h2>

    <label class="lbl">Folder</label>
    <input id="folder-input" class="inp" type="text" placeholder="/path/to/images"
      value="${esc(S.folder || '')}">
    <button class="btn pri full" id="open-btn" style="margin-top:6px">Open</button>

    ${S.folder ? `
      <div class="hr"></div>
      <div style="font-size:0.82em;color:var(--muted)">Tagged</div>
      <div style="font-size:1.1em;font-weight:600;margin-top:2px">${tagged} <span style="color:var(--muted);font-size:0.8em">/ ${total}</span></div>
      <div class="progress-wrap"><div class="progress-fill" style="width:${Math.round(pct * 100)}%"></div></div>

      <div class="hr"></div>
      <button class="btn sec full" id="tags-view-btn">All Tags</button>
      ${S.view !== 'gallery' ? `<button class="btn sec full" id="back-btn" style="margin-top:5px">← Gallery</button>` : ''}
    ` : ''}
  `;

  document.getElementById('open-btn').addEventListener('click', async () => {
    const val = document.getElementById('folder-input').value.trim();
    if (!val) return;
    try {
      await openFolder(val);
    } catch (e) {
      alert('Could not open folder: ' + e.message);
    }
  });

  document.getElementById('folder-input').addEventListener('keydown', async e => {
    if (e.key === 'Enter') document.getElementById('open-btn').click();
  });

  document.getElementById('tags-view-btn')?.addEventListener('click', () => {
    S.view = 'tags';
    render();
  });

  document.getElementById('back-btn')?.addEventListener('click', () => {
    S.view = 'gallery';
    render();
  });
}

// ─── Gallery view ─────────────────────────────────────────────────────────────

function galleryGridHtml() {
  const files = filteredFiles();
  const totalPages = Math.max(1, Math.ceil(files.length / PAGE_SIZE));
  const page = Math.min(S.page, totalPages - 1);
  S.page = page;
  const pageFiles = files.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const pager = totalPages > 1 ? `
    <div class="pager" id="pager-top">
      <button class="btn sec" id="pg-prev" ${page === 0 ? 'disabled' : ''}>← Prev</button>
      <span>Page ${page + 1} / ${totalPages} · ${files.length} files</span>
      <button class="btn sec" id="pg-next" ${page >= totalPages - 1 ? 'disabled' : ''}>Next →</button>
    </div>
  ` : `<p class="muted" style="margin:8px 0;font-size:0.8em" id="pager-top">${files.length} files</p>`;

  const cells = pageFiles.map(f => {
    const absIdx = S.files.indexOf(f);
    const clip = getClip(f);
    const isTagged = clip && clip.tags && clip.tags.length > 0;
    const indicator = isTagged ? '✓' : '○';
    return `
      <div class="thumb-cell" data-abs-idx="${absIdx}">
        <img class="thumb-img" src="${esc(thumbUrl(f))}" loading="lazy" alt="">
        <div class="thumb-label ${isTagged ? 'tagged' : ''}">${esc(indicator)} ${esc(f)}</div>
      </div>`;
  }).join('');

  const pagerBot = totalPages > 1 ? `
    <div class="pager" id="pager-bot">
      <button class="btn sec" id="pg-prev-bot" ${page === 0 ? 'disabled' : ''}>← Prev</button>
      <span>Page ${page + 1} / ${totalPages}</span>
      <button class="btn sec" id="pg-next-bot" ${page >= totalPages - 1 ? 'disabled' : ''}>Next →</button>
    </div>
  ` : '';

  return { pager, cells, pagerBot };
}

function refreshGalleryGrid() {
  const { pager, cells, pagerBot } = galleryGridHtml();
  const pt = document.getElementById('pager-top');
  if (pt) pt.outerHTML = pager;
  const grid = document.getElementById('gallery-grid');
  if (grid) grid.innerHTML = cells;
  const pb = document.getElementById('pager-bot');
  if (pb) pb.outerHTML = pagerBot;

  bindPagerButtons();
}

function bindPagerButtons() {
  document.getElementById('pg-prev')?.addEventListener('click', () => { S.page--; refreshGalleryGrid(); });
  document.getElementById('pg-next')?.addEventListener('click', () => { S.page++; refreshGalleryGrid(); });
  document.getElementById('pg-prev-bot')?.addEventListener('click', () => { S.page--; refreshGalleryGrid(); });
  document.getElementById('pg-next-bot')?.addEventListener('click', () => { S.page++; refreshGalleryGrid(); });
}

function renderGallery() {
  if (!S.folder) {
    document.getElementById('main').innerHTML = `
      <p class="muted" style="margin-top:40px;text-align:center">Open a folder to start tagging.</p>`;
    return;
  }

  const { pager, cells, pagerBot } = galleryGridHtml();

  document.getElementById('main').innerHTML = `
    <div class="gallery-controls">
      <div class="filters">
        <label><input type="checkbox" id="fi-images" ${S.filterImages ? 'checked' : ''}> Images</label>
        <label><input type="checkbox" id="fi-videos" ${S.filterVideos ? 'checked' : ''}> Videos</label>
        <label><input type="checkbox" id="fi-untagged" ${S.filterUntagged ? 'checked' : ''}> Untagged only</label>
      </div>
      <input class="inp" id="gallery-search" type="text" placeholder="search filename or tag…"
        value="${esc(S.search)}" style="width:220px">
    </div>
    ${pager}
    <div class="grid" id="gallery-grid">${cells}</div>
    ${pagerBot}
  `;

  document.getElementById('fi-images').addEventListener('change', e => {
    S.filterImages = e.target.checked; S.page = 0; refreshGalleryGrid();
  });
  document.getElementById('fi-videos').addEventListener('change', e => {
    S.filterVideos = e.target.checked; S.page = 0; refreshGalleryGrid();
  });
  document.getElementById('fi-untagged').addEventListener('change', e => {
    S.filterUntagged = e.target.checked; S.page = 0; refreshGalleryGrid();
  });
  document.getElementById('gallery-search').addEventListener('input', e => {
    const pos = e.target.selectionStart;
    S.search = e.target.value;
    S.page = 0;
    refreshGalleryGrid();
    e.target.setSelectionRange(pos, pos);
  });

  bindPagerButtons();

  document.getElementById('main').addEventListener('click', e => {
    const cell = e.target.closest('.thumb-cell');
    if (cell) {
      S.currentIdx = parseInt(cell.dataset.absIdx, 10);
      S.view = 'detail';
      render();
    }
  });
}

// ─── Detail view ──────────────────────────────────────────────────────────────

function renderDetail() {
  const file = S.files[S.currentIdx];
  if (!file) { S.view = 'gallery'; render(); return; }

  const tags = currentTags();
  const existing = new Set(tags);
  const idx = S.currentIdx;

  const prevIdx = S.filterUntagged ? findPrevUntaggedIdx(idx) : idx - 1;
  const nextIdx = S.filterUntagged ? findNextUntaggedIdx(idx) : idx + 1;
  const untaggedTotal = S.filterUntagged ? S.files.filter(isUntagged).length : S.files.length;
  const navInfo = S.filterUntagged
    ? `<strong>${esc(file)}</strong> &nbsp;·&nbsp; ${untaggedTotal} untagged`
    : `<strong>${esc(file)}</strong> &nbsp;·&nbsp; ${idx + 1} / ${S.files.length}`;

  const mediaHtml = isVideo(file)
    ? `<video src="${esc(mediaUrl(file))}" controls loop muted style="border-radius:6px;width:100%"></video>`
    : `<img src="${esc(mediaUrl(file))}" alt="${esc(file)}" style="border-radius:6px;width:100%;display:block">`;

  const chipsHtml = tags.length
    ? tags.map(t => `<button class="tag-chip" data-rm="${esc(t)}"><span>${esc(t)}</span><span class="rm">✕</span></button>`).join('')
    : `<span class="muted" style="font-size:0.85em">No tags yet.</span>`;

  const quickHtml = COMMON_TAGS.map(t =>
    `<button class="btn sec quick-tag" data-tag="${esc(t)}" ${existing.has(t) ? 'disabled' : ''}>${esc(t)}</button>`
  ).join('');

  document.getElementById('main').innerHTML = `
    <div class="detail-nav">
      <button class="btn sec" id="nav-prev" ${prevIdx < 0 ? 'disabled' : ''}>← Prev</button>
      <div class="nav-info">${navInfo}</div>
      <button class="btn sec" id="nav-next" ${nextIdx < 0 ? 'disabled' : ''}>Next →</button>
    </div>
    <div class="detail-layout">
      <div class="detail-media">${mediaHtml}</div>
      <div class="detail-tags">
        <div class="lbl" style="margin-top:0">Tags</div>
        <div class="tag-chips" id="tag-chips">${chipsHtml}</div>

        <div class="add-tag-row">
          <input class="inp" id="add-tag-input" type="text" placeholder="type tag + Enter" autofocus>
          <button class="btn pri" id="add-tag-btn">+ Add</button>
        </div>

        <div class="hr"></div>
        <div class="lbl">Quick tags</div>
        <div class="quick-tags">${quickHtml}</div>
      </div>
    </div>
  `;

  // Nav
  document.getElementById('nav-prev').addEventListener('click', () => {
    if (prevIdx >= 0) { S.currentIdx = prevIdx; renderDetail(); renderSidebar(); }
  });
  document.getElementById('nav-next').addEventListener('click', () => {
    if (nextIdx >= 0) { S.currentIdx = nextIdx; renderDetail(); renderSidebar(); }
  });

  // Remove tag chip
  document.getElementById('tag-chips').addEventListener('click', e => {
    const btn = e.target.closest('.tag-chip');
    if (!btn) return;
    const tag = btn.dataset.rm;
    const tags = currentTags().filter(t => t !== tag);
    upsertClip(file, tags);
    renderDetail();
    renderSidebar();
  });

  // Add tag
  const addTag = () => {
    const inp = document.getElementById('add-tag-input');
    const val = inp.value.trim().toLowerCase();
    if (!val) return;
    const tags = currentTags();
    if (!tags.includes(val)) {
      tags.push(val);
      upsertClip(file, tags);
    }
    inp.value = '';
    renderDetail();
    renderSidebar();
    document.getElementById('add-tag-input')?.focus();
  };

  document.getElementById('add-tag-btn').addEventListener('click', addTag);
  document.getElementById('add-tag-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); addTag(); }
  });

  // Quick tags
  document.querySelector('.quick-tags').addEventListener('click', e => {
    const btn = e.target.closest('.quick-tag');
    if (!btn || btn.disabled) return;
    const tag = btn.dataset.tag;
    const tags = currentTags();
    if (!tags.includes(tag)) {
      tags.push(tag);
      upsertClip(file, tags);
    }
    renderDetail();
    renderSidebar();
  });

  document.getElementById('add-tag-input')?.focus();
}

// ─── Tags view ────────────────────────────────────────────────────────────────

function renderTagsView() {
  const counts = allTagCounts();
  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);
  const tagged = taggedCount();

  let rows = '';
  for (const [tag, count] of sorted) {
    rows += `<div class="tags-list-row">
      <span class="tag-name">${esc(tag)}</span>
      <span class="tag-count">${count}</span>
    </div>`;
  }

  document.getElementById('main').innerHTML = `
    <div style="margin-bottom:12px">
      <strong>${sorted.length}</strong> unique tags &nbsp;·&nbsp;
      <span class="muted">${tagged} images tagged</span>
    </div>
    <div class="tags-list">${rows || '<p class="muted">No tags yet.</p>'}</div>
  `;
}

// ─── Render ───────────────────────────────────────────────────────────────────

function render() {
  renderSidebar();
  if (S.view === 'gallery') renderGallery();
  else if (S.view === 'detail') renderDetail();
  else if (S.view === 'tags') renderTagsView();
}

// ─── Keyboard shortcuts ───────────────────────────────────────────────────────

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (S.view === 'detail') {
    if (e.key === 'j' || e.key === 'ArrowRight') {
      const next = S.filterUntagged ? findNextUntaggedIdx(S.currentIdx) : S.currentIdx + 1;
      if (next >= 0 && next < S.files.length) { S.currentIdx = next; renderDetail(); renderSidebar(); }
    } else if (e.key === 'k' || e.key === 'ArrowLeft') {
      const prev = S.filterUntagged ? findPrevUntaggedIdx(S.currentIdx) : S.currentIdx - 1;
      if (prev >= 0) { S.currentIdx = prev; renderDetail(); renderSidebar(); }
    } else if (e.key === 'Escape') {
      S.view = 'gallery'; render();
    }
  }
});

// ─── Init ─────────────────────────────────────────────────────────────────────

async function init() {
  const params = new URLSearchParams(location.search);
  const folderParam = params.get('folder');
  if (folderParam) {
    try {
      await openFolder(folderParam);
      return;
    } catch (e) {
      console.warn('Could not restore folder from URL:', e);
    }
  }
  render();
}

init().catch(err => {
  document.getElementById('main').innerHTML =
    `<p style="color:#f66;padding:20px;font-family:monospace">Init failed: ${esc(err.message)}</p>`;
});
