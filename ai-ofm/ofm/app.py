import logging

from .buffer import Buffer
from .db import DB
from .media import Media
from .storage import SourceUrlStorage, SupabaseStorage
from .telegram import Telegram

log = logging.getLogger("ofm")


class App:
    """Wires config, database and API clients together; tests pass fakes in."""

    def __init__(self, cfg, db=None, tg=None, media=None, storage=None, buffer=None, claude=None):
        self.cfg = cfg
        self.db = db or DB(cfg.data_dir / "ofm.sqlite3")
        token, owner = cfg.secret("TELEGRAM_BOT_TOKEN"), cfg.secret("TELEGRAM_OWNER_ID")
        self.tg = tg if tg is not None else (Telegram(token, owner) if token and owner else None)
        self.media = media or Media(cfg, self.db)
        if storage is None:
            url, key = cfg.secret("SUPABASE_URL"), cfg.secret("SUPABASE_SECRET_KEY")
            bucket = cfg.secret("SUPABASE_BUCKET") or "ofm-media"
            storage = SupabaseStorage(url, key, bucket) if url and key else SourceUrlStorage()
        self.storage = storage
        if buffer is None and cfg.secret("BUFFER_API_KEY"):
            buffer = Buffer(cfg.secret("BUFFER_API_KEY"))
        self.buffer = buffer
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

    def lora_url(self):
        return self.cfg.secret("LORA_URL") or self.db.kv_get("lora_url")

    def notify(self, text, markup=None, silent=False):
        log.info(text)
        if self.tg:
            try:
                self.tg.send(text, markup=markup, silent=silent)
            except Exception as e:  # never let a failed notification stop the loop
                log.warning("telegram: %s", e)
