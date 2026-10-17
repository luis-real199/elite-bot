import pytest
import yaml

from ofm import guardrails
from ofm.buffer import Enum, literal, post_input
from ofm.config import ConfigError, load_config

from conftest import ROOT


def write_config(tmp_path, **changes):
    raw = yaml.safe_load((ROOT / "persona.yaml").read_text(encoding="utf-8"))
    for dotted, value in changes.items():
        section, key = dotted.split(".")
        raw[section][key] = value
    path = tmp_path / "persona.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return path


def test_example_config_loads(cfg):
    assert cfg.persona["age"] >= 21
    assert len(cfg.slots) == 3
    assert cfg.generation["social_safety_checker"] is True


def test_underage_persona_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="age"):
        load_config(write_config(tmp_path, **{"persona.age": 19}), env={})


def test_social_safety_checker_cannot_be_disabled(tmp_path):
    path = write_config(tmp_path, **{"generation.social_safety_checker": False})
    assert load_config(path, env={}).generation["social_safety_checker"] is True


def test_video_target_needs_video_slot(tmp_path):
    path = write_config(tmp_path, **{"schedule.slots": [{"time": "10:00", "kind": "image", "targets": ["tiktok"]}]})
    with pytest.raises(ConfigError, match="kind: video"):
        load_config(path, env={})


@pytest.mark.parametrize("text, rule", [
    ("cute teen girl at the beach", "minor"),
    ("wearing a school uniform", "minor"),
    ("she looks 16 years old", "minor"),
    ("μαθήτρια στο σχολείο", "minor"),
    ("Taylor Swift lookalike", "real_person"),
    ("I'm real, not AI 😘", "claims_human"),
])
def test_violations_are_caught(text, rule):
    assert rule in guardrails.violations(text)


@pytest.mark.parametrize("text", [
    "Just kidding, coffee first ☕",
    "Lunch at the canteen after the gym",
    "Sunset in Oia, thirteen degrees and windy",
    "Adult woman, 24, beach day in Naxos",
])
def test_normal_captions_pass(text):
    assert guardrails.violations(text) == []


def test_disclosure_tag_is_added_and_tags_normalised():
    assert guardrails.with_disclosure(["travel", "#Greece", "greece"]) == ["#travel", "#Greece", "#aigenerated"]
    assert guardrails.with_disclosure(["#aigenerated", "fit"]) == ["#aigenerated", "#fit"]


def test_graphql_literal_encoding():
    assert literal({"a": Enum("reel"), "b": True, "c": 'say "hi" ✨', "d": [1, None]}) == (
        '{a: reel, b: true, c: "say \\"hi\\" ✨", d: [1, null]}'
    )


def test_reel_input_shape(cfg):
    from datetime import datetime

    post = {"kind": "video", "caption": "Morning run #fit", "hashtags": ["#AI", "#fit"]}
    data = post_input(post, "instagram_reel", "ch_ig", "https://cdn/1.mp4", datetime(2026, 10, 20, 19, 0, tzinfo=cfg.tz))
    assert data["dueAt"] == "2026-10-20T23:00:00.000Z"  # 19:00 New York (EDT) in UTC
    assert data["assets"] == [{"video": {"url": "https://cdn/1.mp4"}}]
    assert data["metadata"] == {"instagram": {"type": "reel", "shouldShareToFeed": True}}
    assert data["text"].endswith("#AI #fit")


def test_x_text_is_trimmed(cfg):
    from datetime import datetime

    post = {"kind": "image", "caption": "a" * 300, "hashtags": ["#AI"]}
    data = post_input(post, "x", "ch_x", "https://cdn/1.jpg", datetime(2026, 10, 20, tzinfo=cfg.tz))
    assert len(data["text"]) == 280
    assert "metadata" not in data


def test_telegram_errors_do_not_leak_the_token():
    import requests

    from ofm.telegram import Telegram, TelegramError

    class Broken:
        def post(self, url, **kwargs):
            raise requests.ConnectionError(f"Max retries exceeded with url: {url}")

    tg = Telegram("123:SECRET", 1, session=Broken())
    with pytest.raises(TelegramError) as e:
        tg.send("hi")
    assert "SECRET" not in str(e.value) and e.value.__cause__ is None


class FakeResponse:
    def __init__(self, body, status=200):
        self.body, self.status_code, self.text = body, status, str(body)

    def json(self):
        return self.body


class FakeSession:
    def __init__(self, *bodies):
        self.bodies = list(bodies)
        self.sent = []

    def post(self, url, **kwargs):
        self.sent.append((url, kwargs))
        return self.bodies.pop(0)


def test_buffer_responses():
    from ofm.buffer import Buffer, BufferError

    ok = FakeResponse({"data": {"createPost": {"__typename": "PostActionSuccess", "post": {"id": "p1"}}}})
    refused = FakeResponse({"data": {"createPost": {"__typename": "MutationError", "message": "Invalid media URL"}}})
    invalid = FakeResponse({"errors": [{"message": "Unknown argument"}]})
    session = FakeSession(ok, refused, invalid, FakeResponse({}, status=401))
    buffer = Buffer("key", session=session)

    assert buffer.create_post({"text": "hi"}) == "p1"
    assert session.sent[0][1]["headers"]["Authorization"] == "Bearer key"
    for message in ("Invalid media URL", "Unknown argument", "401"):
        with pytest.raises(BufferError, match=message):
            buffer.create_post({"text": "hi"})


def test_telegram_multipart_encodes_markup_and_flags(tmp_path):
    from ofm.telegram import Telegram, keyboard

    photo = tmp_path / "1.jpg"
    photo.write_bytes(b"x")
    session = FakeSession(FakeResponse({"ok": True, "result": {"message_id": 7}}))
    tg = Telegram("t", 1, session=session)
    assert tg.send_media(photo, "cap", keyboard([[("✅", "a:1")]]), silent=True)["message_id"] == 7
    url, kwargs = session.sent[0]
    assert url.endswith("/sendPhoto")
    assert kwargs["data"]["disable_notification"] == "true"
    assert '"callback_data": "a:1"' in kwargs["data"]["reply_markup"]
