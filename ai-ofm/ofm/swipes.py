"""A viral video the owner sends becomes a format for her: what happens, how it is filmed, why people comment.
Three frames go to the vision model; nothing of the original person, footage or words is kept."""

import shutil
import subprocess
from pathlib import Path

from . import llm
from .db import utcnow
from .media import download
from .planner import MECHANICS
from .telegram import TelegramError

SWIPE_SCHEMA = {
    "type": "object",
    "properties": {
        "format": {"type": "string"},
        "hook": {"type": "string"},
        "moves": {"type": "string"},
        "camera": {"type": "string"},
        "setting": {"type": "string"},
        "outfit": {"type": "string"},
        "mechanic": {"type": "string", "enum": MECHANICS},
        "why_it_works": {"type": "string"},
    },
    "required": ["format", "hook", "moves", "camera", "setting", "outfit", "mechanic", "why_it_works"],
    "additionalProperties": False,
}

INSTRUCTIONS = """These are three frames (start, middle, end) of a short vertical video that went viral for another creator.
Describe its FORMAT so a different woman can make her own version in a different place. Describe what happens,
never who: no names, no faces, no bodies, no brand names. Paraphrase any on-screen text instead of copying it.
- format: one sentence, the idea of the video
- hook: the on-screen text idea of the first second, paraphrased, max 8 words
- moves: what she does from start to end (poses, turns, transitions), in order
- camera: angle, distance and movement (mirror selfie, phone on a tripod, friend filming, slow push in...)
- setting: the kind of place
- outfit: the kind of outfit
- mechanic: why viewers comment or share, one of the listed values
- why_it_works: one short sentence"""


class SwipeError(Exception):
    pass


def extract_frames(video, out_dir, count=3, run=subprocess.run):
    """count JPEG frames spread over the video (10% to 90%). Needs ffmpeg and ffprobe."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SwipeError("Λείπει το ffmpeg στον server")
    probe = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                capture_output=True, text=True, timeout=60)
    try:
        duration = float(probe.stdout.strip())
    except ValueError:
        raise SwipeError("Δεν διαβάζεται το βίντεο") from None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for i in range(count):
        at = duration * (0.1 + 0.8 * i / max(count - 1, 1))
        frame = out_dir / f"{Path(video).stem}-{i}.jpg"
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1",
             "-vf", "scale=720:-2", str(frame)], capture_output=True, timeout=120)
        if frame.exists():
            frames.append(frame)
    if not frames:
        raise SwipeError("Δεν βγήκαν καρέ από το βίντεο")
    return frames


def describe(app, frame_urls, note=""):
    content = [{"type": "image", "source": {"type": "url", "url": u}} for u in frame_urls]
    text = INSTRUCTIONS + (f"\n\nThe owner adds: {note}" if note else "")
    content.append({"type": "text", "text": text})
    return llm.ask_json(app, system=None, content=content, schema=SWIPE_SCHEMA, kind="swipe", effort="low",
                        max_tokens=4000, free_max_tokens=1536)


def swipe_text(a):
    return (f"{a['format']} Hook idea: {a['hook']}. Moves: {a['moves']}. Camera: {a['camera']}. "
            f"Setting type: {a['setting']}. Outfit type: {a['outfit']}. Mechanic: {a['mechanic']} ({a['why_it_works']})")


def from_video(app, file_id, note=""):
    """Video from Telegram -> stored swipe. Returns (swipe id, analysis)."""
    folder = app.media_dir / "swipes"
    stamp = utcnow().strftime("%Y%m%d%H%M%S")
    try:
        url = app.tg.file_url(file_id)
    except TelegramError as e:
        if "too big" in str(e):
            raise SwipeError("Το βίντεο είναι πάνω από 20 MB (όριο του Telegram για bots). Στείλε μικρότερο.") from None
        raise
    video = download(url, folder / f"{stamp}.mp4")
    try:
        frames = extract_frames(video, folder)
        urls = [app.media.upload(f, expires_in="1d") for f in frames[:3]]  # the free vision model takes 3 images
        analysis = describe(app, urls, note)
    finally:
        for f in [video, *folder.glob(f"{stamp}-*.jpg")]:
            Path(f).unlink(missing_ok=True)
    swipe_id = app.db.add_swipe(swipe_text(analysis)[:800])
    return swipe_id, analysis


def summary(a):
    return f"🎬 {a['format']}\n🪝 {a['hook']}\n🕺 {a['moves']}\n📷 {a['camera']}"
