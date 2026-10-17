"""Telegram updates: review buttons, setup buttons and slash commands. Only the owner is answered."""

import logging
import time

import requests

from . import jobs, onboarding
from .telegram import TelegramError, keyboard

log = logging.getLogger("ofm")

HELP = """🤖 Εντολές
/status — τι γίνεται τώρα
/plan — φτιάξε πλάνο για τις επόμενες 7 μέρες
/fanvue — στείλε τώρα τα εγκεκριμένα για Fanvue
/report — αναφορά 7 ημερών
/pause, /resume — σταμάτα/ξεκίνα generation και αποστολές

Πρώτο στήσιμο (μία φορά):
/faces — 6 υποψήφια πρόσωπα, διαλέγεις με ⭐
/dataset — 24 φωτογραφίες με το ίδιο πρόσωπο, πετάς όσες δεν μοιάζουν
/train — εκπαίδευση LoRA (~$3)"""


def handle_callback(app, cq):
    action, _, arg = (cq.get("data") or "").partition(":")
    message_id = (cq.get("message") or {}).get("message_id")
    reply, label = "", None
    try:
        if action in ("a", "r", "g"):
            reply, label = jobs.review_action(app, action, int(arg))
        elif action == "f":
            face = onboarding.pick_face(app, int(arg))
            reply, label = "⭐ Επιλέχθηκε", "⭐ Επιλέχθηκε"
            app.notify(f"⭐ Κράτησα αυτό το πρόσωπο ({face['path']}). Τώρα στείλε /dataset.")
        elif action == "d":
            onboarding.drop_dataset_image(app, arg)
            reply, label = "🗑 Πετάχτηκε", "🗑 Πετάχτηκε"
    except ValueError as e:
        reply = str(e)
    app.tg.answer(cq["id"], reply)
    if label and message_id:
        app.tg.set_buttons(message_id, keyboard([[(label, "noop")]]))


def handle_command(app, text, now):
    command = text.split()[0].split("@")[0].lower()
    db = app.db
    if command in ("/start", "/help"):
        app.notify(HELP)
    elif command == "/status":
        app.notify(jobs.status_text(app))
    elif command == "/plan":
        jobs.plan_now(app, now)
    elif command == "/report":
        app.notify(jobs.report_text(app, now))
    elif command == "/fanvue":
        if not jobs.send_fanvue_pack(app):
            app.notify("Δεν υπάρχουν νέα εγκεκριμένα για Fanvue.")
    elif command == "/pause":
        db.kv_set("paused", True)
        app.notify("⏸ Σε παύση. /resume για συνέχεια.")
    elif command == "/resume":
        db.kv_set("paused", False)
        app.notify("▶️ Συνεχίζουμε.")
    elif command == "/faces":
        onboarding.faces(app)
    elif command == "/dataset":
        onboarding.dataset(app)
    elif command == "/train":
        onboarding.train(app)
    else:
        app.notify("Δεν την ξέρω αυτή. /help")


def handle_update(app, update, now):
    if not app.tg.is_owner(update):
        log.info("ignoring update from a non-owner")
        return
    try:
        if update.get("callback_query"):
            handle_callback(app, update["callback_query"])
        else:
            text = ((update.get("message") or {}).get("text") or "").strip()
            if text.startswith("/"):
                handle_command(app, text, now)
    except Exception as e:
        log.exception("update failed")
        app.notify(f"⚠️ {type(e).__name__}: {e}")


def run(app, clock, poll_seconds=20):
    """Main loop: answer Telegram, then run whatever jobs are due."""
    for post in app.db.posts("generating"):
        app.db.update_post(post["id"], status="planned")  # interrupted by a restart
    offset = app.db.kv_get("tg_offset")
    app.notify("🤖 Ξεκίνησα. /help για τις εντολές.", silent=True)
    while True:
        if app.tg:
            try:
                updates = app.tg.updates(offset, timeout=poll_seconds)
            except (TelegramError, requests.RequestException) as e:
                log.warning("telegram poll: %s", e)
                updates = []
                time.sleep(5)
            for update in updates:
                offset = update["update_id"] + 1
                app.db.kv_set("tg_offset", offset)
                handle_update(app, update, clock())
        else:
            time.sleep(poll_seconds)
        jobs.tick(app, clock())
