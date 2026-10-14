/* Anonymous visit counter (no cookies, no IP): one row per page view in Supabase `visits`. */
(function () {
  const C = window.BLACKLIST_CONFIG || {};
  if (!C.SUPABASE_URL || C.SUPABASE_URL.includes('YOUR_') || navigator.webdriver) return;
  let id = null;
  try {
    id = localStorage.getItem('bl_vid');
    if (!id) localStorage.setItem('bl_vid', (id = Math.random().toString(36).slice(2) + Date.now().toString(36)));
  } catch (e) { /* private mode: count as anonymous */ }
  const ua = navigator.userAgent;
  const host = (() => { try { return new URL(document.referrer).hostname.replace(/^www\./, ''); } catch (e) { return ''; } })();
  const KNOWN = [['instagram', /instagram/i], ['tiktok', /tiktok|musical_ly|bytedance/i], ['facebook', /facebook|fb\.|FBAN|FBAV/i],
    ['google', /google\./i], ['youtube', /youtube|youtu\.be/i], ['twitter', /^t\.co$|twitter|x\.com/i], ['spotify', /spotify/i],
    ['whatsapp', /whatsapp/i], ['telegram', /telegram|t\.me/i]];
  let source = (new URLSearchParams(location.search).get('utm_source') || '').toLowerCase();
  if (!source && host && host !== location.hostname) source = (KNOWN.find(([, r]) => r.test(host)) || [host])[0];
  if (!source) source = (KNOWN.find(([, r]) => r.test(ua)) || ['direct'])[0]; // in-app browsers (Instagram, TikTok…)
  const device = /iPad|Tablet/i.test(ua) ? 'tablet' : /Mobi|Android|iPhone/i.test(ua) ? 'mobile' : 'desktop';
  let tz = null;
  try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone || null; } catch (e) { /* ignore */ }
  fetch(`${C.SUPABASE_URL}/rest/v1/visits`, {
    method: 'POST', keepalive: true,
    headers: { apikey: C.SUPABASE_ANON_KEY, Authorization: 'Bearer ' + C.SUPABASE_ANON_KEY, 'Content-Type': 'application/json', Prefer: 'return=minimal' },
    body: JSON.stringify({ visitor: id, path: location.pathname.slice(0, 200), source: source.slice(0, 100), device, tz: tz && tz.slice(0, 60), lang: (navigator.language || '').slice(0, 20) }),
  }).catch(() => {});
})();
