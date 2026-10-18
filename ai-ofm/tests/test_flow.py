from datetime import datetime, timedelta

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
    assert jobs.review_action(app, "a", post_id)[0] == "Ήδη: rejected"


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

    assert onboarding.dataset(app) == len(onboarding.DATASET_SHOTS)
    shots = [c for c in app.media.calls if c[0] == "ref_image"]
    assert shots and all(c[2] == [app.db.kv_get("reference_face")["url"]] for c in shots)
    assert shots[0][1].startswith("Keep exactly the same face") and "Her body and look must be exactly this" in shots[0][1]
    assert app.db.spent_last_week() == 0  # setup costs don't eat the weekly content budget
    bot.handle_update(app, {"update_id": 5, "callback_query": {"id": "c", "from": {"id": OWNER}, "data": "d:00.jpg",
                                                               "message": {"message_id": 2}}}, None)
    assert not (app.setup_dir / "dataset" / "00.jpg").exists()
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
