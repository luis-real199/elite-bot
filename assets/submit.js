/* Demo submission: uploads the file straight to Supabase Storage (with progress), then saves the row. */
(function () {
  const form = document.getElementById('demo-form');
  if (!form) return;
  const C = window.BLACKLIST_CONFIG || {};
  const URL_ = C.SUPABASE_URL || '';
  const KEY = C.SUPABASE_ANON_KEY || '';
  const ready = URL_.startsWith('https://') && !URL_.includes('YOUR_') && KEY && !KEY.includes('YOUR_');
  const MAX = 50 * 1024 * 1024;
  const TYPES = { mp3: 'audio/mpeg', wav: 'audio/wav', aif: 'audio/aiff', aiff: 'audio/aiff', flac: 'audio/flac', m4a: 'audio/mp4' };
  const H = { apikey: KEY, Authorization: 'Bearer ' + KEY };

  const msg = form.querySelector('.msg');
  const bar = form.querySelector('.progress');
  const btn = form.querySelector('button[type=submit]');
  const drop = document.getElementById('drop');
  const fname = document.getElementById('file-name');
  const done = document.getElementById('done');
  const fileHint = fname.textContent;

  const say = (t, bad) => { msg.textContent = t; msg.classList.toggle('bad', !!bad); };

  form.file.addEventListener('change', () => {
    const f = form.file.files[0];
    fname.textContent = f ? `${f.name} · ${(f.size / 1048576).toFixed(1)} MB` : fileHint;
    drop.classList.toggle('has', !!f);
  });

  document.getElementById('again').addEventListener('click', () => {
    form.reset();
    form.file.dispatchEvent(new Event('change'));
    say('');
    done.hidden = true;
    form.hidden = false;
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (form.website.value) return;
    const v = (n) => form[n].value.trim();
    const f = form.file.files[0];
    const ext = f ? f.name.split('.').pop().toLowerCase() : '';

    if (!v('artist') || !v('title')) return say('Please add your artist name and track title.', true);
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v('email'))) return say('Please add a valid email.', true);
    if (!f && !/^https?:\/\//i.test(v('link'))) return say('Upload a file or paste a link to your track.', true);
    if (f && !TYPES[ext]) return say('Please use MP3, WAV, AIFF, FLAC or M4A.', true);
    if (f && f.size > MAX) return say('File is over 50 MB — paste a link instead.', true);
    if (!form.rights.checked) return say('Please confirm you own the rights.', true);
    if (!ready) return say('Submissions open soon.', true);

    btn.disabled = true;
    try {
      let file_path = null;
      if (f) {
        file_path = `uploads/${Date.now()}-${Math.random().toString(36).slice(2, 10)}.${ext}`;
        await upload(file_path, new File([f], `track.${ext}`, { type: TYPES[ext] }));
      }
      say('Saving…');
      const bpm = parseInt(v('bpm'), 10);
      const row = {
        artist: v('artist'), email: v('email'), title: v('title'),
        genre: v('genre') || null, bpm: bpm >= 40 && bpm <= 250 ? bpm : null,
        music_key: v('music_key') || null, instagram: v('instagram') || null,
        link: v('link') || null, message: v('message') || null, file_path,
      };
      const r = await fetch(`${URL_}/rest/v1/demos`, {
        method: 'POST',
        headers: { ...H, 'Content-Type': 'application/json', Prefer: 'return=minimal' },
        body: JSON.stringify(row),
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

  function upload(path, file) {
    return new Promise((resolve, reject) => {
      const x = new XMLHttpRequest();
      x.open('POST', `${URL_}/storage/v1/object/demos/${path}`);
      Object.entries(H).forEach(([k, val]) => x.setRequestHeader(k, val));
      x.setRequestHeader('x-upsert', 'false');
      bar.hidden = false;
      x.upload.onprogress = (e) => {
        if (!e.lengthComputable) return;
        const p = Math.round((e.loaded / e.total) * 100);
        bar.firstElementChild.style.width = p + '%';
        say(`Uploading… ${p}%`);
      };
      x.onload = () => (x.status < 300 ? resolve() : reject(new Error(x.responseText)));
      x.onerror = () => reject(new Error('network'));
      const fd = new FormData();
      fd.append('cacheControl', '3600');
      fd.append('', file);
      x.send(fd);
    });
  }
})();
