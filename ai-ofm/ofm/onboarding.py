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

DATASET_NAME = re.compile(r"^\d{2}\.jpg$")
MIN_DATASET = 12


def _subject(cfg):
    p = cfg.persona
    return f"photo of an adult {p['age']}-year-old {p['subject']}, {p['appearance']}"


def faces(app, n=6):
    """Generate candidate faces (no LoRA yet) and offer them on Telegram."""
    cfg = app.cfg
    prompt = f"{_subject(cfg)}, head and shoulders portrait, looking at the camera, plain light background, {cfg.style.get('photo', '')}"
    candidates = []
    for _ in range(n):
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

    test = {"image_prompt": "casual selfie at a cafe terrace, sunny afternoon"}
    url, _ = app.media.image(full_prompt(app.cfg, test), lora, safety=True, setup=True)
    path = download(url, app.setup_dir / "lora_test.jpg")
    if app.tg:
        app.tg.send_media(path, "✅ Το LoRA είναι έτοιμο. Δοκιμαστική φωτογραφία. Στείλε /plan για να ξεκινήσει το πρόγραμμα.")
    return lora
