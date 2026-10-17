"""Daily check of everything that can silently break: logins, keys, and the files the persona depends on."""

import logging
from pathlib import Path

import requests

from .buffer import BufferError
from .fanvue import FanvueError

log = logging.getLogger("ofm")


def _alive(url, http):
    try:
        r = http.head(url, timeout=20, allow_redirects=True)
        if r.status_code == 405:  # some CDNs refuse HEAD
            r = http.get(url, timeout=20, stream=True)
        return r.status_code < 400
    except requests.RequestException:
        return False


def health_check(app, http=None):
    """Returns the problems found (after fixing what can be fixed) and tells the owner about them."""
    http = http or app.http
    problems = []

    if app.buffer:
        try:
            app.buffer.query("query { account { organizations { id } } }")
        except (BufferError, requests.RequestException) as e:
            problems.append(f"Buffer: {e}")

    if app.fanvue and app.fanvue.connected:
        try:
            app.fanvue.me()
        except FanvueError as e:
            problems.append(f"Fanvue: {e}")

    lora = app.lora_url()
    if lora and not _alive(lora, http):
        backup = app.lora_backup
        if backup.exists() and not app.cfg.secret("LORA_URL"):
            app.db.kv_set("lora_url", app.media.upload(backup, keep=True))
            problems.append("Το link του LoRA χάθηκε: ανέβηκε ξανά από το αντίγραφο, όλα εντάξει.")
        else:
            problems.append("Το link του LoRA δεν ανοίγει και δεν υπάρχει αντίγραφο. Κάνε /train ξανά.")

    refs = app.reference_urls()
    if refs and not _alive(refs[0], http):
        files = [Path(f) for f in app.db.kv_get("reference_files") or [] if Path(f).exists()]
        if files:
            app.db.kv_set("reference_urls", [app.media.upload(f, keep=True) for f in files])
            problems.append("Οι references είχαν χαθεί: ανέβηκαν ξανά, όλα εντάξει.")
        else:
            problems.append("Οι references δεν ανοίγουν. Στείλε /lock.")

    if problems:
        app.notify("🩺 Ημερήσιος έλεγχος:\n" + "\n".join(f"• {p}" for p in problems))
    return problems
