"""Burns the hook text onto a reel with ffmpeg, so silent viewers see it in the first second."""

import re
import shutil
import subprocess
import textwrap
from pathlib import Path

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


class OverlayError(Exception):
    pass


def clean(text):
    """drawtext cannot render emoji: keep letters, digits and plain punctuation."""
    text = re.sub(r"[^\w\s.,!?'’\-:%$&#@()/]", "", text or "")
    return " ".join(text.split())


def burn_hook(src, dest, hook, run=subprocess.run):
    """Writes dest with the hook on top. Returns dest, or None when there is nothing to do or no ffmpeg."""
    lines = textwrap.wrap(clean(hook), 18)[:3]
    if not lines or not shutil.which("ffmpeg"):
        return None
    dest = Path(dest)
    font = f":fontfile={FONT}" if Path(FONT).exists() else ""
    # One drawtext per line so every line is centred on its own.
    text_files, filters = [], []
    for i, line in enumerate(lines):
        text_file = dest.with_name(f"{dest.stem}-{i}.txt")
        text_file.write_text(line, encoding="utf-8")
        text_files.append(text_file)
        filters.append(
            f"drawtext=textfile={text_file}{font}:fontsize=h/28:fontcolor=white:borderw=4"
            f":bordercolor=black@0.85:x=(w-text_w)/2:y=h*0.13+{i}*h/22"
        )
    try:
        result = run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", ",".join(filters), "-c:a", "copy", str(dest)],
            capture_output=True, timeout=300,
        )
    finally:
        for text_file in text_files:
            text_file.unlink(missing_ok=True)
    if result.returncode != 0:
        raise OverlayError((result.stderr or b"").decode(errors="replace")[-300:])
    return dest
