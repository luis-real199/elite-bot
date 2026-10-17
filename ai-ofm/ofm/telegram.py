"""Minimal Telegram Bot API client (long polling, no webhook needed)."""

import json
from pathlib import Path

import requests

CAPTION_LIMIT = 1024


class TelegramError(Exception):
    pass


def keyboard(rows):
    """rows: [[(text, callback_data), ...], ...]"""
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}


def clip(text, limit=CAPTION_LIMIT):
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Telegram:
    def __init__(self, token, owner_id, session=None):
        self.base = f"https://api.telegram.org/bot{token}/"
        self.owner_id = int(owner_id) if owner_id else None
        self.http = session or requests.Session()

    def call(self, method, files=None, http_timeout=60, **params):
        params = {k: v for k, v in params.items() if v is not None}
        try:
            if files:
                data = {k: json.dumps(v) if isinstance(v, (dict, list, bool)) else v for k, v in params.items()}
                r = self.http.post(self.base + method, data=data, files=files, timeout=http_timeout)
            else:
                r = self.http.post(self.base + method, json=params, timeout=http_timeout)
        except requests.RequestException as e:
            # requests puts the URL, and so the bot token, in its messages: keep it out of logs
            raise TelegramError(f"{method}: {type(e).__name__}") from None
        try:
            body = r.json()
        except ValueError:
            raise TelegramError(f"{method}: HTTP {r.status_code}")
        if not body.get("ok"):
            raise TelegramError(f"{method}: {body.get('description')}")
        return body["result"]

    def send(self, text, markup=None, silent=False):
        return self.call(
            "sendMessage", chat_id=self.owner_id, text=clip(text, 4096),
            reply_markup=markup, disable_notification=silent,
        )

    def send_media(self, path, caption="", markup=None, silent=False, as_document=False):
        path = Path(path)
        if as_document:
            method, field = "sendDocument", "document"
        elif path.suffix.lower() in (".mp4", ".mov", ".webm"):
            method, field = "sendVideo", "video"
        else:
            method, field = "sendPhoto", "photo"
        with open(path, "rb") as f:
            return self.call(
                method, files={field: (path.name, f)}, http_timeout=300, chat_id=self.owner_id,
                caption=clip(caption), reply_markup=markup, disable_notification=silent,
            )

    def set_buttons(self, message_id, markup):
        try:
            self.call("editMessageReplyMarkup", chat_id=self.owner_id, message_id=message_id, reply_markup=markup)
        except TelegramError:
            pass  # message too old or unchanged; the database is the source of truth

    def answer(self, callback_id, text=""):
        try:
            self.call("answerCallbackQuery", callback_query_id=callback_id, text=text)
        except TelegramError:
            pass

    def updates(self, offset=None, timeout=20):
        return self.call("getUpdates", http_timeout=timeout + 15, offset=offset, timeout=timeout)

    def is_owner(self, update):
        sender = (update.get("callback_query") or update.get("message") or {}).get("from") or {}
        return self.owner_id is not None and sender.get("id") == self.owner_id
