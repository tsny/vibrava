'use strict';

// ─── Constants ──────────────────────────────────────────────────────────────

const IMAGE_EXTS = new Set(['.jpg', '.jpeg', '.png', '.webp']);
const GIF_EXTS   = new Set(['.gif']);
const VIDEO_EXTS = new Set(['.mp4', '.mov', '.webm']);
const ALL_IMG    = new Set([...IMAGE_EXTS, ...GIF_EXTS]);

const TYPE_FILTER_EXTS = { 'jpg/png': IMAGE_EXTS, 'gif': GIF_EXTS, 'mp4': VIDEO_EXTS };
const PAGE_SIZE = 50;
const COLS = 7;

const ELEVENLABS_VOICES = [
  ['21m00Tcm4TlvDq8ikWAM', 'Rachel - Calm, Confident Narrator'],
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
  ['XB0fDUnXU5powFXDhCwa', 'Charlotte - Mature, Elegant British'],
  ['XrExE9yKIg1WjnnlVkGX', 'Matilda - Knowledgable, Professional'],
  ['bIHbv24MWmeRgasZH58o', 'Will - Relaxed Optimist'],
  ['onwK4e9ZLuTAKqWW03F9', 'Daniel - Deep, Refined British Narrator'],
  ['pFZP5JQG7iQjIQuC4Bku', 'Lily - Warm, Friendly, Conversational'],
  ['pNInz6obpgDQGcFmaJgB', 'Adam - Deep, Authoritative'],
];

const TIKTOK_VOICES = [
  ['en_us_001', 'Female (en_us_001)'],
  ['en_us_002', 'Male (en_us_002)'],
  ['en_us_006', 'Joey'],
  ['en_us_007', 'Professor'],
  ['en_us_009', 'Scientist'],
  ['en_us_010', 'Confidence'],
  ['en_whisper', 'Whisper'],
  ['en_male_narration', 'Story Teller'],
  ['en_male_funny', 'Funny'],
  ['en_female_emotional', 'Emotional'],
  ['en_male_m03_lobby', 'Podcast'],
  ['en_male_m03_sunshine_soon', 'Sunshine Soon'],
  ['en_us_ghostface', 'Ghostface (Scream)'],
  ['en_us_chewbacca', 'Chewbacca'],
  ['en_us_c3po', 'C3PO'],
  ['en_us_stitch', 'Stitch'],
  ['en_us_stormtrooper', 'Stormtrooper'],
  ['en_us_rocket', 'Rocket'],
  ['en_female_madam_leota', 'Madam Leota'],
  ['en_male_grinch', 'Grinch'],
  ['en_male_jarvis', 'Jarvis'],
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
  slot: 'image',   // 'image' | 'image2' | 'overlay_image'
  search: '',
  activeTags: new Set(),
  typeFilter: 'all',
  page: 0,
  saveStatus: '',
  density: localStorage.getItem('vibrava_density') || 'spacious',
};

const videoCache = new Map();
const imgBlobCache = new Map(); // file → blob URL
const sfxAudio = new Audio();
const ttsAudio = new Audio();
let sfxPreviewTimeout = null;

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
const sfxUrl = f => `/sfx/${f.split('/').map(encodeURIComponent).join('/')}`;
const isVideo = f => VIDEO_EXTS.has(ext(f));

function estimateDuration(text) {
  const words = (text || '').trim().split(/\s+/).filter(Boolean).length;
  if (!words) return null;
  return (words / 2.5).toFixed(1);
}

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
  if (S.activeTags.size) {
    clips = clips.filter(c => {
      const clipTags = new Set((c.tags || []).map(t => t.toLowerCase()));
      return [...S.activeTags].some(t => clipTags.has(t));
    });
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
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <h2 style="font-size:1em;font-weight:700;color:#ccc">Vibrava Editor</h2>
      <button id="settings-btn" class="btn sec" style="padding:3px 8px;font-size:0.85em" title="Settings">⚙️</button>
    </div>

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

      <label class="lbl">Voice</label>
      <select id="ss-voiceid" class="inp" style="width:100%">
        <option value="">— default —</option>
        ${((d.tts_provider || 'elevenlabs') === 'tiktok' ? TIKTOK_VOICES : ELEVENLABS_VOICES)
          .map(([id, name]) => `<option value="${esc(id)}"${d.voice_id === id ? ' selected' : ''}>${esc(name)}</option>`).join('')}
      </select>

      <label class="lbl">Caption style</label>
      <select id="ss-caption" class="inp" style="width:100%">
        ${['chunk', 'word', 'line', 'none'].map(v => `<option value="${v}"${(d.caption_style || 'chunk') === v ? ' selected' : ''}>${v}</option>`).join('')}
      </select>

      <label class="lbl">Caption font size (px, blank = auto)</label>
      <input id="ss-capfont" class="inp" type="number" min="8" max="300" step="1" style="width:100%"
        value="${d.caption_font_size ?? ''}" placeholder="auto">

      <label class="lbl">Caption vertical position</label>
      <div style="display:flex;align-items:center;gap:6px">
        <input id="ss-capy" type="range" min="0" max="100" step="1" style="flex:1"
          value="${d.caption_y_pct ?? 80}">
        <span id="ss-capy-val" style="color:#ccc;font-size:0.85em;min-width:32px;text-align:right">${d.caption_y_pct ?? 80}%</span>
      </div>

      <label class="lbl">Output filename</label>
      <input id="ss-outfile" class="inp" style="width:100%" value="${esc(d.output_filename || 'output.mp4')}">

      <label class="lbl">Music file</label>
      <input id="ss-music" class="inp" style="width:100%" value="${esc(d.music || '')}">

      <label class="lbl">Music volume</label>
      <div style="display:flex;align-items:center;gap:6px">
        <input id="ss-musicvol" type="range" min="0" max="1" step="0.01" style="flex:1"
          value="${d.music_volume ?? 0.15}">
        <span id="ss-musicvol-val" style="color:#ccc;font-size:0.85em;min-width:36px;text-align:right">${Math.round((d.music_volume ?? 0.15) * 100)}%</span>
      </div>

      <label class="lbl">Pitch shift (semitones, 0 = off)</label>
      <input id="ss-pitch" class="inp" type="number" step="0.5" style="width:100%"
        value="${d.pitch_shift ?? 0}" placeholder="0">

      <label class="lbl">Speed</label>
      <div style="display:flex;align-items:center;gap:6px">
        <input id="ss-speed" type="range" min="0.5" max="2.0" step="0.05" style="flex:1"
          value="${d.speed ?? 1.0}">
        <span id="ss-speed-val" style="color:#ccc;font-size:0.85em;min-width:36px;text-align:right">${((d.speed ?? 1.0)).toFixed(2)}×</span>
      </div>

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

// ─── Settings modal ──────────────────────────────────────────────────────────

function applyDensity() {
  document.getElementById('app').classList.toggle('compact', S.density === 'compact');
  localStorage.setItem('vibrava_density', S.density);
}

function openSettings() {
  let modal = document.getElementById('settings-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'settings-modal';
    modal.addEventListener('click', e => { if (e.target === modal) closeSettings(); });
    document.body.appendChild(modal);
  }
  modal.innerHTML = `
    <div class="settings-box">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
        <strong style="font-size:1em">Settings</strong>
        <button id="settings-close" class="btn sec" style="padding:2px 8px">✕</button>
      </div>
      <label class="lbl" style="margin-top:0">Sentence density</label>
      <div style="display:flex;gap:6px;margin-top:6px">
        <button class="btn ${S.density === 'spacious' ? 'pri' : 'sec'} density-btn" data-density="spacious" style="flex:1">Spacious</button>
        <button class="btn ${S.density === 'compact' ? 'pri' : 'sec'} density-btn" data-density="compact" style="flex:1">Compact</button>
      </div>
    </div>
  `;
  modal.classList.add('open');
  document.getElementById('settings-close').addEventListener('click', closeSettings);
  modal.querySelectorAll('.density-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      S.density = btn.dataset.density;
      applyDensity();
      modal.querySelectorAll('.density-btn').forEach(b => {
        b.classList.toggle('pri', b.dataset.density === S.density);
        b.classList.toggle('sec', b.dataset.density !== S.density);
      });
    });
  });
}

function closeSettings() {
  document.getElementById('settings-modal')?.classList.remove('open');
}

function bindSidebar() {
  document.getElementById('settings-btn')?.addEventListener('click', openSettings);

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
    S.scriptData.voice_id = null;
    updateVoiceDropdowns();
  });

  document.getElementById('ss-voiceid')?.addEventListener('change', e => {
    S.scriptData.voice_id = e.target.value || null;
  });

  document.getElementById('ss-caption')?.addEventListener('change', e => {
    S.scriptData.caption_style = e.target.value;
  });

  document.getElementById('ss-capfont')?.addEventListener('input', e => {
    const v = parseInt(e.target.value);
    S.scriptData.caption_font_size = isNaN(v) ? null : v;
  });

  document.getElementById('ss-capy')?.addEventListener('input', e => {
    const v = parseInt(e.target.value);
    S.scriptData.caption_y_pct = v;
    const span = document.getElementById('ss-capy-val');
    if (span) span.textContent = v + '%';
  });

  document.getElementById('ss-outfile')?.addEventListener('input', e => {
    S.scriptData.output_filename = e.target.value;
  });

  document.getElementById('ss-music')?.addEventListener('input', e => {
    S.scriptData.music = e.target.value || null;
  });

  document.getElementById('ss-musicvol')?.addEventListener('input', e => {
    const v = parseFloat(e.target.value);
    S.scriptData.music_volume = v;
    const span = document.getElementById('ss-musicvol-val');
    if (span) span.textContent = Math.round(v * 100) + '%';
  });

  document.getElementById('ss-pitch')?.addEventListener('input', e => {
    const v = parseFloat(e.target.value);
    S.scriptData.pitch_shift = isNaN(v) ? 0.0 : v;
  });

  document.getElementById('ss-speed')?.addEventListener('input', e => {
    const v = parseFloat(e.target.value);
    S.scriptData.speed = isNaN(v) ? 1.0 : v;
    const span = document.getElementById('ss-speed-val');
    if (span) span.textContent = v.toFixed(2) + '×';
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

function updateVoiceDropdowns() {
  const isTiktok = (S.scriptData?.tts_provider || 'elevenlabs') === 'tiktok';
  const voices = isTiktok ? TIKTOK_VOICES : ELEVENLABS_VOICES;
  const defaultOpt = '<option value="">— default —</option>';
  const opts = voices.map(([id, name]) => `<option value="${esc(id)}">${esc(name)}</option>`).join('');

  const globalSel = document.getElementById('ss-voiceid');
  if (globalSel) globalSel.innerHTML = defaultOpt + opts;

  document.querySelectorAll('.svoice').forEach(sel => {
    const cur = sel.value;
    sel.innerHTML = '<option value="">— voice default —</option>' + opts;
    // keep selection if same voice exists in new list
    if (voices.some(([id]) => id === cur)) sel.value = cur;
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
  const dur = estimateDuration(s.text);

  return `
    <div class="srow${isSel ? ' srow-sel' : ''}" data-si="${i}">
      <div class="srow-num">${i + 1}</div>
      <div class="srow-fields">
        <textarea class="inp stxt" data-si="${i}" rows="3">${esc(s.text || '')}</textarea>
        <div class="srow-controls">
          <div class="field-group field-group-wide">
            <span class="field-lbl">Sound Effect</span>
            <div style="display:flex;gap:4px">
              <select class="inp ssfx" data-si="${i}" style="flex:1;min-width:80px">
                ${sfxOpts.map(f => `<option value="${esc(f)}"${curSfx === f ? ' selected' : ''}>${esc(f)}</option>`).join('')}
              </select>
              ${s.sound_effect ? `<button class="btn sec ssfxplay" data-si="${i}" title="Play sound effect" style="padding:5px 8px;flex-shrink:0">▶</button>` : ''}
            </div>
          </div>
          ${s.sound_effect ? `
            <div class="field-group field-group-sm">
              <span class="field-lbl">SFX Offset (s)</span>
              <input class="inp ssfxofs" type="number" data-si="${i}"
                value="${s.sfx_offset ?? 0}" min="0" step="0.1">
            </div>
            <div class="field-group field-group-sm">
              <span class="field-lbl">SFX Dur (s)</span>
              <input class="inp ssfxdur" type="number" data-si="${i}"
                value="${s.sfx_duration ?? ''}" min="0" step="0.1" placeholder="full">
            </div>
            <div class="field-group field-group-sm">
              <span class="field-lbl">SFX Vol</span>
              <input class="inp ssfxvol" type="number" data-si="${i}"
                value="${s.sfx_volume ?? ''}" min="0" max="2" step="0.05" placeholder="—">
            </div>
          ` : ''}
          <div class="field-group field-group-wide">
            <span class="field-lbl">Voice</span>
            <select class="inp svoice" data-si="${i}" style="min-width:120px">
              <option value="">— voice default —</option>
              ${((S.scriptData?.tts_provider || 'elevenlabs') === 'tiktok' ? TIKTOK_VOICES : ELEVENLABS_VOICES)
                .map(([id, name]) => `<option value="${esc(id)}"${s.voice_id === id ? ' selected' : ''}>${esc(name)}</option>`).join('')}
            </select>
          </div>
          <div class="field-group field-group-sm">
            <span class="field-lbl">Pause (s)</span>
            <input class="inp spause" type="number" data-si="${i}"
              value="${s.pause_duration ?? ''}" min="0" step="0.1" placeholder="—">
          </div>
          <div class="field-group field-group-sm">
            <span class="field-lbl">Pitch (st)</span>
            <input class="inp spitch" type="number" data-si="${i}"
              value="${s.pitch_shift ?? ''}" step="0.5" placeholder="—">
          </div>
          <div class="field-group field-group-sm">
            <span class="field-lbl">Speed ×</span>
            <input class="inp sspeed" type="number" data-si="${i}"
              value="${s.speed ?? ''}" min="0.5" max="2.0" step="0.05" placeholder="—">
          </div>
          <div class="field-group" style="justify-content:flex-end">
            <span class="sdur muted" style="font-size:0.78em;white-space:nowrap;padding-bottom:6px">${dur !== null ? `~${dur}s` : ''}</span>
          </div>
        </div>
        ${s.overlay_image ? `
        <div class="srow-controls" style="margin-top:4px">
          <div class="field-group field-group-sm">
            <span class="field-lbl">Overlay Opacity</span>
            <input class="inp sovopa" type="number" data-si="${i}"
              value="${s.overlay_opacity ?? 1}" min="0" max="1" step="0.05">
          </div>
          <div class="field-group field-group-sm">
            <span class="field-lbl">Overlay Size (%)</span>
            <input class="inp sovsize" type="number" data-si="${i}"
              value="${Math.round((s.overlay_size ?? 1/3) * 100)}" min="1" max="100" step="1">
          </div>
        </div>
        ` : ''}
      </div>
      ${thumbColHtml(s.image, 'image', i, isSel)}
      ${thumbColHtml(s.image2, 'image2', i, isSel)}
      ${thumbColHtml(s.overlay_image, 'overlay_image', i, isSel)}
      <div style="display:flex;flex-direction:column;gap:4px;align-self:flex-start;margin-top:4px">
        <button class="btn sec sttsplay" data-si="${i}" title="Preview TTS" style="padding:4px 8px">🔊</button>
        <button class="btn sec sdup" data-si="${i}" title="Duplicate" style="padding:4px 8px">⧉</button>
        <button class="btn sec sdel" data-si="${i}" title="Remove" style="padding:4px 8px">✕</button>
      </div>
    </div>
  `;
}

function thumbColHtml(file, slot, si, isSel) {
  const isActive = isSel && S.slot === slot;
  const label = slot === 'image' ? '1️⃣' : slot === 'image2' ? '2️⃣' : '🔲';
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
  const playTts = e.target.closest('.sttsplay');
  if (playTts) {
    const i = +playTts.dataset.si;
    const s = S.scriptData?.sentences?.[i];
    const text = s?.text?.trim();
    if (!text) return;
    const voiceInput = document.querySelector(`.svoice[data-si="${i}"]`);
    const voiceId = voiceInput?.value?.trim() || S.scriptData?.voice_id || '';
    const pitchShift = s.pitch_shift ?? S.scriptData?.pitch_shift ?? 0;
    const speed = s.speed ?? S.scriptData?.speed ?? 1.0;
    playTts.textContent = '⏳';
    playTts.disabled = true;
    fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice_id: voiceId, provider: S.scriptData?.tts_provider || 'elevenlabs', pitch_shift: pitchShift, speed }),
    }).then(r => {
      if (!r.ok) return r.json().then(d => { throw new Error(d.error || r.status); });
      return r.blob();
    }).then(blob => {
      const url = URL.createObjectURL(blob);
      ttsAudio.pause();
      ttsAudio.src = url;
      clearTimeout(sfxPreviewTimeout);
      sfxAudio.pause();
      ttsAudio.play().catch(err => console.warn('TTS playback failed:', err));
      if (s.sound_effect) {
        const offset = (s.sfx_offset ?? 0) * 1000;
        const vol = s.sfx_volume ?? S.scriptData?.sfx_volume ?? 1.0;
        sfxPreviewTimeout = setTimeout(() => {
          sfxAudio.src = sfxUrl(s.sound_effect);
          sfxAudio.volume = Math.max(0, Math.min(2, vol));
          sfxAudio.play().catch(err => console.warn('SFX playback failed:', err));
        }, offset);
      }
    }).catch(err => {
      alert('TTS failed: ' + err.message);
    }).finally(() => {
      playTts.textContent = '🔊';
      playTts.disabled = false;
    });
    return;
  }

  const playSfx = e.target.closest('.ssfxplay');
  if (playSfx) {
    const s = S.scriptData?.sentences?.[+playSfx.dataset.si];
    if (s?.sound_effect) {
      sfxAudio.pause();
      sfxAudio.currentTime = 0;
      sfxAudio.src = sfxUrl(s.sound_effect);
      sfxAudio.play().catch(err => console.warn('SFX playback failed:', err));
    }
    return;
  }

  const dup = e.target.closest('.sdup');
  if (dup) {
    const i = +dup.dataset.si;
    const clone = JSON.parse(JSON.stringify(S.scriptData.sentences[i]));
    clone.id = nextId(S.scriptData.sentences);
    S.scriptData.sentences.splice(i + 1, 0, clone);
    if (S.sel !== null && S.sel > i) S.sel++;
    renderSentences();
    renderPicker();
    return;
  }

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

  if (e.target.classList.contains('stxt')) {
    s.text = e.target.value;
    const dur = estimateDuration(s.text);
    const row = e.target.closest('.srow');
    const badge = row?.querySelector('.sdur');
    if (badge) badge.textContent = dur !== null ? `~${dur}s` : '';
  }
  if (e.target.classList.contains('ssfxofs'))  s.sfx_offset = parseFloat(e.target.value) || 0;
  if (e.target.classList.contains('ssfxdur'))  { const v = parseFloat(e.target.value); s.sfx_duration = isNaN(v) || e.target.value === '' ? null : v; }
  if (e.target.classList.contains('ssfxvol'))  { const v = parseFloat(e.target.value); s.sfx_volume = isNaN(v) || e.target.value === '' ? null : v; }
  if (e.target.classList.contains('spause'))   { const v = parseFloat(e.target.value); s.pause_duration = isNaN(v) ? null : v; }
  if (e.target.classList.contains('spitch'))   { const v = parseFloat(e.target.value); s.pitch_shift = isNaN(v) || e.target.value === '' ? null : v; }
  if (e.target.classList.contains('sspeed'))   { const v = parseFloat(e.target.value); s.speed = isNaN(v) || e.target.value === '' ? null : v; }
  if (e.target.classList.contains('sovopa'))   { const v = parseFloat(e.target.value); s.overlay_opacity = isNaN(v) ? 1.0 : Math.max(0, Math.min(1, v)); }
  if (e.target.classList.contains('sovsize'))  { const v = parseFloat(e.target.value); s.overlay_size = isNaN(v) ? 1/3 : Math.max(1, Math.min(100, v)) / 100; }
}

function handleSentenceChange(e) {
  const si = e.target.dataset.si;
  if (si === undefined) return;
  const i = +si;
  const s = S.scriptData.sentences[i];
  if (!s) return;

  if (e.target.classList.contains('svoice')) {
    s.voice_id = e.target.value || null;
    return;
  }

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
        ? `<div class="clip-thumb asgn" data-video-thumb="${esc(clip.file)}" data-file="${esc(clip.file)}" ${disabled ? 'data-disabled' : ''} style="cursor:${disabled ? 'default' : 'pointer'}"></div>`
        : `<img src="${cachedSrc || ''}" data-file="${esc(clip.file)}" loading="lazy" class="clip-thumb asgn" ${disabled ? 'data-disabled' : ''} style="cursor:${disabled ? 'default' : 'pointer'}">`;
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
  const slotLabel = S.slot === 'image' ? 'Image 1' : S.slot === 'image2' ? 'Image 2 (½ way)' : 'Overlay Image';

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
  const tags = topTags(60);
  const tagHtml = tags.length ? `
    <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px">
      ${tags.map(t => `<button class="btn ${S.activeTags.has(t.toLowerCase()) ? 'pri' : 'sec'} tagbtn" data-tag="${esc(t)}" style="padding:2px 8px;font-size:0.78em">${esc(t)}</button>`).join('')}
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
      ${curThumb(s?.overlay_image, 'overlay_image', 'Overlay')}
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
    const t = tag.dataset.tag.toLowerCase();
    S.activeTags.has(t) ? S.activeTags.delete(t) : S.activeTags.add(t);
    S.page = 0;
    document.querySelectorAll('.tagbtn').forEach(btn => {
      const bt = btn.dataset.tag.toLowerCase();
      btn.classList.toggle('pri', S.activeTags.has(bt));
      btn.classList.toggle('sec', !S.activeTags.has(bt));
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
  if (asgn && S.sel !== null && !asgn.hasAttribute('data-disabled') && !asgn.disabled) {
    const file = asgn.dataset.file;
    const hadOverlay = !!S.scriptData.sentences[S.sel].overlay_image;
    S.scriptData.sentences[S.sel][S.slot] = file;
    if (S.slot === 'overlay_image' && !hadOverlay) {
      // Re-render the row to show the new overlay controls
      const row = document.querySelector(`.srow[data-si="${S.sel}"]`);
      if (row) {
        row.outerHTML = sentenceRowHtml(S.scriptData.sentences[S.sel], S.sel);
        fillVideoThumbs(document.getElementById('sentences-panel'));
      }
    } else {
      const thumbCol = document.querySelector(`.sthumb[data-slot="${S.slot}"][data-si="${S.sel}"]`);
      if (thumbCol) {
        thumbCol.outerHTML = thumbColHtml(file, S.slot, S.sel, true);
        fillVideoThumbs(document.getElementById('sentences-panel'));
      }
    }
    renderPicker();
    return;
  }

  const clr = e.target.closest('.clr-btn');
  if (clr && S.sel !== null) {
    const slot = clr.dataset.slot;
    S.scriptData.sentences[S.sel][slot] = null;
    if (slot === 'overlay_image') {
      // Re-render the row to remove the overlay controls
      const row = document.querySelector(`.srow[data-si="${S.sel}"]`);
      if (row) {
        row.outerHTML = sentenceRowHtml(S.scriptData.sentences[S.sel], S.sel);
        fillVideoThumbs(document.getElementById('sentences-panel'));
      }
    } else {
      const thumbCol = document.querySelector(`.sthumb[data-slot="${slot}"][data-si="${S.sel}"]`);
      if (thumbCol) {
        thumbCol.outerHTML = thumbColHtml(null, slot, S.sel, true);
      }
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
    const d = S.scriptData || {};
    const capFont = d.caption_font_size != null ? `&capfont=${d.caption_font_size}` : '';
    const capY = d.caption_y_pct != null ? `&capy=${d.caption_y_pct}` : '';
    const url = `/api/preview?name=${encodeURIComponent(S.scriptName)}&idx=${S.sel}${capFont}${capY}&t=${Date.now()}`;
    showPreviewModal(url);
  } finally {
    if (btn) { btn.textContent = '🖼 Preview'; btn.disabled = false; }
  }
}

// ─── Script loading ───────────────────────────────────────────────────────────

function setUrlScript(name) {
  const url = new URL(location.href);
  url.searchParams.set('script', name);
  history.replaceState(null, '', url);
}

async function loadScript(name) {
  const data = await get(`/api/script?name=${encodeURIComponent(name)}`);
  S.scriptName = name;
  S.scriptData = data;
  setUrlScript(name);
  if (!Array.isArray(S.scriptData.sentences)) S.scriptData.sentences = [];
  ensureIds(S.scriptData.sentences);
  S.sel = null;
  S.search = '';
  S.activeTags = new Set();
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
  applyDensity();

  if (S.scripts.length) {
    const urlScript = new URLSearchParams(location.search).get('script');
    const initial = (urlScript && S.scripts.includes(urlScript)) ? urlScript : S.scripts[0];
    await loadScript(initial);
  }

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
