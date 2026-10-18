"""Put the API keys into the right .env files, without an editor (standard library only).

    python3 scripts/keys.py sienna          # asks only for what is missing or looks wrong
    python3 scripts/keys.py sienna --all    # asks for every key again (to replace them)

Asks for each key (hidden while you paste), writes the shared keys to .env and the bot token
to personas/sienna/.env, then finds your Telegram ID by itself once you have sent "hi" to the bot.
A bot token pasted into TELEGRAM_OWNER_ID by mistake is moved to where it belongs.
"""

import getpass
import json
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERSONAS = ROOT / "personas"

# key, which file, what to ask, what it looks like, can be left empty
KEYS = [
    ("GROQ_API_KEY", "shared", "Groq key (console.groq.com/keys)", r"gsk_\S{20,}", False),
    ("FAL_KEY", "shared", "fal key (fal.ai/dashboard/keys)", r"\S+:\S{16,}", False),
    ("TELEGRAM_BOT_TOKEN", "persona", "Token του bot (@BotFather)", r"\d{5,}:[\w-]{30,}", False),
    ("BUFFER_API_KEY", "shared", "Buffer API key (Enter για αργότερα)", r"\S{10,}", True),
]


def read_env(path):
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def write_env(path, updates):
    """Replace KEY=... lines in place (comments stay), append keys that are missing."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    done = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and key in updates:
            lines[i] = f"{key}={updates[key]}"
            done.add(key)
    lines += [f"{key}={value}" for key, value in updates.items() if key not in done]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


def telegram_ids(token):
    """Who has written to the bot, as {user id: name}. ValueError if Telegram refuses the token."""
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise ValueError(f"το Telegram δεν δέχεται το token ({e.code})") from None
    except urllib.error.URLError as e:
        raise ValueError(f"δεν απαντάει το Telegram ({e.reason})") from None
    seen = {}
    for update in data.get("result", []):
        sender = (update.get("message") or {}).get("from") or {}
        if sender.get("id") and not sender.get("is_bot"):
            seen[sender["id"]] = sender.get("username") or sender.get("first_name") or ""
    return seen


def ask_keys(current, ask, say, everything=False):
    updates = {"shared": {}, "persona": {}}
    for key, where, label, pattern, optional in KEYS:
        have = current[where].get(key, "")
        if not everything and (re.fullmatch(pattern, have) or (optional and not have)):
            continue
        state = "✅ υπάρχει, Enter για να μείνει" if have else "κενό"
        while True:
            value = ask(f"{label} [{state}]: ").strip()
            if not value:
                if have or optional:
                    break
                say("  Χρειάζεται. Επικόλλησέ το (Cmd+V) και πάτα Enter.")
                continue
            if re.fullmatch(pattern, value):
                updates[where][key] = value
                say(f"  ✅ {value[:6]}…{value[-4:]}")
                break
            say("  ❌ Δεν μοιάζει με αυτό το κλειδί. Μήπως επικόλλησες άλλο; Ξαναδοκίμασε.")
    return updates


def find_owner(token, ask, say, fetch):
    for _ in range(3):
        ask("Στείλε «hi» στο bot σου στο Telegram και μετά πάτα Enter εδώ: ")
        try:
            seen = fetch(token)
        except ValueError as e:
            say(f"  ❌ {e}. Έλεγξε το token και ξανατρέξε το script.")
            return ""
        if len(seen) == 1:
            user_id, name = next(iter(seen.items()))
            say(f"  ✅ Telegram ID {user_id} ({name})")
            return str(user_id)
        if len(seen) > 1:
            people = list(seen.items())
            for n, (user_id, name) in enumerate(people, 1):
                say(f"  {n}. {name} ({user_id})")
            choice = ask("Ποιος είσαι εσύ; Γράψε τον αριθμό: ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(people):
                return str(people[int(choice) - 1][0])
            continue
        say("  Δεν βρήκα μήνυμα ακόμα.")
    say("  Δεν βρέθηκε. Ξανατρέξε το script αφού στείλεις «hi» στο bot.")
    return ""


def main(argv, ask=getpass.getpass, say=print, fetch=telegram_ids):
    everything = "--all" in argv
    names = [a for a in argv if a != "--all"]
    if len(names) != 1 or not (PERSONAS / names[0] / "persona.yaml").exists():
        sys.exit("Χρήση: python3 scripts/keys.py sienna  (πρώτα: python3 scripts/new_persona.py sienna)")
    slug = names[0]
    files = {"shared": ROOT / ".env", "persona": PERSONAS / slug / ".env"}
    if not files["shared"].exists():
        shutil.copy(ROOT / ".env.example", files["shared"])
    current = {where: read_env(path) for where, path in files.items()}
    moved = {}
    misplaced = current["shared"].get("TELEGRAM_OWNER_ID", "")
    if re.fullmatch(KEYS[2][3], misplaced) and not current["persona"].get("TELEGRAM_BOT_TOKEN"):
        current["persona"]["TELEGRAM_BOT_TOKEN"] = moved["TELEGRAM_BOT_TOKEN"] = misplaced
        say("✅ Το token του bot ήταν στο TELEGRAM_OWNER_ID. Το έβαλα στη σωστή θέση.")

    say("Επικόλλησε κάθε κλειδί με Cmd+V και πάτα Enter. Δεν φαίνεται όσο το επικολλάς, είναι κανονικό.\n")
    updates = ask_keys(current, ask, say, everything)
    updates["persona"] = {**moved, **updates["persona"]}

    owner = current["shared"].get("TELEGRAM_OWNER_ID", "")
    if not owner.isdigit():  # empty, or something else pasted there by mistake
        token = updates["persona"].get("TELEGRAM_BOT_TOKEN") or current["persona"].get("TELEGRAM_BOT_TOKEN")
        updates["shared"]["TELEGRAM_OWNER_ID"] = find_owner(token, ask, say, fetch)

    for where, path in files.items():
        if updates[where]:
            write_env(path, updates[where])
    say(f"\nΑποθηκεύτηκαν. Επόμενο: docker compose run --rm {slug} python -m ofm check")


if __name__ == "__main__":
    main(sys.argv[1:])
