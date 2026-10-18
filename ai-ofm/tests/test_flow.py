from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ofm import bot, jobs, planner
from ofm.media import BudgetExceeded

from conftest import OWNER, FakeClaude


def at(cfg, *args):
    return datetime(*args, tzinfo=cfg.tz)


# 2026-10-18 is a Sunday
SUNDAY_EVENING = (2026, 10, 18, 18, 5)


def plan(app, when=SUNDAY_EVENING):
    return planner.plan_ahead(app, at(app.cfg, *when))


def test_slots_for_a_week(cfg):
    slots = planner.build_slots(cfg, at(cfg, 2026, 10, 19).date())
    # 2 daily slots x 7 + feed on tue/thu/sat + 20 fanvue
    assert len(slots) == 14 + 3 + 20
    assert slots[0]["slot_at"] == at(cfg, 2026, 10, 19, 8, 0)
    assert sum(1 for s in slots if s["kind"] == "video") == 7


def test_plan_creates_posts_with_disclosure(app):
    summary = plan(app)
    assert summary["start"].isoformat() == "2026-10-19"
    assert summary["created"] == 37
    request = app.claude.requests[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["fallbacks"] == "default"
    assert request["output_config"]["format"]["type"] == "json_schema"
    posts = app.db.posts("planned")
    assert all(p["hashtags"][-1] == "#aigenerated" for p in posts)
    assert all(p["motion_prompt"] == "" for p in posts if p["kind"] == "image")
    assert app.db.kv_get("planned_until") == "2026-10-25"
    assert app.db.spent_last_week() == pytest.approx((2000 * 4 + 8000 * 20) / 1e6)


def test_next_plan_continues_after_the_last_one(app):
    plan(app)
    assert planner.next_start(app.db, at(app.cfg, *SUNDAY_EVENING)).isoformat() == "2026-10-26"


def test_unsafe_ideas_are_blocked(app):
    def items(n):
        out = [dict(i) for i in __import__("conftest").default_items(n)]
        out[0]["image_prompt"] = "schoolgirl outfit in a classroom"
        return out

    app._claude = FakeClaude(items)
    summary = plan(app)
    assert summary["blocked"] == 1
    assert app.db.posts("blocked")[0]["error"] == "guardrails: minor"


def test_refusal_raises(app):
    app._claude = FakeClaude(stop_reason="refusal")
    with pytest.raises(planner.PlanError):
        plan(app)


def test_generate_review_approve_publish(app):
    cfg = app.cfg
    plan(app)
    now = at(cfg, 2026, 10, 18, 19, 0)
    assert jobs.generate_pending(app, now, limit=100) == 37

    first_video = next(p for p in app.db.posts("ready") if p["kind"] == "video")
    assert first_video["media_path"].endswith(".mp4")
    prompt = next(c[1] for c in app.media.calls if c[0] == "image")
    assert prompt.startswith("m1alaur, photo of an adult 24-year-old woman")

    assert jobs.send_reviews(app) == 37
    assert app.tg.media[0]["markup"]["inline_keyboard"][0][0]["callback_data"].startswith("a:")
    assert "🗂 Όλα έτοιμα: 37 posts περιμένουν έγκριση." in app.tg.messages

    for post in app.db.posts("in_review"):
        assert jobs.review_action(app, "a", post["id"])[0] == "✅ Εγκρίθηκε"

    # Monday 10:00: everything within the next 36 hours goes to Buffer
    jobs.publish_due(app, at(cfg, 2026, 10, 19, 10, 0))
    created = app.buffer.created
    targets = {(c["channelId"], c["metadata"]["instagram"]["type"] if "metadata" in c and "instagram" in c["metadata"] else None) for c in created}
    assert ("ch_ig", "story") in targets and ("ch_ig", "reel") in targets and ("ch_x", None) in targets
    # up to Tue 22:00: Mon 08:00 story+x, Mon 19:00 reel+tiktok+yt, Tue 08:00 story+x,
    # Tue 12:30 feed, Tue 19:00 reel+tiktok+yt = 11
    assert len(created) == 11
    assert all(c["assets"][0].get("video", c["assets"][0].get("image"))["url"].startswith("https://cdn.example/") for c in created)

    # running again does not double-post
    jobs.publish_due(app, at(cfg, 2026, 10, 19, 10, 5))
    assert len(app.buffer.created) == 11
    assert len(app.db.posts("scheduled")) == 5

    # public copies are removed a few days after they went out
    # Fri 09:00 minus 3 days: Monday's 08:00 and 19:00 posts are old enough, Tuesday's 08:00 is not
    assert jobs.cleanup_storage(app, at(cfg, 2026, 10, 23, 7, 0)) == 2
    assert len(app.storage.deleted) == 2
    assert jobs.cleanup_storage(app, at(cfg, 2026, 10, 23, 7, 0)) == 0


def test_fanvue_pack_sends_documents(app):
    plan(app)
    now = at(app.cfg, 2026, 10, 18, 19, 0)
    jobs.generate_pending(app, now, limit=100)
    jobs.send_reviews(app)
    for post in app.db.posts("in_review"):
        if post["targets"] == ["fanvue"]:
            jobs.review_action(app, "a", post["id"])
    assert jobs.send_fanvue_pack(app) == 20
    assert all(m["document"] for m in app.tg.media[-20:])
    assert len(app.db.posts("delivered")) == 20
    assert jobs.send_fanvue_pack(app) == 0


def test_nsfw_flag_retries_then_fails(app):
    plan(app)
    post = app.db.posts("planned")[0]
    app.media.flag_next = 10
    for _ in range(4):
        jobs.generate_post(app, app.db.get_post(post["id"]))
    assert app.db.get_post(post["id"])["status"] == "failed"
    assert any("απέτυχε" in m for m in app.tg.messages)


def test_regenerate_limit(app):
    plan(app)
    post_id = app.db.posts("planned")[0]["id"]
    for _ in range(3):
        app.db.update_post(post_id, status="in_review")
        assert jobs.review_action(app, "g", post_id)[0] == "🔁 Θα ξαναφτιαχτεί"
    app.db.update_post(post_id, status="in_review")
    assert jobs.review_action(app, "g", post_id)[1] == "❌ Όριο επαναλήψεων"
    assert jobs.review_action(app, "a", post_id)[0] == "Ήδη: απορρίφθηκαν"


def test_budget_stops_generation(app):
    plan(app)
    app.db.add_cost("video", app.cfg.weekly_budget)
    with pytest.raises(BudgetExceeded):
        jobs.generate_pending(app, at(app.cfg, 2026, 10, 18, 19, 0))
    assert not app.db.posts("generating")


def test_missed_slots_are_not_generated(app):
    plan(app)
    jobs.generate_pending(app, at(app.cfg, 2026, 10, 21, 0, 0), limit=0)
    missed = app.db.posts("missed")
    assert missed and all(p["slot_at"] < at(app.cfg, 2026, 10, 21) for p in missed)
    assert not any(p["targets"] == ["fanvue"] for p in missed)


def test_late_approval_and_buffer_errors(app):
    cfg = app.cfg
    plan(app)
    jobs.generate_pending(app, at(cfg, 2026, 10, 18, 19, 0), limit=100)
    jobs.send_reviews(app)
    social = [p for p in app.db.posts("in_review") if p.social_targets]
    first = social[0]  # Mon 08:00 story + x
    jobs.review_action(app, "a", first["id"])

    app.buffer.fail_with = "Invalid media URL"
    jobs.publish_due(app, at(cfg, 2026, 10, 19, 12, 0))
    assert app.db.publication(first["id"], "x")["status"] == "failed"
    assert any("Invalid media URL" in m for m in app.tg.messages)

    # three days later it is too late: marked missed, never posted
    app.buffer.fail_with = None
    second = social[1]
    jobs.review_action(app, "a", second["id"])
    jobs.publish_due(app, second["slot_at"] + timedelta(days=3))
    assert app.db.get_post(second["id"])["status"] == "missed"


def test_dry_run_changes_nothing(app):
    plan(app)
    jobs.generate_pending(app, at(app.cfg, 2026, 10, 18, 19, 0), limit=100)
    jobs.send_reviews(app)
    for post in app.db.posts("in_review"):
        jobs.review_action(app, "a", post["id"])
    previews = jobs.publish_due(app, at(app.cfg, 2026, 10, 19, 10, 0), dry_run=True)
    assert previews and all(p.startswith("mutation CreatePost($input: CreatePostInput!)") for p in previews)
    assert '"schedulingType": "automatic"' in previews[0]
    assert not app.buffer.created and not app.storage.uploads


def test_tick_runs_weekly_jobs_once(app):
    cfg = app.cfg
    jobs.tick(app, at(cfg, *SUNDAY_EVENING))
    assert len(app.claude.requests) == 1
    assert any("Νέο πλάνο 19/10–25/10" in m for m in app.tg.messages)
    jobs.tick(app, at(cfg, 2026, 10, 18, 18, 30))
    assert len(app.claude.requests) == 1

    jobs.tick(app, at(cfg, 2026, 10, 18, 20, 1))
    reports = [m for m in app.tg.messages if m.startswith("📊")]
    jobs.tick(app, at(cfg, 2026, 10, 18, 21, 0))
    assert len(reports) == 1 == len([m for m in app.tg.messages if m.startswith("📊")])


def test_bot_ignores_strangers_and_handles_commands(app):
    stranger = {"update_id": 1, "message": {"from": {"id": 999}, "text": "/pause"}}
    bot.handle_update(app, stranger, at(app.cfg, *SUNDAY_EVENING))
    assert not app.db.kv_get("paused")

    owner = {"update_id": 2, "message": {"from": {"id": OWNER}, "text": "/pause"}}
    bot.handle_update(app, owner, at(app.cfg, *SUNDAY_EVENING))
    assert app.db.kv_get("paused") is True
    assert jobs.generate_pending(app, at(app.cfg, *SUNDAY_EVENING)) == 0


def test_review_button_updates_message(app):
    plan(app)
    jobs.generate_pending(app, at(app.cfg, 2026, 10, 18, 19, 0), limit=1)
    jobs.send_reviews(app)
    post = app.db.posts("in_review")[0]
    update = {"update_id": 3, "callback_query": {"id": "cb", "from": {"id": OWNER}, "data": f"r:{post['id']}",
                                                 "message": {"message_id": post["review_message_id"]}}}
    bot.handle_update(app, update, at(app.cfg, *SUNDAY_EVENING))
    assert app.db.get_post(post["id"])["status"] == "rejected"
    assert app.tg.answers == ["❌ Απορρίφθηκε"]
    assert app.tg.buttons[-1][0] == post["review_message_id"]


def test_onboarding_flow(app):
    from ofm import onboarding

    app.db.kv_set("lora_url", None)
    onboarding.faces(app, n=3)
    assert len(app.tg.media) == 3
    prompts = [c[1] for c in app.media.calls if c[0] == "face"]
    assert len(set(prompts)) == 3 and all("adult" in p and "iPhone" in p for p in prompts)
    onboarding.faces(app, n=3)  # asking again shows different faces, not the same three
    again = [c[1] for c in app.media.calls if c[0] == "face"][3:]
    assert not set(again) & set(prompts)
    app.tg.media.clear()
    bot.handle_update(app, {"update_id": 4, "callback_query": {"id": "c", "from": {"id": OWNER}, "data": "f:1",
                                                               "message": {"message_id": 1}}}, None)
    assert app.db.kv_get("reference_face")["url"].endswith("face5.jpg")

    app.media.ref_fail_next = 1  # the first shot is refused once: it goes again in milder words
    assert onboarding.dataset(app) == len(onboarding.DATASET_SHOTS)
    shots = [c for c in app.media.calls if c[0] == "ref_image"]
    assert len(shots) == len(onboarding.DATASET_SHOTS) + 1
    assert shots and all(c[2] == [app.db.kv_get("reference_face")["url"]] for c in shots)
    assert shots[0][1].startswith("Keep exactly the same face") and "Her body and look must be exactly this" in shots[0][1]
    assert app.db.spent_last_week() == 0  # setup costs don't eat the weekly content budget
    bot.handle_update(app, {"update_id": 5, "callback_query": {"id": "c", "from": {"id": OWNER}, "data": "d:00.jpg",
                                                               "message": {"message_id": 2}}}, None)
    assert not (app.setup_dir / "dataset" / "00.jpg").exists()
    assert onboarding.dataset(app) == 1  # running it again only remakes the one that was thrown away
    with pytest.raises(ValueError):
        onboarding.drop_dataset_image(app, "../../ofm.sqlite3")

    lora = onboarding.train(app)
    assert lora == app.lora_url() == "https://fal.media/lora.safetensors"
    assert ("train", "https://fal.media/dataset.zip", "m1alaur") in app.media.calls


def test_a_photo_sent_to_the_bot_becomes_her_face(app):
    from ofm import onboarding

    update = {"update_id": 9, "message": {"from": {"id": OWNER}, "photo": [{"file_id": "small"}, {"file_id": "big"}]}}
    bot.handle_update(app, update, at(app.cfg, *SUNDAY_EVENING))
    face = app.db.kv_get("reference_face")
    assert face["path"].endswith("faces/custom.jpg") and face["url"] == "https://fal.media/custom.jpg"
    assert ("upload", face["path"], True) in app.media.calls  # kept on fal, so the dataset can use it
    assert any("/dataset" in m for m in app.tg.messages)
    assert onboarding.dataset(app) == len(onboarding.DATASET_SHOTS)
    assert all(c[2] == ["https://fal.media/custom.jpg"] for c in app.media.calls if c[0] == "ref_image")


def test_a_new_face_clears_the_old_womans_dataset(app):
    from ofm import onboarding

    onboarding.faces(app, n=2)
    onboarding.pick_face(app, 0)
    onboarding.dataset(app)
    onboarding.lock_references(app)
    assert len(list((app.setup_dir / "dataset").glob("*.jpg"))) == len(onboarding.DATASET_SHOTS)
    onboarding.pick_face(app, 0)  # same face again: nothing is lost
    assert len(list((app.setup_dir / "dataset").glob("*.jpg"))) == len(onboarding.DATASET_SHOTS)
    onboarding.pick_face(app, 1)  # another woman: her dataset starts empty
    assert not list((app.setup_dir / "dataset").glob("*.jpg")) and not app.reference_urls()


def test_a_video_sent_to_the_bot_is_remade_as_her_next_reel(app, monkeypatch, tmp_path):
    from ofm import swipes

    def frames(video, out_dir, count=3, run=None):
        assert Path(video).exists()
        out = []
        for i in range(count):
            f = Path(out_dir) / f"{Path(video).stem}-{i}.jpg"
            f.write_bytes(b"x")
            out.append(f)
        return out

    monkeypatch.setattr(swipes, "extract_frames", frames)
    monkeypatch.setattr(swipes, "download", lambda url, dest: (Path(dest).parent.mkdir(parents=True, exist_ok=True),
                                                               Path(dest).write_bytes(b"v"), Path(dest))[2])
    plan(app)
    video = {"update_id": 20, "message": {"from": {"id": OWNER}, "video": {"file_id": "vid1"}, "caption": "2M views"}}
    bot.handle_update(app, video, at(app.cfg, 2026, 10, 18, 18, 10))

    sent = app.claude.swipe_requests[0]["messages"][0]["content"]
    assert [b["type"] for b in sent] == ["image", "image", "image", "text"] and "2M views" in sent[-1]["text"]
    assert "Hook idea: which one for tonight" in app.db.swipe(1)["text"]
    assert app.tg.markups[-1]["inline_keyboard"][0][0]["callback_data"] == "sw:1"
    assert not list((app.media_dir / "swipes").iterdir())  # the video and frames are not kept

    first_reel = min((p for p in app.db.posts("planned") if p["kind"] == "video"), key=lambda p: p["slot_at"])
    press = {"update_id": 21, "callback_query": {"id": "c", "from": {"id": OWNER}, "data": "sw:1", "message": {"message_id": 5}}}
    bot.handle_update(app, press, at(app.cfg, 2026, 10, 18, 18, 10))
    remake = app.claude.requests[-1]["messages"][0]["content"]
    assert "Remake this viral format" in remake and "which one for tonight" in remake
    after = app.db.get_post(first_reel["id"])
    assert after["status"] == "planned" and after["idea"] == "Ιδέα 0" and after["hashtags"][-1] == "#aigenerated"
    assert app.db.swipe(1)["used"] == 1 and any("Το reel της" in m for m in app.tg.messages)


def test_a_remake_without_a_free_reel_waits_for_the_next_plan(app):
    swipe_id = app.db.add_swipe("mirror outfit check")
    assert planner.remake_next_reel(app, at(app.cfg, *SUNDAY_EVENING), swipe_id) is None
    assert app.db.swipe(swipe_id)["used"] == 0


def test_profile_only_disclosure_leaves_hashtags_clean(app):
    app.cfg.persona["disclosure_tag"] = ""
    plan(app)
    assert not any("#aigenerated" in p["hashtags"] for p in app.db.posts("planned"))
    assert "Do not add any AI tag yourself." in app.claude.requests[0]["system"]


def test_turning_the_tag_off_cleans_posts_not_yet_sent(app):
    plan(app)
    assert all(p["hashtags"][-1] == "#aigenerated" for p in app.db.posts("planned"))
    app.cfg.persona["disclosure_tag"] = ""
    assert jobs.apply_tag_settings(app) == 37
    assert not any("#aigenerated" in p["hashtags"] for p in app.db.posts("planned"))
    assert jobs.apply_tag_settings(app) == 0


def test_no_hashtags_persona_posts_clean_captions(app):
    def items(n):
        out = __import__("conftest").default_items(n)
        for item in out:
            item["caption"] = "leg day 🍑 1-10? #gym #fitgirl"
        return out

    app._claude = FakeClaude(items)
    app.cfg.persona["hashtags"] = False
    plan(app)
    post = app.db.posts("planned")[0]
    assert post["hashtags"] == [] and post["caption"] == "leg day 🍑 1-10?"
    assert "she never uses hashtags" in app.claude.requests[0]["system"]


def test_ideas_wait_for_the_owner_before_anything_is_made(app):
    app.cfg.generation["idea_approval"] = True
    jobs.plan_now(app, at(app.cfg, *SUNDAY_EVENING))
    assert app.db.posts("proposed") and not app.db.posts("planned")
    assert any("φτιάχνω μόνο όσες πατήσεις ✅" in m for m in app.tg.messages)
    days = [m for m in app.tg.messages if m.startswith("📅")]
    assert len(days) == 7 and any(m.startswith("💎 Fanvue") for m in app.tg.messages)
    assert "1. 📸 08:00 IG Story, X" in days[0] and "🪝 Rate my fit 1-10" in days[0]
    markup = app.tg.markups[-1 - len(days)] if False else next(m for m in app.tg.markups if m and m["inline_keyboard"][0][0]["callback_data"].startswith("p:"))
    first = markup["inline_keyboard"][0]
    assert first[0]["text"] == "✅ 1" and first[1]["text"] == "❌ 1"

    # nothing costs anything until a tap
    assert jobs.generate_pending(app, at(app.cfg, 2026, 10, 18, 19, 0), limit=100) == 0
    assert app.media.calls == []

    post_id = int(first[0]["callback_data"].split(":")[1])
    message_id = next(mid for mid in range(101, 200) if app.db.kv_get(f"proposal:{mid}") and post_id in app.db.kv_get(f"proposal:{mid}"))
    tap = {"update_id": 30, "callback_query": {"id": "c1", "from": {"id": OWNER}, "data": f"p:{post_id}:a",
                                                "message": {"message_id": message_id}}}
    bot.handle_update(app, tap, at(app.cfg, *SUNDAY_EVENING))
    assert app.db.get_post(post_id)["status"] == "planned" and app.tg.answers[-1] == "✅ Θα φτιαχτεί"
    refreshed = app.tg.buttons[-1][1]["inline_keyboard"]
    assert refreshed[0][0]["text"] == "1 ☑️ θα φτιαχτεί" and len(refreshed[0]) == 1 and refreshed[1][0]["text"] == "✅ 2"

    second = int(markup["inline_keyboard"][1][0]["callback_data"].split(":")[1])
    bot.handle_update(app, {"update_id": 31, "callback_query": {"id": "c2", "from": {"id": OWNER}, "data": f"p:{second}:r",
                                                                "message": {"message_id": message_id}}}, None)
    assert app.db.get_post(second)["status"] == "rejected"

    assert jobs.generate_pending(app, at(app.cfg, 2026, 10, 18, 19, 0), limit=100) == 1
    assert app.db.get_post(post_id)["status"] == "ready"

    bot.handle_update(app, {"update_id": 32, "message": {"from": {"id": OWNER}, "text": "/approve_all"}}, None)
    assert not app.db.posts("proposed") and len(app.db.posts("planned")) == 35
    assert any("35 ιδέες" in m for m in app.tg.messages)


def test_unapproved_ideas_expire_without_cost(app):
    app.cfg.generation["idea_approval"] = True
    plan(app)
    jobs.generate_pending(app, at(app.cfg, 2026, 10, 21, 0, 0), limit=100)
    missed = app.db.posts("missed")
    assert missed and all("χωρίς ✅" in p["error"] for p in missed) and app.media.calls == []
    assert all(p["targets"] == ["fanvue"] or p["slot_at"] >= at(app.cfg, 2026, 10, 21) for p in app.db.posts("proposed"))


def test_empty_fal_balance_pauses_once_instead_of_failing_every_post(app):
    plan(app)
    app.db.kv_set("reference_urls", ["https://fal.media/ref1.jpg"])
    app.media.locked = True
    jobs.generate_pending(app, at(app.cfg, 2026, 10, 18, 19, 0), limit=100)
    assert app.db.kv_get("paused") is True
    paused = [m for m in app.tg.messages if m.startswith("⏸")]
    assert len(paused) == 1 and "credits" in paused[0] and "/resume" in paused[0]
    assert not app.db.posts("failed") and not app.db.posts("generating")
    assert all(p["attempts"] == 0 for p in app.db.posts("planned"))
    # paused: the next tick makes nothing and says nothing more
    assert jobs.generate_pending(app, at(app.cfg, 2026, 10, 18, 19, 5), limit=100) == 0
    assert len([m for m in app.tg.messages if m.startswith("⏸")]) == 1


def test_feed_posts_are_carousels_of_the_same_moment(app):
    app.cfg.generation["carousel_size"] = 3
    app.db.kv_set("reference_urls", ["https://fal.media/ref1.jpg", "https://fal.media/ref2.jpg"])
    plan(app)
    feed = next(p for p in app.db.posts("planned") if p["targets"] == ["instagram_feed"])
    story = next(p for p in app.db.posts("planned") if "instagram_story" in p["targets"])
    jobs.generate_post(app, feed)
    jobs.generate_post(app, story)
    feed = app.db.get_post(feed["id"])
    assert len(feed["extra_media"]) == 2 and all(Path(m["path"]).exists() for m in feed["extra_media"])
    shots = [c for c in app.media.calls if c[0] == "ref_image"]
    assert app.media.aspects == ["4:5", "4:5", "4:5", "9:16"]
    assert "photo 2 of the same set" in shots[1][1] and shots[1][2][0] == feed["image_url"]
    assert app.db.get_post(story["id"])["extra_media"] == []  # stories stay single and full-screen

    jobs.send_reviews(app)
    assert app.tg.albums == [[feed["media_path"], *(m["path"] for m in feed["extra_media"])]]
    assert any(m.startswith("🖼 Carousel 3 φωτογραφίες") for m in app.tg.messages)
    jobs.review_action(app, "a", feed["id"])
    jobs.publish_due(app, feed["slot_at"] - timedelta(hours=5))
    created = next(c for c in app.buffer.created if c["channelId"] == "ch_ig")
    assert [list(a) for a in created["assets"]] == [["image"], ["image"], ["image"]]
    assert len({a["image"]["url"] for a in created["assets"]}) == 3
    assert len(app.storage.uploads) == 3
    jobs.cleanup_storage(app, feed["slot_at"] + timedelta(days=4))
    assert len(app.storage.deleted) == 3


def test_camera_and_motion_rules_in_the_plan(app):
    plan(app)
    system = app.claude.requests[0]["system"]
    assert "at most one in four is (c)" in system and "her hands are free" in system
    assert "Never slow robotic turns" in system


def test_a_voice_slot_becomes_a_spoken_skit(app, tmp_path):
    import yaml

    from ofm.config import ConfigError, load_config

    from conftest import OWNER as owner_id

    raw = yaml.safe_load((app.cfg.path if hasattr(app.cfg, "path") else __import__("conftest").ROOT / "persona.example.yaml").read_text(encoding="utf-8"))
    raw["schedule"]["slots"][1]["video"] = {"seconds": 15, "voice": True}
    path = tmp_path / "persona.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    cfg = load_config(path, env={"TELEGRAM_OWNER_ID": str(owner_id), "OFM_DATA_DIR": str(tmp_path / "data")})
    assert cfg.slots[1].video == {"seconds": 15, "voice": True} and cfg.slots[0].video is None
    raw["schedule"]["slots"][0]["video"] = {"seconds": 15}
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ConfigError, match="kind: video"):
        load_config(path, env={})

    app.cfg.slots[1].video = {"seconds": 15, "voice": True}

    def items(n):
        out = __import__("conftest").default_items(n)
        for item in out:
            item["speech"] = "babe I said I'm not hungry, why are you eating my fries"
        return out

    app._claude = FakeClaude(items)
    plan(app)
    sent = app.claude.requests[0]["messages"][0]["content"]
    assert '"video": {"seconds": 15, "voice": true}' in sent
    assert "speech: only for slots with" in app.claude.requests[0]["system"]
    reel = next(p for p in app.db.posts("planned") if p["kind"] == "video")
    story = next(p for p in app.db.posts("planned") if p["kind"] == "image" and p.social_targets)
    assert reel["voice"] == 1 and reel["video_seconds"] == 15 and reel["speech"].startswith("babe I said")
    assert story["voice"] == 0 and story["speech"] == ""  # speech is kept only where she speaks

    app.db.kv_set("reference_urls", ["https://fal.media/ref1.jpg"])
    before = app.db.spent_last_week()
    jobs.generate_post(app, reel)
    assert app.media.videos == [{"seconds": 15, "audio": True, "voice_id": None}]
    motion = next(c[1] for c in app.media.calls if c[0] == "video")
    assert 'says: "babe I said' in motion and "lips in sync" in motion
    assert app.db.spent_last_week() - before == pytest.approx(0.15 + 0.68 * 15 / 8 * 1.5 + 0.02, abs=0.01)
    jobs.send_reviews(app)
    assert any("🗣 «babe I said" in m["caption"] for m in app.tg.media)


def test_replan_keeps_what_is_made_and_redoes_the_rest_from_tomorrow(app):
    plan(app)
    now = at(app.cfg, 2026, 10, 20, 15, 0)  # Tuesday afternoon of the planned week
    jobs.generate_pending(app, at(app.cfg, 2026, 10, 18, 19, 0), limit=3)
    made = {p["id"] for p in app.db.posts("ready")}
    assert len(made) == 3
    failed = next(p for p in app.db.posts("planned") if p["slot_at"] > at(app.cfg, 2026, 10, 22))
    app.db.update_post(failed["id"], status="failed", attempts=4)
    today_left = [p for p in app.db.posts("planned") if at(app.cfg, 2026, 10, 20) <= p["slot_at"] < at(app.cfg, 2026, 10, 21)]

    app.cfg.generation["idea_approval"] = True
    bot.handle_update(app, {"update_id": 40, "message": {"from": {"id": OWNER}, "text": "/replan"}}, now)

    assert {p["id"] for p in app.db.posts("ready")} == made  # nothing already made is lost
    assert app.db.get_post(failed["id"]) is None
    assert all(app.db.get_post(p["id"]) for p in today_left)  # today's remaining posts stay
    fresh = app.db.posts("proposed")
    assert fresh and min(p["slot_at"] for p in fresh if p["targets"] != ["fanvue"]).date() == at(app.cfg, 2026, 10, 21).date()
    assert len([p for p in fresh if p["targets"] == ["fanvue"]]) == app.cfg.fanvue_per_week
    assert app.db.kv_get("planned_until") == "2026-10-27"
    assert any(m.startswith("♻️ Πέταξα") for m in app.tg.messages)


def test_the_first_approved_skit_locks_her_voice_for_the_rest(app, monkeypatch, tmp_path):
    app.cfg.slots[1].video = {"seconds": 15, "voice": True}

    def items(n):
        out = __import__("conftest").default_items(n)
        for item in out:
            item["speech"] = "no I did not eat your fries"
        return out

    app._claude = FakeClaude(items)
    app.db.kv_set("reference_urls", ["https://fal.media/ref1.jpg"])
    plan(app)
    reels = [p for p in app.db.posts("planned") if p["voice"]][:2]
    jobs.generate_post(app, reels[0])
    assert app.media.videos[-1]["voice_id"] is None
    assert "in a casual American voice" in next(c[1] for c in app.media.calls if c[0] == "video")

    monkeypatch.setattr(jobs, "extract_audio", lambda src, dest, run=None: (Path(dest).write_bytes(b"wav"), dest)[1])
    jobs.send_reviews(app)
    assert jobs.review_action(app, "a", reels[0]["id"])[0] == "✅ Εγκρίθηκε"
    assert app.db.kv_get("voice_id") == "voice-abc" and any(m.startswith("🔒") for m in app.tg.messages)

    jobs.generate_post(app, reels[1])
    assert app.media.videos[-1]["voice_id"] == "voice-abc"
    assert "<<<voice_1>>>" in [c[1] for c in app.media.calls if c[0] == "video"][-1]
    spent_voice = [c for c in app.media.calls if c[0] == "voice"]
    assert len(spent_voice) == 1  # cloned once, reused after


def test_identity_and_realism_go_into_every_image_prompt(app):
    app.cfg.persona["marks"] = "a beauty mark under the left eye, a slightly asymmetric smile"
    app.cfg.persona["skin_hex"] = "#E9B894"
    app.db.kv_set("reference_urls", ["https://fal.media/ref1.jpg"])
    plan(app)
    story = next(p for p in app.db.posts("planned") if "instagram_story" in p["targets"])
    fanvue = next(p for p in app.db.posts("planned") if p["targets"] == ["fanvue"])
    jobs.generate_post(app, story)
    jobs.generate_post(app, fanvue)
    ref = next(c[1] for c in app.media.calls if c[0] == "ref_image")
    lora = next(c[1] for c in app.media.calls if c[0] == "image")
    for prompt in (ref, lora):
        assert "beauty mark under the left eye" in prompt and "Visible skin pores" in prompt
    assert "Skin tone #E9B894" in ref and "Preserve her natural asymmetry" in ref
    system = app.claude.requests[0]["system"]
    assert "'someone filmed me' rear camera" in system and "phone propped on a table" in system


def test_a_spoken_swipe_takes_the_next_voice_slot_and_needs_no_second_tap(app):
    from datetime import time as _time

    from ofm.config import Slot

    app.cfg.slots[1].video = {"seconds": 15, "voice": True}
    app.cfg.slots.append(Slot(_time(12, 30), "video", ["instagram_reel", "tiktok", "youtube_short"], list(range(7))))
    app.cfg.generation["idea_approval"] = True
    plan(app)
    swipe_id = app.db.add_swipe("Girlfriend scolds him in the kitchen. Hook idea: when he says he is not hungry. Spoken: yes, she talks to camera")
    post = planner.remake_next_reel(app, at(app.cfg, *SUNDAY_EVENING), swipe_id)
    assert post["voice"] == 1 and post["status"] == "planned"  # the 🎬 tap was the approval
    assert "Remake this viral format" in app.claude.requests[-1]["messages"][0]["content"]
    quiet = app.db.add_swipe("outfit transition. Spoken: no, music and text only")
    other = planner.remake_next_reel(app, at(app.cfg, *SUNDAY_EVENING), quiet)
    assert other["voice"] == 0 and other["id"] != post["id"]
