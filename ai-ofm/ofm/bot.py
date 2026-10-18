"""Telegram updates: review buttons, setup buttons and slash commands. Only the owner is answered."""

import logging
import time
from datetime import datetime

import requests

from . import chat, jobs, onboarding, planner, swipes
from .telegram import TelegramError, keyboard

log = logging.getLogger("ofm")

HELP = """🤖 Εντολές
/status — τι γίνεται τώρα
/plan — φτιάξε πλάνο για τις επόμενες 7 μέρες (σου έρχονται οι ιδέες, φτιάχνονται μόνο όσες πατήσεις ✅)
/approve_all — ✅ σε όλες τις ιδέες που περιμένουν
/replan — πέτα ό,τι δεν έχει φτιαχτεί ακόμα και ξανακάνε το πλάνο από αύριο (μετά από αλλαγές στο persona.yaml)
/fanvue — στείλε τώρα τα εγκεκριμένα για Fanvue
/report — αναφορά 7 ημερών
/pause, /resume — σταμάτα/ξεκίνα generation και αποστολές
/swipe <περιγραφή ή link> — ένα viral βίντεο άλλου creator: η φόρμα του μπαίνει στο επόμενο πλάνο
🎬 Ή στείλε μου κατευθείαν το βίντεο (έως 20 MB): το κάνει η Sienna, σε δικό της μέρος

Fanvue και chat:
/fanvue_login — σύνδεση με το Fanvue (μία φορά)
/chat — κατάσταση του chat
/chat_approve — κάθε απάντηση την εγκρίνεις εσύ (προεπιλογή)
/chat_auto — το bot απαντάει και πουλάει PPV μόνο του
/chat_off — σταματάει το chat

Πρώτο στήσιμο (μία φορά):
/faces — 6 υποψήφια πρόσωπα, διαλέγεις με ⭐ (ή στείλε μου μια φωτογραφία που έφτιαξες αλλού)
/dataset — 24 φωτογραφίες με το ίδιο πρόσωπο, πετάς όσες δεν μοιάζουν
/train — εκπαίδευση LoRA (~$3), κλειδώνει και τις references
/lock — ξανακλείδωμα των references (αν άλλαξες το dataset)"""


def handle_callback(app, cq, now=None):
    action, _, arg = (cq.get("data") or "").partition(":")
    message_id = (cq.get("message") or {}).get("message_id")
    reply, label = "", None
    try:
        if action == "p":
            post_id, _, choice = arg.partition(":")
            reply, markup = jobs.proposal_action(app, int(post_id), choice, message_id)
            app.tg.answer(cq["id"], reply)
            if markup and message_id:
                app.tg.set_buttons(message_id, markup)
            return
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
        elif action == "sw":
            post = planner.remake_next_reel(app, now or datetime.now(app.cfg.tz), int(arg))
            if post:
                reply, label = "🎬 Μπήκε", f"🎬 Reel {jobs.when_label(post)}"
                app.notify(f"🎬 Το reel της {jobs.when_label(post)} θα είναι αυτό, με τη Sienna:\n{post['idea']}\n"
                           f"🪝 {post['hook']}\nΘα σου έρθει για ✅ μόλις φτιαχτεί.")
            else:
                reply, label = "Μπαίνει στο επόμενο πλάνο", "🗂 Στο επόμενο πλάνο"
                app.notify("Δεν βρήκα reel της εβδομάδας που να μην έχει φτιαχτεί ακόμα. Θα μπει στο πλάνο της Κυριακής.")
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
    elif command == "/replan":
        dropped, _ = jobs.replan(app, now)
        app.notify(f"♻️ Πέταξα {dropped} posts που δεν είχαν φτιαχτεί και ξαναέκανα το πλάνο από αύριο με τις νέες ρυθμίσεις.", silent=True)
    elif command == "/report":
        app.notify(jobs.report_text(app, now))
    elif command == "/fanvue":
        if not jobs.send_fanvue_pack(app):
            app.notify("Δεν υπάρχουν νέα εγκεκριμένα για Fanvue.")
    elif command == "/approve_all":
        n = jobs.approve_all_ideas(app)
        app.notify(f"✅ {n} ιδέες μπήκαν για generation." if n else "Δεν υπάρχουν ιδέες σε αναμονή.")
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
    elif command == "/swipe":
        idea = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
        if not idea:
            app.notify("Γράψε μετά το /swipe τι γίνεται στο βίντεο, π.χ.\n/swipe κοπέλα ρωτάει 'rate my fit 1-10', 3 outfits με snap transition, 2M views")
        else:
            db.add_swipe(idea[:500])
            app.notify(f"🗂 Μπήκε στο swipe file ({len(db.swipes())} για το επόμενο πλάνο).")
    elif command == "/lock":
        onboarding.lock_references(app)
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
            handle_callback(app, update["callback_query"], now)
        else:
            message = update.get("message") or {}
            text = (message.get("text") or "").strip()
            replied_to = (message.get("reply_to_message") or {}).get("message_id")
            if text.startswith("/"):
                handle_command(app, text, now)
            elif replied_to and text and chat.send_custom(app, replied_to, text):
                pass
            elif message.get("video") or str((message.get("document") or {}).get("mime_type", "")).startswith("video/"):
                file_id = (message.get("video") or message.get("document"))["file_id"]
                app.notify("🎬 Το βλέπω, 1 λεπτό...", silent=True)
                swipe_id, analysis = swipes.from_video(app, file_id, message.get("caption") or "")
                app.tg.send(f"{swipes.summary(analysis)}\n\nΚράτησα τη φόρμα, όχι το πρόσωπο ή το βίντεο. "
                            "Να το κάνει η Sienna στο επόμενο reel;",
                            keyboard([[("🎬 Ναι, στο επόμενο reel", f"sw:{swipe_id}")]]))
            elif message.get("photo") or str((message.get("document") or {}).get("mime_type", "")).startswith("image/"):
                photo = message.get("photo")
                file_id = photo[-1]["file_id"] if photo else message["document"]["file_id"]  # last = largest size
                onboarding.use_face(app, file_id)
                app.notify("✅ Αυτό είναι το πρόσωπό της από εδώ και πέρα. Στείλε /dataset για να φτιάξω τις 24 φωτογραφίες.")
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
    jobs.apply_tag_settings(app)
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
