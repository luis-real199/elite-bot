"""Buffer GraphQL API: schedules approved posts on Instagram, TikTok, YouTube and X."""

import json
import re
from datetime import timezone

import requests

API_URL = "https://api.buffer.com"

CHANNEL_ENV = {
    "instagram_reel": "BUFFER_CHANNEL_INSTAGRAM",
    "instagram_story": "BUFFER_CHANNEL_INSTAGRAM",
    "instagram_feed": "BUFFER_CHANNEL_INSTAGRAM",
    "tiktok": "BUFFER_CHANNEL_TIKTOK",
    "youtube_short": "BUFFER_CHANNEL_YOUTUBE",
    "x": "BUFFER_CHANNEL_X",
}

INSTAGRAM_TYPE = {"instagram_reel": "reel", "instagram_story": "story", "instagram_feed": "post"}


class BufferError(Exception):
    pass


class Enum(str):
    """A bare GraphQL enum value, written without quotes."""


def literal(value):
    if isinstance(value, Enum):
        return str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float, str)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(literal(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}: {literal(v)}" for k, v in value.items()) + "}"
    raise TypeError(f"cannot encode {type(value).__name__}")


def post_text(post, target):
    tags = " ".join(post["hashtags"])
    text = f"{post['caption']}\n\n{tags}".strip()
    if target == "x" and len(text) > 280:
        text = text[:279] + "…"
    return text


def post_input(post, target, channel_id, media_url, due_at):
    is_video = post["kind"] == "video"
    data = {
        "text": post_text(post, target),
        "channelId": channel_id,
        "schedulingType": Enum("automatic"),
        "mode": Enum("customScheduled"),
        "dueAt": due_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "assets": [{"video": {"url": media_url}} if is_video else {"image": {"url": media_url}}],
    }
    if target in INSTAGRAM_TYPE:
        instagram = {"type": Enum(INSTAGRAM_TYPE[target])}
        if target == "instagram_reel":
            instagram["shouldShareToFeed"] = True
        data["metadata"] = {"instagram": instagram}
    elif target == "youtube_short":
        title = re.sub(r"#\w+", "", post["caption"]).strip()[:90] or "New short"
        data["metadata"] = {"youtube": {"title": title}}
    return data


def create_post_mutation(data):
    return (
        "mutation { createPost(input: " + literal(data) + ") { "
        "__typename ... on PostActionSuccess { post { id } } ... on MutationError { message } } }"
    )


class Buffer:
    def __init__(self, api_key, session=None):
        self.api_key = api_key
        self.http = session or requests.Session()

    def query(self, query):
        r = self.http.post(
            API_URL,
            json={"query": query},
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            timeout=60,
        )
        if r.status_code == 401:
            raise BufferError("Λάθος BUFFER_API_KEY (401)")
        try:
            body = r.json()
        except ValueError:
            raise BufferError(f"HTTP {r.status_code}: {r.text[:200]}")
        if body.get("errors"):
            raise BufferError("; ".join(e.get("message", str(e)) for e in body["errors"]))
        return body.get("data") or {}

    def create_post(self, data):
        result = self.query(create_post_mutation(data)).get("createPost") or {}
        if result.get("post"):
            return result["post"]["id"]
        raise BufferError(result.get("message") or f"Άγνωστη απάντηση: {result}")

    def channels(self):
        orgs = self.query("query { account { organizations { id name } } }")["account"]["organizations"]
        found = []
        for org in orgs:
            q = "query { channels(input: {organizationId: " + literal(org["id"]) + "}) { id name service } }"
            for ch in self.query(q).get("channels") or []:
                found.append({**ch, "organization": org["name"]})
        return found
