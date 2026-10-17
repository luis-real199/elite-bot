import argparse
import logging
import sys
from datetime import datetime

from . import bot, jobs, onboarding, planner
from .app import App
from .config import ENV_KEYS, ConfigError, load_config, load_dotenv
from .telegram import Telegram


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m ofm", description="AI OFM: πλάνο, generation, έγκριση, αποστολή")
    parser.add_argument("--config", help="persona.yaml (default: persona.yaml)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="τρέχει συνέχεια: Telegram bot + όλες οι προγραμματισμένες δουλειές")
    sub.add_parser("check", help="ελέγχει ρυθμίσεις και κλειδιά")
    sub.add_parser("telegram-id", help="δείχνει το Telegram ID σου (στείλε πρώτα ένα μήνυμα στο bot)")
    sub.add_parser("buffer-channels", help="δείχνει τα κανάλια του Buffer για το .env")
    sub.add_parser("plan", help="φτιάχνει πλάνο για τις επόμενες 7 μέρες")
    gen = sub.add_parser("generate", help="φτιάχνει εικόνες/βίντεο για τα posts του πλάνου")
    gen.add_argument("--limit", type=int, default=100)
    sub.add_parser("review", help="στέλνει στο Telegram όσα είναι έτοιμα")
    pub = sub.add_parser("publish", help="στέλνει στο Buffer όσα εγκρίθηκαν")
    pub.add_argument("--dry-run", action="store_true", help="δείχνει τι θα σταλεί χωρίς να στείλει")
    sub.add_parser("fanvue", help="στέλνει στο Telegram τα εγκεκριμένα για Fanvue")
    sub.add_parser("report", help="εβδομαδιαία αναφορά")
    sub.add_parser("status", help="κατάσταση")
    faces = sub.add_parser("faces", help="υποψήφια πρόσωπα")
    faces.add_argument("-n", type=int, default=6)
    pick = sub.add_parser("pick-face", help="διάλεξε πρόσωπο χωρίς Telegram")
    pick.add_argument("number", type=int, help="1, 2, 3...")
    sub.add_parser("dataset", help="φωτογραφίες για το LoRA από το επιλεγμένο πρόσωπο")
    sub.add_parser("train", help="εκπαίδευση LoRA")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(".env")
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        sys.exit(f"Ρυθμίσεις: {e}")
    if args.command == "telegram-id":
        return telegram_id(cfg)

    app = App(cfg)
    now = datetime.now(cfg.tz)
    command = args.command
    if command == "run":
        bot.run(app, clock=lambda: datetime.now(cfg.tz))
    elif command == "check":
        check(app)
    elif command == "buffer-channels":
        if not app.buffer:
            sys.exit("Βάλε πρώτα BUFFER_API_KEY στο .env")
        for ch in app.buffer.channels():
            print(f"{ch['service']:<12} {ch['name']:<30} {ch['id']}   ({ch['organization']})")
    elif command == "plan":
        print(planner.plan_ahead(app, now))
    elif command == "generate":
        print(f"Έγιναν {jobs.generate_pending(app, now, limit=args.limit)}")
    elif command == "review":
        print(f"Στάλθηκαν {jobs.send_reviews(app)}")
    elif command == "publish":
        previews = jobs.publish_due(app, now, dry_run=args.dry_run)
        print("\n\n".join(previews) if args.dry_run else "OK")
    elif command == "fanvue":
        print(f"Στάλθηκαν {jobs.send_fanvue_pack(app)}")
    elif command == "report":
        print(jobs.report_text(app, now))
    elif command == "status":
        print(jobs.status_text(app))
    elif command == "faces":
        for i, c in enumerate(onboarding.faces(app, args.n), 1):
            print(i, c["path"])
    elif command == "pick-face":
        print(onboarding.pick_face(app, args.number - 1)["path"])
    elif command == "dataset":
        print(f"Έγιναν {onboarding.dataset(app)}")
    elif command == "train":
        print(f"LoRA: {onboarding.train(app)}")


def check(app):
    cfg = app.cfg
    print(f"Περσόνα: {cfg.persona['name']}, {cfg.persona['age']} · {len(cfg.slots)} slots στο πρόγραμμα · "
          f"Fanvue {cfg.fanvue_per_week}/εβδομάδα · όριο ${cfg.weekly_budget}/εβδομάδα")
    for key in ENV_KEYS:
        print(f"  {'✅' if cfg.secret(key) else '—'} {key}")
    if app.tg:
        try:
            me = app.tg.call("getMe")
            print(f"Telegram bot: @{me['username']}")
        except Exception as e:
            print(f"Telegram: {e}")
    print(jobs.status_text(app))


def telegram_id(cfg):
    token = cfg.secret("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("Βάλε πρώτα TELEGRAM_BOT_TOKEN στο .env")
    seen = {}
    for update in Telegram(token, None).updates(timeout=0):
        sender = (update.get("message") or {}).get("from") or {}
        if sender.get("id"):
            seen[sender["id"]] = sender.get("username") or sender.get("first_name")
    if not seen:
        print("Δεν βρέθηκαν μηνύματα. Στείλε «hi» στο bot σου και ξανατρέξε το.")
    for user_id, name in seen.items():
        print(f"TELEGRAM_OWNER_ID={user_id}   ({name})")


if __name__ == "__main__":
    main()
