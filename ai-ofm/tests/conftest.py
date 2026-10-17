import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from ofm import jobs, onboarding
from ofm.app import App
from ofm.config import load_config
from ofm.db import DB

ROOT = Path(__file__).resolve().parents[1]
OWNER = 4242


class FakeTelegram:
    def __init__(self):
        self.owner_id = OWNER
        self.messages = []
        self.media = []
        self.buttons = []
        self.answers = []
        self._next_id = 100

    def _id(self):
        self._next_id += 1
        return self._next_id

    def send(self, text, markup=None, silent=False):
        self.messages.append(text)
        return {"message_id": self._id()}

    def send_media(self, path, caption="", markup=None, silent=False, as_document=False):
        self.media.append({"path": str(path), "caption": caption, "markup": markup, "document": as_document})
        return {"message_id": self._id()}

    def set_buttons(self, message_id, markup):
        self.buttons.append((message_id, markup))

    def answer(self, callback_id, text=""):
        self.answers.append(text)

    def is_owner(self, update):
        sender = (update.get("callback_query") or update.get("message") or {}).get("from") or {}
        return sender.get("id") == OWNER


class FakeMedia:
    def __init__(self, cfg, db):
        self.cfg, self.db = cfg, db
        self.calls = []
        self.flag_next = 0
        self.fail_next = 0

    def check_budget(self, *kinds):
        from ofm.media import BudgetExceeded

        spent = self.db.spent_last_week()
        if spent + sum(self.cfg.estimates[k] for k in kinds) > self.cfg.weekly_budget:
            raise BudgetExceeded("over")

    def image(self, prompt, lora_url=None, safety=True, setup=False):
        from ofm.media import GenerationError

        self.calls.append(("image", prompt, lora_url, safety))
        if self.fail_next:
            self.fail_next -= 1
            raise GenerationError("boom")
        self.db.add_cost(("setup:" if setup else "") + "image", self.cfg.estimates["image"])
        flagged = self.flag_next > 0
        self.flag_next = max(0, self.flag_next - 1)
        return f"https://fal.media/img{len(self.calls)}.jpg", flagged

    def edit(self, image_url, prompt, setup=False):
        self.calls.append(("edit", prompt, image_url))
        return f"https://fal.media/edit{len(self.calls)}.jpg"

    def video(self, image_url, motion_prompt):
        self.calls.append(("video", motion_prompt, image_url))
        self.db.add_cost("video", self.cfg.estimates["video"])
        return f"https://fal.media/vid{len(self.calls)}.mp4"

    def upload(self, path):
        self.calls.append(("upload", str(path)))
        return "https://fal.media/dataset.zip"

    def train_lora(self, zip_url, trigger_word):
        self.calls.append(("train", zip_url, trigger_word))
        return "https://fal.media/lora.safetensors"


class FakeStorage:
    def __init__(self):
        self.uploads = []
        self.deleted = []

    def delete(self, public_url):
        self.deleted.append(public_url)

    def upload(self, path, post_id, source_url=None):
        self.uploads.append((str(path), post_id))
        return f"https://cdn.example/{post_id}{Path(path).suffix}"


class FakeBuffer:
    def __init__(self):
        self.created = []
        self.fail_with = None

    def create_post(self, data):
        from ofm.buffer import BufferError

        if self.fail_with:
            raise BufferError(self.fail_with)
        self.created.append(data)
        return f"buf{len(self.created)}"


class FakeClaude:
    """Mimics client.beta.messages.stream(...) for plans and .create(...) for chat replies."""

    def __init__(self, make_items=None, stop_reason="end_turn"):
        self.requests = []
        self.make_items = make_items
        self.stop_reason = stop_reason
        self.chat_replies = []
        self.chat_requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream, create=self._create))

    def _create(self, **kwargs):
        self.chat_requests.append(kwargs)
        reply = {"reply": "hey you 😊 what are you up to tonight?", "offer_media_uuid": "", "offer_price_usd": 0,
                 "escalate": False, "escalate_reason": "", "fan_request": ""}
        if self.chat_replies:
            reply.update(self.chat_replies.pop(0))
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=json.dumps(reply))],
            usage=SimpleNamespace(input_tokens=3000, output_tokens=300),
        )

    @contextmanager
    def _stream(self, **kwargs):
        self.requests.append(kwargs)
        n = len(json.loads(kwargs["messages"][0]["content"].split("\n")[1]))
        items = self.make_items(n) if self.make_items else default_items(n)
        message = SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=json.dumps({"items": items}))],
            usage=SimpleNamespace(input_tokens=2000, output_tokens=8000),
        )
        yield SimpleNamespace(get_final_message=lambda: message)


class FakeFanvue:
    """In-memory stand-in for ofm.fanvue.Fanvue: records uploads, posts and messages."""

    def __init__(self, me_uuid="me-1"):
        self.connected = True
        self.me_uuid = me_uuid
        self.uploads, self.posts, self.sent, self.vault = [], [], [], []
        self.chats = []        # what unread_chats() returns
        self.history = {}      # fan uuid -> messages
        self.read = []

    def me(self):
        return {"uuid": self.me_uuid, "handle": "mia"}

    def upload(self, path, media_type, name=None):
        self.uploads.append((str(path), media_type))
        return f"media-{len(self.uploads)}"

    def wait_ready(self, media_uuid, timeout=180, every=5):
        return True

    def create_post(self, text, media_uuids, publish_at=None, price_cents=None, audience="subscribers"):
        self.posts.append({"text": text, "media": list(media_uuids), "publish_at": publish_at, "price": price_cents})
        return f"post-{len(self.posts)}"

    def add_to_vault(self, folder, media_uuids):
        self.vault += list(media_uuids)

    def unread_chats(self, size=20):
        return list(self.chats)

    def messages(self, fan_uuid, size=20, mark_read=False):
        if mark_read:
            self.read.append(fan_uuid)
        return list(self.history.get(fan_uuid, []))

    def send_message(self, fan_uuid, text, media_uuids=None, price_cents=None):
        self.sent.append({"fan": fan_uuid, "text": text, "media": media_uuids, "price": price_cents})
        return f"msg-{len(self.sent)}"

    def fan_says(self, fan_uuid, text, msg_uuid, top=False, name="Jake"):
        """Queue an unread chat where the fan's last message is `text`."""
        self.history.setdefault(fan_uuid, []).append(
            {"uuid": msg_uuid, "text": text, "sentAt": msg_uuid, "sender": {"uuid": fan_uuid}})
        self.chats = [c for c in self.chats if c["user"]["uuid"] != fan_uuid] + [{
            "user": {"uuid": fan_uuid, "handle": name.lower(), "displayName": name, "isTopSpender": top},
            "lastMessage": {"uuid": msg_uuid, "text": text, "senderUuid": fan_uuid},
        }]


def default_items(n):
    return [
        {
            "slot": i,
            "idea": f"Ιδέα {i}",
            "image_prompt": f"sunny terrace, white linen dress, scene {i}",
            "motion_prompt": "she turns towards the camera and smiles",
            "caption": f"Golden hour again {i}",
            "hashtags": ["travel", "greece"],
        }
        for i in range(n)
    ]


@pytest.fixture
def cfg(tmp_path):
    env = {"TELEGRAM_OWNER_ID": str(OWNER), "BUFFER_CHANNEL_INSTAGRAM": "ch_ig", "BUFFER_CHANNEL_TIKTOK": "ch_tt",
           "BUFFER_CHANNEL_YOUTUBE": "ch_yt", "BUFFER_CHANNEL_X": "ch_x", "OFM_DATA_DIR": str(tmp_path / "data")}
    return load_config(ROOT / "persona.yaml", env=env)


@pytest.fixture
def fake_download(monkeypatch):
    def download(url, dest):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x")
        return dest

    monkeypatch.setattr(jobs, "download", download)
    monkeypatch.setattr(onboarding, "download", download)
    return download


@pytest.fixture
def fv_app(app):
    app.fanvue = FakeFanvue()
    return app


@pytest.fixture
def app(cfg, fake_download):
    db = DB(":memory:")
    a = App(cfg, db=db, tg=FakeTelegram(), media=FakeMedia(cfg, db), storage=FakeStorage(),
            buffer=FakeBuffer(), claude=FakeClaude())
    db.kv_set("lora_url", "https://fal.media/lora.safetensors")
    return a
