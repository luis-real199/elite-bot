"""Create a persona folder and regenerate docker-compose.yml (standard library only).

    python3 scripts/new_persona.py ava

Creates personas/ava/persona.yaml (from persona.example.yaml, with its own LoRA trigger word)
and personas/ava/.env (her own Telegram bot and Buffer channels), keeping files that exist.
Then writes one docker-compose service per folder in personas/.
"""

import re
import secrets
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERSONAS = ROOT / "personas"
SLUG = re.compile(r"^[a-z][a-z0-9-]{1,30}$")

PERSONA_ENV = """# Μόνο για αυτή την περσόνα. Τα κοινά κλειδιά (Claude, fal, Buffer API, Supabase, Fanvue app,
# TELEGRAM_OWNER_ID) είναι στο .env του φακέλου ai-ofm.

# Δικό της Telegram bot: @BotFather → /newbot (π.χ. "{title} bot")
TELEGRAM_BOT_TOKEN=

# Τα κανάλια της στο Buffer: docker compose run --rm {slug} python -m ofm buffer-channels
BUFFER_CHANNEL_INSTAGRAM=
BUFFER_CHANNEL_INSTAGRAM_BACKUP=
BUFFER_CHANNEL_TIKTOK=
BUFFER_CHANNEL_YOUTUBE=
BUFFER_CHANNEL_X=

# Προαιρετικό: έτοιμο LoRA
LORA_URL=
"""

SERVICE = """  {slug}:
    build: .
    image: ai-ofm
    restart: unless-stopped
    env_file:
      - .env
      - personas/{slug}/.env
    environment:
      OFM_PERSONA: {slug}
      OFM_CONFIG: /app/persona/persona.yaml
      OFM_DATA_DIR: /app/persona/data
    volumes:
      - ./personas/{slug}:/app/persona
"""


def trigger_word():
    letters = "".join(secrets.choice(string.ascii_lowercase) for _ in range(3))
    return f"{letters}{secrets.randbelow(10)}{secrets.choice(string.ascii_lowercase)}{secrets.randbelow(10)}"


def create(slug):
    folder = PERSONAS / slug
    folder.mkdir(parents=True, exist_ok=True)
    persona = folder / "persona.yaml"
    if not persona.exists():
        text = (ROOT / "persona.example.yaml").read_text(encoding="utf-8")
        text = re.sub(r'(\n  name: )"[^"]*"', rf'\1"{slug.title()}"', text, count=1)
        text = re.sub(r'(\n  trigger_word: )"[^"]*"', rf'\1"{trigger_word()}"', text, count=1)
        persona.write_text(text, encoding="utf-8")
        print(f"+ {persona.relative_to(ROOT)}  (άλλαξε όνομα, εμφάνιση, niche)")
    env = folder / ".env"
    if not env.exists():
        env.write_text(PERSONA_ENV.format(slug=slug, title=slug.title()), encoding="utf-8")
        print(f"+ {env.relative_to(ROOT)}  (βάλε το token του bot της)")


def write_compose():
    slugs = sorted(p.name for p in PERSONAS.iterdir() if (p / "persona.yaml").exists()) if PERSONAS.exists() else []
    body = "# Φτιάχνεται από το scripts/new_persona.py: μία υπηρεσία ανά φάκελο στο personas/\nservices:\n"
    body += "\n".join(SERVICE.format(slug=s) for s in slugs)
    (ROOT / "docker-compose.yml").write_text(body, encoding="utf-8")
    print(f"docker-compose.yml: {', '.join(slugs) or '(καμία περσόνα)'}")
    return slugs


def main(argv):
    if len(argv) != 1 or not SLUG.match(argv[0]):
        sys.exit("Χρήση: python3 scripts/new_persona.py <όνομα>   (μικρά λατινικά, π.χ. ava)")
    create(argv[0])
    write_compose()


if __name__ == "__main__":
    main(sys.argv[1:])
