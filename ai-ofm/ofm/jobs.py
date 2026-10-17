"""The weekly loop: generate → review on Telegram → schedule on Buffer → Fanvue pack → report."""

import logging
from datetime import date, datetime, timedelta

from . import chat, health, overlay, planner, qc
from .buffer import CHANNEL_ENV, BufferError, create_post_mutation, post_input
from .config import TARGET_LABELS
from .db import utcnow
from .fanvue import FanvueError
from .media import GenerationError, download
from .storage import StorageError
from .telegram import TelegramError, keyboard

log = logging.getLogger("ofm")

WEEKDAYS = ["Δε", "Τρ", "Τε", "Πε", "Πα", "Σα", "Κυ"]
ICON = {"image": "📸", "video": "🎬"}
MAX_PUBLISH_ATTEMPTS = 3
LATE_GRACE = timedelta(hours=12)


class SetupNeeded(Exception):
    pass


# ---------- generation ----------

def full_prompt(cfg, post):
    p = cfg.persona
    parts = [
        p["trigger_word"],
        f"photo of an adult {p['age']}-year-old {p['subject']}",
        p["appearance"],
        post["image_prompt"],
        cfg.style.get("photo", ""),
    ]
    return ", ".join(x.strip().rstrip(",") for x in parts if x and x.strip())


def ref_prompt(cfg, post):
    """Prompt for the reference-image model: the locked references carry the identity."""
    p = cfg.persona
    return (
        f"{cfg.generation['consistency_line']} She is an adult {p['age']}-year-old {p['subject']}. "
        f"{post['image_prompt']}. {cfg.style.get('photo', '')}. Vertical 9:16 photo."
    )


def _retry_or_fail(app, post, error):
    attempts = (post["attempts"] or 0) + 1
    if attempts > app.cfg.generation["max_regenerations"]:
        app.db.update_post(post["id"], status="failed", attempts=attempts, error=error)
        app.notify(f"⚠️ Το post #{post['id']} απέτυχε {attempts} φορές: {error}")
    else:
        app.db.update_post(post["id"], status="planned", attempts=attempts, error=error)


def _first_image(app, post, refs, lora):
    """Social posts use the locked references (Nano Banana); Fanvue, or a reference model refusal, use the LoRA.
    Returns the image URL; raises GenerationError, or returns None after scheduling a retry."""
    cfg = app.cfg
    if post.social_targets and refs:
        try:
            return app.media.ref_image(ref_prompt(cfg, post), refs)
        except GenerationError as e:
            log.info("reference model refused #%s, falling back to LoRA: %s", post["id"], e)
    if not lora:
        raise GenerationError("Δεν υπάρχει LoRA για αυτό το post. Κάνε /train.")
    safety = True if post.social_targets else cfg.generation["fanvue_safety_checker"]
    image_url, flagged = app.media.image(full_prompt(cfg, post), lora, safety)
    if flagged:
        _retry_or_fail(app, post, "safety checker: NSFW")
        return None
    return image_url


def generate_post(app, post):
    cfg, db = app.cfg, app.db
    lora, refs = app.lora_url(), app.reference_urls()
    if not lora and not refs:
        raise SetupNeeded("Δεν υπάρχει ούτε LoRA ούτε references. Κάνε πρώτα /faces, /dataset και /train.")
    kinds = ["ref_image" if post.social_targets and refs else "image"]
    if post["kind"] == "video":
        kinds.append("video")
    if cfg.generation["quality_check"]:
        kinds.append("qc")
    app.media.check_budget(*kinds)

    db.update_post(post["id"], status="generating")
    try:
        image_url = _first_image(app, post, refs, lora)
        if image_url is None:
            return
        reference = refs[0] if refs else (db.kv_get("reference_face") or {}).get("url")
        if cfg.generation["quality_check"] and reference:
            passed, reason = qc.check_image(app, image_url, reference)
            if not passed:
                return _retry_or_fail(app, post, f"QC: {reason}")
            db.update_post(post["id"], qc="pass")
        path = download(image_url, app.media_dir / f"{post['id']}.jpg")
        video_url = None
        if post["kind"] == "video":
            motion = post["motion_prompt"] or "subtle natural movement, slow camera push-in"
            video_url = app.media.video(image_url, motion, refs)
            path = download(video_url, app.media_dir / f"{post['id']}.mp4")
            if post["hook"] and post.social_targets and cfg.generation["hook_overlay"]:
                try:
                    path = overlay.burn_hook(path, app.media_dir / f"{post['id']}-hook.mp4", post["hook"]) or path
                except overlay.OverlayError as e:
                    log.warning("hook overlay #%s: %s", post["id"], e)
    except (GenerationError, OSError) as e:
        return _retry_or_fail(app, post, str(e))
    db.update_post(post["id"], status="ready", image_url=image_url, video_url=video_url, media_path=str(path), error=None)


def generate_pending(app, now, limit=2):
    """Generate up to `limit` planned posts. Returns how many were attempted."""
    if app.db.kv_get("paused"):
        return 0
    pending = []
    for post in app.db.posts("planned"):
        if post.social_targets and post["slot_at"] < now:
            app.db.update_post(post["id"], status="missed", error="η ώρα του πέρασε πριν φτιαχτεί")
        else:
            pending.append(post)
    for post in pending[:limit]:
        generate_post(app, post)
    return len(pending[:limit])


# ---------- review ----------

def when_label(post):
    if post["targets"] == ["fanvue"]:
        return "vault"
    t = post["slot_at"]
    return f"{WEEKDAYS[t.weekday()]} {t:%d/%m %H:%M}"


def review_caption(post):
    targets = ", ".join(TARGET_LABELS[t] for t in post["targets"])
    extra = ""
    if post["hook"]:
        extra += f"\n🪝 {post['hook']}"
    if post["pinned_comment"]:
        extra += f"\n📌 {post['pinned_comment']}"
    qc_line = " · ✅ QC" if post["qc"] == "pass" else ""
    return (
        f"#{post['id']} · {when_label(post)} · {ICON[post['kind']]}{qc_line}\n"
        f"→ {targets}\n"
        f"💡 {post['idea']}{extra}\n\n"
        f"📝 {post['caption']}\n{' '.join(post['hashtags'])}"
    )


def sampled_for_review(app, post):
    """With generation.review_sample < 1, QC-passed posts skip review except a fixed sample."""
    rate = float(app.cfg.generation["review_sample"])
    if rate >= 1 or post["qc"] != "pass":
        return True
    return (post["id"] * 37) % 100 < rate * 100


def review_buttons(post_id):
    return keyboard([[("✅ Έγκριση", f"a:{post_id}"), ("🔁 Ξανά", f"g:{post_id}"), ("❌ Όχι", f"r:{post_id}")]])


def send_reviews(app):
    if not app.tg:
        return 0
    sent = 0
    for post in app.db.posts("ready"):
        if not sampled_for_review(app, post):
            app.db.update_post(post["id"], status="approved", auto_approved=1)
            continue
        try:
            msg = app.tg.send_media(post["media_path"], review_caption(post), review_buttons(post["id"]), silent=True)
        except (TelegramError, OSError) as e:
            _report_error(app, "review", f"#{post['id']}: {e}")
            continue
        app.db.update_post(post["id"], status="in_review", review_message_id=msg["message_id"])
        sent += 1
    # One audible message once the whole batch is ready, instead of one per generated post.
    if sent and not app.db.posts(("planned", "generating", "ready")):
        waiting = len(app.db.posts("in_review"))
        app.notify(f"🗂 Όλα έτοιμα: {waiting} posts περιμένουν έγκριση.")
        if waiting and any(p["pinned_comment"] for p in app.db.posts("in_review")):
            app.notify("📌 Το καρφιτσωμένο σχόλιο κάθε post το βάζεις εσύ από την εφαρμογή (προαιρετικό, 10″ ανά post).", silent=True)
    return sent


def review_action(app, action, post_id):
    """Apply a review button. Returns (reply text, new button label or None)."""
    db = app.db
    post = db.get_post(post_id)
    if not post:
        return "Δεν βρέθηκε", None
    if post["status"] != "in_review":
        return f"Ήδη: {post['status']}", None
    if action == "a":
        db.update_post(post_id, status="approved")
        return "✅ Εγκρίθηκε", "✅ Εγκρίθηκε"
    if action == "r":
        db.update_post(post_id, status="rejected")
        return "❌ Απορρίφθηκε", "❌ Απορρίφθηκε"
    if action == "g":
        attempts = (post["attempts"] or 0) + 1
        if attempts > app.cfg.generation["max_regenerations"]:
            db.update_post(post_id, status="rejected", attempts=attempts, error="όριο επαναλήψεων")
            return "Έφτασε το όριο, απορρίφθηκε", "❌ Όριο επαναλήψεων"
        db.update_post(post_id, status="planned", attempts=attempts, review_message_id=None, error=None)
        return "🔁 Θα ξαναφτιαχτεί", "🔁 Ξαναφτιάχνεται"
    return "Άγνωστη ενέργεια", None


# ---------- publishing ----------

def _publication_done(pub):
    return pub and (pub["status"] in ("scheduled", "missed", "skipped") or pub["attempts"] >= MAX_PUBLISH_ATTEMPTS)


def publish_due(app, now, dry_run=False):
    """Send approved social posts that are due within publish_ahead_hours to Buffer."""
    cfg, db = app.cfg, app.db
    if db.kv_get("paused") or (not app.buffer and not dry_run):
        return []
    horizon = now + timedelta(hours=cfg.publish_ahead_hours)
    previews = []
    for post in db.posts("approved"):
        targets = post.social_targets
        if not targets or post["slot_at"] > horizon:
            continue
        if post["slot_at"] < now - LATE_GRACE:
            for target in targets:
                if not db.publication(post["id"], target) and not dry_run:
                    db.save_publication(post["id"], target, "missed", error="εγκρίθηκε πολύ αργά")
        else:
            if not post["public_url"] and not dry_run:
                try:
                    url = app.storage.upload(post["media_path"], post["id"], source_url=post["video_url"] or post["image_url"])
                except (StorageError, OSError) as e:
                    app.notify(f"⚠️ Upload για το #{post['id']} απέτυχε: {e}")
                    continue
                db.update_post(post["id"], public_url=url)
                post["public_url"] = url
            for target in targets:
                if _publication_done(db.publication(post["id"], target)):
                    continue
                delay = timedelta(minutes=cfg.backup_delay_minutes if target == "instagram_backup" else 0)
                due = max(post["slot_at"] + delay, now + timedelta(minutes=10))
                channel = cfg.secret(CHANNEL_ENV[target])
                data = post_input(post, target, channel or "CHANNEL_ID", post["public_url"] or "MEDIA_URL", due)
                if dry_run:
                    previews.append(create_post_mutation(data))
                    continue
                if not channel:
                    db.save_publication(post["id"], target, "skipped", error=f"λείπει το {CHANNEL_ENV[target]}")
                    continue
                try:
                    external_id = app.buffer.create_post(data)
                    db.save_publication(post["id"], target, "scheduled", due_at=due.isoformat(), external_id=external_id)
                except BufferError as e:
                    db.save_publication(post["id"], target, "failed", due_at=due.isoformat(), error=str(e))
                    app.notify(f"⚠️ Buffer ({TARGET_LABELS[target]}) για το #{post['id']}: {e}")
        pubs = [db.publication(post["id"], t) for t in targets]
        if not dry_run and all(_publication_done(p) for p in pubs):
            db.update_post(post["id"], status="missed" if all(p["status"] == "missed" for p in pubs) else "scheduled")
    return previews


def cleanup_storage(app, now, keep_days=3):
    """Free the public copies once Buffer has published them (Supabase free tier is 1 GB)."""
    removed = 0
    for post in app.db.posts(("scheduled", "missed")):
        if post["public_url"] and post["slot_at"] < now - timedelta(days=keep_days):
            app.storage.delete(post["public_url"])
            app.db.update_post(post["id"], public_url=None)
            removed += 1
    return removed


def publish_fanvue(app, now):
    """Upload approved Fanvue items: the first feed_per_week of each batch become daily feed posts,
    the rest go to the vault as PPV the chat can offer."""
    fv, cfg, db = app.fanvue, app.cfg, app.db
    if not fv or not fv.connected or db.kv_get("paused"):
        return 0
    done = {"feed": 0, "vault": 0}
    for post in db.posts("approved"):
        if "fanvue" not in post["targets"] or post["sent_to_fanvue"]:
            continue
        try:
            media_uuid = fv.upload(post["media_path"], "video" if post["kind"] == "video" else "image", name=f"post-{post['id']}")
        except (FanvueError, OSError) as e:
            _report_error(app, "fanvue", f"#{post['id']}: {e}")
            continue
        batch, description = post["batch"], post["image_prompt"][:160]
        feed_count = len(db.fanvue_media(purpose="feed", batch=batch))
        purpose = "feed" if feed_count < cfg.fanvue["feed_per_week"] else "vault"
        if purpose == "feed":
            publish_at = datetime.combine(date.fromisoformat(batch) + timedelta(days=feed_count), cfg.fanvue["feed_time"], cfg.tz)
            when = publish_at if publish_at > now + timedelta(minutes=10) else None
            try:
                fv.wait_ready(media_uuid)
                post_uuid = fv.create_post(f"{post['caption']}\n\n{' '.join(post['hashtags'])}", [media_uuid], publish_at=when)
                db.add_fanvue_media(post["id"], media_uuid, "feed", batch, description, post_uuid, (when or now).isoformat())
            except FanvueError as e:
                _report_error(app, "fanvue", f"post #{post['id']}: {e}")
                purpose = "vault"
        if purpose == "vault":
            try:
                fv.add_to_vault(cfg.fanvue["vault_folder"], [media_uuid])
            except FanvueError as e:
                log.warning("vault folder: %s", e)
            db.add_fanvue_media(post["id"], media_uuid, "vault", batch, description)
        done[purpose] += 1
        db.update_post(post["id"], sent_to_fanvue=1, status="delivered" if not post.social_targets else "approved")
    if sum(done.values()):
        app.notify(f"📤 Fanvue: {done['feed']} posts στο feed (ένα τη μέρα), {done['vault']} στο vault για PPV στο chat.", silent=True)
    return sum(done.values())


def send_fanvue_pack(app):
    if not app.tg:
        return 0
    sent = 0
    for post in app.db.posts("approved"):
        if "fanvue" not in post["targets"] or post["sent_to_fanvue"]:
            continue
        caption = f"#{post['id']} {post['caption']}\n{' '.join(post['hashtags'])}"
        app.tg.send_media(post["media_path"], caption, silent=True, as_document=True)
        app.db.update_post(post["id"], sent_to_fanvue=1, status="delivered" if not post.social_targets else "approved")
        sent += 1
    if sent:
        app.notify(f"📦 {sent} αρχεία για το Fanvue. Ανέβασέ τα στο vault και κανόνισε posts/PPV για την εβδομάδα.")
    return sent


# ---------- status and report ----------

STATUS_LABELS = {
    "planned": "σε αναμονή για generation", "generating": "φτιάχνονται", "ready": "έτοιμα για αποστολή",
    "in_review": "περιμένουν έγκριση", "approved": "εγκρίθηκαν", "scheduled": "στο Buffer",
    "delivered": "στάλθηκαν για Fanvue", "rejected": "απορρίφθηκαν", "blocked": "μπλοκαρίστηκαν από τους κανόνες",
    "failed": "απέτυχαν", "missed": "έχασαν την ώρα τους",
}


def _counts_text(counts):
    lines = [f"  • {STATUS_LABELS.get(s, s)}: {n}" for s, n in sorted(counts.items(), key=lambda kv: -kv[1])]
    return "\n".join(lines) or "  • (τίποτα ακόμα)"


def status_text(app):
    cfg, db = app.cfg, app.db
    checks = [
        ("LoRA", bool(app.lora_url())),
        ("Buffer", bool(app.buffer)),
        ("Supabase", type(app.storage).__name__ == "SupabaseStorage"),
        ("Fanvue", bool(app.fanvue and app.fanvue.connected)),
    ]
    return (
        f"📋 Κατάσταση{' (⏸ σε παύση)' if db.kv_get('paused') else ''}\n"
        f"{_counts_text(db.status_counts())}\n\n"
        f"💶 7 ημέρες: ${db.spent_last_week():.2f} / ${cfg.weekly_budget:.2f}\n"
        f"🗓 Πλάνο μέχρι: {db.kv_get('planned_until') or '—'}\n"
        + " · ".join(f"{name} {'✅' if ok else '❌'}" for name, ok in checks)
    )


def report_text(app, now):
    db = app.db
    since = utcnow() - timedelta(days=7)
    pubs = db.publication_counts(since)
    return (
        f"📊 Εβδομαδιαία αναφορά ({(now - timedelta(days=7)):%d/%m}–{now:%d/%m})\n"
        f"Posts που φτιάχτηκαν αυτή την εβδομάδα:\n{_counts_text(db.status_counts(since))}\n"
        f"Εγκρίθηκαν αυτόματα μετά το QC: {db.auto_approved_count(since)}\n"
        f"Buffer: {pubs.get('scheduled', 0)} προγραμματίστηκαν · {pubs.get('failed', 0)} απέτυχαν · "
        f"{pubs.get('missed', 0)} έχασαν την ώρα τους\n"
        f"💶 Κόστος: ${db.spent_last_week():.2f} / ${app.cfg.weekly_budget:.2f} "
        f"(+ setup ${db.spent(since, include_setup=True) - db.spent_last_week():.2f})\n"
        f"🗓 Πλάνο μέχρι: {db.kv_get('planned_until') or '—'}\n"
        f"{chat.chat_status(app)}\n\n"
        "Για σένα: δες τα στατιστικά σε Instagram και Fanvue (5') και άλλαξε στο persona.yaml ό,τι δεν δουλεύει."
    )


# ---------- periodic jobs ----------

def _week_id(now):
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def _at_or_after(moment, now):
    return now.weekday() == moment.day and now.time() >= moment.time


def _report_error(app, job, error):
    key = f"last_error:{job}"
    prev = app.db.kv_get(key) or {}
    now = utcnow()
    text = str(error)
    stale = not prev.get("ts") or now - datetime.fromisoformat(prev["ts"]) > timedelta(hours=6)
    if prev.get("text") != text or stale:
        app.notify(f"⚠️ {job}: {text}")
        app.db.kv_set(key, {"text": text, "ts": now.isoformat()})


def plan_now(app, now):
    summary = planner.plan_ahead(app, now)
    app.notify(
        f"🗓 Νέο πλάνο {summary['start']:%d/%m}–{summary['end']:%d/%m}: {summary['created']} posts"
        + (f", {summary['blocked']} μπλοκαρίστηκαν από τους κανόνες" if summary["blocked"] else "")
        + (f", {summary['missing']} slots χωρίς ιδέα" if summary["missing"] else "")
        + ". Ξεκινάει το generation."
    )
    return summary


def tick(app, now):
    cfg, db = app.cfg, app.db

    def guarded(job, fn):
        try:
            return fn()
        except Exception as e:
            log.exception(job)
            _report_error(app, job, e)

    planned_until = db.kv_get("planned_until")
    needs_plan = not planned_until or planned_until < (now.date() + timedelta(days=7)).isoformat()
    last_try = db.kv_get("plan_attempt")
    if _at_or_after(cfg.plan_at, now) and needs_plan and last_try != now.strftime("%Y-%m-%d %H"):
        db.kv_set("plan_attempt", now.strftime("%Y-%m-%d %H"))
        guarded("plan", lambda: plan_now(app, now))

    guarded("generate", lambda: generate_pending(app, now))
    guarded("review", lambda: send_reviews(app))
    guarded("publish", lambda: publish_due(app, now))

    if db.kv_get("cleanup_day") != now.date().isoformat():
        db.kv_set("cleanup_day", now.date().isoformat())
        guarded("cleanup", lambda: cleanup_storage(app, now))
        guarded("health", lambda: health.health_check(app))

    week = _week_id(now)
    if app.fanvue and app.fanvue.connected:
        guarded("fanvue", lambda: publish_fanvue(app, now))
    elif _at_or_after(cfg.fanvue_pack_at, now) and db.kv_get("fanvue_pack_week") != week:
        db.kv_set("fanvue_pack_week", week)
        guarded("fanvue", lambda: send_fanvue_pack(app))

    last_check = db.kv_get("chat_last_check")
    if not last_check or (now - datetime.fromisoformat(last_check)).total_seconds() >= cfg.chat["check_every_seconds"]:
        db.kv_set("chat_last_check", now.isoformat())
        guarded("chat", lambda: chat.poll_chats(app, now))

    if _at_or_after(cfg.report_at, now) and db.kv_get("report_week") != week:
        db.kv_set("report_week", week)
        guarded("report", lambda: app.notify(report_text(app, now)))
