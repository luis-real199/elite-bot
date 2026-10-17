import logging

import requests

from .buffer import Buffer
from .db import DB
from .fanvue import Fanvue
from .media import Media
from .storage import SourceUrlStorage, SupabaseStorage
from .telegram import Telegram

log = logging.getLogger("ofm")


class App:
    """Wires config, database and API clients together; tests pass fakes in."""

    def __init__(self, cfg, db=None, tg=None, media=None, storage=None, buffer=None, claude=None, fanvue=None):
        self.cfg = cfg
        self.db = db or DB(cfg.data_dir / "ofm.sqlite3")
        token, owner = cfg.secret("TELEGRAM_BOT_TOKEN"), cfg.secret("TELEGRAM_OWNER_ID")
        self.tg = tg if tg is not None else (Telegram(token, owner) if token and owner else None)
        self.media = media or Media(cfg, self.db)
        if storage is None:
            url, key = cfg.secret("SUPABASE_URL"), cfg.secret("SUPABASE_SECRET_KEY")
            bucket = cfg.secret("SUPABASE_BUCKET") or "ofm-media"
            storage = SupabaseStorage(url, key, bucket, prefix=f"{cfg.slug}/") if url and key else SourceUrlStorage()
        self.storage = storage
        if buffer is None and cfg.secret("BUFFER_API_KEY"):
            buffer = Buffer(cfg.secret("BUFFER_API_KEY"))
        self.buffer = buffer
        fanvue_keys = [cfg.secret(k) for k in ("FANVUE_CLIENT_ID", "FANVUE_CLIENT_SECRET", "FANVUE_REDIRECT_URI")]
        if fanvue is None and all(fanvue_keys):
            fanvue = Fanvue(*fanvue_keys, self.db)
        self.fanvue = fanvue
        self.http = requests.Session()  # plain checks such as "does this file URL still open?"
        self._claude = claude

    @property
    def claude(self):
        if self._claude is None:
            import anthropic

            self._claude = anthropic.Anthropic()
        return self._claude

    @property
    def media_dir(self):
        return self.cfg.data_dir / "media"

    @property
    def setup_dir(self):
        return self.cfg.data_dir / "setup"

    @property
    def lora_backup(self):
        return self.setup_dir / "lora.safetensors"

    def lora_url(self):
        return self.cfg.secret("LORA_URL") or self.db.kv_get("lora_url")

    def reference_urls(self):
        """The locked reference photos (face first) that keep her identity on every social post."""
        return self.db.kv_get("reference_urls") or []

    def notify(self, text, markup=None, silent=False):
        log.info(text)
        if self.tg:
            try:
                self.tg.send(text, markup=markup, silent=silent)
            except Exception as e:  # never let a failed notification stop the loop
                log.warning("telegram: %s", e)
