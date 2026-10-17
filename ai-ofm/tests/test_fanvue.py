from datetime import datetime

import pytest

from ofm import bot, chat, jobs, planner
from ofm.db import DB
from ofm.fanvue import API_URL, API_VERSION, PART_SIZE, TOKEN_KEY, Fanvue, FanvueAuthError

from conftest import OWNER


# ---------- the API client, against a fake HTTP session ----------

class Response:
    def __init__(self, status=200, body=None, headers=None, text=None):
        self.status_code, self.headers = status, headers or {}
        self._body = body
        self.text = text if text is not None else ("" if body is None else str(body))
        self.content = b"" if body is None and text is None else b"x"

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class Session:
    def __init__(self):
        self.calls, self.queue = [], []

    def _next(self, call):
        self.calls.append(call)
        return self.queue.pop(0)

    def post(self, url, **kw):
        return self._next(("POST", url, kw))

    def put(self, url, **kw):
        return self._next(("PUT", url, kw))

    def request(self, method, url, **kw):
        return self._next((method, url, kw))


def client(clock=lambda: 1000.0):
    db, http = DB(":memory:"), Session()
    return Fanvue("cid", "secret", "https://bot.example/callback", db, session=http, sleep=lambda s: None, clock=clock), http, db


def test_login_flow_checks_state_and_stores_tokens():
    fv, http, db = client()
    url = fv.login_url()
    assert url.startswith("https://auth.fanvue.com/oauth2/auth?") and "code_challenge_method=S256" in url
    pkce = db.kv_get("fanvue_pkce")
    state = pkce["state"]

    with pytest.raises(FanvueAuthError):
        fv.finish_login("https://bot.example/callback?code=abc&state=wrong")

    http.queue = [Response(body={"access_token": "A1", "refresh_token": "R1", "expires_in": 3600}),
                  Response(body={"uuid": "me-1", "handle": "mia"})]
    me = fv.finish_login(f"https://bot.example/callback?code=abc&state={state}")
    assert me["handle"] == "mia" and fv.connected
    token_call = http.calls[0]
    assert token_call[2]["data"] == {"grant_type": "authorization_code", "code": "abc", "client_id": "cid",
                                     "redirect_uri": "https://bot.example/callback", "code_verifier": pkce["verifier"]}
    assert db.kv_get("fanvue_pkce") is None
    assert token_call[2]["headers"]["Authorization"].startswith("Basic ")
    assert http.calls[1][2]["headers"] == {"Authorization": "Bearer A1", "X-Fanvue-API-Version": API_VERSION}
    assert db.kv_get("fanvue_me")["uuid"] == "me-1"


def test_expired_token_refreshes_and_keeps_rotated_refresh_token():
    now = [1000.0]
    fv, http, db = client(clock=lambda: now[0])
    db.kv_set(TOKEN_KEY, {"access_token": "old", "refresh_token": "R1", "expires_at": 1030.0})
    http.queue = [Response(body={"access_token": "A2", "refresh_token": "R2", "expires_in": 3600}),
                  Response(body={"uuid": "me-1"})]
    fv.me()
    assert http.calls[0][2]["data"] == {"grant_type": "refresh_token", "refresh_token": "R1", "client_id": "cid"}
    assert db.kv_get(TOKEN_KEY)["refresh_token"] == "R2"
    assert http.calls[1][2]["headers"]["Authorization"] == "Bearer A2"


def test_401_triggers_one_refresh_then_auth_error_is_raised():
    fv, http, db = client()
    db.kv_set(TOKEN_KEY, {"access_token": "A1", "refresh_token": "R1", "expires_at": 99999.0})
    http.queue = [Response(401, text="expired"), Response(400, text="invalid_grant")]
    with pytest.raises(FanvueAuthError):
        fv.me()


def test_multipart_upload(tmp_path):
    fv, http, db = client()
    db.kv_set(TOKEN_KEY, {"access_token": "A1", "refresh_token": "R1", "expires_at": 99999.0})
    video = tmp_path / "7.mp4"
    video.write_bytes(b"v" * (PART_SIZE + 10))
    http.queue = [
        Response(body={"uploadId": "up1", "mediaUuid": "m1"}),
        Response(body={"url": "https://s3.example/p1"}), Response(headers={"ETag": '"e1"'}),
        Response(text="https://s3.example/p2"), Response(headers={"ETag": '"e2"'}),
        Response(body={"status": "processing"}),
    ]
    assert fv.upload(video, "video") == "m1"
    start = http.calls[0]
    assert start[1] == f"{API_URL}/media/uploads"
    assert start[2]["json"] == {"name": "7", "filename": "7.mp4", "mediaType": "video", "sizeBytes": PART_SIZE + 10}
    assert http.calls[1][1].endswith("/media/uploads/up1/parts/1/url")
    assert http.calls[2][0] == "PUT" and len(http.calls[2][2]["data"]) == PART_SIZE
    assert len(http.calls[4][2]["data"]) == 10
    assert http.calls[5][0] == "PATCH" and http.calls[5][2]["json"] == {
        "parts": [{"partNumber": 1, "etag": '"e1"'}, {"partNumber": 2, "etag": '"e2"'}]}


def test_post_and_message_bodies(cfg):
    fv, http, db = client()
    db.kv_set(TOKEN_KEY, {"access_token": "A1", "refresh_token": "R1", "expires_at": 99999.0})
    http.queue = [Response(body={"uuid": "p1"}), Response(body={"messageUuid": "msg1"})]
    when = datetime(2026, 10, 20, 20, 0, tzinfo=cfg.tz)
    assert fv.create_post("hi #AI", ["m1"], publish_at=when) == "p1"
    assert http.calls[0][2]["json"] == {"text": "hi #AI", "mediaUuids": ["m1"], "audience": "subscribers",
                                        "publishAt": "2026-10-20T20:00:00-04:00"}
    assert fv.send_message("fan1", "unlock this 👀", ["m2"], 1200) == "msg1"
    assert http.calls[1][1] == f"{API_URL}/chats/fan1/message"
    assert http.calls[1][2]["json"] == {"text": "unlock this 👀", "mediaUuids": ["m2"], "price": 1200}


# ---------- publishing approved items to Fanvue ----------

def approve_fanvue_batch(app):
    planner.plan_ahead(app, datetime(2026, 10, 18, 18, 5, tzinfo=app.cfg.tz))
    jobs.generate_pending(app, datetime(2026, 10, 18, 19, 0, tzinfo=app.cfg.tz), limit=100)
    jobs.send_reviews(app)
    for post in app.db.posts("in_review"):
        if post["targets"] == ["fanvue"]:
            jobs.review_action(app, "a", post["id"])


def test_feed_posts_one_per_day_rest_to_vault(fv_app):
    app = fv_app
    approve_fanvue_batch(app)
    assert jobs.publish_fanvue(app, datetime(2026, 10, 18, 22, 0, tzinfo=app.cfg.tz)) == 20
    fv = app.fanvue
    assert len(fv.posts) == 7 and len(fv.vault) == 13
    days = [p["publish_at"] for p in fv.posts]
    assert days[0] == datetime(2026, 10, 19, 20, 0, tzinfo=app.cfg.tz)
    assert days[-1] == datetime(2026, 10, 25, 20, 0, tzinfo=app.cfg.tz)
    assert all(p["text"].endswith("#aigenerated") for p in fv.posts)
    assert len(app.db.fanvue_media(purpose="vault")) == 13
    assert len(app.db.posts("delivered")) == 20
    assert jobs.publish_fanvue(app, datetime(2026, 10, 18, 22, 5, tzinfo=app.cfg.tz)) == 0


# ---------- chat ----------

NOW = datetime(2026, 10, 20, 21, 0)


def vault_item(app, uuid="vault-1"):
    app.db.add_fanvue_media(1, uuid, "vault", "2026-10-19", "red bikini on a boat at sunset")


def test_approve_mode_sends_only_after_tap(fv_app):
    app, fv = fv_app, fv_app.fanvue
    vault_item(app)
    app.claude.chat_replies = [{"reply": "made something just for you 🙈", "offer_media_uuid": "vault-1", "offer_price_usd": 40,
                                "fan_request": "red bikini"}]
    fv.fan_says("fan1", "show me something special", "m1")
    assert chat.poll_chats(app, NOW) == 1
    assert fv.sent == []
    card = app.tg.messages[-1]
    assert "show me something special" in card and "💰 PPV $25" in card  # price clamped to max
    draft = app.db.draft(1)
    assert draft["status"] == "pending" and draft["offer_price_cents"] == 2500

    reply, label = chat.draft_action(app, "cs", 1)
    assert label == "📤 Στάλθηκε"
    assert fv.sent == [{"fan": "fan1", "text": "made something just for you 🙈", "media": ["vault-1"], "price": 2500}]
    assert fv.read == ["fan1"]
    assert app.db.offered_to("fan1") == {"vault-1"}
    assert app.db.fan_requests()[0]["text"] == "red bikini"

    # the same unread message is not drafted twice
    assert chat.poll_chats(app, NOW) == 0


def test_auto_mode_sends_and_escalates_top_spenders(fv_app):
    app, fv = fv_app, fv_app.fanvue
    app.db.kv_set("chat_mode", "auto")
    fv.fan_says("fan1", "hey", "m1")
    fv.fan_says("fan2", "hey gorgeous", "m2", top=True, name="Rich")
    chat.poll_chats(app, NOW)
    assert [s["fan"] for s in fv.sent] == ["fan1"]
    assert "⭐ top spender" in app.tg.messages[-1] and "Rich" in app.tg.messages[-1]


def test_unknown_or_repeated_offers_are_dropped(fv_app):
    app, fv = fv_app, fv_app.fanvue
    app.db.kv_set("chat_mode", "auto")
    vault_item(app)
    app.db.add_offer("fan1", "vault-1", 1200)
    app.claude.chat_replies = [{"offer_media_uuid": "vault-1", "offer_price_usd": 12}]
    fv.fan_says("fan1", "anything new?", "m1")
    chat.poll_chats(app, NOW)
    assert fv.sent[0]["media"] is None and fv.sent[0]["price"] is None
    prompt = app.claude.chat_requests[0]["system"][1]["text"]
    assert "do not offer anything" in prompt


def test_minor_cues_and_rule_breaking_drafts_never_auto_send(fv_app):
    app, fv = fv_app, fv_app.fanvue
    app.db.kv_set("chat_mode", "auto")
    fv.fan_says("fan1", "im 16 yo lol", "m1")
    app.claude.chat_replies = [{}, {"reply": "I'm real, not AI 😘"}]
    fv.fan_says("fan2", "are you real?", "m2", name="Sam")
    chat.poll_chats(app, NOW)
    assert fv.sent == []
    assert any("πιθανός ανήλικος" in m for m in app.tg.messages)
    assert any("έσπασε κανόνες" in m for m in app.tg.messages)


def test_owner_reply_overrides_the_draft(fv_app):
    app, fv = fv_app, fv_app.fanvue
    fv.fan_says("fan1", "can you do a custom?", "m1")
    chat.poll_chats(app, NOW)
    tg_id = app.db.draft(1)["tg_message_id"]
    update = {"update_id": 9, "message": {"from": {"id": OWNER}, "text": "for you? maybe 😏 tell me more",
                                          "reply_to_message": {"message_id": tg_id}}}
    bot.handle_update(app, update, NOW)
    assert fv.sent == [{"fan": "fan1", "text": "for you? maybe 😏 tell me more", "media": None, "price": None}]
    assert app.db.draft(1)["status"] == "sent_custom"


def test_chat_budget_and_modes(fv_app):
    app = fv_app
    app.db.add_cost("chat", app.cfg.chat["weekly_usd"])
    app.fanvue.fan_says("fan1", "hey", "m1")
    with pytest.raises(RuntimeError, match="όριο"):
        chat.poll_chats(app, NOW)
    app.db.kv_set("chat_mode", "off")
    assert chat.poll_chats(app, NOW) == 0

    bot.handle_update(app, {"update_id": 1, "message": {"from": {"id": OWNER}, "text": "/chat_auto"}}, NOW)
    assert app.db.kv_get("chat_mode") == "auto"


def test_fan_requests_feed_the_next_plan(fv_app):
    app = fv_app
    app.db.add_fan_request("fan1", "black lingerie in a hotel room")
    planner.plan_ahead(app, datetime(2026, 10, 18, 18, 5, tzinfo=app.cfg.tz))
    prompt = app.claude.requests[0]["messages"][0]["content"]
    assert "black lingerie in a hotel room" in prompt
    assert app.db.fan_requests() == []


def test_tick_polls_chat_once_a_minute(fv_app):
    app = fv_app
    app.fanvue.fan_says("fan1", "hey", "m1")
    jobs.tick(app, datetime(2026, 10, 20, 21, 0, 0, tzinfo=app.cfg.tz))
    app.fanvue.fan_says("fan2", "hey", "m2", name="Sam")
    jobs.tick(app, datetime(2026, 10, 20, 21, 0, 30, tzinfo=app.cfg.tz))
    assert len(app.claude.chat_requests) == 1
    jobs.tick(app, datetime(2026, 10, 20, 21, 1, 5, tzinfo=app.cfg.tz))
    assert len(app.claude.chat_requests) == 2
