"""Image, video and LoRA calls on fal.ai, with cost tracking and the weekly budget."""

import mimetypes
from pathlib import Path

import requests

IMAGE_TIMEOUT = 300
VIDEO_TIMEOUT = 900
TRAINING_TIMEOUT = 3600


class BudgetExceeded(Exception):
    pass


class GenerationError(Exception):
    pass


def _fal():
    import fal_client

    return fal_client


class Media:
    def __init__(self, cfg, db, fal=None):
        self.cfg = cfg
        self.db = db
        self._fal_module = fal

    @property
    def fal(self):
        if self._fal_module is None:
            self._fal_module = _fal()
        return self._fal_module

    def _call(self, model_key, arguments, timeout):
        model = self.cfg.models[model_key]
        try:
            return self.fal.subscribe(model, arguments=arguments, client_timeout=timeout)
        except Exception as e:
            raise GenerationError(f"{model}: {e}") from e

    def check_budget(self, *kinds):
        spent = self.db.spent_last_week()
        if spent + sum(self.cfg.estimates[k] for k in kinds) > self.cfg.weekly_budget:
            raise BudgetExceeded(f"Ξοδεύτηκαν ${spent:.2f} από ${self.cfg.weekly_budget:.2f} τις τελευταίες 7 μέρες")

    def _charge(self, kind, detail, setup=False):
        self.db.add_cost(("setup:" if setup else "") + kind, self.cfg.estimates[kind], detail)

    def image(self, prompt, lora_url=None, safety=True, setup=False):
        """Return (url, flagged). flagged means the safety checker caught NSFW content."""
        gen = self.cfg.generation
        arguments = {
            "prompt": prompt,
            "image_size": gen["image_size"],
            "num_images": 1,
            "enable_safety_checker": bool(safety),
            "output_format": "jpeg",
        }
        if lora_url:
            arguments["loras"] = [{"path": lora_url, "scale": float(gen["lora_scale"])}]
        result = self._call("image", arguments, IMAGE_TIMEOUT)
        self._charge("image", prompt[:80], setup)
        images = result.get("images") or []
        if not images:
            raise GenerationError(f"Καμία εικόνα στην απάντηση: {result}")
        flagged = bool((result.get("has_nsfw_concepts") or [False])[0])
        return images[0]["url"], flagged

    def edit(self, image_url, prompt, setup=False):
        result = self._call("edit", {"prompt": prompt, "image_url": image_url}, IMAGE_TIMEOUT)
        self._charge("edit", prompt[:80], setup)
        images = result.get("images") or []
        if not images:
            raise GenerationError(f"Καμία εικόνα στην απάντηση: {result}")
        return images[0]["url"]

    def video(self, image_url, motion_prompt):
        arguments = {
            "prompt": motion_prompt,
            "image_url": image_url,
            "duration": str(self.cfg.generation["video_duration"]),
        }
        result = self._call("video", arguments, VIDEO_TIMEOUT)
        self._charge("video", motion_prompt[:80])
        url = (result.get("video") or {}).get("url")
        if not url:
            raise GenerationError(f"Κανένα βίντεο στην απάντηση: {result}")
        return url

    def upload(self, path):
        try:
            return self.fal.upload_file(Path(path))
        except Exception as e:
            raise GenerationError(f"upload {path}: {e}") from e

    def train_lora(self, zip_url, trigger_word):
        arguments = {
            "images_data_url": zip_url,
            "trigger_word": trigger_word,
            "steps": int(self.cfg.generation["training_steps"]),
        }
        result = self._call("trainer", arguments, TRAINING_TIMEOUT)
        self._charge("training", trigger_word, setup=True)
        url = (result.get("diffusers_lora_file") or {}).get("url")
        if not url:
            raise GenerationError(f"Δεν επέστρεψε LoRA: {result}")
        return url


def download(url, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        if not dest.suffix:
            ext = mimetypes.guess_extension((r.headers.get("content-type") or "").split(";")[0]) or ""
            dest = dest.with_suffix(ext)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    return dest
