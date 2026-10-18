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
    "instagram_backup": "BUFFER_CHANNEL_INSTAGRAM_BACKUP",
    "tiktok": "BUFFER_CHANNEL_TIKTOK",
    "youtube_short": "BUFFER_CHANNEL_YOUTUBE",
    "x": "BUFFER_CHANNEL_X",
}

INSTAGRAM_TYPE = {"instagram_reel": "reel", "instagram_story": "story", "instagram_feed": "post"}


class BufferError(Exception):
    pass


def post_text(post, target):
    tags = " ".join(post["hashtags"])
    caption = post.get("alt_caption") if target == "instagram_backup" and post.get("alt_caption") else post["caption"]
    text = f"{caption}\n\n{tags}".strip()
    if target == "x" and len(text) > 280:
        text = text[:279] + "…"
    return text


def post_input(post, target, channel_id, media_url, due_at):
    is_video = post["kind"] == "video"
    data = {
        "text": post_text(post, target),
        "channelId": channel_id,
        "schedulingType": "automatic",
        "mode": "customScheduled",
        "dueAt": due_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "assets": [{"video": {"url": media_url}} if is_video else {"image": {"url": media_url}}],
    }
    if target in INSTAGRAM_TYPE or target == "instagram_backup":
        kind = INSTAGRAM_TYPE.get(target) or ("reel" if is_video else "post")
        # shouldShareToFeed is required for every Instagram type (false only makes sense for stories)
        data["metadata"] = {"instagram": {"type": kind, "shouldShareToFeed": kind != "story"}}
    elif target == "youtube_short":
        title = re.sub(r"#\w+", "", post["caption"]).strip()[:90] or "New short"
        # categoryId is required on create; 22 = People & Blogs. Realistic AI people must be flagged.
        data["metadata"] = {"youtube": {"title": title, "categoryId": "22", "madeForKids": False, "isAiGenerated": True}}
    return data


CREATE_POST = (
    "mutation CreatePost($input: CreatePostInput!) { createPost(input: $input) { "
    "__typename ... on PostActionSuccess { post { id } } ... on MutationError { message } } }"
)


def create_post_mutation(data):
    """Readable preview for --dry-run."""
    return CREATE_POST + "\nvariables: " + json.dumps({"input": data}, ensure_ascii=False)


class Buffer:
    def __init__(self, api_key, session=None):
        self.api_key = api_key
        self.http = session or requests.Session()

    def query(self, query, variables=None):
        body = {"query": query}
        if variables:
            body["variables"] = variables
        r = self.http.post(
            API_URL,
            json=body,
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
        result = self.query(CREATE_POST, {"input": data}).get("createPost") or {}
        if result.get("post"):
            return result["post"]["id"]
        raise BufferError(result.get("message") or result.get("__typename") or f"Άγνωστη απάντηση: {result}")

    def channels(self):
        orgs = self.query("query { account { organizations { id name } } }")["account"]["organizations"]
        found = []
        for org in orgs:
            q = "query { channels(input: {organizationId: " + json.dumps(org["id"]) + "}) { id name service } }"
            for ch in self.query(q).get("channels") or []:
                found.append({**ch, "organization": org["name"]})
        return found
