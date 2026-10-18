"""Daily check of everything that can silently break: logins, keys, and the files the persona depends on."""

import logging
from pathlib import Path

import requests

from . import llm
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


def _llm_models_missing(app):
    """Free providers retire models with little notice (Groq did twice in 2026): check they still exist."""
    s = llm.settings(app.cfg)
    key = app.cfg.secret(s["key_env"]) if s["key_env"] else None
    if s["provider"] == "claude" or not key:
        return []
    try:
        r = app.llm_http.get(s["base_url"].rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"}, timeout=30)
        available = {m.get("id") for m in (r.json().get("data") or [])} if r.status_code < 300 else None
    except (requests.RequestException, ValueError):
        available = None
    if available is None:
        return [f"{s['provider']}: δεν μπόρεσα να δω τη λίστα μοντέλων"]
    gone = sorted({s["model"], s["vision_model"]} - available)
    return [f"{s['provider']}: το μοντέλο {m} δεν υπάρχει πια. Άλλαξέ το στο persona.yaml (models.llm)." for m in gone]


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

    problems += _llm_models_missing(app)

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
