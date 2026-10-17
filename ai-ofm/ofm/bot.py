"""Telegram updates: review buttons, setup buttons and slash commands. Only the owner is answered."""

import logging
import time

import requests

from . import chat, jobs, onboarding
from .telegram import TelegramError, keyboard

log = logging.getLogger("ofm")

HELP = """🤖 Εντολές
/status — τι γίνεται τώρα
/plan — φτιάξε πλάνο για τις επόμενες 7 μέρες
/fanvue — στείλε τώρα τα εγκεκριμένα για Fanvue
/report — αναφορά 7 ημερών
/pause, /resume — σταμάτα/ξεκίνα generation και αποστολές

Fanvue και chat:
/fanvue_login — σύνδεση με το Fanvue (μία φορά)
/chat — κατάσταση του chat
/chat_approve — κάθε απάντηση την εγκρίνεις εσύ (προεπιλογή)
/chat_auto — το bot απαντάει και πουλάει PPV μόνο του
/chat_off — σταματάει το chat

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
        elif action in ("cs", "cx"):
            reply, label = chat.draft_action(app, action, int(arg))
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
    elif command == "/fanvue_login":
        if not app.fanvue:
            app.notify("Βάλε πρώτα FANVUE_CLIENT_ID, FANVUE_CLIENT_SECRET και FANVUE_REDIRECT_URI στο .env.")
        else:
            app.notify(
                "1. Άνοιξε αυτό το link και κάνε login στο Fanvue της περσόνας:\n"
                f"{app.fanvue.login_url()}\n\n"
                "2. Θα καταλήξεις σε σελίδα που ίσως δεν ανοίγει. Δεν πειράζει: αντέγραψε ολόκληρη τη διεύθυνση "
                "από πάνω (ξεκινάει με https και έχει code=) και στείλ' τη μου εδώ."
            )
    elif command == "/chat":
        app.notify(chat.chat_status(app))
    elif command in ("/chat_approve", "/chat_auto", "/chat_off"):
        mode = command.split("_")[1]
        db.kv_set("chat_mode", mode)
        app.notify({
            "approve": "💬 Κάθε απάντηση έρχεται πρώτα σε σένα για ✅.",
            "auto": "💬 Το bot απαντάει και στέλνει PPV μόνο του. Σε σένα έρχονται μόνο οι δύσκολες περιπτώσεις.",
            "off": "💬 Το chat σταμάτησε.",
        }[mode])
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
            message = update.get("message") or {}
            text = (message.get("text") or "").strip()
            replied_to = (message.get("reply_to_message") or {}).get("message_id")
            if text.startswith("/"):
                handle_command(app, text, now)
            elif replied_to and text and chat.send_custom(app, replied_to, text):
                pass
            elif text.startswith("http") and "code=" in text and app.fanvue:
                me = app.fanvue.finish_login(text)
                app.notify(f"✅ Συνδέθηκε το Fanvue: @{me.get('handle')}. Από τώρα τα εγκεκριμένα ανεβαίνουν μόνα τους.")
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
