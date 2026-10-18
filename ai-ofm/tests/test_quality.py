import shutil
import subprocess
from datetime import datetime
from types import SimpleNamespace

import pytest

from ofm import bot, health, jobs, onboarding, overlay, planner
from ofm.media import Media

from conftest import OWNER, FakeHTTP

REFS = [f"https://fal.media/ref-{i}.jpg" for i in range(6)]
SUNDAY = (2026, 10, 18, 18, 5)


def at(cfg, *args):
    return datetime(*args, tzinfo=cfg.tz)


def planned(app):
    planner.plan_ahead(app, at(app.cfg, *SUNDAY))
    return app.db.posts("planned")


def test_plan_stores_hook_pinned_comment_and_mechanic(app):
    posts = planned(app)
    reel = next(p for p in posts if p["kind"] == "video")
    assert reel["hook"] == "Rate my fit 1-10" and reel["mechanic"] == "rating"
    assert reel["pinned_comment"] == "lowest score picks next week's outfit"
    vault = next(p for p in posts if p["targets"] == ["fanvue"])
    assert vault["hook"] == "" and vault["mechanic"] == "none"
    system = app.claude.requests[0]["system"]
    assert "engagement bait" in system and "8 seconds" in system
    assert "ai_debate" not in system and "do not mention that she is AI" in system


def test_unsafe_hook_is_blocked(app):
    from conftest import FakeClaude, default_items

    def items(n):
        out = default_items(n)
        out[0]["hook"] = "POV: back to high school"
        return out

    app._claude = FakeClaude(items)
    planned(app)
    assert len(app.db.posts("blocked")) == 1


def test_swipe_file_feeds_the_plan(app):
    bot.handle_update(app, {"update_id": 1, "message": {"from": {"id": OWNER},
                      "text": "/swipe girl asks 'rate my fit 1-10', 3 outfits, snap transitions, 2M views"}}, None)
    assert "swipe file" in app.tg.messages[-1]
    planned(app)
    assert "snap transitions" in app.claude.requests[0]["messages"][0]["content"]
    assert app.db.swipes() == []


def test_social_posts_use_references_and_fanvue_uses_lora(app):
    app.db.kv_set("reference_urls", REFS)
    planned(app)
    jobs.generate_pending(app, at(app.cfg, 2026, 10, 18, 19, 0), limit=100)
    ref_calls = [c for c in app.media.calls if c[0] == "ref_image"]
    lora_calls = [c for c in app.media.calls if c[0] == "image"]
    assert len(ref_calls) == 17 and len(lora_calls) == 20
    assert ref_calls[0][1].startswith("Remain the same model from the reference images")
    assert "adult 24-year-old" in ref_calls[0][1] and ref_calls[0][2] == REFS
    video_calls = [c for c in app.media.calls if c[0] == "video"]
    assert video_calls and all(c[3] == REFS for c in video_calls)
    assert len(app.claude.qc_requests) == 37
    qc_images = app.claude.qc_requests[0]["messages"][0]["content"]
    assert qc_images[0]["source"]["url"] == REFS[0]


def test_reference_refusal_falls_back_to_lora(app):
    app.db.kv_set("reference_urls", REFS)
    post = next(p for p in planned(app) if p.social_targets)
    app.media.ref_fail_next = 1
    jobs.generate_post(app, post)
    assert app.db.get_post(post["id"])["status"] == "ready"
    assert [c[0] for c in app.media.calls][:3] == ["ref_image", "ref_image", "video"] or \
        [c[0] for c in app.media.calls][:2] == ["ref_image", "ref_image"]  # refused once: plainer words, no LoRA needed
    app.media.calls.clear()
    other = next(p for p in planned(app) if p.social_targets and p["id"] != post["id"])
    app.media.ref_fail_next = 2
    jobs.generate_post(app, other)
    assert [c[0] for c in app.media.calls][:3] == ["ref_image", "ref_image", "image"]


def test_failed_quality_check_regenerates(app):
    app.db.kv_set("reference_urls", REFS)
    post = next(p for p in planned(app) if p.social_targets)
    app.claude.qc_replies = [{"verdict": "fail", "reason": "six fingers on the left hand"}]
    jobs.generate_post(app, post)
    after = app.db.get_post(post["id"])
    assert after["status"] == "planned" and after["attempts"] == 1
    assert after["error"] == "QC: six fingers on the left hand"
    jobs.generate_post(app, after)
    assert app.db.get_post(post["id"])["status"] == "ready"


def test_review_sample_auto_approves_the_rest(app):
    app.cfg.generation["review_sample"] = 0.2
    app.db.kv_set("reference_urls", REFS)
    planned(app)
    jobs.generate_pending(app, at(app.cfg, 2026, 10, 18, 19, 0), limit=100)
    jobs.send_reviews(app)
    reviewed, auto = len(app.db.posts("in_review")), len(app.db.posts("approved"))
    assert reviewed + auto == 37 and 3 <= reviewed <= 12
    assert app.db.auto_approved_count(datetime(2000, 1, 1)) == auto
    captions = [m["caption"] for m in app.tg.media]
    assert all("✅ QC" in c for c in captions)
    assert any("🪝 Rate my fit 1-10" in c and "📌 lowest score" in c for c in captions)


def test_without_quality_check_everything_is_reviewed(app):
    app.cfg.generation["review_sample"] = 0.2
    app.cfg.generation["quality_check"] = False
    app.db.kv_set("reference_urls", REFS)
    planned(app)
    jobs.generate_pending(app, at(app.cfg, 2026, 10, 18, 19, 0), limit=100)
    jobs.send_reviews(app)
    assert len(app.db.posts("in_review")) == 37 and app.claude.qc_requests == []


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_hook_is_burned_into_the_video(tmp_path):
    src, dest = tmp_path / "in.mp4", tmp_path / "out.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=360x640:rate=10",
                    "-t", "1", "-pix_fmt", "yuv420p", str(src)], check=True)
    assert overlay.burn_hook(src, dest, "Rate my gym fit 1-10 😌 be honest") == dest
    assert dest.stat().st_size > 0 and not list(tmp_path.glob("*.txt"))


def test_hook_text_is_cleaned_and_overlay_errors_are_reported(tmp_path):
    assert overlay.clean("Rate my fit 😌🔥 1-10!") == "Rate my fit 1-10!"
    assert overlay.burn_hook(tmp_path / "a.mp4", tmp_path / "b.mp4", "😌🔥") is None
    if shutil.which("ffmpeg"):
        failing = lambda *a, **k: SimpleNamespace(returncode=1, stderr=b"No such file")
        with pytest.raises(overlay.OverlayError, match="No such file"):
            overlay.burn_hook(tmp_path / "a.mp4", tmp_path / "b.mp4", "hello", run=failing)


class FakeFal:
    def __init__(self):
        self.calls = []
        self.StorageSettings = lambda expires_in: ("lifecycle", expires_in)

    def subscribe(self, model, arguments, client_timeout):
        self.calls.append((model, arguments))
        if "video" in model:
            return {"video": {"url": "https://fal.media/v.mp4"}}
        return {"images": [{"url": "https://fal.media/i.jpg"}]}

    def upload_file(self, path, lifecycle=None):
        self.calls.append(("upload", str(path), lifecycle))
        return "https://fal.media/u"


def test_media_arguments_for_nano_banana_and_kling_v3(cfg, tmp_path):
    from ofm.db import DB

    fal = FakeFal()
    media = Media(cfg, DB(":memory:"), fal=fal)
    media.ref_image("prompt", REFS[:3])
    assert fal.calls[-1] == ("fal-ai/nano-banana-pro/edit", {"prompt": "prompt", "image_urls": REFS[:3], "num_images": 1,
                                                             "aspect_ratio": "9:16", "output_format": "jpeg"})
    media.video("https://fal.media/start.jpg", "she smiles", REFS)
    model, args = fal.calls[-1]
    assert model == "fal-ai/kling-video/v3/standard/image-to-video"
    assert args == {"prompt": "she smiles", "duration": "8", "start_image_url": "https://fal.media/start.jpg",
                    "generate_audio": False,
                    "elements": [{"frontal_image_url": REFS[0], "reference_image_urls": REFS[1:4]}]}
    cfg.models["video"] = "fal-ai/kling-video/v2.5-turbo/standard/image-to-video"
    media.video("https://fal.media/start.jpg", "she smiles", REFS)
    assert fal.calls[-1][1] == {"prompt": "she smiles", "duration": "8", "image_url": "https://fal.media/start.jpg"}
    media.upload(tmp_path / "x.jpg", keep=True)
    assert fal.calls[-1] == ("upload", str(tmp_path / "x.jpg"), ("lifecycle", "never"))


def test_train_locks_references_and_keeps_a_lora_backup(app):
    app.db.kv_set("lora_url", None)
    onboarding.faces(app, n=2)
    onboarding.pick_face(app, 0)
    onboarding.dataset(app)
    onboarding.train(app)
    refs = app.reference_urls()
    assert len(refs) == onboarding.MAX_REFERENCES and refs[0].endswith("face_0.jpg")
    assert all(c[2] is True for c in app.media.calls if c[0] == "upload" and c[1].endswith(".jpg"))
    assert app.lora_backup.exists()


def test_health_check_restores_dead_links(app):
    app.lora_backup.parent.mkdir(parents=True, exist_ok=True)
    app.lora_backup.write_bytes(b"lora")
    ref_file = app.setup_dir / "dataset" / "00.jpg"
    ref_file.parent.mkdir(parents=True, exist_ok=True)
    ref_file.write_bytes(b"x")
    app.db.kv_set("reference_urls", ["https://fal.media/old.jpg"])
    app.db.kv_set("reference_files", [str(ref_file)])

    assert health.health_check(app) == []
    assert app.tg.messages == []

    app.http = FakeHTTP(status=404)
    problems = health.health_check(app)
    assert len(problems) == 2 and "🩺" in app.tg.messages[-1]
    assert app.lora_url() == "https://fal.media/lora.safetensors"
    assert app.reference_urls() == ["https://fal.media/00.jpg"]


def test_feed_photos_are_4_5_stories_and_reels_9_16(app):
    app.db.kv_set("reference_urls", REFS)
    posts = planned(app)
    story = next(p for p in posts if "instagram_story" in p["targets"])
    feed = next(p for p in posts if p["targets"] == ["instagram_feed"])
    reel = next(p for p in posts if p["kind"] == "video")
    fanvue = next(p for p in posts if p["targets"] == ["fanvue"])
    for post in (story, feed, reel):
        jobs.generate_post(app, post)
    assert app.media.aspects == ["9:16", "4:5", "9:16"]
    assert "Vertical 4:5 photo." in [c for c in app.media.calls if c[0] == "ref_image"][1][1]
    jobs.generate_post(app, fanvue)
    assert app.media.sizes[-1] == {"width": 1024, "height": 1280}
