"""Fan chat on Fanvue: Claude drafts replies in the persona's voice and suggests PPV from the vault.

Nothing is ever sent to a fan without the owner: every draft goes to Telegram and is sent only
when the owner taps 📤 or replies with their own text.

Modes (chat.mode in persona.yaml):
- approve: drafts come to Telegram for one-tap approval
- off: nothing is read or drafted
"""

import json
import logging
from datetime import timedelta

from . import guardrails
from .db import utcnow
from .fanvue import FanvueError
from .telegram import keyboard

log = logging.getLogger("ofm")

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "offer_media_uuid": {"type": "string"},
        "offer_price_usd": {"type": "number"},
        "escalate": {"type": "boolean"},
        "escalate_reason": {"type": "string"},
        "fan_request": {"type": "string"},
    },
    "required": ["reply", "offer_media_uuid", "offer_price_usd", "escalate", "escalate_reason", "fan_request"],
    "additionalProperties": False,
}

EST_COST = 0.05  # rough upper bound per draft, used against chat.weekly_usd


def _bullets(items):
    return "\n".join(f"- {i}" for i in items or []) or "- (none)"


def system_prompt(cfg):
    p, price = cfg.persona, cfg.fanvue["ppv_price_usd"]
    return f"""You write chat replies for {p['name']}, an openly AI-generated character ({p['disclosure']}) on her Fanvue page. Fans subscribe knowing she is AI.

Who she is:
- {p['age']}-year-old adult {p['subject']}. {p.get('backstory', '')}
- Vibe: {p.get('vibe', '')}
- Voice: {p.get('personality', '')}
- Texting style: {p.get('chat_style', '')}

She never says:
{_bullets(p.get('never_say'))}

Hard rules:
1. She is an AI character. If asked whether she is real, she says playfully but clearly that she is AI. Never claim to be human, never promise to meet, call, video call or share contact details, a location or social handles outside Fanvue.
2. Money only through Fanvue. Never mention or accept payment anywhere else.
3. Flirty and teasing is fine; keep messages suggestive, never sexually explicit, and never describe sexual acts.
4. Adults only. If anything suggests the fan may be under 18, write a short neutral reply and set escalate=true.
5. Set escalate=true (and still draft a reply) when the fan is upset, asks for a refund, mentions self-harm, threatens, asks for something against these rules, or wants a custom request that needs the owner.

Selling:
- Build rapport first; do not pitch in every message. Offer at most one item from the catalogue when the conversation gives a natural opening, describing it as a tease, never graphically.
- To offer, put the item's id in offer_media_uuid and a price in offer_price_usd between {price['min']:g} and {price['max']:g} (default {price['default']:g}). Otherwise use an empty string and 0. Only use ids from the catalogue.
- If the fan asks for a kind of content (outfit, setting, theme), summarise it in fan_request in a few words so the owner can create it; else an empty string.

Reply with 1-3 short texts in her style, in the fan's language if it is not English."""


def catalogue_text(db, fan_uuid, limit=20):
    offered = db.offered_to(fan_uuid)
    items = [m for m in db.fanvue_media(purpose="vault") if m["media_uuid"] not in offered][-limit:]
    if not items:
        return "Catalogue: (empty, do not offer anything)"
    return "Catalogue (id: what it shows):\n" + "\n".join(f"- {m['media_uuid']}: {m['description']}" for m in items)


def transcript(messages, me_uuid, limit=20):
    lines = []
    for m in messages[-limit:]:
        who = "Her" if (m.get("sender") or {}).get("uuid") == me_uuid else "Fan"
        text = (m.get("text") or "").strip()
        if m.get("hasMedia"):
            text = (text + f" [{m.get('mediaType') or 'media'}]").strip()
        if m.get("pricing") and not m.get("purchasedAt"):
            text += " [locked PPV, not bought yet]"
        elif m.get("purchasedAt"):
            text += " [PPV bought]"
        if text:
            lines.append(f"{who}: {text}")
    return "\n".join(lines)


def draft_reply(app, fan, messages, me_uuid):
    cfg, db = app.cfg, app.db
    response = app.claude.beta.messages.create(
        model=cfg.models["claude"],
        max_tokens=8000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": REPLY_SCHEMA}},
        system=[
            {"type": "text", "text": system_prompt(cfg), "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": catalogue_text(db, fan["uuid"])},
        ],
        messages=[{
            "role": "user",
            "content": (
                f"Fan: {fan.get('displayName') or fan.get('handle')}"
                f"{' (top spender)' if fan.get('isTopSpender') else ''}\n\n"
                f"Chat so far, oldest first:\n{transcript(messages, me_uuid)}\n\nWrite her next reply."
            ),
        }],
    )
    price = cfg.models["claude_usd_per_mtok"]
    usage = response.usage
    db.add_cost("chat", (usage.input_tokens * price["input"] + usage.output_tokens * price["output"]) / 1_000_000, fan["uuid"])
    if response.stop_reason == "refusal":
        return {"reply": "", "offer_media_uuid": "", "offer_price_usd": 0, "escalate": True,
                "escalate_reason": "το Claude δεν απάντησε σε αυτό το chat", "fan_request": ""}
    text = next((b.text for b in response.content if b.type == "text"), "")
    return json.loads(text)


def _clean_offer(cfg, db, fan_uuid, draft):
    """Keep an offer only if it points at real catalogue media; clamp the price. Returns (uuid, cents)."""
    uuid = (draft.get("offer_media_uuid") or "").strip()
    vault = {m["media_uuid"] for m in db.fanvue_media(purpose="vault")}
    if not uuid or uuid not in vault or uuid in db.offered_to(fan_uuid):
        return None, None
    limits = cfg.fanvue["ppv_price_usd"]
    usd = draft.get("offer_price_usd") or limits["default"]
    usd = min(max(float(usd), limits["min"]), limits["max"])
    return uuid, int(round(usd * 100))


def send_reply(app, fan_uuid, text, media_uuid=None, price_cents=None):
    app.fanvue.send_message(fan_uuid, text, [media_uuid] if media_uuid else None, price_cents)
    if media_uuid:
        app.db.add_offer(fan_uuid, media_uuid, price_cents)
    try:
        app.fanvue.messages(fan_uuid, size=1, mark_read=True)
    except FanvueError:
        pass


def draft_card(draft, fan_lines):
    offer = f"\n💰 PPV ${draft['offer_price_cents'] / 100:.0f}" if draft.get("offer_media_uuid") else ""
    reason = f"\n⚠️ {draft['reason']}" if draft.get("reason") else ""
    return (
        f"💬 {draft['fan_name']}{reason}\n\n{fan_lines}\n\n"
        f"✍️ Πρόταση:\n{draft['text'] or '(καμία)'}{offer}\n\n"
        "Πάτα 📤 για αποστολή ή κάνε reply σε αυτό το μήνυμα με δικό σου κείμενο."
    )


def poll_chats(app, now):
    """Read unread Fanvue chats once. Returns how many chats were handled."""
    cfg, db = app.cfg, app.db
    mode = db.kv_get("chat_mode") or cfg.chat["mode"]
    if mode == "off" or not app.fanvue or not app.fanvue.connected or db.kv_get("paused"):
        return 0
    if db.spent_on("chat", utcnow() - timedelta(days=7)) + EST_COST > cfg.chat["weekly_usd"]:
        raise RuntimeError(f"Το όριο του chat (${cfg.chat['weekly_usd']}/εβδομάδα) εξαντλήθηκε")
    me = db.kv_get("fanvue_me") or {}
    me_uuid = me.get("uuid")
    if not me_uuid:
        me_uuid = app.fanvue.me().get("uuid")
        db.kv_set("fanvue_me", {"uuid": me_uuid})

    handled = 0
    for chat in app.fanvue.unread_chats():
        if handled >= cfg.chat["max_chats_per_check"]:
            break
        fan, last = chat.get("user") or {}, chat.get("lastMessage") or {}
        if not fan.get("uuid") or not last.get("uuid") or last.get("senderUuid") == me_uuid:
            continue
        if db.chat_seen(fan["uuid"]) == last["uuid"]:
            continue
        messages = app.fanvue.messages(fan["uuid"])
        draft = draft_reply(app, fan, messages, me_uuid)
        db.set_chat_seen(fan["uuid"], last["uuid"])
        handled += 1

        if draft.get("fan_request"):
            db.add_fan_request(fan["uuid"], draft["fan_request"][:200])
        fan_text = "\n".join(m.get("text") or "" for m in messages if (m.get("sender") or {}).get("uuid") != me_uuid)
        reasons = []
        if draft.get("escalate"):
            reasons.append(draft.get("escalate_reason") or "θέλει εσένα")
        if fan.get("isTopSpender"):
            reasons.append("⭐ top spender")
        if "minor" in guardrails.violations(fan_text):
            reasons.append("πιθανός ανήλικος: μην απαντήσεις αυτόματα")
        bad = guardrails.violations(draft.get("reply"))
        if bad:
            reasons.append("η πρόταση έσπασε κανόνες: " + ", ".join(bad))
        media_uuid, price_cents = _clean_offer(cfg, db, fan["uuid"], draft)
        name = fan.get("displayName") or fan.get("handle") or "fan"

        draft_id = db.add_draft(fan["uuid"], name, draft.get("reply") or "", media_uuid, price_cents,
                                "; ".join(reasons) or None, "pending")
        if app.tg:
            recent = [f"👤 {m.get('text')}" for m in messages if (m.get("sender") or {}).get("uuid") != me_uuid and m.get("text")][-3:]
            card = draft_card(db.draft(draft_id), "\n".join(recent))
            buttons = [("📤 Στείλε", f"cs:{draft_id}"), ("🙅 Άσε το", f"cx:{draft_id}")] if draft.get("reply") and not bad else [("🙅 Άσε το", f"cx:{draft_id}")]
            msg = app.tg.send(card, markup=keyboard([buttons]), silent=not reasons)
            db.update_draft(draft_id, tg_message_id=msg["message_id"])
    return handled


def draft_action(app, action, draft_id):
    """Telegram button on a chat draft. Returns (reply text, button label)."""
    draft = app.db.draft(draft_id)
    if not draft or draft["status"] != "pending":
        return "Ήδη το χειρίστηκες", None
    if action == "cs":
        send_reply(app, draft["fan_uuid"], draft["text"], draft["offer_media_uuid"], draft["offer_price_cents"])
        app.db.update_draft(draft_id, status="sent")
        return "📤 Στάλθηκε", "📤 Στάλθηκε"
    app.db.update_draft(draft_id, status="skipped")
    return "Το άφησες", "🙅 Δεν στάλθηκε"


def send_custom(app, tg_message_id, text):
    """The owner replied to a draft card with their own words: send those instead."""
    draft = app.db.draft(tg_message_id=tg_message_id)
    if not draft:
        return False
    if guardrails.violations(text):
        app.notify("⚠️ Το κείμενό σου έχει κάτι που σπάει τους κανόνες, δεν στάλθηκε.")
        return True
    send_reply(app, draft["fan_uuid"], text)
    app.db.update_draft(draft["id"], status="sent_custom", text=text)
    app.notify(f"📤 Στάλθηκε στον/στην {draft['fan_name']}.", silent=True)
    return True


def chat_status(app):
    db = app.db
    counts = db.draft_counts(utcnow() - timedelta(days=7))
    mode = db.kv_get("chat_mode") or app.cfg.chat["mode"]
    return (
        f"💬 Chat: {mode}{' · Fanvue ✅' if app.fanvue and app.fanvue.connected else ' · Fanvue ❌ (/fanvue_login)'}\n"
        f"7 ημέρες: {counts.get('sent', 0) + counts.get('sent_custom', 0)} στάλθηκαν · "
        f"{counts.get('pending', 0)} περιμένουν · {counts.get('skipped', 0)} αφέθηκαν\n"
        f"💶 ${db.spent_on('chat', utcnow() - timedelta(days=7)):.2f} / ${app.cfg.chat['weekly_usd']}"
    )
