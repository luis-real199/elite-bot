import importlib.util
import os
import shutil
from datetime import datetime

import yaml

from ofm import jobs, planner
from ofm.config import load_config
from ofm.storage import SupabaseStorage

from conftest import ROOT


def load_script(tmp_path):
    spec = importlib.util.spec_from_file_location("new_persona", ROOT / "scripts" / "new_persona.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    shutil.copy(ROOT / "persona.example.yaml", tmp_path / "persona.example.yaml")
    module.ROOT, module.PERSONAS = tmp_path, tmp_path / "personas"
    return module


def test_new_persona_creates_files_and_compose(tmp_path):
    script = load_script(tmp_path)
    script.main(["ava"])
    persona = yaml.safe_load((tmp_path / "personas/ava/persona.yaml").read_text(encoding="utf-8"))["persona"]
    example = yaml.safe_load((ROOT / "persona.example.yaml").read_text(encoding="utf-8"))["persona"]
    assert persona["name"] == "Ava" and persona["trigger_word"] != example["trigger_word"]
    assert "TELEGRAM_BOT_TOKEN=" in (tmp_path / "personas/ava/.env").read_text(encoding="utf-8")

    (tmp_path / "personas/ava/persona.yaml").write_text("edited", encoding="utf-8")
    script.main(["mia"])
    assert (tmp_path / "personas/ava/persona.yaml").read_text(encoding="utf-8") == "edited"
    compose = yaml.safe_load((tmp_path / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    assert sorted(compose) == ["ava", "mia"]
    assert compose["mia"]["env_file"] == [".env", "personas/mia/.env"]
    assert compose["mia"]["volumes"] == ["./personas/mia:/app/persona"]
    assert compose["mia"]["environment"]["OFM_PERSONA"] == "mia"


def test_bad_names_are_refused(tmp_path):
    script = load_script(tmp_path)
    for bad in (["Ava"], ["../x"], []):
        try:
            script.main(bad)
        except SystemExit:
            continue
        raise AssertionError(f"accepted {bad}")


def test_config_lives_next_to_the_persona(tmp_path):
    folder = tmp_path / "personas" / "ava"
    folder.mkdir(parents=True)
    shutil.copy(ROOT / "persona.example.yaml", folder / "persona.yaml")
    cfg = load_config(folder / "persona.yaml", env={})
    assert cfg.slug == "ava" and cfg.data_dir == folder / "data"
    assert load_config(folder / "persona.yaml", env={"OFM_PERSONA": "x", "OFM_DATA_DIR": "/d"}).slug == "x"


def test_cli_reads_the_personas_own_keys_first(tmp_path, monkeypatch, capsys):
    from ofm.__main__ import main

    folder = tmp_path / "personas" / "ava"
    folder.mkdir(parents=True)
    shutil.copy(ROOT / "persona.example.yaml", folder / "persona.yaml")
    (folder / ".env").write_text("BUFFER_CHANNEL_X=ava-x\n", encoding="utf-8")
    (tmp_path / ".env").write_text("BUFFER_CHANNEL_X=shared-x\nFAL_KEY=shared-fal\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(os, "environ", {})
    main(["--persona", "ava", "check"])
    out = capsys.readouterr().out
    assert "Περσόνα [ava]" in out
    assert os.environ["BUFFER_CHANNEL_X"] == "ava-x" and os.environ["FAL_KEY"] == "shared-fal"
    assert (folder / "data" / "ofm.sqlite3").exists()


def test_backup_instagram_gets_its_own_caption_later(app):
    app.cfg.env["BUFFER_CHANNEL_INSTAGRAM_BACKUP"] = "ch_ig2"
    for slot in app.cfg.slots:
        if slot.kind == "video":
            slot.targets = ["instagram_reel", "instagram_backup", "tiktok", "youtube_short"]

    from conftest import FakeClaude, default_items

    def items(n):
        out = default_items(n)
        for item in out:
            item["alt_caption"] = "same vibe, different words"
        return out

    app._claude = FakeClaude(items)
    planner.plan_ahead(app, datetime(2026, 10, 18, 18, 5, tzinfo=app.cfg.tz))
    reel = next(p for p in app.db.posts("planned") if p["kind"] == "video")
    assert reel["alt_caption"] == "same vibe, different words"
    story = next(p for p in app.db.posts("planned") if p["kind"] == "image" and p.social_targets)
    assert story["alt_caption"] == ""

    jobs.generate_pending(app, datetime(2026, 10, 18, 19, 0, tzinfo=app.cfg.tz), limit=100)
    jobs.send_reviews(app)
    jobs.review_action(app, "a", reel["id"])
    jobs.publish_due(app, datetime(2026, 10, 19, 10, 0, tzinfo=app.cfg.tz))
    main, backup = [c for c in app.buffer.created if c["channelId"] in ("ch_ig", "ch_ig2")]
    assert main["text"].startswith("Golden hour") and backup["text"].startswith("same vibe, different words")
    assert backup["metadata"] == {"instagram": {"type": "reel", "shouldShareToFeed": True}}
    assert main["dueAt"] == "2026-10-19T23:00:00.000Z" and backup["dueAt"] == "2026-10-20T02:00:00.000Z"


def test_each_persona_uploads_into_its_own_folder(tmp_path):
    class Session:
        def post(self, url, **kw):
            self.url = url
            return type("R", (), {"status_code": 200, "text": ""})()

    media = tmp_path / "1.jpg"
    media.write_bytes(b"x")
    storage = SupabaseStorage("https://x.supabase.co", "k", "ofm-media", session=Session(), prefix="ava/")
    url = storage.upload(media, 1)
    assert "/storage/v1/object/ofm-media/ava/1-" in storage.http.url
    assert url.startswith("https://x.supabase.co/storage/v1/object/public/ofm-media/ava/1-")
