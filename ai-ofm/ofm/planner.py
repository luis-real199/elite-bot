"""Weekly content plan: code decides the slots, Claude fills in ideas, prompts and captions."""

import json
from datetime import date, datetime, time, timedelta

from . import guardrails, llm

MECHANICS = ["choice", "rating", "hot_take", "guess", "relatable", "useful", "series", "none"]

ENGAGEMENT = """Engagement: every social item must give viewers a reason to comment or share. Pick one mechanic per item and vary them across the week:
- choice: ask viewers to pick (outfit 1, 2 or 3; iced or hot)
- rating: ask for a number with a stake ("rate my fit 1-10, lowest score picks next week's outfit")
- hot_take: a light, harmless opinion people will argue with ("gym at 6am > gym at 6pm")
- guess: ask viewers to guess something about her (her height, her coffee order)
- relatable: a POV people send to a friend ("POV: your gym partner cancels again")
- useful: something worth saving (3 beach spots, a 20-minute hotel workout)
- series: a recurring numbered format people follow ("Outfit #8", "Day 12 of...")
Never use engagement bait such as "like if", "tag 3 friends" or "comment YES": Instagram demotes it.
The caption ends with the same question or stake as the hook, phrased naturally.
- hook: on-screen text for the first seconds, max 8 words, no hashtags, no emoji, readable without sound
- pinned_comment: the first comment she pins under the post, continuing the mechanic
- alt_caption: only when targets include instagram_backup (her second Instagram account): the same idea and mechanic in different words, so the two accounts never share identical text. Otherwise an empty string.
For Fanvue items use an empty hook and pinned_comment and mechanic "none"."""

ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slot": {"type": "integer"},
                    "idea": {"type": "string"},
                    "image_prompt": {"type": "string"},
                    "motion_prompt": {"type": "string"},
                    "caption": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "hook": {"type": "string"},
                    "alt_caption": {"type": "string"},
                    "pinned_comment": {"type": "string"},
                    "mechanic": {"type": "string", "enum": MECHANICS},
                },
                "required": ["slot", "idea", "image_prompt", "motion_prompt", "caption", "hashtags",
                             "hook", "pinned_comment", "mechanic", "alt_caption"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


class PlanError(Exception):
    pass


def build_slots(cfg, start, days=7):
    slots = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        for s in cfg.slots:
            if day.weekday() in s.days:
                slots.append({"slot_at": datetime.combine(day, s.time, cfg.tz), "kind": s.kind, "targets": s.targets})
    slots.sort(key=lambda s: s["slot_at"])
    vault_at = datetime.combine(start, time(9, 0), cfg.tz)
    slots += [{"slot_at": vault_at, "kind": "image", "targets": ["fanvue"]} for _ in range(cfg.fanvue_per_week)]
    return slots


def _bullets(items):
    return "\n".join(f"  - {i}" for i in items or []) or "  - (none)"


def system_prompt(cfg):
    p = cfg.persona
    return f"""You are the content planner for {p['name']}, a fictional, openly AI-generated influencer ({p['disclosure']}).

Persona:
- Age: {p['age']}, an adult {p['subject']}.
- Look (reference photos and her LoRA already handle face, hair and body; never describe them): {p['appearance']}
- Vibe: {p.get('vibe', '')}
- Niche: {p.get('niche', '')}
- Voice: {p.get('personality', '')}
- Content pillars:
{_bullets(p.get('content_pillars'))}
- Always avoid:
{_bullets(p.get('avoid'))}

Hard rules:
1. Adults only. Nothing that suggests youth: no school settings or uniforms, no childlike poses, props or wording, no ages under 21.
2. No real people: no celebrities, lookalikes, real influencers or public figures, and no brand logos.
3. She is an AI character. Captions never claim she is human or real, never say "not AI", and never promise meetups or real-life contact. They also do not bring up being AI.
4. Items that target Instagram, TikTok, YouTube or X are strictly safe for work: no nudity, no sexual acts, no explicit wording. Swimwear, gym wear and night-out outfits are fine.
5. Fanvue items are for her paid page, in this style: {p.get('fanvue_style', 'glamour photos')}. Keep within that style and the rules above.

For each slot write:
- idea: one short sentence in {p['owner_language']} so the owner can approve it at a glance.
- image_prompt: English, 40-80 words: scene, outfit, pose, framing, lighting, camera angle. Write it as a real, unposed photo someone took on a phone (mirror selfie, friend holding the phone, arm's-length selfie, candid mid-action): everyday places with real clutter, natural or ambient light, imperfect framing. Never use words like 8k, render, hyperrealistic, cinematic, studio, flawless, perfect, glowing or airbrushed. Do not describe her face, hair or body and do not use her name.
- motion_prompt: for video slots, English, {cfg.generation['video_duration']} seconds of natural motion (camera move plus what she does) whose last frame matches the first so the reel loops. For image slots, an empty string.
- caption: in {p['caption_language']}, in her voice, 1-3 short sentences that fit the platform. For Fanvue items, a short teaser for subscribers.
- hashtags: 3-8 relevant hashtags. Do not add an AI tag yourself; one is appended automatically.

Hooks, captions and pinned comments do not mention that she is AI: her bio and the platform's AI label
handle disclosure. They also never claim or imply that she is a real human.

{ENGAGEMENT}

Spread the pillars, settings and outfits across the week, match the time of day of each slot, and return exactly one item per slot number."""


def user_prompt(indexed_slots, recent_ideas, fan_requests=(), swipes=()):
    lines = []
    for i, s in indexed_slots:
        when = "vault" if s["targets"] == ["fanvue"] else s["slot_at"].strftime("%a %d %b %H:%M")
        lines.append({"slot": i, "when": when, "kind": s["kind"], "targets": s["targets"]})
    return (
        f"Plan these {len(lines)} slots:\n{json.dumps(lines)}\n\n"
        f"Recent ideas, don't repeat them:\n{_bullets(recent_ideas)}\n\n"
        f"What paying fans asked for in chat (make several Fanvue items match these):\n{_bullets(fan_requests)}\n\n"
        "Formats that went viral for other creators. Use several for her reels, adapting the format and mechanic "
        f"to her own setting; never copy their words, footage or appearance:\n{_bullets(swipes)}"
    )


def request_plan(app, slots, fan_requests=(), swipes=()):
    """Claude plans the whole week in one call; free APIs get it in chunks that fit their per-minute limits.
    A chunk the model cannot answer with valid JSON is split in half; a single slot that still fails is left out."""
    cfg, db = app.cfg, app.db
    s = llm.settings(cfg)
    indexed = list(enumerate(slots))
    size = len(indexed) if s["provider"] == "claude" else s["plan_chunk"]
    pending = [indexed[i:i + size] for i in range(0, len(indexed), size)]
    items, last_error = {}, None
    while pending:
        chunk = pending.pop(0)
        try:
            data = llm.ask_json(
                app, system=system_prompt(cfg), schema=ITEM_SCHEMA, kind="claude", effort="medium",
                max_tokens=64000, stream=True,
                content=user_prompt(chunk, db.recent_ideas() + [i["idea"] for i in items.values()], fan_requests, swipes),
            )
        except llm.LLMRefusal:
            raise PlanError("Το μοντέλο αρνήθηκε το πλάνο. Έλεγξε τα κείμενα στο persona.yaml.")
        except llm.LLMBadOutput as e:
            last_error = e
            if len(chunk) > 1:
                half = len(chunk) // 2
                pending[:0] = [chunk[:half], chunk[half:]]
            continue
        except llm.LLMError as e:
            raise PlanError(f"Το πλάνο απέτυχε: {e}")
        wanted = {i for i, _ in chunk}
        for item in data.get("items") or []:
            if isinstance(item, dict) and item.get("slot") in wanted:
                items[item["slot"]] = item
    if not items and last_error:
        raise PlanError(f"Το πλάνο απέτυχε: {last_error}")
    return items


def next_start(db, now):
    start = (now + timedelta(days=1)).date()
    planned_until = db.kv_get("planned_until")
    if planned_until:
        start = max(start, date.fromisoformat(planned_until) + timedelta(days=1))
    return start


def plan_ahead(app, now, days=7):
    cfg, db = app.cfg, app.db
    start = next_start(db, now)
    slots = build_slots(cfg, start, days)
    requests, swipes = db.fan_requests(), db.swipes()
    items = request_plan(app, slots, [r["text"] for r in requests], [s["text"] for s in swipes])
    db.mark_requests_used([r["id"] for r in requests])
    db.mark_swipes_used([s["id"] for s in swipes])

    summary = {"start": start, "end": start + timedelta(days=days - 1), "created": 0, "blocked": 0, "missing": 0}
    for i, slot in enumerate(slots):
        item = items.get(i)
        if not item:
            summary["missing"] += 1
            continue
        hashtags = guardrails.with_disclosure(item["hashtags"])
        motion = item["motion_prompt"] if slot["kind"] == "video" else ""
        social = slot["targets"] != ["fanvue"]
        hook = item.get("hook", "") if social else ""
        pinned = item.get("pinned_comment", "") if social else ""
        bad = guardrails.violations(item["idea"], item["image_prompt"], motion, item["caption"], " ".join(hashtags), hook, pinned)
        db.insert_post(
            batch=start.isoformat(),
            slot_at=slot["slot_at"],
            kind=slot["kind"],
            targets=slot["targets"],
            idea=item["idea"],
            image_prompt=item["image_prompt"],
            motion_prompt=motion,
            caption=item["caption"],
            hashtags=hashtags,
            hook=hook,
            pinned_comment=pinned,
            alt_caption=item.get("alt_caption", "") if "instagram_backup" in slot["targets"] else "",
            mechanic=item.get("mechanic", "none") if social else "none",
            status="blocked" if bad else "planned",
            error=("guardrails: " + ", ".join(bad)) if bad else None,
        )
        summary["blocked" if bad else "created"] += 1
    db.kv_set("planned_until", summary["end"].isoformat())
    return summary
