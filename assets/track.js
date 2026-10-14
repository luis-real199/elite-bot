/* Anonymous visit counter (no cookies, no IP). One row per page view in Supabase `visits`,
   plus a heartbeat every 15s while the page is open, for "live now" and time on site. */
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

  const rpc = (fn, body) => fetch(`${C.SUPABASE_URL}/rest/v1/rpc/${fn}`, {
    method: 'POST', keepalive: true,
    headers: { apikey: C.SUPABASE_ANON_KEY, Authorization: 'Bearer ' + C.SUPABASE_ANON_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  rpc('start_visit', { p_visitor: id, p_path: location.pathname, p_source: source, p_device: device, p_tz: tz, p_lang: navigator.language || null })
    .then((r) => (r.ok ? r.json() : null))
    .then((visit) => {
      if (!visit) return;
      const ping = () => rpc('ping_visit', { p_id: visit, p_visitor: id }).catch(() => {});
      setInterval(() => !document.hidden && ping(), 15000);
      document.addEventListener('visibilitychange', ping);
      addEventListener('pagehide', ping);
    })
    .catch(() => {});
})();
