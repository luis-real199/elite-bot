import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
SOCIAL_TARGETS = {"instagram_reel", "instagram_story", "instagram_feed", "instagram_backup", "tiktok", "youtube_short", "x"}
VIDEO_TARGETS = {"instagram_reel", "tiktok", "youtube_short"}
TARGETS = SOCIAL_TARGETS | {"fanvue"}
TARGET_LABELS = {
    "instagram_reel": "IG Reel", "instagram_story": "IG Story", "instagram_feed": "IG Feed",
    "instagram_backup": "IG backup", "tiktok": "TikTok", "youtube_short": "YT Shorts", "x": "X", "fanvue": "Fanvue",
}
MIN_AGE = 21

DEFAULT_MODELS = {
    "claude": "claude-opus-5-5",
    "claude_usd_per_mtok": {"input": 4.0, "output": 20.0},
    "image": "fal-ai/flux-lora",
    "ref_image": "fal-ai/nano-banana-pro/edit",
    "face": "fal-ai/nano-banana-pro",
    "edit": "fal-ai/flux-pro/kontext",
    "video": "fal-ai/kling-video/v3/standard/image-to-video",
    "trainer": "fal-ai/flux-lora-fast-training",
    "voice": "fal-ai/kling-video/create-voice",
}
SOFTER = [  # Google's moderation on Nano Banana reads the words: when it refuses, the same shape in plainer ones
    ("very large, round, full breasts (visibly enhanced, pushed up)", "a very large full bust"),
    ("a full natural-looking bust (about 34C, soft natural shape with natural movement)", "a full bust"),
    ("a big round lifted squat-built butt that looks strong and firm", "strong round glutes"),
    ("an extremely big, round, lifted butt (far wider than her tiny waist)", "very big round hips and backside"),
    ("a very big round lifted butt", "very big round hips and backside"),
    ("tight, fitted, low-cut outfits", "fitted outfits"),
    ("surgically enhanced", "full"),
    ("breast implants", "large bust"),
    ("deep cleavage", "a fitted top"),
    ("sexy", "glamorous"),
]


def soften(text):
    for strong, mild in SOFTER:
        text = text.replace(strong, mild)
    return text


# Real photos are full of small accidents. Written as observed detail, not as a request, in every image prompt.
REALISM = (
    "Real unedited iPhone photo. Visible skin pores and slight T-zone shine, a few flyaway baby hairs at the hairline, "
    "faint natural under-eye shadow, mildly uneven skin tone with warmer cheeks, visible fabric weave with small wrinkles "
    "and a strap mark on the skin, ordinary clutter at the frame edges, one slightly blown highlight and uneven fill light, "
    "fine sensor grain with a touch of motion blur, real cuticles on the nails, jewelry hanging with real weight. "
    "No beauty filter, no smoothing, no HDR glow, no studio look."
)

CONSISTENCY_LINE = (
    "Remain the same model from the reference images, preserving her facial features, "
    "body proportions, and identity exactly."
)

ENV_KEYS = [
    "ANTHROPIC_API_KEY", "FAL_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_ID",
    "BUFFER_API_KEY", "BUFFER_CHANNEL_INSTAGRAM", "BUFFER_CHANNEL_INSTAGRAM_BACKUP", "BUFFER_CHANNEL_TIKTOK",
    "BUFFER_CHANNEL_YOUTUBE", "BUFFER_CHANNEL_X",
    "SUPABASE_URL", "SUPABASE_SECRET_KEY", "SUPABASE_BUCKET", "LORA_URL",
    "FANVUE_CLIENT_ID", "FANVUE_CLIENT_SECRET", "FANVUE_REDIRECT_URI",
    "GROQ_API_KEY", "GEMINI_API_KEY",
]
CHAT_MODES = ("approve", "auto", "off")
LLM_PROVIDERS = ("claude", "groq", "gemini")


class ConfigError(Exception):
    pass


@dataclass
class Slot:
    time: time
    kind: str
    targets: list
    days: list
    video: dict = None  # {"seconds": 15, "voice": True}; None = generation defaults


@dataclass
class Moment:
    day: int
    time: time


@dataclass
class Config:
    persona: dict
    style: dict
    slots: list
    fanvue_per_week: int
    tz: ZoneInfo
    plan_at: Moment
    report_at: Moment
    fanvue_pack_at: Moment
    publish_ahead_hours: int
    weekly_budget: float
    estimates: dict
    generation: dict
    models: dict
    fanvue: dict
    chat: dict
    env: dict
    data_dir: Path
    slug: str = "persona"
    backup_delay_minutes: int = 180

    def secret(self, key):
        return self.env.get(key) or None


def load_dotenv(path):
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def _time(value, where):
    try:
        hours, minutes = str(value).split(":")
        return time(int(hours), int(minutes))
    except ValueError:
        raise ConfigError(f"{where}: η ώρα πρέπει να είναι σαν \"19:00\", όχι {value!r}")


def _day(value, where):
    if value not in DAYS:
        raise ConfigError(f"{where}: η μέρα πρέπει να είναι μία από {DAYS}")
    return DAYS.index(value)


def _moment(raw, where):
    return Moment(_day(raw.get("day"), where), _time(raw.get("time"), where))


def _slots(raw):
    slots = []
    for i, item in enumerate(raw or []):
        where = f"schedule.slots[{i}]"
        kind = item.get("kind")
        if kind not in ("image", "video"):
            raise ConfigError(f"{where}: kind πρέπει να είναι image ή video")
        targets = item.get("targets") or []
        unknown = set(targets) - TARGETS
        if not targets or unknown:
            raise ConfigError(f"{where}: άγνωστα targets {sorted(unknown)}; επιτρέπονται {sorted(TARGETS)}")
        if kind == "image" and set(targets) & VIDEO_TARGETS:
            raise ConfigError(f"{where}: τα {sorted(set(targets) & VIDEO_TARGETS)} θέλουν kind: video")
        days = [_day(d, where) for d in item.get("days") or DAYS]
        video = item.get("video")
        if video is not None:
            if kind != "video" or not isinstance(video, dict):
                raise ConfigError(f"{where}: το video: {{seconds, voice}} πάει μόνο σε slots με kind: video")
            seconds = int(video.get("seconds", 8))
            if not 3 <= seconds <= 15:
                raise ConfigError(f"{where}: video.seconds από 3 έως 15")
            video = {"seconds": seconds, "voice": bool(video.get("voice", False))}
        slots.append(Slot(_time(item.get("time"), where), kind, list(targets), days, video))
    return slots


def load_config(path=None, env=None):
    env = dict(os.environ) if env is None else env
    path = Path(path or env.get("OFM_CONFIG", "persona.yaml"))
    if not path.exists():
        raise ConfigError(f"Δεν βρέθηκε το {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    persona = raw.get("persona") or {}
    for key in ("name", "age", "trigger_word", "appearance"):
        if not persona.get(key):
            raise ConfigError(f"persona.{key} λείπει")
    if int(persona["age"]) < MIN_AGE:
        raise ConfigError(f"persona.age πρέπει να είναι τουλάχιστον {MIN_AGE}")
    persona.setdefault("subject", "woman")
    persona.setdefault("caption_language", "English")
    persona.setdefault("owner_language", "Greek")
    persona.setdefault("disclosure", "AI-generated character")
    persona.setdefault("disclosure_tag", "#aigenerated")
    persona.setdefault("hashtags", True)
    persona.setdefault("never_say", [])
    persona.setdefault("marks", "")      # moles, freckles, a slight asymmetry: pinned to places, identical in every shot
    persona.setdefault("skin_hex", "")   # a value cannot be reinterpreted between generations; a description can
    persona.setdefault("chat_style", "short, playful texts, asks questions back")

    schedule = raw.get("schedule") or {}
    slots = _slots(schedule.get("slots"))
    if not slots:
        raise ConfigError("schedule.slots είναι άδειο")
    budget = raw.get("budget") or {}
    generation = {
        "image_size": {"width": 896, "height": 1600},
        "video_duration": "8",
        "video_audio": False,
        "hook_overlay": True,
        "lora_scale": 1.0,
        "training_steps": 1000,
        "max_regenerations": 3,
        "social_safety_checker": True,
        "fanvue_safety_checker": True,
        "consistency_line": CONSISTENCY_LINE,
        "quality_check": True,
        "review_sample": 1.0,
        "idea_approval": True,
        "carousel_size": 3,
        "auto_retry": False,  # a failed image is shown to the owner; nothing is remade without a tap
        "voice_lock": True,  # her voice is cloned from the first approved spoken reel and reused in every later one
        **(raw.get("generation") or {}),
    }
    # The social checker is not optional: mainstream platforms ban explicit content.
    generation["social_safety_checker"] = True
    if not 0 <= float(generation["review_sample"]) <= 1:
        raise ConfigError("generation.review_sample πρέπει να είναι από 0 έως 1")

    fanvue = {"feed_per_week": 7, "feed_time": "20:00", "vault_folder": "Chat PPV", **(raw.get("fanvue") or {})}
    fanvue["feed_time"] = _time(fanvue["feed_time"], "fanvue.feed_time")
    price = {"min": 8, "default": 12, "max": 25, **(fanvue.get("ppv_price_usd") or {})}
    if float(price["min"]) < 3:
        raise ConfigError("fanvue.ppv_price_usd.min: το Fanvue δέχεται από $3 και πάνω")
    fanvue["ppv_price_usd"] = {k: float(v) for k, v in price.items()}
    llm_settings = (raw.get("models") or {}).get("llm") or {}
    if llm_settings.get("provider") not in (None, "", *LLM_PROVIDERS):
        raise ConfigError(f"models.llm.provider πρέπει να είναι ένα από {LLM_PROVIDERS}")
    chat = {"mode": "approve", "weekly_usd": 15, "max_chats_per_check": 5, "check_every_seconds": 60, **(raw.get("chat") or {})}
    if chat["mode"] not in CHAT_MODES:
        raise ConfigError(f"chat.mode πρέπει να είναι ένα από {CHAT_MODES}")

    return Config(
        persona=persona,
        style={"realism": REALISM, **(raw.get("style") or {})},
        slots=slots,
        fanvue_per_week=int(schedule.get("fanvue_per_week", 0)),
        tz=ZoneInfo(schedule.get("timezone", "Europe/Athens")),
        plan_at=_moment(schedule.get("plan") or {"day": "sun", "time": "18:00"}, "schedule.plan"),
        report_at=_moment(schedule.get("report") or {"day": "sun", "time": "20:00"}, "schedule.report"),
        fanvue_pack_at=_moment(schedule.get("fanvue_pack") or {"day": "mon", "time": "09:00"}, "schedule.fanvue_pack"),
        publish_ahead_hours=int(schedule.get("publish_ahead_hours", 36)),
        weekly_budget=float(budget.get("weekly_usd", 15)),
        estimates={"image": 0.07, "ref_image": 0.15, "face": 0.15, "edit": 0.04, "video": 0.68, "video_voice": 1.9, "voice": 0.01,
                   "qc": 0.02, "training": 3.0,
                   **(budget.get("estimates_usd") or {})},
        generation=generation,
        models={**DEFAULT_MODELS, **(raw.get("models") or {})},
        fanvue=fanvue,
        chat=chat,
        env={k: env.get(k, "") for k in ENV_KEYS},
        data_dir=Path(env.get("OFM_DATA_DIR") or path.parent / "data"),
        slug=env.get("OFM_PERSONA") or path.parent.resolve().name,
        backup_delay_minutes=int(schedule.get("backup_delay_minutes", 180)),
    )
