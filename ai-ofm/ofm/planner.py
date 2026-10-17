"""Weekly content plan: code decides the slots, Claude fills in ideas, prompts and captions."""

import json
from datetime import date, datetime, time, timedelta

from . import guardrails

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
                },
                "required": ["slot", "idea", "image_prompt", "motion_prompt", "caption", "hashtags"],
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
- Look (her LoRA already handles face, hair and body; never describe them): {p['appearance']}
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
3. She is an AI character. Captions never claim she is human or real, never say "not AI", and never promise meetups or real-life contact.
4. Items that target Instagram, TikTok, YouTube or X are strictly safe for work: no nudity, no sexual acts, no explicit wording. Swimwear, gym wear and night-out outfits are fine.
5. Fanvue items are for her paid page, in this style: {p.get('fanvue_style', 'glamour photos')}. Keep within that style and the rules above.

For each slot write:
- idea: one short sentence in {p['owner_language']} so the owner can approve it at a glance.
- image_prompt: English, 40-80 words: scene, outfit, pose, framing, lighting, camera angle. Do not describe her face, hair or body and do not use her name.
- motion_prompt: for video slots, English, about 5 seconds of subtle, natural motion (camera move plus what she does). For image slots, an empty string.
- caption: in {p['caption_language']}, in her voice, 1-3 short sentences that fit the platform. For Fanvue items, a short teaser for subscribers.
- hashtags: 3-8 relevant hashtags including #AI.

Spread the pillars, settings and outfits across the week, match the time of day of each slot, and return exactly one item per slot number."""


def user_prompt(slots, recent_ideas):
    lines = []
    for i, s in enumerate(slots):
        when = "vault" if s["targets"] == ["fanvue"] else s["slot_at"].strftime("%a %d %b %H:%M")
        lines.append({"slot": i, "when": when, "kind": s["kind"], "targets": s["targets"]})
    return (
        f"Plan these {len(slots)} slots:\n{json.dumps(lines)}\n\n"
        f"Recent ideas, don't repeat them:\n{_bullets(recent_ideas)}"
    )


def request_plan(client, cfg, db, slots):
    with client.beta.messages.stream(
        model=cfg.models["claude"],
        max_tokens=64000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": ITEM_SCHEMA}},
        system=system_prompt(cfg),
        messages=[{"role": "user", "content": user_prompt(slots, db.recent_ideas())}],
    ) as stream:
        response = stream.get_final_message()

    price = cfg.models["claude_usd_per_mtok"]
    usage = response.usage
    db.add_cost(
        "claude",
        (usage.input_tokens * price["input"] + usage.output_tokens * price["output"]) / 1_000_000,
        f"plan {len(slots)} slots",
    )
    if response.stop_reason == "refusal":
        raise PlanError("Το Claude αρνήθηκε το πλάνο. Έλεγξε τα κείμενα στο persona.yaml.")
    if response.stop_reason == "max_tokens":
        raise PlanError("Το πλάνο κόπηκε (max_tokens). Μείωσε τα slots ή το fanvue_per_week.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        items = json.loads(text)["items"]
    except (ValueError, KeyError) as e:
        raise PlanError(f"Μη έγκυρη απάντηση από το Claude: {e}")
    return {item["slot"]: item for item in items if isinstance(item.get("slot"), int)}


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
    items = request_plan(app.claude, cfg, db, slots)

    summary = {"start": start, "end": start + timedelta(days=days - 1), "created": 0, "blocked": 0, "missing": 0}
    for i, slot in enumerate(slots):
        item = items.get(i)
        if not item:
            summary["missing"] += 1
            continue
        hashtags = guardrails.with_disclosure(item["hashtags"])
        motion = item["motion_prompt"] if slot["kind"] == "video" else ""
        bad = guardrails.violations(item["idea"], item["image_prompt"], motion, item["caption"], " ".join(hashtags))
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
            status="blocked" if bad else "planned",
            error=("guardrails: " + ", ".join(bad)) if bad else None,
        )
        summary["blocked" if bad else "created"] += 1
    db.kv_set("planned_until", summary["end"].isoformat())
    return summary
