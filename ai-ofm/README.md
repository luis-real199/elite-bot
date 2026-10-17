# AI OFM: αυτόματο σύστημα

Φτιάχνει μόνο του το πρόγραμμα της εβδομάδας, τις φωτογραφίες και τα βίντεο, και τα προγραμματίζει σε Instagram, TikTok, YouTube Shorts και X. Εσύ απλώς εγκρίνεις από το κινητό στο Telegram.

## Πώς δουλεύει

| Πότε | Τι κάνει το σύστημα | Τι κάνεις εσύ |
|---|---|---|
| Κυριακή 18:00 | Το Claude γράφει πλάνο 7 ημερών: ιδέες, prompts, captions με #AI | — |
| Κυριακή βράδυ | Το fal.ai φτιάχνει εικόνες (με το LoRA της περσόνας) και βίντεο (Kling) | — |
| Δευτέρα πρωί | Στέλνει κάθε post στο Telegram με κουμπιά ✅ 🔁 ❌ | Εγκρίνεις (~45') |
| Κάθε μέρα | Ανεβάζει τα εγκεκριμένα στο Supabase και τα προγραμματίζει στο Buffer | — |
| Δευτέρα 09:00 | Σου στέλνει τα αρχεία του Fanvue σε αρχική ποιότητα | Τα ανεβάζεις στο vault/PPV (~30') |
| Κυριακή 20:00 | Αναφορά: τι βγήκε, τι απέτυχε, πόσα ξοδεύτηκαν | Τη διαβάζεις (~20') |

Όλες οι ώρες και το πόσα posts βγαίνουν ρυθμίζονται στο `persona.yaml`.

## Κανόνες ασφαλείας (ενσωματωμένοι, δεν απενεργοποιούνται)
- Η περσόνα πρέπει να είναι τουλάχιστον 21 χρονών. Κάθε prompt γράφει «adult, 24-year-old».
- Μπλοκάρεται ό,τι θυμίζει ανήλικο (teen, school uniform, μαθήτρια κ.λπ.), πραγματικά πρόσωπα και lookalikes, και captions που λένε «είμαι αληθινή» ή «not AI».
- Μπαίνει πάντα hashtag #AI.
- Για Instagram/TikTok/YouTube/X το φίλτρο NSFW είναι πάντα ανοιχτό.
- Τίποτα δεν ανεβαίνει χωρίς το δικό σου ✅.
- Όριο εξόδων ανά εβδομάδα (`budget.weekly_usd`): όταν το φτάσει, σταματά και σου στέλνει μήνυμα.

## Στήσιμο (μία φορά, ~2 ώρες)

### 1. Λογαριασμοί και κλειδιά
1. **Claude:** https://console.anthropic.com, **API Keys**, φτιάξε key και βάλε λίγα credits.
2. **fal.ai:** https://fal.ai/dashboard/keys, φτιάξε key και βάλε ~$20 credits.
3. **Telegram bot:** στο Telegram γράψε στον **@BotFather** την εντολή `/newbot` και κράτα το token.
4. **Buffer:** https://buffer.com (πλάνο Essentials). Σύνδεσε Instagram (Business ή Creator), TikTok (Business), YouTube, X. Μετά **Settings**, **API**, φτιάξε key.
5. **Supabase:** φτιάξε **νέο** project, ξεχωριστό από το Blacklist Records.
   - **Storage**, **New bucket**, όνομα `ofm-media`, ενεργό το **Public bucket**.
   - **Project Settings**, **API Keys**: αντέγραψε το URL και ένα **secret key**.
6. **Instagram:** Settings, άνοιξε την ετικέτα **AI-generated profile**. Χωρίς αυτήν, από 31/8/2026 κόβεται το reach.
7. **Fanvue:** επαλήθευση με τη δική σου ταυτότητα και ενεργή η ένδειξη AI content στο προφίλ.

### 2. Server (ένα μικρό VPS, ~€5 τον μήνα)
Χρειάζεται να τρέχει 24/7. Ένα Hetzner CX22 ή κάτι αντίστοιχο φτάνει.
```bash
ssh root@IP-του-server
curl -fsSL https://get.docker.com | sh
git clone https://github.com/luis-real199/elite-bot.git
cd elite-bot && git checkout claude/funny-bell-565xkp && cd ai-ofm
cp .env.example .env
nano .env          # βάλε τα κλειδιά από το βήμα 1
```
Αν το repo είναι private, το `git clone` θα ζητήσει GitHub token. Εναλλακτικά, ανέβασε τον φάκελο `ai-ofm` στον server με όποιον τρόπο θες.

Στείλε «hi» στο bot σου στο Telegram και μετά:
```bash
docker compose run --rm ofm python -m ofm telegram-id        # βάλε το TELEGRAM_OWNER_ID στο .env
docker compose run --rm ofm python -m ofm buffer-channels    # βάλε τα BUFFER_CHANNEL_* στο .env
docker compose run --rm ofm python -m ofm check              # όλα ✅;
docker compose up -d --build                                 # ξεκινά και μένει ανοιχτό
```
Στείλε `/help` στο bot. Αν απαντήσει, το σύστημα τρέχει.

### 3. Περσόνα (από το Telegram)
1. Άλλαξε το `persona.yaml` (όνομα, εμφάνιση, θέματα) και κάνε `docker compose restart`.
2. `/faces`: 6 υποψήφια πρόσωπα. Πάτα ⭐ σε αυτό που θες.
3. `/dataset`: 24 φωτογραφίες με το ίδιο πρόσωπο. Πάτα 🗑 σε όσες δεν μοιάζουν. Πρέπει να μείνουν τουλάχιστον 12.
4. `/train`: εκπαίδευση LoRA (~$3, 5–20 λεπτά). Στο τέλος σου στέλνει μια δοκιμαστική φωτογραφία.
5. `/plan`: το πρώτο πλάνο. Από εκεί και πέρα το σύστημα συνεχίζει μόνο του κάθε Κυριακή.

### 4. Πρώτο τεστ του Buffer
Πριν τα πρώτα posts:
```bash
docker compose run --rm ofm python -m ofm publish --dry-run
```
Σου δείχνει τι θα σταλεί, χωρίς να στείλει τίποτα. Μετά τα πρώτα κανονικά posts, κοίτα στο Buffer ότι μπήκαν σωστά (Reel, Story, Feed). Αν έρθει μήνυμα σφάλματος στο Telegram, στείλε μου το κείμενο και το διορθώνω.

## Εντολές Telegram
`/status` · `/plan` · `/fanvue` · `/report` · `/pause` · `/resume` · `/faces` · `/dataset` · `/train` · `/help`

## Κόστος (περίπου)
| | ανά μήνα |
|---|---|
| fal.ai: ~150 εικόνες + ~30 βίντεο | $20–35 |
| Claude: 4 πλάνα | ~$1 |
| Buffer Essentials, 4 κανάλια | ~$24 |
| VPS | ~€5 |
| Supabase | δωρεάν (τα αρχεία σβήνονται 3 μέρες μετά το post) |

## Τι μένει χειροκίνητο (και γιατί)
- **Ανέβασμα στο Fanvue:** δεν υπάρχει ακόμα σταθερό δημόσιο API για ανέβασμα αρχείων, οπότε τα αρχεία σου έρχονται έτοιμα στο Telegram.
- **Chat με fans:** χρησιμοποίησε τα AI εργαλεία του ίδιου του Fanvue και μην κρύβεις ότι η περσόνα είναι AI.
- **Trending ήχοι σε Reels/TikTok:** δεν μπαίνουν μέσω API. Αν τους θες, 5 λεπτά από την εφαρμογή.
- **Reddit:** εκτός συστήματος. Τα αυτόματα posts εκεί φέρνουν ban.

## Αρχεία
- `persona.yaml`: περσόνα, πρόγραμμα, όριο εξόδων, μοντέλα
- `.env`: κλειδιά (δεν ανεβαίνει ποτέ στο GitHub)
- `ofm/`: ο κώδικας (`planner` = Claude, `media` = fal.ai, `jobs` = η εβδομαδιαία ροή, `bot` = Telegram)
- `data/`: βάση δεδομένων και αρχεία που φτιάχτηκαν
- Tests: `pip install -r requirements.txt pytest && pytest`

Αν το fal.ai αλλάξει όνομα σε κάποιο μοντέλο, άλλαξέ το στο `models:` του `persona.yaml`.
