import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from ofm import chat, llm, planner, qc
from ofm.config import ConfigError, load_config

from conftest import ROOT, default_items


class FreeAPI:
    """Stands in for Groq's OpenAI-compatible /chat/completions."""

    def __init__(self):
        self.requests, self.replies = [], []

    def post(self, url, json=None, headers=None, timeout=None):
        self.requests.append({"url": url, "body": json, "headers": headers})
        reply = self.replies.pop(0) if self.replies else self.auto(json)
        if isinstance(reply, SimpleNamespace):
            return reply
        return SimpleNamespace(status_code=200, headers={}, text="", json=lambda: reply)

    def auto(self, body):
        prompt = body["messages"][1]["content"]
        if isinstance(prompt, list):  # quality check
            content = '{"same_person": true, "clearly_adult": true, "defects": [], "verdict": "pass", "reason": ""}'
        elif prompt.startswith("Plan these"):
            slots = __import__("json").loads(prompt.split("\n")[1])
            items = default_items(max(s["slot"] for s in slots) + 1)
            content = "```json\n" + __import__("json").dumps({"items": [items[s["slot"]] for s in slots]}) + "\n```"
        else:
            content = ('{"reply": "hi there", "offer_media_uuid": "", "offer_price_usd": 0, '
                       '"escalate": false, "escalate_reason": "", "fan_request": ""}')
        return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 900, "completion_tokens": 300}}


@pytest.fixture
def free(app):
    app.cfg.models["llm"] = {"provider": "groq"}
    app.cfg.env["GROQ_API_KEY"] = "gsk_test"
    app.llm_http = FreeAPI()
    app.sleep = lambda s: None
    return app


def test_example_persona_defaults_to_groq_and_rejects_unknown_providers(tmp_path):
    cfg = load_config(ROOT / "persona.example.yaml", env={})
    assert llm.settings(cfg)["provider"] == "groq"
    bad = tmp_path / "persona.yaml"
    bad.write_text((ROOT / "persona.example.yaml").read_text(encoding="utf-8").replace("provider: groq", "provider: gpt"),
                   encoding="utf-8")
    with pytest.raises(ConfigError, match="provider"):
        load_config(bad, env={})


def test_plan_is_sent_in_chunks_to_the_free_api(free):
    summary = planner.plan_ahead(free, datetime(2026, 10, 18, 18, 5, tzinfo=free.cfg.tz))
    assert summary["created"] == 37 and summary["missing"] == 0
    reqs = free.llm_http.requests
    assert len(reqs) == 7  # 37 slots in chunks of 6, to stay under the free 8K tokens/minute
    first = reqs[0]
    assert first["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert first["headers"] == {"Authorization": "Bearer gsk_test"}
    assert first["body"]["model"] == "openai/gpt-oss-120b" and first["body"]["reasoning_effort"] == "low"
    assert first["body"]["response_format"] == {"type": "json_object"}
    assert "JSON schema" in first["body"]["messages"][0]["content"]
    assert free.db.spent_last_week() == 0
    assert free.claude.requests == []


def test_quality_check_sends_both_images_to_the_vision_model(free):
    passed, reason = qc.check_image(free, "https://fal.media/new.jpg", "https://fal.media/ref.jpg")
    assert passed is True
    body = free.llm_http.requests[0]["body"]
    assert body["model"] == "qwen/qwen3.8-27b" and "reasoning_effort" not in body
    images = [p["image_url"]["url"] for p in body["messages"][1]["content"] if p["type"] == "image_url"]
    assert images == ["https://fal.media/ref.jpg", "https://fal.media/new.jpg"]


def test_rate_limit_waits_then_retries(free):
    waits = []
    free.sleep = waits.append
    free.llm_http.replies = [SimpleNamespace(status_code=429, headers={"retry-after": "7"}, text="slow down")]
    passed, _ = qc.check_image(free, "https://fal.media/new.jpg", "https://fal.media/ref.jpg")
    assert passed is True and waits == [7.0]


def test_invalid_json_is_asked_again_then_given_up(free):
    bad = {"choices": [{"message": {"content": "sure! here you go"}, "finish_reason": "stop"}], "usage": {}}
    free.llm_http.replies = [bad, bad]
    passed, reason = qc.check_image(free, "https://fal.media/new.jpg", "https://fal.media/ref.jpg")
    assert passed is None and "έγκυρο JSON" in reason
    assert "not valid JSON" in json.dumps(free.llm_http.requests[1]["body"]["messages"][-1])


def test_missing_key_and_content_filter(free):
    free.cfg.env["GROQ_API_KEY"] = ""
    with pytest.raises(llm.LLMError, match="GROQ_API_KEY"):
        llm.ask_json(free, system="s", content="c", schema={"type": "object"}, kind="chat")
    free.cfg.env["GROQ_API_KEY"] = "gsk_test"
    free.llm_http.replies = [{"choices": [{"message": {"content": ""}, "finish_reason": "content_filter"}]}]
    draft = chat.draft_reply(free, {"uuid": "f1", "displayName": "Jake"}, [], "me")
    assert draft["escalate"] and draft["reply"] == ""


def test_chat_uses_the_free_api(free):
    draft = chat.draft_reply(free, {"uuid": "f1", "displayName": "Jake"},
                             [{"text": "hey", "sender": {"uuid": "f1"}}], "me")
    assert draft["reply"] == "hi there"
    system = free.llm_http.requests[0]["body"]["messages"][0]["content"]
    assert "openly AI-generated character" in system and "Catalogue" in system


def test_reasoning_text_is_ignored(free):
    free.llm_http.replies = [{"choices": [{"message": {"content": '<think>{"maybe": 1}</think>\n{"same_person": true, '
                              '"clearly_adult": true, "defects": [], "verdict": "fail", "reason": "warped hand"}'},
                              "finish_reason": "stop"}]}]
    assert qc.check_image(free, "https://fal.media/new.jpg", "https://fal.media/ref.jpg") == (False, "warped hand")


def test_health_check_warns_when_a_free_model_is_retired(free):
    from ofm import health

    class Models:
        def get(self, url, headers=None, timeout=None):
            assert url == "https://api.groq.com/openai/v1/models"
            return SimpleNamespace(status_code=200, json=lambda: {"data": [{"id": "openai/gpt-oss-120b"}]})

    free.llm_http = Models()
    problems = health.health_check(free)
    assert problems == ["groq: το μοντέλο qwen/qwen3.8-27b δεν υπάρχει πια. Άλλαξέ το στο persona.yaml (models.llm)."]
