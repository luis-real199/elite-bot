"""Fanvue's official API (api.fanvue.com): OAuth 2.0 with PKCE, media upload, posts and chats.

Endpoints follow Fanvue's docs (API version 2025-06-26) as used by their own repos
(fanvue/fanvue-app-starter, fanvue/fanvue-chatbot-example, fanvue/plugins).
"""

import base64
import hashlib
import secrets
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

AUTH_URL = "https://auth.fanvue.com/oauth2/auth"
TOKEN_URL = "https://auth.fanvue.com/oauth2/token"
API_URL = "https://api.fanvue.com"
API_VERSION = "2025-06-26"
SCOPES = (
    "openid offline_access offline read:self read:chat write:chat "
    "read:post write:post read:media write:media"
)
PART_SIZE = 10 * 1024 * 1024
TOKEN_KEY = "fanvue_token"
PKCE_KEY = "fanvue_pkce"


class FanvueError(Exception):
    pass


class FanvueAuthError(FanvueError):
    """The saved login is missing or can no longer be refreshed: run /fanvue_login again."""


def _b64url(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


class Fanvue:
    def __init__(self, client_id, client_secret, redirect_uri, db, session=None, sleep=time.sleep, clock=time.time):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.db = db
        self.http = session or requests.Session()
        self.sleep = sleep
        self.clock = clock

    # ---------- login ----------

    @property
    def connected(self):
        return bool(self.db.kv_get(TOKEN_KEY))

    def login_url(self):
        verifier = _b64url(secrets.token_bytes(32))
        challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
        state = secrets.token_hex(16)
        self.db.kv_set(PKCE_KEY, {"verifier": verifier, "state": state})
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": SCOPES,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "login",
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    def finish_login(self, redirected_url):
        """Exchange the code from the URL the browser landed on after logging in."""
        query = parse_qs(urlparse(redirected_url.strip()).query)
        code, state = (query.get("code") or [None])[0], (query.get("state") or [None])[0]
        pkce = self.db.kv_get(PKCE_KEY)
        if not code:
            raise FanvueAuthError("Δεν βρέθηκε code στο link. Αντέγραψε ολόκληρη τη διεύθυνση μετά το login.")
        if not pkce or state != pkce["state"]:
            raise FanvueAuthError("Το link δεν ταιριάζει με το τελευταίο /fanvue_login. Ξεκίνα ξανά.")
        self._token({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": pkce["verifier"],
        })
        self.db.kv_set(PKCE_KEY, None)
        me = self.me()
        self.db.kv_set("fanvue_me", {"uuid": me.get("uuid"), "handle": me.get("handle")})
        return me

    def _token(self, data):
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        try:
            r = self.http.post(TOKEN_URL, data=data, headers={"Authorization": f"Basic {basic}"}, timeout=30)
        except requests.RequestException as e:
            raise FanvueError(f"token: {type(e).__name__}") from None
        if r.status_code != 200:
            raise FanvueAuthError(f"Fanvue login: HTTP {r.status_code} {r.text[:200]}")
        body = r.json()
        previous = self.db.kv_get(TOKEN_KEY) or {}
        token = {
            "access_token": body["access_token"],
            # Fanvue rotates refresh tokens: always keep the newest one
            "refresh_token": body.get("refresh_token") or previous.get("refresh_token"),
            "expires_at": self.clock() + int(body.get("expires_in") or 3600),
        }
        self.db.kv_set(TOKEN_KEY, token)
        return token

    def _access_token(self, force_refresh=False):
        token = self.db.kv_get(TOKEN_KEY)
        if not token:
            raise FanvueAuthError("Το Fanvue δεν έχει συνδεθεί. Στείλε /fanvue_login.")
        if force_refresh or self.clock() > token["expires_at"] - 60:
            if not token.get("refresh_token"):
                raise FanvueAuthError("Έληξε η σύνδεση με το Fanvue. Στείλε /fanvue_login.")
            token = self._token({
                "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"],
                "client_id": self.client_id,
            })
        return token["access_token"]

    # ---------- requests ----------

    def request(self, method, path, retry=True, **kwargs):
        headers = {"Authorization": f"Bearer {self._access_token()}", "X-Fanvue-API-Version": API_VERSION}
        try:
            r = self.http.request(method, API_URL + path, headers=headers, timeout=60, **kwargs)
        except requests.RequestException as e:
            raise FanvueError(f"{method} {path}: {type(e).__name__}") from None
        if r.status_code == 401 and retry:
            self._access_token(force_refresh=True)
            return self.request(method, path, retry=False, **kwargs)
        if r.status_code == 429 and retry:
            try:
                wait = int(r.headers.get("Retry-After") or 30)
            except ValueError:
                wait = 30
            self.sleep(min(wait, 120))
            return self.request(method, path, retry=False, **kwargs)
        if r.status_code >= 300:
            raise FanvueError(f"{method} {path}: HTTP {r.status_code} {r.text[:300]}")
        if not r.content:
            return {}
        try:
            return r.json()
        except ValueError:
            return r.text

    def me(self):
        return self.request("GET", "/users/me")

    # ---------- media and posts ----------

    def upload(self, path, media_type, name=None):
        """Multipart upload: create session, PUT each part to its signed URL, complete. Returns the media UUID."""
        path = Path(path)
        session = self.request("POST", "/media/uploads", json={
            "name": name or path.stem,
            "filename": path.name,
            "mediaType": media_type,
            "sizeBytes": path.stat().st_size,
        })
        upload_id, media_uuid = session["uploadId"], session["mediaUuid"]
        part_size = int(session.get("partSize") or PART_SIZE)
        parts = []
        with open(path, "rb") as f:
            number = 1
            while True:
                chunk = f.read(part_size)
                if not chunk and parts:
                    break
                signed = self.request("GET", f"/media/uploads/{upload_id}/parts/{number}/url")
                url = signed if isinstance(signed, str) else (signed.get("url") or signed.get("uploadUrl") or signed.get("signedUrl"))
                if not url:
                    raise FanvueError(f"Χωρίς URL για το κομμάτι {number}: {signed}")
                try:
                    r = self.http.put(url, data=chunk, timeout=300)
                except requests.RequestException as e:
                    raise FanvueError(f"upload part {number}: {type(e).__name__}") from None
                if r.status_code >= 300:
                    raise FanvueError(f"upload part {number}: HTTP {r.status_code}")
                parts.append({"PartNumber": number, "ETag": r.headers.get("ETag", "")})
                if len(chunk) < part_size:
                    break
                number += 1
        self.request("PATCH", f"/media/uploads/{upload_id}", json={"parts": parts})
        return media_uuid

    def wait_ready(self, media_uuid, timeout=180, every=5):
        waited = 0
        while True:
            status = (self.request("GET", f"/media/{media_uuid}") or {}).get("status")
            if status == "ready":
                return True
            if status == "error":
                raise FanvueError(f"Το Fanvue απέρριψε το αρχείο {media_uuid}")
            if waited >= timeout:
                return False
            self.sleep(every)
            waited += every

    def create_post(self, text, media_uuids, publish_at=None, price_cents=None, audience="subscribers"):
        body = {"text": text, "mediaUuids": list(media_uuids), "audience": audience}
        if publish_at:
            body["publishAt"] = publish_at.isoformat()
        if price_cents:
            body["price"] = int(price_cents)
        result = self.request("POST", "/posts", json=body) or {}
        return result.get("uuid") if isinstance(result, dict) else None

    def add_to_vault(self, folder, media_uuids):
        """Best effort: the vault only organises media, posts and messages work without it."""
        try:
            self.request("POST", "/vault/folders", json={"name": folder})
        except FanvueError:
            pass  # usually "already exists"
        self.request("POST", f"/vault/folders/{folder}/media", json={"mediaUuids": list(media_uuids)})

    # ---------- chats ----------

    def unread_chats(self, size=20):
        result = self.request("GET", "/chats", params={"filter": "unread", "sortBy": "most_recent_messages", "size": size})
        return (result or {}).get("data") or []

    def messages(self, fan_uuid, size=20, mark_read=False):
        result = self.request(
            "GET", f"/chats/{fan_uuid}/messages",
            params={"size": size, "markAsRead": "true" if mark_read else "false"},
        )
        items = (result or {}).get("data") or []
        return sorted(items, key=lambda m: m.get("sentAt") or "")

    def send_message(self, fan_uuid, text, media_uuids=None, price_cents=None):
        body = {"text": text}
        if media_uuids:
            body["mediaUuids"] = list(media_uuids)
            if price_cents:
                body["price"] = int(price_cents)
        result = self.request("POST", f"/chats/{fan_uuid}/message", json=body) or {}
        return result.get("messageUuid") if isinstance(result, dict) else None
