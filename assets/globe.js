/* Blacklist Records — rotating night globe with Greece & Cyprus lit.
   Canvas 2D + d3-geo. Throttled to 30fps on phones, paused when off-screen. */
(function () {
  const cv = document.getElementById('globe');
  if (!cv || !window.d3) return;
  const ctx = cv.getContext('2d');
  const small = matchMedia('(max-width: 768px)').matches || (navigator.hardwareConcurrency || 8) <= 4;
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const DPR = Math.min(window.devicePixelRatio || 1, small ? 1.5 : 2);
  const FRAME = 1000 / (small ? 30 : 50);
  const LAT = 22;      // view tilt: Europe slightly from above, like the logo
  const FOCUS = 26;    // slow down when Greece/Cyprus face the viewer
  const SPEED = 9;     // degrees per second
  const RAD = Math.PI / 180;

  const proj = d3.geoOrthographic().clipAngle(90).precision(0.8);
  const path = d3.geoPath(proj, ctx);
  const grat = d3.geoGraticule10();
  const xyz = ([l, p]) => [Math.cos(p * RAD) * Math.cos(l * RAD), Math.cos(p * RAD) * Math.sin(l * RAD), Math.sin(p * RAD)];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

  let land, borders, hl, lights = [], gold = [], spots = [];
  let size = 0, R = 0, base, shade, glow;
  let lon = 62, last = 0, running = false, onScreen = true;

  function layer(fn) {
    const c = document.createElement('canvas');
    c.width = c.height = Math.round(size * DPR);
    const g = c.getContext('2d');
    g.scale(DPR, DPR);
    fn(g, size / 2);
    return c;
  }

  function sprite() {
    const c = document.createElement('canvas');
    c.width = c.height = 64;
    const g = c.getContext('2d');
    const r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    r.addColorStop(0, 'rgba(255,196,110,0.8)');
    r.addColorStop(0.25, 'rgba(255,160,60,0.4)');
    r.addColorStop(1, 'rgba(255,130,30,0)');
    g.fillStyle = r;
    g.fillRect(0, 0, 64, 64);
    return c;
  }

  function resize() {
    const s = Math.round(cv.clientWidth);
    if (!s || s === size) return;
    size = s;
    R = s * 0.41;
    cv.width = cv.height = Math.round(s * DPR);
    proj.translate([s / 2, s / 2]).scale(R);

    base = layer((g, c) => {
      const haze = g.createRadialGradient(c, c, R * 0.92, c, c, R * 1.22);
      haze.addColorStop(0, 'rgba(255,190,120,0.16)');
      haze.addColorStop(0.3, 'rgba(255,170,90,0.05)');
      haze.addColorStop(1, 'rgba(0,0,0,0)');
      g.fillStyle = haze;
      g.fillRect(0, 0, s, s);
      const body = g.createRadialGradient(c * 0.84, c * 0.76, R * 0.1, c, c, R);
      body.addColorStop(0, '#202022');
      body.addColorStop(0.7, '#0b0b0c');
      body.addColorStop(1, '#040404');
      g.fillStyle = body;
      g.beginPath(); g.arc(c, c, R, 0, 2 * Math.PI); g.fill();
    });

    shade = layer((g, c) => {
      const d = g.createRadialGradient(c * 0.9, c * 0.8, R * 0.2, c, c, R * 1.01);
      d.addColorStop(0, 'rgba(0,0,0,0)');
      d.addColorStop(0.72, 'rgba(0,0,0,0.25)');
      d.addColorStop(1, 'rgba(0,0,0,0.78)');
      g.fillStyle = d;
      g.beginPath(); g.arc(c, c, R, 0, 2 * Math.PI); g.fill();
      const rim = g.createLinearGradient(c - R, c + R, c + R, c - R);
      rim.addColorStop(0, 'rgba(255,255,255,0.04)');
      rim.addColorStop(0.55, 'rgba(255,225,180,0.22)');
      rim.addColorStop(1, 'rgba(255,205,145,0.95)');
      g.strokeStyle = rim;
      g.lineWidth = 1.5;
      g.beginPath(); g.arc(c, c, R, 0, 2 * Math.PI); g.stroke();
    });

    glow = glow || sprite();
    if (!running) draw(performance.now());
  }

  function draw(t) {
    const s = size;
    if (!s) return;
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    ctx.clearRect(0, 0, s, s);
    ctx.drawImage(base, 0, 0, s, s);
    if (!land) return;

    proj.rotate([-lon, -LAT]);
    const view = xyz([lon, LAT]);
    const pulse = 0.5 + 0.5 * Math.sin(t * 0.0025);
    ctx.lineJoin = 'round';

    ctx.beginPath(); path(grat);
    ctx.strokeStyle = 'rgba(255,255,255,0.055)'; ctx.lineWidth = 0.6; ctx.stroke();

    ctx.beginPath(); path(land);
    ctx.fillStyle = 'rgba(165,165,170,0.17)'; ctx.fill();
    ctx.strokeStyle = 'rgba(240,228,210,0.45)'; ctx.lineWidth = 0.7; ctx.stroke();

    ctx.beginPath(); path(borders);
    ctx.strokeStyle = 'rgba(240,220,190,0.17)'; ctx.lineWidth = 0.5; ctx.stroke();

    ctx.fillStyle = '#ffd9a0';
    for (const L of lights) {
      const d = dot(L.v, view);
      if (d < 0.08) continue;
      const p = proj(L.p);
      ctx.globalAlpha = Math.min(1, d * 1.5) * (0.4 + 0.35 * Math.sin(t * 0.0018 + L.k));
      ctx.fillRect(p[0] - 0.6, p[1] - 0.6, 1.2, 1.2);
    }
    ctx.globalAlpha = 1;

    ctx.beginPath(); path(hl);
    ctx.fillStyle = `rgba(240,150,50,${0.5 + 0.25 * pulse})`; ctx.fill();
    ctx.strokeStyle = 'rgba(255,228,175,0.95)'; ctx.lineWidth = 0.9; ctx.stroke();

    ctx.drawImage(shade, 0, 0, s, s);

    ctx.globalCompositeOperation = 'lighter';
    for (const S of spots) {
      const d = dot(S.v, view);
      if (d <= 0) continue;
      const p = proj(S.p);
      const r = R * S.r * (0.85 + 0.3 * pulse);
      ctx.globalAlpha = Math.min(1, d * 2.2) * (0.7 + 0.3 * pulse);
      ctx.drawImage(glow, p[0] - r, p[1] - r, r * 2, r * 2);
    }
    ctx.fillStyle = '#ffd08a';
    for (const G of gold) {
      const d = dot(G.v, view);
      if (d < 0.05) continue;
      const p = proj(G.p);
      ctx.globalAlpha = Math.min(1, d * 2) * (0.35 + 0.35 * Math.sin(t * 0.004 + G.k));
      ctx.fillRect(p[0] - 0.8, p[1] - 0.8, 1.6, 1.6);
    }
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'source-over';
  }

  function loop(t) {
    if (!running) return;
    requestAnimationFrame(loop);
    if (t - last < FRAME) return;
    const dt = Math.min(0.1, (t - last) / 1000);
    last = t;
    const d = (((lon - FOCUS) % 360) + 540) % 360 - 180;
    lon = (lon - SPEED * (1 - 0.7 * Math.exp(-d * d / 800)) * dt + 360) % 360;
    draw(t);
  }

  function start() {
    if (running || still || !land || !onScreen || document.hidden) return;
    running = true;
    last = performance.now();
    requestAnimationFrame(loop);
  }
  const stop = () => { running = false; };

  new ResizeObserver(resize).observe(cv);
  new IntersectionObserver(([e]) => { onScreen = e.isIntersecting; onScreen ? start() : stop(); }).observe(cv);
  document.addEventListener('visibilitychange', () => (document.hidden ? stop() : start()));

  fetch('assets/world.json')
    .then((r) => r.json())
    .then((w) => {
      land = { type: 'MultiPolygon', coordinates: w.land };
      borders = { type: 'MultiLineString', coordinates: w.borders };
      hl = { type: 'MultiPolygon', coordinates: w.hl };
      lights = w.lights.map((p) => ({ p, v: xyz(p), k: Math.random() * 6.28 }));
      gold = w.gold.map((p) => ({ p, v: xyz(p), k: Math.random() * 6.28 }));
      spots = [{ p: w.gr, v: xyz(w.gr), r: 0.17 }, { p: w.cy, v: xyz(w.cy), r: 0.09 }];
      if (still) lon = FOCUS;
      resize();
      draw(performance.now());
      cv.classList.add('ready');
      start();
    })
    .catch(() => cv.classList.add('ready'));
})();
