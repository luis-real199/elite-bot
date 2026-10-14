/* Demo submission: up to 10 tracks, each uploaded straight to Supabase Storage (with progress),
   then saved as one row per track sharing a submission_id. */
(function () {
  const form = document.getElementById('demo-form');
  if (!form) return;
  const C = window.BLACKLIST_CONFIG || {};
  const URL_ = C.SUPABASE_URL || '';
  const KEY = C.SUPABASE_ANON_KEY || '';
  const ready = URL_.startsWith('https://') && !URL_.includes('YOUR_') && KEY && !KEY.includes('YOUR_');
  const MAX = 50 * 1024 * 1024;
  const LIMIT = 10;
  const TYPES = { mp3: 'audio/mpeg', wav: 'audio/wav', aif: 'audio/aiff', aiff: 'audio/aiff', flac: 'audio/flac', m4a: 'audio/mp4',
    aac: 'audio/aac', ogg: 'audio/ogg', opus: 'audio/ogg', mp4: 'video/mp4', m4v: 'video/mp4', mov: 'video/quicktime', webm: 'video/webm' };
  const H = { apikey: KEY, Authorization: 'Bearer ' + KEY };

  const msg = form.querySelector('.msg');
  const bar = form.querySelector('.progress');
  const btn = form.querySelector('button[type=submit]');
  const drop = document.getElementById('drop');
  const list = document.getElementById('tracks');
  const done = document.getElementById('done');
  let tracks = [];

  const say = (t, bad) => { msg.textContent = t; msg.classList.toggle('bad', !!bad); };
  const ext = (f) => f.name.split('.').pop().toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 5) || 'bin';
  const mime = (f) => (/^(audio|video)\//.test(f.type) ? f.type : TYPES[ext(f)]);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const uuid = () => (crypto.randomUUID ? crypto.randomUUID() :
    '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, (c) => (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16)));

  function render() {
    drop.classList.toggle('has', tracks.length > 0);
    list.innerHTML = tracks.map((t, i) => `<div class="track" data-i="${i}">
      <span class="tnum">${i + 1}</span>
      <div class="tfields">
        <input data-k="name" maxlength="150" placeholder="Track name" value="${esc(t.name)}">
        <input data-k="feat" maxlength="150" placeholder="feat. (optional)" value="${esc(t.feat)}">
        <small>${esc(t.file.name)} · ${(t.file.size / 1048576).toFixed(1)} MB</small>
      </div>
      <button type="button" class="tdel" aria-label="Remove">×</button>
    </div>`).join('');
  }

  form.file.addEventListener('change', () => {
    const bad = [];
    for (const f of form.file.files) {
      if (tracks.length >= LIMIT) { bad.push(`Max ${LIMIT} tracks.`); break; }
      if (!mime(f)) bad.push(`${f.name}: not an audio or video file.`);
      else if (f.size > MAX) bad.push(`${f.name}: over 50 MB — paste a link instead.`);
      else tracks.push({ file: f, mime: mime(f), name: f.name.replace(/\.[^.]+$/, '').slice(0, 150), feat: '' });
    }
    form.file.value = '';
    render();
    say(bad.join(' '), bad.length > 0);
  });

  list.addEventListener('input', (e) => {
    const row = e.target.closest('[data-i]');
    if (row && e.target.dataset.k) tracks[row.dataset.i][e.target.dataset.k] = e.target.value;
  });
  list.addEventListener('click', (e) => {
    if (!e.target.closest('.tdel')) return;
    tracks.splice(e.target.closest('[data-i]').dataset.i, 1);
    render();
  });

  document.getElementById('again').addEventListener('click', () => {
    form.reset();
    tracks = [];
    render();
    say('');
    done.hidden = true;
    form.hidden = false;
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (form.website.value) return;
    const v = (n) => form[n].value.trim();
    const link = v('link');

    if (!v('artist')) return say('Please add your artist name.', true);
    if (!tracks.length && !/^https?:\/\//i.test(link)) return say('Upload at least one track.', true);
    if (!ready) return say('Submissions open soon.', true);

    btn.disabled = true;
    try {
      const submission_id = uuid();
      const base = { submission_id, artist: v('artist'), instagram: v('instagram') || null, link: link || null, message: v('message') || null };
      const total = tracks.reduce((s, t) => s + t.file.size, 0);
      let sent = 0;
      const rows = [];
      for (const [i, t] of tracks.entries()) {
        const x = ext(t.file);
        const file_path = `uploads/${submission_id}/${i + 1}-${Math.random().toString(36).slice(2, 8)}.${x}`;
        await upload(file_path, new File([t.file], `track.${x}`, { type: t.mime }), (loaded) => {
          const p = Math.round(((sent + loaded) / total) * 100);
          bar.firstElementChild.style.width = p + '%';
          say(`Uploading ${i + 1}/${tracks.length}… ${p}%`);
        });
        sent += t.file.size;
        rows.push({ ...base, track_no: i + 1, file_path, title: t.name.trim() || null, feat: t.feat.trim() || null });
      }
      if (!rows.length) rows.push({ ...base, title: null });

      say('Saving…');
      const r = await fetch(`${URL_}/rest/v1/demos`, {
        method: 'POST',
        headers: { ...H, 'Content-Type': 'application/json', Prefer: 'return=minimal' },
        body: JSON.stringify(rows),
      });
      if (!r.ok) throw new Error(await r.text());
      say('');
      form.hidden = true;
      done.hidden = false;
      done.scrollIntoView({ block: 'center' });
    } catch (err) {
      console.error(err);
      say('Something went wrong. Please try again.', true);
    } finally {
      btn.disabled = false;
      bar.hidden = true;
    }
  });

  function upload(path, file, onProgress) {
    return new Promise((resolve, reject) => {
      const x = new XMLHttpRequest();
      x.open('POST', `${URL_}/storage/v1/object/demos/${path}`);
      Object.entries(H).forEach(([k, val]) => x.setRequestHeader(k, val));
      x.setRequestHeader('x-upsert', 'false');
      bar.hidden = false;
      x.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded);
      x.onload = () => (x.status < 300 ? resolve() : reject(new Error(x.responseText)));
      x.onerror = () => reject(new Error('network'));
      const fd = new FormData();
      fd.append('cacheControl', '3600');
      fd.append('', file);
      x.send(fd);
    });
  }
})();
