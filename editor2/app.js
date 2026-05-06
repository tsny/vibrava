'use strict';

// ─── Constants ──────────────────────────────────────────────────────────────

const IMAGE_EXTS = new Set(['.jpg', '.jpeg', '.png', '.webp']);
const GIF_EXTS   = new Set(['.gif']);
const VIDEO_EXTS = new Set(['.mp4', '.mov', '.webm']);
const ALL_IMG    = new Set([...IMAGE_EXTS, ...GIF_EXTS]);

const TYPE_FILTER_EXTS = { 'jpg/png': IMAGE_EXTS, 'gif': GIF_EXTS, 'mp4': VIDEO_EXTS };
const PAGE_SIZE = 50;
const COLS = 5;

const ELEVENLABS_VOICES = [
  ['nPczCjzI2devNBz1zQrb', 'Brian - Deep, Narrative'],
  ['CwhRBWXzGAHq8TQ4Fs17', 'Roger - Laid-Back, Casual, Resonant'],
  ['EXAVITQu4vr4xnSDxMaL', 'Sarah - Mature, Reassuring, Confident'],
  ['FGY2WhTYpPnrIDTdsKH5', 'Laura - Enthusiast, Quirky Attitude'],
  ['IKne3meq5aSn9XLyUdCD', 'Charlie - Deep, Confident, Energetic'],
  ['JBFqnCBsd6RMkjVDRZzb', 'George - Warm, Captivating Storyteller'],
  ['N2lVS1w4EtoT3dr4eOWO', 'Callum - Husky Trickster'],
  ['SAz9YHcvj6GT2YYXdXww', 'River - Relaxed, Neutral, Informative'],
  ['SOYHLrjzK2X1ezoPC6cr', 'Harry - Fierce Warrior'],
  ['TX3LPaxmHKxFdv7VOQHJ', 'Liam - Energetic, Social Media Creator'],
  ['Xb7hH8MSUJpSbSDYk0k2', 'Alice - Clear, Engaging Educator'],
  ['XrExE9yKIg1WjnnlVkGX', 'Matilda - Knowledgable, Professional'],
  ['bIHbv24MWmeRgasZH58o', 'Will - Relaxed Optimist'],
];

// ─── State ───────────────────────────────────────────────────────────────────

const S = {
  scripts: [],
  scriptName: null,
  scriptData: null,
  libraryPath: 'res',
  sfxPath: 'sfx',
  clips: [],
  sfxFiles: [],
  sel: null,        // selected sentence index
  slot: 'image',   // 'image' | 'image2'
  search: '',
  typeFilter: 'all',
  page: 0,
  saveStatus: '',
};

const videoCache = new Map();
const imgBlobCache = new Map(); // file → blob URL

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

// ─── Utils ───────────────────────────────────────────────────────────────────

const esc = s => String(s ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const ext  = f => { const d = (f || '').lastIndexOf('.'); return d >= 0 ? f.slice(d).toLowerCase() : ''; };
const libUrl = f => `/lib/${f.split('/').map(encodeURIComponent).join('/')}`;
const isVideo = f => VIDEO_EXTS.has(ext(f));

function nextId(sentences) {
  const used = new Set(sentences.map(s => String(s.id || '')));
  const nums = [...used].filter(id => /^s\d+$/.test(id)).map(id => +id.slice(1));
  let n = (nums.length ? Math.max(...nums) : 0) + 1;
  while (used.has(`s${n}`)) n++;
  return `s${n}`;
}

function ensureIds(sentences) {
  for (const s of sentences) if (!s.id) s.id = nextId(sentences);
}

function topTags(n = 20) {
  const counts = new Map();
  for (const c of S.clips) for (const t of (c.tags || [])) counts.set(t, (counts.get(t) || 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, n).map(([t]) => t);
}

function filteredClips() {
  let clips = S.clips;
  if (S.typeFilter !== 'all') {
    const allowed = TYPE_FILTER_EXTS[S.typeFilter];
    clips = clips.filter(c => allowed.has(ext(c.file || '')));
  }
  const terms = S.search.split(/\s+/).filter(Boolean).map(t => t.toLowerCase());
  if (terms.length) {
    clips = clips.filter(c => {
      const hay = (c.tags || []).join(' ').toLowerCase() + ' ' + (c.file || '').toLowerCase();
      return terms.every(t => hay.includes(t));
    });
  }
  return clips;
}

// ─── Video thumbnails ────────────────────────────────────────────────────────

async function getImgBlobUrl(file) {
  if (imgBlobCache.has(file)) return imgBlobCache.get(file);
  try {
    const r = await fetch(libUrl(file));
    if (!r.ok) return null;
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    imgBlobCache.set(file, url);
    return url;
  } catch { return null; }
}

async function fillImgBlobUrls(container) {
  const imgs = [...container.querySelectorAll('img[data-file]')];
  await Promise.all(imgs.map(async img => {
    const url = await getImgBlobUrl(img.dataset.file);
    if (url) img.src = url;
  }));
}

async function getVideoThumb(file) {
  if (videoCache.has(file)) return videoCache.get(file);
  return new Promise(resolve => {
    const video = document.createElement('video');
    video.muted = true;
    video.src = libUrl(file);
    video.addEventListener('error', () => resolve(null));
    video.addEventListener('loadeddata', () => { video.currentTime = 0; });
    video.addEventListener('seeked', () => {
      const c = document.createElement('canvas');
      c.width = c.height = 96;
      const ctx = c.getContext('2d');
      ctx.fillStyle = '#181818';
      ctx.fillRect(0, 0, 96, 96);
      const a = video.videoWidth / video.videoHeight;
      const [w, h] = a > 1 ? [96, 96 / a] : [96 * a, 96];
      ctx.drawImage(video, (96 - w) / 2, (96 - h) / 2, w, h);
      const url = c.toDataURL();
      videoCache.set(file, url);
      video.src = '';
      resolve(url);
    });
    video.load();
  });
}

async function fillVideoThumbs(container) {
  for (const el of container.querySelectorAll('[data-video-thumb]')) {
    const file = el.dataset.videoThumb;
    const url = await getVideoThumb(file);
    if (url) {
      el.innerHTML = `<img src="${url}" style="width:100%;height:100%;object-fit:cover">`;
    } else {
      el.textContent = '▶️';
    }
  }
}

// ─── Sidebar ─────────────────────────────────────────────────────────────────

function renderSidebar() {
  const d = S.scriptData;
  document.getElementById('sidebar').innerHTML = `
    <h2 style="font-size:1em;font-weight:700;margin-bottom:12px;color:#ccc">Vibrava Editor</h2>

    <label class="lbl">Script</label>
    ${S.scripts.length
      ? `<select id="ss-select" class="inp" style="width:100%">
           ${S.scripts.map(n => `<option value="${esc(n)}"${n === S.scriptName ? ' selected' : ''}>${esc(n)}</option>`).join('')}
         </select>`
      : `<p class="muted" style="font-size:0.85em">No scripts in scripts/</p>`}

    <div style="display:flex;gap:6px;margin-top:8px">
      <input id="ss-newname" class="inp" placeholder="new script name" style="flex:1;min-width:0">
      <button id="ss-newbtn" class="btn sec">＋</button>
    </div>

    ${d ? `
      <div class="hr"></div>
      <label class="lbl">TTS Provider</label>
      <select id="ss-provider" class="inp" style="width:100%">
        <option value="elevenlabs"${(d.tts_provider || 'elevenlabs') === 'elevenlabs' ? ' selected' : ''}>elevenlabs</option>
        <option value="tiktok"${d.tts_provider === 'tiktok' ? ' selected' : ''}>tiktok</option>
      </select>

      <label class="lbl">Voice ID</label>
      <input id="ss-voiceid" class="inp" style="width:100%" value="${esc(d.voice_id || '')}"
        placeholder="${d.tts_provider === 'tiktok' ? 'e.g. en_us_002' : 'e.g. 21m00Tcm4TlvDq8ikWAM'}">

      <details style="margin:8px 0">
        <summary class="btn sec" style="list-style:none;cursor:pointer;width:100%;text-align:left;padding:5px 12px">🎤 Browse voices</summary>
        <div style="margin-top:6px;max-height:180px;overflow-y:auto;background:#1a1a1a;border-radius:4px;padding:8px">
          ${ELEVENLABS_VOICES.map(([id, name]) => `
            <div style="margin-bottom:8px">
              <div style="font-size:0.8em;font-weight:600;color:#ccc">${esc(name)}</div>
              <code class="voice-code" data-vid="${esc(id)}" title="Click to use"
                style="display:block;font-size:0.75em;background:#252525;padding:2px 6px;border-radius:3px;cursor:pointer;color:#7ec8e3;margin-top:2px">${esc(id)}</code>
            </div>
          `).join('')}
        </div>
      </details>

      <label class="lbl">Caption style</label>
      <select id="ss-caption" class="inp" style="width:100%">
        ${['word', 'line', 'none'].map(v => `<option value="${v}"${(d.caption_style || 'line') === v ? ' selected' : ''}>${v}</option>`).join('')}
      </select>

      <label class="lbl">Output filename</label>
      <input id="ss-outfile" class="inp" style="width:100%" value="${esc(d.output_filename || 'output.mp4')}">

      <label class="lbl">Music file</label>
      <input id="ss-music" class="inp" style="width:100%" value="${esc(d.music || '')}">

      <label class="lbl">Overlay image</label>
      <div style="display:flex;gap:6px">
        <input id="ss-overlay" class="inp" style="flex:1;min-width:0" value="${esc(d.overlay_image || '')}" placeholder="e.g. watermark.png">
        <input id="ss-overlay-size" class="inp" type="number" min="1" max="100" step="1" style="width:64px"
          value="${Math.round((d.overlay_image_size ?? 1/6) * 100)}" title="Size (% of video width)">
        <span style="align-self:center;color:var(--muted);font-size:0.85em">%</span>
      </div>

      <div class="hr"></div>
      <button id="ss-save" class="btn pri" style="width:100%">💾 Save</button>
      <div id="ss-status" style="margin-top:6px;color:#4caf50;font-size:0.8em;min-height:16px">${esc(S.saveStatus)}</div>
    ` : ''}
  `;
  bindSidebar();
}

function bindSidebar() {
  document.getElementById('ss-select')?.addEventListener('change', async e => {
    await loadScript(e.target.value);
    renderSidebar();
    renderSentences();
    renderPicker();
  });

  document.getElementById('ss-newbtn')?.addEventListener('click', async () => {
    const name = document.getElementById('ss-newname').value.trim();
    if (!name) return;
    try {
      const res = await post('/api/scripts', { name });
      S.scripts = await get('/api/scripts');
      await loadScript(res.name);
      renderSidebar();
      renderSentences();
      renderPicker();
    } catch (e) { alert(e.message); }
  });

  document.getElementById('ss-provider')?.addEventListener('change', e => {
    S.scriptData.tts_provider = e.target.value;
  });

  document.getElementById('ss-voiceid')?.addEventListener('input', e => {
    S.scriptData.voice_id = e.target.value || null;
  });

  document.querySelectorAll('.voice-code').forEach(el => {
    el.addEventListener('click', () => {
      const id = el.dataset.vid;
      const inp = document.getElementById('ss-voiceid');
      if (inp) { inp.value = id; S.scriptData.voice_id = id; }
      navigator.clipboard?.writeText(id);
    });
  });

  document.getElementById('ss-caption')?.addEventListener('change', e => {
    S.scriptData.caption_style = e.target.value;
  });

  document.getElementById('ss-outfile')?.addEventListener('input', e => {
    S.scriptData.output_filename = e.target.value;
  });

  document.getElementById('ss-music')?.addEventListener('input', e => {
    S.scriptData.music = e.target.value || null;
  });

  document.getElementById('ss-overlay')?.addEventListener('input', e => {
    S.scriptData.overlay_image = e.target.value || null;
  });

  document.getElementById('ss-overlay-size')?.addEventListener('input', e => {
    const pct = parseFloat(e.target.value);
    S.scriptData.overlay_image_size = isNaN(pct) ? 1/6 : Math.max(1, Math.min(100, pct)) / 100;
  });

  document.getElementById('ss-save')?.addEventListener('click', async () => {
    try {
      await post(`/api/script?name=${encodeURIComponent(S.scriptName)}`, S.scriptData);
      S.saveStatus = 'Saved.';
      const el = document.getElementById('ss-status');
      if (el) el.textContent = 'Saved.';
      setTimeout(() => {
        S.saveStatus = '';
        const el2 = document.getElementById('ss-status');
        if (el2) el2.textContent = '';
      }, 2000);
    } catch (e) { alert('Save failed: ' + e.message); }
  });
}

// ─── Sentences panel ─────────────────────────────────────────────────────────

function renderSentences() {
  const panel = document.getElementById('sentences-panel');
  if (!S.scriptData) {
    panel.innerHTML = '<p class="muted center">Open a script from the sidebar.</p>';
    return;
  }
  const sentences = S.scriptData.sentences || [];
  panel.innerHTML = `
    <div class="panel-header">
      <strong>${esc(S.scriptName)}</strong>
      <span class="muted"> · ${sentences.length} sentences · mode: ${esc(S.scriptData.mode || '?')}</span>
    </div>
    <div id="sentence-list">
      ${sentences.map((s, i) => sentenceRowHtml(s, i)).join('')}
    </div>
    <button id="add-sent-btn" class="btn sec" style="width:100%;margin-top:8px">＋ Add sentence</button>
  `;
  fillVideoThumbs(panel);
}

function sentenceRowHtml(s, i) {
  const isSel = S.sel === i;
  const sfxOpts = ['(none)', ...S.sfxFiles];
  const curSfx = s.sound_effect || '(none)';

  return `
    <div class="srow${isSel ? ' srow-sel' : ''}" data-si="${i}">
      <div class="srow-num">${i + 1}</div>
      <div class="srow-fields">
        <textarea class="inp stxt" data-si="${i}" rows="3">${esc(s.text || '')}</textarea>
        <div class="srow-meta">
          <select class="inp ssfx" data-si="${i}" style="flex:1;min-width:100px">
            ${sfxOpts.map(f => `<option value="${esc(f)}"${curSfx === f ? ' selected' : ''}>${esc(f)}</option>`).join('')}
          </select>
          ${s.sound_effect ? `
            <input class="inp ssfxofs" type="number" data-si="${i}"
              value="${s.sfx_offset ?? 0}" min="0" step="0.1" style="width:72px" placeholder="s offset">
          ` : ''}
          <input class="inp svoice" type="text" data-si="${i}"
            value="${esc(s.voice_id || '')}" placeholder="voice ID override" style="flex:1;min-width:100px">
        </div>
      </div>
      ${thumbColHtml(s.image, 'image', i, isSel)}
      ${thumbColHtml(s.image2, 'image2', i, isSel)}
      <button class="btn sec sdel" data-si="${i}" title="Remove" style="align-self:flex-start;margin-top:4px;padding:4px 8px">✕</button>
    </div>
  `;
}

function thumbColHtml(file, slot, si, isSel) {
  const isActive = isSel && S.slot === slot;
  const label = slot === 'image' ? '1️⃣' : '2️⃣';
  let img;
  if (file && isVideo(file)) {
    img = `<div class="thumb" data-video-thumb="${esc(file)}" style="width:72px;height:72px"></div>`;
  } else if (file) {
    img = `<img src="${libUrl(file)}" class="thumb" style="width:72px;height:72px">`;
  } else {
    img = `<div class="thumb thumb-empty" style="width:72px;height:72px"></div>`;
  }
  return `
    <div class="sthumb" data-slot="${slot}" data-si="${si}">
      ${img}
      <button class="btn ${isActive ? 'pri' : 'sec'} spick" data-si="${si}" data-slot="${slot}" style="width:72px;font-size:0.82em;padding:3px">${label}</button>
    </div>
  `;
}

function handleSentenceClick(e) {
  const del = e.target.closest('.sdel');
  if (del) {
    const i = +del.dataset.si;
    S.scriptData.sentences.splice(i, 1);
    if (S.sel === i) S.sel = null;
    else if (S.sel !== null && S.sel > i) S.sel--;
    renderSentences();
    renderPicker();
    return;
  }

  const pick = e.target.closest('.spick');
  if (pick) {
    const i = +pick.dataset.si;
    const slot = pick.dataset.slot;
    if (S.sel === i && S.slot === slot) {
      S.sel = null;
    } else {
      if (S.sel !== i) S.page = 0;
      S.sel = i;
      S.slot = slot;
    }
    // Update selection styling without re-rendering the whole list
    document.querySelectorAll('.srow').forEach(row => {
      const ri = +row.dataset.si;
      row.classList.toggle('srow-sel', ri === S.sel);
    });
    document.querySelectorAll('.spick').forEach(btn => {
      const active = +btn.dataset.si === S.sel && btn.dataset.slot === S.slot;
      btn.classList.toggle('pri', active);
      btn.classList.toggle('sec', !active);
    });
    renderPicker();
    return;
  }

  if (e.target.id === 'add-sent-btn') {
    const sentences = S.scriptData.sentences;
    sentences.push({ id: nextId(sentences), text: '', sound_effect: null });
    S.sel = sentences.length - 1;
    renderSentences();
    renderPicker();
  }
}

function handleSentenceInput(e) {
  const si = e.target.dataset.si;
  if (si === undefined) return;
  const s = S.scriptData.sentences[+si];
  if (!s) return;

  if (e.target.classList.contains('stxt'))     s.text = e.target.value;
  if (e.target.classList.contains('ssfxofs'))  s.sfx_offset = parseFloat(e.target.value) || 0;
  if (e.target.classList.contains('svoice'))   s.voice_id = e.target.value || null;
}

function handleSentenceChange(e) {
  const si = e.target.dataset.si;
  if (si === undefined) return;
  const i = +si;
  const s = S.scriptData.sentences[i];
  if (!s) return;

  if (e.target.classList.contains('ssfx')) {
    s.sound_effect = e.target.value === '(none)' ? null : e.target.value;
    // Re-render just this row to show/hide offset input
    const row = document.querySelector(`.srow[data-si="${i}"]`);
    if (row) {
      row.outerHTML = sentenceRowHtml(s, i);
      fillVideoThumbs(document.getElementById('sentences-panel'));
    }
  }
}

// ─── Picker panel ────────────────────────────────────────────────────────────

function clipGridHtml(clips, curFile, disabled = false) {
  if (!clips.length) {
    return `<p class="muted">${S.search ? 'No clips match.' : 'No clips in library.'}</p>`;
  }
  const totalPages = Math.max(1, Math.ceil(clips.length / PAGE_SIZE));
  const page = Math.min(S.page, totalPages - 1);
  S.page = page;
  const pageClips = clips.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  let html = '';
  for (let i = 0; i < pageClips.length; i += COLS) {
    const cells = pageClips.slice(i, i + COLS).map(clip => {
      const isCur = !disabled && curFile === clip.file;
      const cachedSrc = !isVideo(clip.file) && imgBlobCache.get(clip.file);
      const thumb = isVideo(clip.file)
        ? `<div class="clip-thumb" data-video-thumb="${esc(clip.file)}"></div>`
        : `<img src="${cachedSrc || ''}" data-file="${esc(clip.file)}" loading="lazy" class="clip-thumb">`;
      return `<div class="clip-cell">
        ${thumb}
        <button class="btn ${isCur ? 'pri' : 'sec'} asgn" data-file="${esc(clip.file)}"
          ${disabled ? 'disabled' : ''}
          style="width:100%;margin-top:3px;font-size:0.68em;padding:2px 3px;overflow:hidden;text-overflow:ellipsis"
          title="${esc(clip.file)}">${isCur ? '✓ ' : ''}${esc(clip.file)}</button>
      </div>`;
    }).join('');
    html += `<div class="clip-row">${cells}</div>`;
  }
  return html;
}

function renderPicker() {
  const panel = document.getElementById('picker-panel');
  if (!S.scriptData) {
    panel.innerHTML = '<p class="muted center">Open a script from the sidebar.</p>';
    return;
  }

  const noSel = S.sel === null || S.sel >= S.scriptData.sentences.length;
  const s = noSel ? null : S.scriptData.sentences[S.sel];
  const slotLabel = S.slot === 'image' ? 'Image 1' : 'Image 2 (½ way)';

  const headerHtml = noSel
    ? `<div class="panel-header"><span class="muted">Select a sentence to assign images</span>
        <button class="btn sec" id="preview-btn" style="margin-left:auto;white-space:nowrap" disabled>🖼 Preview</button></div>`
    : `<div class="panel-header" style="display:flex;align-items:center;gap:10px">
        <span><strong>Sentence ${S.sel + 1}</strong> — <em style="color:#aaa">${esc((s.text || '').slice(0, 60))}</em> · picking <strong>${esc(slotLabel)}</strong></span>
        <button class="btn sec" id="preview-btn" style="margin-left:auto;white-space:nowrap">🖼 Preview</button>
      </div>`;

  const curThumb = (file, slotKey, lbl) => {
    if (noSel) return `<div class="cur-thumb"><p class="lbl">${esc(lbl)}</p><p class="muted" style="font-size:0.82em">—</p></div>`;
    if (!file) return `<div class="cur-thumb"><p class="lbl">${esc(lbl)}</p><p class="muted" style="font-size:0.82em">None</p></div>`;
    const img = isVideo(file)
      ? `<div class="thumb" data-video-thumb="${esc(file)}" style="width:96px;height:96px"></div>`
      : `<img src="${libUrl(file)}" class="cur-img">`;
    return `<div class="cur-thumb">
      <p class="lbl">${esc(lbl)}</p>
      ${img}
      <p class="muted" style="font-size:0.72em;margin-top:3px;word-break:break-all">${esc(file)}</p>
      <button class="btn sec clr-btn" data-slot="${esc(slotKey)}" style="font-size:0.75em;padding:2px 8px;margin-top:4px">✕ Clear</button>
    </div>`;
  };

  // Top tags
  const tags = topTags(20);
  const active = new Set(S.search.split(/\s+/).filter(Boolean).map(t => t.toLowerCase()));
  const tagHtml = tags.length ? `
    <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:4px">
      ${tags.slice(0, 10).map(t => `<button class="btn ${active.has(t.toLowerCase()) ? 'pri' : 'sec'} tagbtn" data-tag="${esc(t)}" style="padding:2px 8px;font-size:0.78em">${esc(t)}</button>`).join('')}
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px">
      ${tags.slice(10).map(t => `<button class="btn ${active.has(t.toLowerCase()) ? 'pri' : 'sec'} tagbtn" data-tag="${esc(t)}" style="padding:2px 8px;font-size:0.78em">${esc(t)}</button>`).join('')}
    </div>
  ` : '';

  // Type filter
  const typeOpts = ['all', 'jpg/png', 'gif', 'mp4'];
  const typeHtml = `<div style="display:flex;gap:4px;margin-bottom:10px">
    ${typeOpts.map(o => `<button class="btn ${S.typeFilter === o ? 'pri' : 'sec'} tfbtn" data-tf="${esc(o)}" style="padding:3px 10px;font-size:0.78em">${esc(o)}</button>`).join('')}
  </div>`;

  const clips = filteredClips();
  const totalPages = Math.max(1, Math.ceil(clips.length / PAGE_SIZE));
  const page = Math.min(S.page, totalPages - 1);
  S.page = page;

  const makePager = (suffix) => totalPages > 1 ? `
    <div class="pager">
      <button class="btn sec" id="pgprev${suffix}" ${page === 0 ? 'disabled' : ''}>← Prev</button>
      <span>Page ${page + 1} / ${totalPages} · ${clips.length} clips</span>
      <button class="btn sec" id="pgnext${suffix}" ${page >= totalPages - 1 ? 'disabled' : ''}>Next →</button>
    </div>
  ` : `<p class="muted" style="margin-top:6px;font-size:0.8em">${clips.length} clips</p>`;

  panel.innerHTML = `
    ${headerHtml}
    <div class="cur-thumbs">
      ${curThumb(s?.image, 'image', 'Image 1')}
      ${curThumb(s?.image2, 'image2', 'Image 2')}
    </div>
    <div class="hr"></div>
    ${tagHtml}
    <input id="picker-search" class="inp" type="text" placeholder="tag or filename…" value="${esc(S.search)}" style="width:100%;margin-bottom:8px">
    ${typeHtml}
    ${makePager('-top')}
    <div id="clip-grid">${clipGridHtml(clips, s?.[S.slot], noSel)}</div>
    ${makePager('-bot')}
  `;

  fillVideoThumbs(panel);
  fillImgBlobUrls(panel);
}

function refreshClipGrid() {
  const grid = document.getElementById('clip-grid');
  if (!grid) return;
  const noSel = S.sel === null || S.sel >= (S.scriptData?.sentences?.length ?? 0);
  const clips = filteredClips();
  const curFile = noSel ? null : S.scriptData?.sentences[S.sel]?.[S.slot];
  grid.innerHTML = clipGridHtml(clips, curFile, noSel);
  fillVideoThumbs(grid);
  fillImgBlobUrls(grid);

  // Refresh pagination
  const totalPages = Math.max(1, Math.ceil(clips.length / PAGE_SIZE));
  const page = S.page;
  for (const id of ['pgprev-top', 'pgprev-bot']) { const el = document.getElementById(id); if (el) el.disabled = page === 0; }
  for (const id of ['pgnext-top', 'pgnext-bot']) { const el = document.getElementById(id); if (el) el.disabled = page >= totalPages - 1; }
}

function handlePickerClick(e) {
  if (e.target.matches('#preview-btn')) { handlePreview(); return; }
  if (e.target.matches('#pgprev-top,#pgprev-bot')) { S.page = Math.max(0, S.page - 1); refreshClipGrid(); return; }
  if (e.target.matches('#pgnext-top,#pgnext-bot')) { S.page++; refreshClipGrid(); return; }

  const tag = e.target.closest('.tagbtn');
  if (tag) {
    const terms = new Set(S.search.split(/\s+/).filter(Boolean).map(t => t.toLowerCase()));
    const t = tag.dataset.tag.toLowerCase();
    terms.has(t) ? terms.delete(t) : terms.add(t);
    S.search = [...terms].sort().join(' ');
    S.page = 0;
    // Sync search input
    const inp = document.getElementById('picker-search');
    if (inp) inp.value = S.search;
    // Update tag button styles
    document.querySelectorAll('.tagbtn').forEach(btn => {
      const bt = btn.dataset.tag.toLowerCase();
      btn.classList.toggle('pri', terms.has(bt));
      btn.classList.toggle('sec', !terms.has(bt));
    });
    refreshClipGrid();
    return;
  }

  const tf = e.target.closest('.tfbtn');
  if (tf) {
    S.typeFilter = tf.dataset.tf;
    S.page = 0;
    document.querySelectorAll('.tfbtn').forEach(btn => {
      btn.classList.toggle('pri', btn.dataset.tf === S.typeFilter);
      btn.classList.toggle('sec', btn.dataset.tf !== S.typeFilter);
    });
    refreshClipGrid();
    return;
  }

  const asgn = e.target.closest('.asgn');
  if (asgn && S.sel !== null) {
    const file = asgn.dataset.file;
    S.scriptData.sentences[S.sel][S.slot] = file;
    // Update thumbnail in sentence row without re-rendering the list
    const thumbCol = document.querySelector(`.sthumb[data-slot="${S.slot}"][data-si="${S.sel}"]`);
    if (thumbCol) {
      thumbCol.outerHTML = thumbColHtml(file, S.slot, S.sel, true);
      fillVideoThumbs(document.getElementById('sentences-panel'));
    }
    renderPicker();
    return;
  }

  const clr = e.target.closest('.clr-btn');
  if (clr && S.sel !== null) {
    const slot = clr.dataset.slot;
    S.scriptData.sentences[S.sel][slot] = null;
    const thumbCol = document.querySelector(`.sthumb[data-slot="${slot}"][data-si="${S.sel}"]`);
    if (thumbCol) {
      thumbCol.outerHTML = thumbColHtml(null, slot, S.sel, true);
    }
    renderPicker();
  }
}

function handlePickerInput(e) {
  if (e.target.id === 'picker-search') {
    const pos = e.target.selectionStart;
    S.search = e.target.value;
    S.page = 0;
    // Update tag button styles
    const active = new Set(S.search.split(/\s+/).filter(Boolean).map(t => t.toLowerCase()));
    document.querySelectorAll('.tagbtn').forEach(btn => {
      const t = btn.dataset.tag.toLowerCase();
      btn.classList.toggle('pri', active.has(t));
      btn.classList.toggle('sec', !active.has(t));
    });
    refreshClipGrid();
    // Restore cursor position (refreshClipGrid doesn't touch the input)
    e.target.setSelectionRange(pos, pos);
  }
}

// ─── Preview modal ───────────────────────────────────────────────────────────

function showPreviewModal(imgSrc) {
  let modal = document.getElementById('preview-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'preview-modal';
    modal.style.cssText = 'display:none;position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:1000;align-items:center;justify-content:center;cursor:pointer';
    modal.innerHTML = `
      <div style="position:relative">
        <img id="preview-modal-img" style="max-width:90vw;max-height:90vh;border-radius:6px;display:block">
        <button style="position:absolute;top:-14px;right:-14px;background:#333;border:1px solid #555;color:#ddd;border-radius:50%;width:28px;height:28px;font-size:1em;cursor:pointer;display:flex;align-items:center;justify-content:center">✕</button>
      </div>`;
    modal.addEventListener('click', () => { modal.style.display = 'none'; });
    document.body.appendChild(modal);
  }
  document.getElementById('preview-modal-img').src = imgSrc;
  modal.style.display = 'flex';
}

async function handlePreview() {
  if (S.sel === null || !S.scriptName) return;
  const btn = document.getElementById('preview-btn');
  if (btn) { btn.textContent = '⏳ Rendering…'; btn.disabled = true; }
  try {
    const url = `/api/preview?name=${encodeURIComponent(S.scriptName)}&idx=${S.sel}&t=${Date.now()}`;
    showPreviewModal(url);
  } finally {
    if (btn) { btn.textContent = '🖼 Preview'; btn.disabled = false; }
  }
}

// ─── Script loading ───────────────────────────────────────────────────────────

async function loadScript(name) {
  const data = await get(`/api/script?name=${encodeURIComponent(name)}`);
  S.scriptName = name;
  S.scriptData = data;
  if (!Array.isArray(S.scriptData.sentences)) S.scriptData.sentences = [];
  ensureIds(S.scriptData.sentences);
  S.sel = null;
  S.search = '';
  S.typeFilter = 'all';
  S.page = 0;
}

// ─── Init ────────────────────────────────────────────────────────────────────

async function init() {
  const [cfg, scripts, clips, sfxFiles] = await Promise.all([
    get('/api/config'),
    get('/api/scripts'),
    get('/api/clips'),
    get('/api/sfx'),
  ]);
  S.libraryPath = cfg.library_path;
  S.sfxPath = cfg.sfx_path;
  S.scripts = scripts;
  S.clips = clips;
  S.sfxFiles = sfxFiles;

  if (S.scripts.length) await loadScript(S.scripts[0]);

  renderSidebar();
  renderSentences();
  renderPicker();

  // Bind delegated listeners once — they survive innerHTML re-renders of children
  const sentPanel = document.getElementById('sentences-panel');
  sentPanel.addEventListener('click',  handleSentenceClick);
  sentPanel.addEventListener('input',  handleSentenceInput);
  sentPanel.addEventListener('change', handleSentenceChange);

  const pickPanel = document.getElementById('picker-panel');
  pickPanel.addEventListener('click', handlePickerClick);
  pickPanel.addEventListener('input', handlePickerInput);
}

init().catch(err => {
  document.body.innerHTML = `<p style="color:#f66;padding:20px;font-family:monospace">Init failed: ${esc(err.message)}</p>`;
});
