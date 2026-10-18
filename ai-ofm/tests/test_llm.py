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
    assert len(reqs) == 8  # 37 slots in chunks of 5, to stay under the free 8K tokens/minute
    first = reqs[0]
    assert first["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert first["headers"] == {"Authorization": "Bearer gsk_test"}
    assert first["body"]["model"] == "openai/gpt-oss-120b" and first["body"]["reasoning_effort"] == "low"
    fmt = first["body"]["response_format"]  # strict schema output: Groq's constrained decoding for gpt-oss
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] and fmt["json_schema"]["name"] == "weekly_plan"
    assert fmt["json_schema"]["schema"] == planner.ITEM_SCHEMA
    assert "JSON schema" not in first["body"]["messages"][0]["content"]
    assert first["body"]["max_completion_tokens"] == 1024 + 800 * 5 and first["body"]["temperature"] == 0.7
    assert free.db.spent_last_week() == 0
    assert free.claude.requests == []


def test_quality_check_sends_both_images_to_the_vision_model(free):
    passed, reason = qc.check_image(free, "https://fal.media/new.jpg", "https://fal.media/ref.jpg")
    assert passed is True
    body = free.llm_http.requests[0]["body"]
    assert body["model"] == "qwen/qwen3.8-27b" and body["reasoning_effort"] == "none"
    assert body["response_format"] == {"type": "json_object"}  # strict mode with images is not documented
    assert "JSON schema" in body["messages"][0]["content"] and body["max_completion_tokens"] == 1024
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


def json_validate_failed():
    err = {"error": {"message": "Failed to generate JSON. Please adjust your prompt.", "type": "invalid_request_error",
                     "code": "json_validate_failed", "failed_generation": '{"items": [{"slot": 0'}}
    return SimpleNamespace(status_code=400, headers={}, text=json.dumps(err), json=lambda: err)


def test_groq_json_failure_is_retried_calmer(free):
    free.llm_http.replies = [json_validate_failed()]
    passed, _ = qc.check_image(free, "https://fal.media/new.jpg", "https://fal.media/ref.jpg")
    assert passed is True
    first, second = (r["body"] for r in free.llm_http.requests)
    assert first is second and second["temperature"] <= 0.5


def test_a_chunk_that_keeps_failing_is_split_instead_of_losing_the_week(free):
    free.llm_http.replies = [json_validate_failed(), json_validate_failed()]
    summary = planner.plan_ahead(free, datetime(2026, 10, 18, 18, 5, tzinfo=free.cfg.tz))
    assert summary["created"] == 37 and summary["missing"] == 0
    sizes = [len(json.loads(r["body"]["messages"][1]["content"].split("\n")[1])) for r in free.llm_http.requests]
    assert sizes[:4] == [5, 5, 2, 3]  # the failed chunk of 5 went again as 2 + 3


def test_cut_off_answer_is_split_and_a_hopeless_slot_is_left_out(free):
    cut = {"choices": [{"message": {"content": '{"items": [{"slot": 0'}, "finish_reason": "length"}]}
    free.llm_http.replies = [cut, cut, json_validate_failed(), json_validate_failed()]
    summary = planner.plan_ahead(free, datetime(2026, 10, 18, 18, 5, tzinfo=free.cfg.tz))
    # 5 is cut off -> 2 + 3; the 2 is cut off -> 1 + 1; that first 1 fails twice and is left out
    assert summary["created"] == 36 and summary["missing"] == 1


def test_other_errors_stop_the_plan_with_a_short_message(free):
    err = {"error": {"message": "Invalid API Key", "type": "invalid_request_error", "code": "invalid_api_key"}}
    free.llm_http.replies = [SimpleNamespace(status_code=401, headers={}, text=json.dumps(err), json=lambda: err)]
    with pytest.raises(planner.PlanError, match="HTTP 401 invalid_api_key: Invalid API Key"):
        planner.plan_ahead(free, datetime(2026, 10, 18, 18, 5, tzinfo=free.cfg.tz))
    assert len(free.llm_http.requests) == 1


def test_rejected_but_complete_json_is_salvaged_from_the_error(free):
    good = {"same_person": True, "clearly_adult": True, "defects": [], "verdict": "fail", "reason": "waxy skin"}
    err = {"error": {"code": "json_validate_failed", "message": "Failed to generate JSON.", "failed_generation": json.dumps(good)}}
    free.llm_http.replies = [SimpleNamespace(status_code=400, headers={}, text=json.dumps(err), json=lambda: err)]
    assert qc.check_image(free, "https://fal.media/new.jpg", "https://fal.media/ref.jpg") == (False, "waxy skin")
    assert len(free.llm_http.requests) == 1


def test_too_large_request_splits_the_chunk_and_daily_quota_stops(free):
    big = {"error": {"code": "rate_limit_exceeded", "message": "Request too large for model on tokens per minute (TPM): Limit 8000, Requested 9000"}}
    free.llm_http.replies = [SimpleNamespace(status_code=413, headers={}, text="", json=lambda: big)] * 2
    summary = planner.plan_ahead(free, datetime(2026, 10, 18, 18, 5, tzinfo=free.cfg.tz))
    assert summary["missing"] == 0
    assert free.llm_http.requests[2]["body"]["max_completion_tokens"] == 1024 + 800 * 2

    daily = {"error": {"code": "rate_limit_exceeded", "message": "Rate limit reached on tokens per day (TPD): Limit 200000"}}
    free.llm_http.replies = [SimpleNamespace(status_code=429, headers={"retry-after": "3000"}, text="", json=lambda: daily)]
    waits = []
    free.sleep = waits.append
    passed, reason = qc.check_image(free, "https://fal.media/new.jpg", "https://fal.media/ref.jpg")
    assert passed is None and "ημερήσιο" in reason and waits == []


def test_strict_mode_falls_back_to_json_mode_if_the_provider_rejects_it(free):
    err = {"error": {"code": "invalid_request_error", "message": "response_format json_schema is not supported for this model"}}
    free.llm_http.replies = [SimpleNamespace(status_code=400, headers={}, text="", json=lambda: err)]
    draft = chat.draft_reply(free, {"uuid": "f1", "displayName": "Jake"}, [{"text": "hey", "sender": {"uuid": "f1"}}], "me")
    assert draft["reply"] == "hi there"
    first, second = (r["body"] for r in free.llm_http.requests)
    assert first["response_format"]["type"] == "json_schema" and first["max_completion_tokens"] == 1536
    assert second["response_format"] == {"type": "json_object"} and "JSON schema" in second["messages"][0]["content"]
