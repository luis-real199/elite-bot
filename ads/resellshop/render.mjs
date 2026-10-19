// Renders ad.html frame-by-frame with Playwright/Chromium and encodes it with ffmpeg.
//
//   node render.mjs --config config.el.json --size 1080x1920 --out out/ad.mp4 [--audio out/music.wav] [--fps 30]
//   node render.mjs --config config.el.json --stills 0.6,1.5,3.5 --out out/stills   (PNG stills for review)
//   node render.mjs --events out/events.json                                          (timeline events for the audio script)
import { chromium } from '/opt/node-tools/node_modules/playwright/index.mjs';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, arr) => { if (v.startsWith('--')) a.push([v.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : true]); return a; }, []));
const configPath = path.resolve(here, args.config || 'config.el.json');
const [W, H] = String(args.size || '1080x1920').split('x').map(Number);
const fps = Number(args.fps || 30);
const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));

const browser = await chromium.launch({ args: ['--font-render-hinting=none', '--disable-lcd-text', '--force-color-profile=srgb'] });
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
await page.addInitScript(() => { window.__RENDER__ = true; });
await page.goto('file://' + path.join(here, 'ad.html'));
await page.evaluate(() => document.fonts.ready);
await page.evaluate(([cfg, w, h]) => window.build(cfg, w, h), [config, W, H]);
await page.evaluate(() => document.fonts.ready);
const meta = await page.evaluate(() => window.getEvents());
const duration = Number(args.duration || meta.duration);

if (args.events) {
  fs.mkdirSync(path.dirname(path.resolve(args.events)), { recursive: true });
  fs.writeFileSync(path.resolve(args.events), JSON.stringify(meta, null, 2));
  console.log('events ->', args.events);
}

if (args.stills) {
  const dir = path.resolve(args.out || 'out/stills'); fs.mkdirSync(dir, { recursive: true });
  for (const ts of String(args.stills).split(',').map(Number)) {
    await page.evaluate(t => window.seek(t), ts);
    const f = path.join(dir, `still_${ts.toFixed(2).replace('.', '_')}.png`);
    await page.screenshot({ path: f, type: 'png' });
    console.log('still ->', f);
  }
} else if (args.out) {
  const out = path.resolve(args.out); fs.mkdirSync(path.dirname(out), { recursive: true });
  const total = Math.round(duration * fps);
  const ff = ['-y', '-hide_banner', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'png', '-i', '-'];
  if (args.audio) ff.push('-i', path.resolve(args.audio));
  ff.push('-c:v', 'libx264', '-preset', 'slow', '-crf', String(args.crf || 19), '-pix_fmt', 'yuv420p', '-r', String(fps),
          '-x264-params', 'keyint=60:min-keyint=30', '-movflags', '+faststart', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709');
  if (args.audio) ff.push('-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-shortest');
  ff.push(out);
  const enc = spawn('ffmpeg', ff, { stdio: ['pipe', 'inherit', 'inherit'] });
  const done = new Promise((res, rej) => enc.on('close', code => code === 0 ? res() : rej(new Error('ffmpeg exit ' + code))));
  const t0 = Date.now();
  for (let i = 0; i < total; i++) {
    await page.evaluate(t => window.seek(t), i / fps);
    const buf = await page.screenshot({ type: 'png' });
    if (!enc.stdin.write(buf)) await new Promise(r => enc.stdin.once('drain', r));
    if (i % 60 === 0) process.stdout.write(`frame ${i}/${total} (${((Date.now() - t0) / 1000).toFixed(0)}s)\n`);
  }
  enc.stdin.end();
  await done;
  console.log(`done -> ${out} (${total} frames, ${((Date.now() - t0) / 1000).toFixed(0)}s)`);
}
await browser.close();
