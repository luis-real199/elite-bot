/* A&R dashboard: list demos, play them back-to-back, rate, shortlist, take notes. */
(function () {
  const C = window.BLACKLIST_CONFIG || {};
  const $ = (id) => document.getElementById(id);
  if (!window.supabase || !C.SUPABASE_URL || C.SUPABASE_URL.includes('YOUR_')) {
    $('login').hidden = false;
    $('login-msg').textContent = 'Συμπλήρωσε πρώτα το config.js με τα στοιχεία του Supabase.';
    return;
  }
  const sb = supabase.createClient(C.SUPABASE_URL, C.SUPABASE_ANON_KEY);
  $('login-form').email.value = C.ADMIN_EMAIL || '';

  const STATUS = { new: 'Νέο', listened: 'Ακούστηκε', shortlist: 'Shortlist', signed: 'Υπογράφηκε', rejected: 'Απορρίφθηκε' };
  const TABS = [['all', 'Όλα'], ...Object.entries(STATUS)];
  const ICON = {
    play: '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>',
    pause: '<svg viewBox="0 0 24 24"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>',
    link: '<svg viewBox="0 0 24 24"><path d="M14 3h7v7h-2V6.4l-9.3 9.3-1.4-1.4L17.6 5H14zM5 5h6v2H5v12h12v-6h2v8H3V5z"/></svg>',
  };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const time = (s) => (isFinite(s) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}` : '0:00');
  const name = (d) => d.title || (d.track_no ? `Track ${d.track_no}` : 'Link');
  const safeUrl = (u) => (/^https?:\/\//i.test(u || '') ? u : null);

  let demos = [], tab = 'new', query = '', openId = null, current = null;
  const urls = new Map();
  const audio = $('media');
  const isVideo = (d) => /\.(mp4|m4v|mov|webm)$/i.test(d.file_path || '');

  // ---------- auth ----------
  $('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target;
    $('login-msg').textContent = '';
    const { error } = await sb.auth.signInWithPassword({ email: C.ADMIN_EMAIL, password: f.password.value });
    if (error) $('login-msg').textContent = 'Λάθος κωδικός.';
    else boot();
  });
  $('logout').addEventListener('click', async () => { await sb.auth.signOut(); location.reload(); });
  $('refresh').addEventListener('click', load);
  sb.auth.getSession().then(({ data }) => (data.session ? boot() : ($('login').hidden = false)));

  function boot() {
    $('login').hidden = true;
    $('app').hidden = false;
    load();
  }

  async function load() {
    const { data, error } = await sb.from('demos').select('*').order('created_at', { ascending: false }).order('track_no', { ascending: true }).limit(1000);
    if (error) { alert('Σφάλμα: ' + error.message); return; }
    demos = data;
    render();
  }

  // ---------- render ----------
  const visible = () => {
    const q = query.toLowerCase();
    return demos.filter((d) => (tab === 'all' || d.status === tab) &&
      (!q || [d.artist, d.title, d.feat, d.genre, d.email, d.instagram].some((x) => (x || '').toLowerCase().includes(q))));
  };

  function render() {
    const count = (k) => (k === 'all' ? demos.length : demos.filter((d) => d.status === k).length);
    $('tabs').innerHTML = TABS.map(([k, l]) => `<button type="button" data-tab="${k}" class="${tab === k ? 'on' : ''}">${l} · ${count(k)}</button>`).join('');
    const rows = visible();
    $('list').innerHTML = rows.length
      ? rows.map(card).join('')
      : `<p class="empty">${demos.length ? 'Τίποτα εδώ.' : 'Δεν υπάρχουν demos ακόμα.<br>Αν περιμένεις, έλεγξε ότι το email σου είναι στον πίνακα admins.'}</p>`;
  }

  function card(d) {
    const playing = current && current.id === d.id;
    const icon = d.file_path ? (playing && !audio.paused ? ICON.pause : ICON.play) : ICON.link;
    const sub = [d.artist + (d.feat ? ` feat. ${d.feat}` : ''), isVideo(d) && 'Video', d.genre, d.bpm && `${d.bpm} BPM`].filter(Boolean).map(esc).join(' · ');
    return `<article class="demo${playing ? ' playing' : ''}" data-id="${d.id}">
      <button class="play" type="button" data-act="play" aria-label="Play">${icon}</button>
      <div class="meta" data-act="open"><strong>${esc(name(d))}</strong><span>${sub}</span></div>
      <div class="side"><span class="badge s-${d.status}">${STATUS[d.status]}</span><span class="stars">${'★'.repeat(d.rating || 0)}</span></div>
      ${openId === d.id ? details(d) : ''}
    </article>`;
  }

  function details(d) {
    const ig = d.instagram && d.instagram.replace(/^@/, '').replace(/^https?:\/\/(www\.)?instagram\.com\//i, '').replace(/\/.*$/, '');
    const link = safeUrl(d.link);
    const info = [
      ['Ημερομηνία', new Date(d.created_at).toLocaleString('el-GR')],
      d.email && ['Email', `<a href="mailto:${esc(d.email)}">${esc(d.email)}</a>`, true],
      ig && ['Instagram', `<a href="https://instagram.com/${encodeURIComponent(ig)}" target="_blank" rel="noopener">@${esc(ig)}</a>`, true],
      link && ['Link', `<a href="${esc(link)}" target="_blank" rel="noopener">${esc(link)}</a>`, true],
      d.music_key && ['Key', d.music_key],
      d.message && ['Μήνυμα', d.message],
    ].filter(Boolean).map(([k, v, html]) => `<dt>${k}</dt><dd>${html ? v : esc(v)}</dd>`).join('');
    return `<div class="details">
      <dl>${info}</dl>
      <div class="row">${Object.entries(STATUS).map(([k, l]) => `<button type="button" class="chip${d.status === k ? ' on' : ''}" data-act="status" data-v="${k}">${l}</button>`).join('')}</div>
      <div class="rate">${[1, 2, 3, 4, 5].map((n) => `<button type="button" data-act="rate" data-v="${n}" class="${(d.rating || 0) >= n ? 'on' : ''}" aria-label="${n} αστέρια">★</button>`).join('')}</div>
      <textarea rows="3" data-act="notes" placeholder="Σημειώσεις (μόνο εσύ τις βλέπεις)">${esc(d.notes)}</textarea>
      <div class="row">
        ${d.file_path ? '<button type="button" class="chip" data-act="download">Κατέβασμα</button>' : ''}
        <button type="button" class="chip danger" data-act="delete">Διαγραφή</button>
      </div>
    </div>`;
  }

  // ---------- actions ----------
  $('tabs').addEventListener('click', (e) => {
    const b = e.target.closest('[data-tab]');
    if (b) { tab = b.dataset.tab; render(); }
  });
  $('search').addEventListener('input', (e) => { query = e.target.value.trim(); render(); });

  $('list').addEventListener('click', (e) => {
    const el = e.target.closest('[data-act]');
    const art = e.target.closest('[data-id]');
    if (!el || !art) return;
    const d = demos.find((x) => x.id === art.dataset.id);
    const v = el.dataset.v;
    switch (el.dataset.act) {
      case 'play': return d.file_path ? (current && current.id === d.id ? toggle() : play(d)) : window.open(safeUrl(d.link) || '#', '_blank', 'noopener');
      case 'open': openId = openId === d.id ? null : d.id; return render();
      case 'status': return save(d, { status: v });
      case 'rate': return save(d, { rating: d.rating === +v ? null : +v });
      case 'download': return download(d);
      case 'delete': return remove(d);
    }
  });
  $('list').addEventListener('change', (e) => {
    if (e.target.dataset.act !== 'notes') return;
    const d = demos.find((x) => x.id === e.target.closest('[data-id]').dataset.id);
    save(d, { notes: e.target.value.trim() || null }, false);
  });

  async function save(d, patch, rerender = true) {
    const before = { ...d };
    Object.assign(d, patch);
    if (rerender) render();
    const { error } = await sb.from('demos').update(patch).eq('id', d.id);
    if (error) { Object.assign(d, before); render(); alert('Δεν αποθηκεύτηκε: ' + error.message); }
  }

  async function signed(d, opts) {
    const { data, error } = await sb.storage.from('demos').createSignedUrl(d.file_path, 3600, opts);
    if (error) throw error;
    return data.signedUrl;
  }

  async function download(d) {
    try {
      const ext = d.file_path.split('.').pop();
      location.href = await signed(d, { download: `${d.artist} - ${name(d)}.${ext}` });
    } catch (err) { alert('Σφάλμα: ' + err.message); }
  }

  async function remove(d) {
    if (!confirm(`Διαγραφή του "${name(d)}" από ${d.artist};`)) return;
    if (current && current.id === d.id) { audio.pause(); current = null; $('player').hidden = true; }
    if (d.file_path) await sb.storage.from('demos').remove([d.file_path]);
    const { error } = await sb.from('demos').delete().eq('id', d.id);
    if (error) return alert('Σφάλμα: ' + error.message);
    demos = demos.filter((x) => x !== d);
    render();
  }

  // ---------- player ----------
  async function play(d) {
    current = d;
    $('player').hidden = false;
    $('now-title').textContent = name(d);
    $('now-artist').textContent = d.artist;
    try {
      const hit = urls.get(d.id);
      const url = hit && hit.exp > Date.now() ? hit.url : await signed(d);
      urls.set(d.id, { url, exp: Date.now() + 50 * 60 * 1000 });
      if (current !== d) return;
      audio.src = url;
      await audio.play();
    } catch (err) {
      if (err.name !== 'AbortError') alert('Δεν παίζει: ' + err.message);
    }
    if (d.status === 'new') save(d, { status: 'listened' });
    else render();
  }

  const toggle = () => { if (current) audio.paused ? audio.play() : audio.pause(); };
  function step(dir) {
    const q = visible().filter((d) => d.file_path);
    if (!q.length) return;
    const i = current ? q.findIndex((d) => d.id === current.id) : -1;
    const n = q[i + dir];
    if (n) play(n);
  }

  const paint = () => {
    $('toggle').innerHTML = audio.paused ? ICON.play : ICON.pause;
    const btn = current && document.querySelector(`[data-id="${current.id}"] .play`);
    if (btn) btn.innerHTML = audio.paused ? ICON.play : ICON.pause;
  };
  audio.addEventListener('play', paint);
  audio.addEventListener('pause', paint);
  audio.addEventListener('ended', () => step(1));
  audio.addEventListener('loadedmetadata', () => {
    const v = audio.videoWidth > 0;
    $('player').classList.toggle('video', v);
    document.body.classList.toggle('has-video', v);
  });
  audio.addEventListener('timeupdate', () => {
    $('t-cur').textContent = time(audio.currentTime);
    $('t-dur').textContent = time(audio.duration);
    if (audio.duration) $('seek').value = Math.round((audio.currentTime / audio.duration) * 1000);
  });
  $('seek').addEventListener('input', (e) => { if (audio.duration) audio.currentTime = (e.target.value / 1000) * audio.duration; });
  $('toggle').addEventListener('click', toggle);
  $('prev').addEventListener('click', () => step(-1));
  $('next').addEventListener('click', () => step(1));
  paint();

  // ---------- traffic & visitors ----------
  let view = 'demos', days = 30;
  const SOURCES = { direct: 'Απευθείας', instagram: 'Instagram', tiktok: 'TikTok', google: 'Google', facebook: 'Facebook',
    youtube: 'YouTube', twitter: 'X / Twitter', spotify: 'Spotify', whatsapp: 'WhatsApp', telegram: 'Telegram' };
  const DEVICES = { mobile: 'Κινητό', desktop: 'Υπολογιστής', tablet: 'Tablet' };
  const place = (tz) => (!tz ? 'Άγνωστο' : /Athens/.test(tz) ? 'Ελλάδα' : /Nicosia|Famagusta/.test(tz) ? 'Κύπρος' : tz.split('/').pop().replace(/_/g, ' '));
  const day = (d) => new Date(d + 'T12:00:00').toLocaleDateString('el-GR', { day: 'numeric', month: 'short' });
  const num = (n) => Number(n || 0).toLocaleString('el-GR');

  function hbars(list, label) {
    const merged = {};
    list.forEach((x) => { const k = label(x.name); merged[k] = (merged[k] || 0) + x.n; });
    const rows = Object.entries(merged).sort((a, b) => b[1] - a[1]);
    const max = Math.max(1, ...rows.map((r) => r[1]));
    return rows.length
      ? rows.map(([k, n]) => `<li><span>${esc(k)}</span><i style="--w:${(n / max) * 100}%"></i><b>${num(n)}</b></li>`).join('')
      : '<li class="none">Κανένα δεδομένο ακόμα</li>';
  }

  async function loadTraffic() {
    const { data: t, error } = await sb.rpc('traffic_stats', { days });
    if (error) { $('traffic').innerHTML = `<p class="empty">Σφάλμα: ${esc(error.message)}</p>`; return; }
    const max = Math.max(1, ...t.daily.map((d) => d.visitors));
    const conv = t.visitors ? Math.round((t.submissions / t.visitors) * 1000) / 10 : 0;
    $('traffic').innerHTML = `
      <div class="kpis">
        <div><small>Σήμερα</small><b>${num(t.today)}</b><span>επισκέπτες</span></div>
        <div><small>${days} ημέρες</small><b>${num(t.visitors)}</b><span>επισκέπτες</span></div>
        <div><small>Προβολές</small><b>${num(t.views)}</b><span>σελίδας</span></div>
        <div><small>Αποστολές</small><b>${num(t.submissions)}</b><span>${num(t.tracks)} tracks · ${conv}% των επισκεπτών</span></div>
      </div>
      <section class="panel">
        <h3>Επισκέπτες ανά ημέρα</h3>
        <p class="readout" id="readout">Μέγιστο ${num(max)} · άγγιξε μια μπάρα</p>
        <div class="bars">${t.daily.map((d) => `<button type="button" style="--h:${(d.visitors / max) * 100}%" data-tip="${day(d.day)} · ${num(d.visitors)} επισκέπτες · ${num(d.views)} προβολές" aria-label="${day(d.day)}: ${d.visitors} επισκέπτες"></button>`).join('')}</div>
        <div class="axis-x"><span>${t.daily.length ? day(t.daily[0].day) : ''}</span><span>Σήμερα</span></div>
      </section>
      <div class="panels">
        <section class="panel"><h3>Από πού έρχονται</h3><ul class="hbars">${hbars(t.sources, (n) => SOURCES[n] || n || 'Άγνωστο')}</ul></section>
        <section class="panel"><h3>Συσκευές</h3><ul class="hbars">${hbars(t.devices, (n) => DEVICES[n] || 'Άγνωστο')}</ul></section>
        <section class="panel"><h3>Χώρες / περιοχές</h3><ul class="hbars">${hbars(t.places, place)}</ul></section>
      </div>`;
  }

  const tip = (e) => { const b = e.target.closest('[data-tip]'); if (b) $('readout').textContent = b.dataset.tip; };
  $('traffic').addEventListener('mouseover', tip);
  $('traffic').addEventListener('click', tip);
  $('views').addEventListener('click', (e) => {
    const b = e.target.closest('[data-view]');
    if (!b) return;
    view = b.dataset.view;
    $('views').querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b));
    $('demos-view').hidden = view !== 'demos';
    $('traffic-view').hidden = view !== 'traffic';
    if (view === 'traffic') loadTraffic();
  });
  $('range').addEventListener('click', (e) => {
    const b = e.target.closest('[data-days]');
    if (!b) return;
    days = +b.dataset.days;
    $('range').querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b));
    loadTraffic();
  });
  $('refresh').addEventListener('click', () => view === 'traffic' && loadTraffic());

  document.addEventListener('keydown', (e) => {
    if (e.target.closest('input, textarea') || e.metaKey || e.ctrlKey || e.altKey || $('app').hidden || view !== 'demos') return;
    const k = e.key.toLowerCase();
    if (k === ' ') { e.preventDefault(); current ? toggle() : step(1); }
    else if (k === 'n') step(1);
    else if (k === 'p') step(-1);
    else if (k === 'arrowright') audio.currentTime += 10;
    else if (k === 'arrowleft') audio.currentTime -= 10;
    else if (current && k === 's') save(current, { status: 'shortlist' });
    else if (current && k === 'x') save(current, { status: 'rejected' });
    else if (current && k >= '1' && k <= '5') save(current, { rating: +k });
  });
})();
