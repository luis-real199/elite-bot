# AI OFM: αυτόματο σύστημα

Φτιάχνει μόνο του το πρόγραμμα της εβδομάδας, τις φωτογραφίες και τα βίντεο, και τα προγραμματίζει σε Instagram, TikTok, YouTube Shorts και X. Εσύ απλώς εγκρίνεις από το κινητό στο Telegram.

## Πώς δουλεύει

| Πότε | Τι κάνει το σύστημα | Τι κάνεις εσύ |
|---|---|---|
| Κυριακή 18:00 | Το Claude γράφει πλάνο 7 ημερών: ιδέες, prompts, captions με #AI | — |
| Κυριακή βράδυ | Το fal.ai φτιάχνει εικόνες (με το LoRA της περσόνας) και βίντεο (Kling) | — |
| Δευτέρα πρωί | Στέλνει κάθε post στο Telegram με κουμπιά ✅ 🔁 ❌ | Εγκρίνεις (~45') |
| Κάθε μέρα | Ανεβάζει τα εγκεκριμένα στο Supabase και τα προγραμματίζει στο Buffer | — |
| Μόλις εγκρίνεις | Ανεβάζει τα Fanvue στο Fanvue: 7 posts στο feed (ένα τη μέρα, 20:00), τα υπόλοιπα στο vault για PPV | — |
| Κάθε λεπτό | Διαβάζει τα αδιάβαστα chat στο Fanvue, γράφει απάντηση με τη φωνή της και προτείνει PPV | Πατάς 📤 ή, με `/chat_auto`, μόνο τις δύσκολες |
| Κυριακή 20:00 | Αναφορά: τι βγήκε, τι απέτυχε, πόσα ξοδεύτηκαν, πώς πάει το chat | Τη διαβάζεις (~20') |

Ό,τι ζητάνε οι fans στο chat («κόκκινο μαγιό», «gym») μπαίνει μόνο του στο πλάνο της επόμενης εβδομάδας.

Όλες οι ώρες και το πόσα posts βγαίνουν ρυθμίζονται στο `persona.yaml`.

## Κανόνες ασφαλείας (ενσωματωμένοι, δεν απενεργοποιούνται)
- Η περσόνα πρέπει να είναι τουλάχιστον 21 χρονών. Κάθε prompt γράφει «adult, 24-year-old».
- Μπλοκάρεται ό,τι θυμίζει ανήλικο (teen, school uniform, μαθήτρια κ.λπ.), πραγματικά πρόσωπα και lookalikes, και captions που λένε «είμαι αληθινή» ή «not AI».
- Μπαίνει πάντα hashtag #AI.
- Για Instagram/TikTok/YouTube/X το φίλτρο NSFW είναι πάντα ανοιχτό.
- Κανένα post δεν ανεβαίνει χωρίς το δικό σου ✅. Το chat στέλνει μόνο του μόνο αν το βάλεις εσύ σε `/chat_auto`.
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

### 4. Fanvue (ανέβασμα και chat)
1. Στο Fanvue (με ολοκληρωμένο KYC) πήγαινε **fanvue.com/developers**, **Create app**. Αν δεν σου βγάζει την επιλογή, ζήτα API access από το help center του Fanvue.
2. **Redirect URI:** βάλε το ίδιο με το `FANVUE_REDIRECT_URI` του `.env` (π.χ. `https://ofm-bot.example/callback`, δεν χρειάζεται να ανοίγει). **Scopes:** `read:self read:chat write:chat read:post write:post read:media write:media`.
3. Βάλε `FANVUE_CLIENT_ID` και `FANVUE_CLIENT_SECRET` στο `.env` και κάνε `docker compose restart`.
4. Στείλε `/fanvue_login` στο bot, άνοιξε το link, κάνε login, και στείλε στο bot ολόκληρη τη διεύθυνση όπου κατέληξες (έχει `code=`).
5. **Chat:** ξεκινάει σε `approve`: κάθε απάντηση σου έρχεται στο Telegram, πατάς 📤, ή κάνεις reply στο μήνυμα με δικό σου κείμενο. Όταν δεις ότι γράφει καλά, στείλε `/chat_auto`: απαντάει και πουλάει PPV μόνο του, και σε σένα έρχονται μόνο οι top spenders, τα παράπονα, ό,τι θυμίζει ανήλικο και ό,τι σπάει τους κανόνες. Σταματάει με `/chat_off`.

Το chat δηλώνει πάντα ότι είναι AI, δεν κλείνει συναντήσεις, δεν δίνει στοιχεία, δεν γράφει άσεμνα, και πουλάει μόνο ό,τι υπάρχει στο vault σε τιμή μέσα στα όρια του `fanvue.ppv_price_usd`. Έχει δικό του όριο εξόδων (`chat.weekly_usd`).

### 5. Πρώτο τεστ του Buffer
Πριν τα πρώτα posts:
```bash
docker compose run --rm ofm python -m ofm publish --dry-run
```
Σου δείχνει τι θα σταλεί, χωρίς να στείλει τίποτα. Μετά τα πρώτα κανονικά posts, κοίτα στο Buffer ότι μπήκαν σωστά (Reel, Story, Feed). Αν έρθει μήνυμα σφάλματος στο Telegram, στείλε μου το κείμενο και το διορθώνω.

## Εντολές Telegram
`/status` · `/plan` · `/fanvue` · `/report` · `/pause` · `/resume` · `/fanvue_login` · `/chat` · `/chat_approve` · `/chat_auto` · `/chat_off` · `/faces` · `/dataset` · `/train` · `/help`

## Κόστος (περίπου)
| | ανά μήνα |
|---|---|
| fal.ai: ~150 εικόνες + ~30 βίντεο | $20–35 |
| Claude: 4 πλάνα | ~$1 |
| Claude: chat (~2–3 σεντς ανά απάντηση) | ~$10–40, με όριο στο `chat.weekly_usd` |
| Buffer Essentials, 4 κανάλια | ~$24 |
| VPS | ~€5 |
| Supabase | δωρεάν (τα αρχεία σβήνονται 3 μέρες μετά το post) |

## Τι μένει χειροκίνητο (και γιατί)
- **Fanvue χωρίς σύνδεση API:** αν δεν έχεις κάνει `/fanvue_login`, τα αρχεία σου έρχονται κάθε Δευτέρα στο Telegram για χειροκίνητο ανέβασμα.
- **Τολμηρά chat (sexting):** το bot μένει σε flirty αλλά όχι άσεμνο ύφος. Ό,τι πάει πιο πέρα σου έρχεται στο Telegram.
- **Trending ήχοι σε Reels/TikTok:** δεν μπαίνουν μέσω API. Αν τους θες, 5 λεπτά από την εφαρμογή.
- **Reddit:** εκτός συστήματος. Τα αυτόματα posts εκεί φέρνουν ban.

## Αρχεία
- `persona.yaml`: περσόνα, πρόγραμμα, όριο εξόδων, μοντέλα
- `.env`: κλειδιά (δεν ανεβαίνει ποτέ στο GitHub)
- `ofm/`: ο κώδικας (`planner` = Claude, `media` = fal.ai, `jobs` = η εβδομαδιαία ροή, `bot` = Telegram, `fanvue` = Fanvue API, `chat` = απαντήσεις σε fans)
- `data/`: βάση δεδομένων και αρχεία που φτιάχτηκαν
- Tests: `pip install -r requirements.txt pytest && pytest`

Αν το fal.ai αλλάξει όνομα σε κάποιο μοντέλο, άλλαξέ το στο `models:` του `persona.yaml`.
