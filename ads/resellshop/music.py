"""Generates a royalty-free synth beat + sound effects for the ad, synced to the
timeline events exported by render.mjs (out/events.json).

  python3 -I music.py --events out/events.json --out out/music.wav [--bpm 126] [--no-sfx]
"""
import argparse, json, math, wave, struct
import numpy as np

SR = 48000
ap = argparse.ArgumentParser()
ap.add_argument('--events', default='out/events.json')
ap.add_argument('--out', default='out/music.wav')
ap.add_argument('--bpm', type=float, default=126.0)
ap.add_argument('--no-sfx', action='store_true')
ap.add_argument('--gain', type=float, default=0.8)
A = ap.parse_args()

meta = json.load(open(A.events))
DUR = float(meta['duration']) + 0.05
N = int(DUR * SR)
t_all = np.arange(N) / SR
rng = np.random.default_rng(7)

def sec(x): return int(x * SR)
def add(buf, start, sig, gain=1.0):
    i = sec(start)
    if i >= N or i + len(sig) <= 0: return
    if i < 0: sig = sig[-i:]; i = 0
    j = min(N, i + len(sig)); buf[i:j] += sig[:j - i] * gain
def env_ad(n, a, d, curve=4.0):
    """attack/decay envelope, exponential-ish decay"""
    t = np.arange(n) / SR
    e = np.minimum(t / max(a, 1e-4), 1.0)
    e = e * np.exp(-curve * np.maximum(t - a, 0) / max(d, 1e-4))
    return e
def onepole_lp(x, fc):
    """one-pole lowpass with constant cutoff (vectorised via lfilter-free recursion in numpy)"""
    a = math.exp(-2 * math.pi * fc / SR); b = 1 - a
    y = np.empty_like(x); acc = 0.0
    # recursion; fine for our sizes
    for i in range(len(x)):
        acc = b * x[i] + a * acc; y[i] = acc
    return y
def fft_lp(x, fc, order=2.0):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / np.sqrt(1 + (f / fc) ** (2 * order)); return np.fft.irfft(X, len(x))
def fft_hp(x, fc, order=2.0):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / np.sqrt(1 + (fc / np.maximum(f, 1e-3)) ** (2 * order)); return np.fft.irfft(X, len(x))
def fft_bp(x, lo, hi): return fft_hp(fft_lp(x, hi), lo)
def note(n): return 440.0 * 2 ** ((n - 69) / 12)
def saw(freq, n, phase=0.0):
    t = np.arange(n) / SR
    # band-limited-ish saw by summing harmonics up to ~12 kHz
    y = np.zeros(n); k = 1
    while freq * k < 12000 and k < 60:
        y += ((-1) ** (k + 1)) * np.sin(2 * np.pi * freq * k * t + phase) / k; k += 1
    return y * (2 / np.pi)
def sine(freq, n, phase=0.0): return np.sin(2 * np.pi * freq * np.arange(n) / SR + phase)

beat = 60.0 / A.bpm
bar = 4 * beat
drop = float(meta['sections']['drop']); cta = float(meta['sections']['cta'])
# Align the first bar of the full beat with the "drop" (start of products scene) by starting the grid before 0.
grid0 = drop - math.ceil(drop / bar) * bar

# ---------------- drums ----------------
drums = np.zeros(N)
def kick():
    n = sec(0.42); t = np.arange(n) / SR
    f = 42 + 160 * np.exp(-t * 38)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t * 9.5)
    click = rng.standard_normal(n) * np.exp(-t * 900) * 0.6
    return np.tanh((body + click) * 1.6) * 0.95
def clap():
    n = sec(0.28); t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    e = np.exp(-t * 26) + 0.5 * np.exp(-((t - 0.012) ** 2) / 2e-6) + 0.4 * np.exp(-((t - 0.024) ** 2) / 2e-6)
    return fft_bp(noise * e, 900, 7000) * 0.55
def hat(open_=False):
    n = sec(0.32 if open_ else 0.07); t = np.arange(n) / SR
    noise = rng.standard_normal(n) * np.exp(-t * (9 if open_ else 70))
    return fft_hp(noise, 7000) * (0.32 if open_ else 0.26)
K, CL, HH, HO = kick(), clap(), hat(), hat(True)

nbars = int(math.ceil((DUR - grid0) / bar)) + 1
for b in range(nbars):
    tb = grid0 + b * bar
    full = tb >= drop - 1e-6  # full beat after the drop; filtered/lighter intro before it
    for i in range(4):
        tk = tb + i * beat
        if tk < -0.5 or tk > DUR: continue
        add(drums, tk, K, 1.0 if full else 0.55)
        if full and i in (1, 3): add(drums, tk, CL)
        for j in range(2):
            th = tk + j * beat / 2
            if full: add(drums, th, HH, 0.75 if j else 1.0)
            elif th >= 0: add(drums, th, HH, 0.45)
        if full and i == 3: add(drums, tk + beat / 2, HO, 0.7)
    if full:  # extra kick on the "and" of 4 every 2nd bar for bounce
        if b % 2 == 1: add(drums, tb + 3.5 * beat, K, 0.7)
# break: fade drums out slightly in the final bar before CTA and hit hard at CTA
# (riser/impact handled below)

# ---------------- bass + chords ----------------
# progression (A minor): Am - F - C - G  (bar roots), repeated
roots = [57, 53, 48, 55]       # A3 F3 C3 G3 (MIDI) for chords
chords = [[57, 60, 64, 67], [53, 57, 60, 65], [48, 52, 55, 60], [55, 59, 62, 67]]
bass = np.zeros(N); pad = np.zeros(N); pluck = np.zeros(N)
side = np.ones(N)  # sidechain envelope
for b in range(nbars):
    tb = grid0 + b * bar
    for i in range(4):
        tk = tb + i * beat
        if tk < 0 or tk > DUR: continue
        n = sec(beat); k = sec(tk); e = 1 - 0.85 * np.exp(-np.arange(n) / SR * 12)
        side[k:k + n] = np.minimum(side[k:k + n], e[:min(n, N - k)])
for b in range(nbars):
    tb = grid0 + b * bar
    ch = chords[b % 4]; root = roots[b % 4] - 24  # bass two octaves down
    # bass: 8th-note pulses
    for j in range(8):
        tn = tb + j * beat / 2
        if tn < 0 or tn > DUR: continue
        n = sec(beat / 2 * 0.95); f = note(root if j % 4 != 3 else root + 12)
        s = (saw(f, n) * 0.6 + sine(f, n) * 0.7) * env_ad(n, 0.004, beat / 2, 3.0)
        add(bass, tn, s, 0.5 if tb >= drop - 1e-6 else 0.0)
    # pad: detuned saws, one chord per bar
    n = sec(bar * 1.02); p = np.zeros(n)
    for m in ch:
        f = note(m)
        p += saw(f * 0.997, n, rng.uniform(0, 6)) + saw(f * 1.003, n, rng.uniform(0, 6)) + 0.6 * saw(f * 0.5, n)
    p = fft_lp(p, 1500 if tb >= drop else 700) * env_ad(n, 0.05, bar * 1.2, 1.2)
    add(pad, tb, p, 0.075)
    # pluck arpeggio: 16ths over chord tones (octave up)
    for j in range(16):
        tn = tb + j * beat / 4
        if tn < 0 or tn > DUR or tb < drop - 1e-6: continue
        if j % 4 == 2: continue  # leave a little space
        m = ch[[0, 2, 1, 3, 2, 0, 3, 1][j % 8]] + 12
        n = sec(0.22); s = (saw(note(m), n) * 0.5 + sine(note(m) * 2, n) * 0.3) * env_ad(n, 0.002, 0.16, 5.0)
        add(pluck, tn, fft_lp(s, 5000), 0.11)
bass = fft_lp(bass, 220, 1.5) * side
pad = pad * (0.35 + 0.65 * side)
pluck = pluck * (0.5 + 0.5 * side)

# ---------------- transitions ----------------
fx = np.zeros(N)
def riser(dur):
    n = sec(dur); t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    X = np.fft.rfft(noise); f = np.fft.rfftfreq(n, 1 / SR)
    # sweeping bandpass approximated by applying a gentle tilt + amplitude envelope
    noise = fft_hp(noise, 400)
    e = (t / dur) ** 2.2
    tone = sine(220, n) * np.sin(2 * np.pi * np.cumsum(220 + 660 * (t / dur) ** 2) / SR) * 0.3
    return (noise * 0.5 + tone) * e * 0.55
def impact():
    n = sec(1.2); t = np.arange(n) / SR
    f = 36 + 90 * np.exp(-t * 18)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)
    nz = fft_lp(rng.standard_normal(n), 2500) * np.exp(-t * 14) * 0.5
    return np.tanh((body * 1.3 + nz) * 1.4) * 0.9
def whoosh():
    n = sec(0.32); t = np.arange(n) / SR
    nz = fft_bp(rng.standard_normal(n), 600, 6000)
    e = np.sin(np.pi * np.minimum(t / 0.32, 1)) ** 1.5
    return nz * e * 0.22
def pop(idx=0):
    n = sec(0.13); t = np.arange(n) / SR
    f0 = 520 * (1.12 ** (idx % 4))
    f = f0 * (1 + 0.9 * np.exp(-t * 60))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 32)
    return s * 0.42
def tick(idx=0):
    n = sec(0.16); t = np.arange(n) / SR
    f = 1500 * (1.06 ** (idx % 4))
    s = (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 2.01 * t)) * np.exp(-t * 28)
    return s * 0.22
def slam():
    n = sec(0.6); t = np.arange(n) / SR
    f = 60 + 220 * np.exp(-t * 30)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7)
    nz = fft_lp(rng.standard_normal(n), 4000) * np.exp(-t * 40) * 0.6
    return np.tanh((body + nz) * 1.5) * 0.85
def tap():
    n = sec(0.35); t = np.arange(n) / SR
    s = (np.sin(2 * np.pi * 880 * t) * np.exp(-t * 14) + 0.6 * np.sin(2 * np.pi * 1320 * t) * np.exp(-t * 10)) * 0.3
    s[:sec(0.01)] *= np.linspace(0, 1, sec(0.01))
    return s

if not A.no_sfx:
    for ev in meta['events']:
        ty, t0 = ev['type'], float(ev['t'])
        if ty == 'whoosh': add(fx, t0 - 0.12, whoosh())
        elif ty == 'pop': add(fx, t0, pop(ev.get('idx', 0)))
        elif ty == 'tick': add(fx, t0, tick(ev.get('idx', 0)))
        elif ty == 'slam': add(fx, t0, slam())
        elif ty == 'riser': add(fx, t0, riser(float(ev.get('dur', 1.0))))
        elif ty == 'impact': add(fx, t0, impact())
        elif ty == 'tap': add(fx, t0, tap())

# ---------------- mix ----------------
# duck the music slightly under the riser->impact for contrast
duck = np.ones(N)
k0, k1 = sec(cta - 0.6), sec(cta)
duck[k0:k1] = np.linspace(1, 0.55, k1 - k0); duck[k1:sec(cta + 0.25)] = np.linspace(0.55, 1, sec(cta + 0.25) - k1)
music = (drums * 0.9 + bass + pad + pluck) * duck
# intro before the drop: lowpass the whole music bed so the drop "opens up"
intro = music[:sec(drop)]
music[:sec(drop)] = fft_lp(intro, 900, 1.5) * np.linspace(0.6, 0.95, len(intro))
mix = music + fx
# tail: fade out over the last 0.6 s
fade_n = sec(0.6); mix[-fade_n:] *= np.linspace(1, 0, fade_n)
mix[:sec(0.02)] *= np.linspace(0, 1, sec(0.02))
# soft clip + normalise
mix = np.tanh(mix * 1.15)
mix = mix / (np.max(np.abs(mix)) + 1e-9) * A.gain
# simple stereo: slight widening of pad/pluck with a short delay on the right channel
d = sec(0.011)
right = mix.copy(); wide = (pad + pluck) * 0.35 * duck
right[d:] += wide[:-d]; left = mix + wide
peak = max(np.max(np.abs(left)), np.max(np.abs(right))) + 1e-9
left = left / peak * A.gain; right = right / peak * A.gain
pcm = np.empty(2 * N, dtype=np.int16); pcm[0::2] = (left * 32767).astype(np.int16); pcm[1::2] = (right * 32767).astype(np.int16)
with wave.open(A.out, 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
print(f'wrote {A.out}: {DUR:.2f}s, bpm {A.bpm}, grid0 {grid0:.3f}, drop {drop}, cta {cta}')
