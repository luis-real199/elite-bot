"""One-time persona setup: pick a face, build a dataset around it, train the LoRA."""

import re
import zipfile
from pathlib import Path

from .jobs import full_prompt
from .media import GenerationError, download
from .telegram import keyboard

DATASET_SHOTS = [
    "close-up portrait, soft smile, looking at the camera, neutral studio background",
    "side profile portrait, natural window light",
    "looking back over her shoulder, outdoors in a sunny street",
    "full body, standing in a park, jeans and a white t-shirt",
    "sitting at a cafe table holding a coffee cup, morning light",
    "at the gym in a sports bra and leggings, holding a water bottle",
    "on a beach at golden hour in a light summer dress",
    "laughing candidly, eyes half closed, outdoors",
    "serious expression, studio headshot, dramatic side light",
    "wearing an elegant black evening dress, city lights behind her at night",
    "mirror selfie in a bright bedroom, casual outfit",
    "walking down a city street at night, leather jacket",
    "cooking in a modern kitchen, apron, smiling",
    "reading a book on a sofa, cozy sweater, warm lamp light",
    "hair tied up in a bun, white tank top, plain wall",
    "sunglasses on her head, on a boat, blue sea behind her",
    "three-quarter view portrait, overcast soft light",
    "photo taken from slightly above, sitting on stairs",
    "photo taken from slightly below, standing on a terrace",
    "hands near her face, thoughtful expression, close-up",
    "grey hoodie, sitting on a bed, morning light",
    "red lipstick, glamour portrait, softbox lighting",
    "hiking outfit, mountain view behind her",
    "swimsuit by a hotel pool, sunny day",
]

# Image models drift to one "default pretty face" when the prompt is the same, so every candidate
# gets its own facial structure; the persona's hair, eyes and skin still come from persona.yaml.
FACE_VARIANTS = [  # face structure only: eyes, lips and hair stay as persona.yaml describes them
    "oval face, high cheekbones, thin straight nose",
    "heart-shaped face, soft round cheeks, small upturned nose, dimples",
    "square jawline, strong brows, slightly wide nose",
    "round face, a small beauty mark on the cheek",
    "long face, defined chin, high arched eyebrows",
    "diamond-shaped face, sharp cheekbones, Roman nose, natural thick brows",
    "soft features, light freckles across the nose, small chin",
    "angular features, almond-shaped eyes, straight brows, defined jaw",
    "wide face, full cheeks, button nose",
    "delicate features, pointed chin, thin arched brows",
]

DATASET_NAME = re.compile(r"^\d{2}\.jpg$")
MIN_DATASET = 12
MAX_REFERENCES = 10


def _subject(cfg):
    p = cfg.persona
    return f"photo of an adult {p['age']}-year-old {p['subject']}, {p['appearance']}"


def faces(app, n=6):
    """Generate candidate faces (no LoRA yet) and offer them on Telegram."""
    cfg = app.cfg
    start = app.db.kv_get("face_round") or 0  # each /faces continues through the list, so a retry shows new faces
    app.db.kv_set("face_round", start + n)
    candidates = []
    for i in range(n):
        variant = FACE_VARIANTS[(start + i) % len(FACE_VARIANTS)]
        prompt = (f"{_subject(cfg)}, clearly a grown woman, {variant}, natural skin texture, distinctive real face, "
                  f"head and shoulders portrait, looking at the camera, plain light background, {cfg.style.get('photo', '')}")
        url, flagged = app.media.image(prompt, safety=True, setup=True)
        if flagged:
            continue
        idx = len(candidates)
        path = download(url, app.setup_dir / "faces" / f"face_{idx}.jpg")
        candidates.append({"url": url, "path": str(path)})
        if app.tg:
            app.tg.send_media(path, f"Πρόσωπο {idx + 1}", keyboard([[("⭐ Αυτό", f"f:{idx}")]]), silent=True)
    app.db.kv_set("face_candidates", candidates)
    app.notify(f"Έτοιμα {len(candidates)} πρόσωπα. Διάλεξε ένα με ⭐ (ή /faces για άλλα).")
    return candidates


def pick_face(app, idx):
    candidates = app.db.kv_get("face_candidates") or []
    if not 0 <= idx < len(candidates):
        raise ValueError(f"Δεν υπάρχει πρόσωπο {idx + 1}")
    app.db.kv_set("reference_face", candidates[idx])
    return candidates[idx]


def dataset(app, n=len(DATASET_SHOTS)):
    """Create varied photos of the chosen face for LoRA training."""
    ref = app.db.kv_get("reference_face")
    if not ref:
        raise ValueError("Διάλεξε πρώτα πρόσωπο (/faces)")
    out = app.setup_dir / "dataset"
    out.mkdir(parents=True, exist_ok=True)
    style = app.cfg.style.get("photo", "")
    made = 0
    for i, shot in enumerate(DATASET_SHOTS[:n]):
        prompt = f"Keep exactly the same person: same face, same hair, same skin. She is an adult. {shot}. Photorealistic photo, {style}"
        try:
            url = app.media.edit(ref["url"], prompt, setup=True)
        except GenerationError as e:
            app.notify(f"⚠️ Dataset {i + 1}: {e}", silent=True)
            continue
        path = download(url, out / f"{i:02d}.jpg")
        made += 1
        if app.tg:
            app.tg.send_media(path, f"Dataset {i + 1}/{n}", keyboard([[("🗑 Πέτα", f"d:{path.name}")]]), silent=True)
    app.notify(f"Έτοιμες {made} φωτογραφίες. Πέτα (🗑) όσες δεν μοιάζουν στο πρόσωπο και μετά στείλε /train.")
    return made


def drop_dataset_image(app, name):
    if not DATASET_NAME.match(name):
        raise ValueError("Μη έγκυρο όνομα αρχείου")
    path = app.setup_dir / "dataset" / name
    if path.exists():
        path.unlink()
    return path


def lock_references(app, count=MAX_REFERENCES):
    """Lock the chosen face plus the best dataset photos as permanent references (never expire on fal)."""
    face = (app.db.kv_get("reference_face") or {}).get("path")
    files = ([Path(face)] if face and Path(face).exists() else []) + sorted((app.setup_dir / "dataset").glob("*.jpg"))
    if not files:
        raise ValueError("Δεν υπάρχουν φωτογραφίες. Κάνε πρώτα /faces και /dataset.")
    urls = [app.media.upload(f, keep=True) for f in files[:count]]
    app.db.kv_set("reference_urls", urls)
    app.db.kv_set("reference_files", [str(f) for f in files[:count]])
    app.notify(f"🔒 Κλείδωσαν {len(urls)} references. Κάθε social post θα κρατάει αυτό το πρόσωπο.")
    return urls


def train(app):
    files = sorted((app.setup_dir / "dataset").glob("*.jpg"))
    if len(files) < MIN_DATASET:
        raise ValueError(f"Χρειάζονται τουλάχιστον {MIN_DATASET} φωτογραφίες, υπάρχουν {len(files)}")
    zip_path = app.setup_dir / "dataset.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for f in files:
            z.write(f, Path(f).name)
    app.notify(f"⏳ Εκπαίδευση LoRA με {len(files)} φωτογραφίες (περίπου 5-20 λεπτά)...")
    zip_url = app.media.upload(zip_path)
    lora = app.media.train_lora(zip_url, app.cfg.persona["trigger_word"])
    app.db.kv_set("lora_url", lora)
    try:
        download(lora, app.lora_backup)  # if fal ever drops the file, health_check re-uploads this copy
    except OSError as e:
        app.notify(f"⚠️ Δεν κράτησα αντίγραφο του LoRA: {e}", silent=True)
    if not app.reference_urls():
        lock_references(app)

    test = {"image_prompt": "casual selfie at a cafe terrace, sunny afternoon"}
    url, _ = app.media.image(full_prompt(app.cfg, test), lora, safety=True, setup=True)
    path = download(url, app.setup_dir / "lora_test.jpg")
    if app.tg:
        app.tg.send_media(path, "✅ Το LoRA είναι έτοιμο. Δοκιμαστική φωτογραφία. Στείλε /plan για να ξεκινήσει το πρόγραμμα.")
    return lora
