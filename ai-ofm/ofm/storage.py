"""Public hosting for approved social media files (Buffer needs a URL that stays up until the post goes out)."""

import mimetypes
import secrets
from pathlib import Path

import requests


class StorageError(Exception):
    pass


class SupabaseStorage:
    def __init__(self, url, key, bucket, session=None, prefix=""):
        self.url = url.rstrip("/")
        self.key = key
        self.bucket = bucket
        self.prefix = prefix  # one folder per persona, since post ids repeat across personas
        self.http = session or requests.Session()

    def upload(self, path, post_id, source_url=None):
        path = Path(path)
        name = f"{self.prefix}{post_id}-{secrets.token_hex(8)}{path.suffix}"
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            r = self.http.post(
                f"{self.url}/storage/v1/object/{self.bucket}/{name}",
                data=f,
                headers={
                    "Authorization": f"Bearer {self.key}",
                    "apikey": self.key,
                    "Content-Type": mime,
                    "x-upsert": "true",
                },
                timeout=300,
            )
        if r.status_code >= 300:
            raise StorageError(f"Supabase upload HTTP {r.status_code}: {r.text[:200]}")
        return f"{self.url}/storage/v1/object/public/{self.bucket}/{name}"

    def delete(self, public_url):
        prefix = f"{self.url}/storage/v1/object/public/{self.bucket}/"
        if not public_url.startswith(prefix):
            return
        r = self.http.delete(
            f"{self.url}/storage/v1/object/{self.bucket}",
            json={"prefixes": [public_url[len(prefix):]]},
            headers={"Authorization": f"Bearer {self.key}", "apikey": self.key},
            timeout=60,
        )
        if r.status_code >= 300:
            raise StorageError(f"Supabase delete HTTP {r.status_code}: {r.text[:200]}")


class FalStorage:
    """Default: host the final file (with the hook burned in) on fal's CDN for 30 days.
    Free Supabase projects pause after a week without activity and their public links stop working."""

    def __init__(self, media):
        self.media = media

    def upload(self, path, post_id, source_url=None):
        try:
            return self.media.upload(path, expires_in="30d")
        except Exception as e:
            raise StorageError(f"fal upload: {e}") from e

    def delete(self, public_url):
        pass  # expires on its own
