# AI OFM: αυτόματο σύστημα

Φτιάχνει μόνο του το πρόγραμμα της εβδομάδας, τις φωτογραφίες και τα βίντεο, και τα προγραμματίζει σε Instagram, TikTok, YouTube Shorts και X. Εσύ απλώς εγκρίνεις από το κινητό στο Telegram.

## Πώς δουλεύει

| Πότε | Τι κάνει το σύστημα | Τι κάνεις εσύ |
|---|---|---|
| Κυριακή 18:00 | Το Claude γράφει πλάνο 7 ημερών: ιδέες, prompts, captions, hashtags | — |
| Κυριακή βράδυ | Φτιάχνει εικόνες (Nano Banana με τις κλειδωμένες references για τα social, LoRA για το Fanvue) και βίντεο Kling 3.0 που κρατάνε το ίδιο πρόσωπο, και γράφει το hook πάνω στο βίντεο | — |
| Αμέσως μετά | Το Claude ελέγχει κάθε εικόνα: ίδιο πρόσωπο, ενήλικη εμφάνιση, χέρια, γράμματα. Ό,τι κόβεται ξαναφτιάχνεται μόνο του | — |
| Δευτέρα πρωί | Στέλνει τα posts στο Telegram με κουμπιά ✅ 🔁 ❌, μαζί με hook και καρφιτσωμένο σχόλιο | Εγκρίνεις (~45', ή ~10' με `review_sample: 0.2`) |
| Κάθε μέρα | Ανεβάζει τα εγκεκριμένα στο Supabase και τα προγραμματίζει στο Buffer | — |
| Μόλις εγκρίνεις | Ανεβάζει τα Fanvue στο Fanvue: 7 posts στο feed (ένα τη μέρα, 20:00), τα υπόλοιπα στο vault για PPV | — |
| Κάθε λεπτό | Διαβάζει τα αδιάβαστα chat στο Fanvue, γράφει απάντηση με τη φωνή της και προτείνει PPV | Πατάς 📤 ή, με `/chat_auto`, μόνο τις δύσκολες |
| Κυριακή 20:00 | Αναφορά: τι βγήκε, τι απέτυχε, πόσα ξοδεύτηκαν, πώς πάει το chat | Τη διαβάζεις (~20') |

Ό,τι ζητάνε οι fans στο chat («κόκκινο μαγιό», «gym») μπαίνει μόνο του στο πλάνο της επόμενης εβδομάδας.

**Για σχόλια και shares:** κάθε social post έχει έναν μηχανισμό (επιλογή, βαθμολογία, διαφωνία, μάντεψε, relatable POV, χρήσιμο, σειρά), ένα hook πάνω στο βίντεο και ένα σχόλιο για καρφίτσωμα. Όταν δεις viral βίντεο άλλου creator, στείλε `/swipe` με περιγραφή: η **φόρμα** του (όχι το βίντεο) μπαίνει στο επόμενο πλάνο, προσαρμοσμένη στη δική σου περσόνα.

**Ημερήσιος έλεγχος:** κάθε μέρα ελέγχει Buffer, Fanvue, το link του LoRA και τις references. Αν κάτι χάθηκε, το ξανανεβάζει από το αντίγραφο ή σου λέει τι να κάνεις.

**Backup Instagram:** το ίδιο reel ανεβαίνει και σε δεύτερο Instagram λογαριασμό 3 ώρες αργότερα, με διαφορετικό caption. Αν πέσει ο κύριος, το traffic συνεχίζει.

Όλες οι ώρες και το πόσα posts βγαίνουν ρυθμίζονται στο `personas/<όνομα>/persona.yaml`.

## Κανόνες ασφαλείας (ενσωματωμένοι, δεν απενεργοποιούνται)
- Η περσόνα πρέπει να είναι τουλάχιστον 21 χρονών. Κάθε prompt γράφει «adult, 24-year-old».
- Μπλοκάρεται ό,τι θυμίζει ανήλικο (teen, school uniform, μαθήτρια κ.λπ.), πραγματικά πρόσωπα και lookalikes, και captions που λένε «είμαι αληθινή» ή «not AI».
- Τα reels και τα posts **δεν** λένε «είμαι AI». Η δήλωση γίνεται στο bio, με την ετικέτα «AI-generated profile» του Instagram (υποχρεωτική), και με ένα `#aigenerated` στο τέλος των hashtags, που το ζητάει ο νόμος της ΕΕ (AI Act, άρθρο 50) και το TikTok και δεν αφαιρείται.
- Για Instagram/TikTok/YouTube/X το φίλτρο NSFW είναι πάντα ανοιχτό.
- Κανένα post δεν ανεβαίνει χωρίς το δικό σου ✅. Το chat στέλνει μόνο του μόνο αν το βάλεις εσύ σε `/chat_auto`.
- Όριο εξόδων ανά εβδομάδα (`budget.weekly_usd`): όταν το φτάσει, σταματά και σου στέλνει μήνυμα.

## Στήσιμο (μία φορά, ~2 ώρες)

### 1. Λογαριασμοί και κλειδιά
1. **Μοντέλο κειμένου (δωρεάν):** https://console.groq.com/keys, φτιάξε key (χωρίς κάρτα). Αν θες αργότερα καλύτερη ποιότητα, άλλαξε στο `persona.yaml` το `models.llm.provider` σε `claude` και βάλε `ANTHROPIC_API_KEY`.
2. **fal.ai:** https://fal.ai/dashboard/keys, φτιάξε key και βάλε ~$20 credits.
3. **Telegram bot:** στο Telegram γράψε στον **@BotFather** την εντολή `/newbot` και κράτα το token. Κάθε περσόνα έχει δικό της bot.
4. **Buffer:** https://buffer.com (πλάνο Essentials). Σύνδεσε Instagram (Business ή Creator, κύριο και backup), TikTok (Business), YouTube, X. Μετά **Settings**, **API**, φτιάξε key.
5. **Φιλοξενία αρχείων:** δεν χρειάζεται κάτι. Τα τελικά αρχεία για το Buffer ανεβαίνουν στο fal (κρατιούνται 30 μέρες). Το Supabase είναι προαιρετικό: η δωρεάν έκδοση «κοιμάται» μετά από 7 μέρες και τα links σταματούν.
6. **Instagram:** Settings, άνοιξε την ετικέτα **AI-generated profile**. Χωρίς αυτήν, από 31/8/2026 κόβεται το reach.
7. **Fanvue:** επαλήθευση με τη δική σου ταυτότητα και ενεργή η ένδειξη AI content στο προφίλ. **Το API δίνεται με λίστα αναμονής:** ζήτα πρόσβαση νωρίς και μην πληρώσεις τίποτα για το Fanvue κομμάτι μέχρι να εγκριθεί το app σου. Μέχρι τότε τα αρχεία σού έρχονται στο Telegram για χειροκίνητο ανέβασμα.

### 2. Server (ένα μικρό VPS, ~€5 τον μήνα)
Χρειάζεται να τρέχει 24/7. Ένα Hetzner CX22 ή κάτι αντίστοιχο φτάνει.
```bash
ssh root@IP-του-server
curl -fsSL https://get.docker.com | sh
git clone https://github.com/luis-real199/elite-bot.git
cd elite-bot && git checkout claude/funny-bell-565xkp && cd ai-ofm
cp .env.example .env
nano .env                              # κοινά κλειδιά από το βήμα 1
python3 scripts/new_persona.py sienna  # φτιάχνει το personas/sienna/.env
nano personas/sienna/.env              # το token του bot της
```
Αν το repo είναι private, το `git clone` θα ζητήσει GitHub token. Εναλλακτικά, ανέβασε τον φάκελο `ai-ofm` στον server με όποιον τρόπο θες.

Στείλε «hi» στο bot σου στο Telegram και μετά:
```bash
docker compose run --rm sienna python -m ofm telegram-id        # βάλε το TELEGRAM_OWNER_ID στο .env
docker compose run --rm sienna python -m ofm buffer-channels    # βάλε τα BUFFER_CHANNEL_* στο personas/sienna/.env
docker compose run --rm sienna python -m ofm check              # όλα ✅;
docker compose up -d --build                                 # ξεκινά και μένει ανοιχτό
```
Στείλε `/help` στο bot. Αν απαντήσει, το σύστημα τρέχει.

### 3. Περσόνα (από το Telegram)
1. Άλλαξε το `personas/sienna/persona.yaml` (όνομα, εμφάνιση, θέματα) και κάνε `docker compose restart sienna`.
2. `/faces`: 6 υποψήφια πρόσωπα. Πάτα ⭐ σε αυτό που θες.
3. `/dataset`: 24 φωτογραφίες με το ίδιο πρόσωπο. Πάτα 🗑 σε όσες δεν μοιάζουν. Πρέπει να μείνουν τουλάχιστον 12.
4. `/train`: εκπαίδευση LoRA (~$3, 5–20 λεπτά). Κλειδώνει και τις 10 references (το πρόσωπο + τις καλύτερες του dataset) και κρατάει αντίγραφο του LoRA. Στο τέλος σου στέλνει μια δοκιμαστική φωτογραφία.
5. `/plan`: το πρώτο πλάνο. Από εκεί και πέρα το σύστημα συνεχίζει μόνο του κάθε Κυριακή.

### 4. Fanvue (ανέβασμα και chat)
1. Στο Fanvue (με ολοκληρωμένο KYC) πήγαινε **fanvue.com/developers**, **Create app**. Αν δεν σου βγάζει την επιλογή, ζήτα API access από το help center του Fanvue.
2. **Redirect URI:** βάλε το ίδιο με το `FANVUE_REDIRECT_URI` του `.env` (π.χ. `https://ofm-bot.example/callback`, δεν χρειάζεται να ανοίγει). **Scopes:** `read:self read:chat write:chat read:post write:post read:media write:media`.
3. Βάλε `FANVUE_CLIENT_ID` και `FANVUE_CLIENT_SECRET` στο `.env` και κάνε `docker compose restart`.
4. Στείλε `/fanvue_login` στο bot της περσόνας, άνοιξε το link, κάνε login **στο Fanvue της συγκεκριμένης περσόνας**, και στείλε στο bot ολόκληρη τη διεύθυνση όπου κατέληξες (έχει `code=`).
5. **Chat:** ξεκινάει σε `approve`: κάθε απάντηση σου έρχεται στο Telegram, πατάς 📤, ή κάνεις reply στο μήνυμα με δικό σου κείμενο. Όταν δεις ότι γράφει καλά, στείλε `/chat_auto`: απαντάει και πουλάει PPV μόνο του, και σε σένα έρχονται μόνο οι top spenders, τα παράπονα, ό,τι θυμίζει ανήλικο και ό,τι σπάει τους κανόνες. Σταματάει με `/chat_off`.

Το chat δηλώνει πάντα ότι είναι AI, δεν κλείνει συναντήσεις, δεν δίνει στοιχεία, δεν γράφει άσεμνα, και πουλάει μόνο ό,τι υπάρχει στο vault σε τιμή μέσα στα όρια του `fanvue.ppv_price_usd`. Έχει δικό του όριο εξόδων (`chat.weekly_usd`).

### 5. Πρώτο τεστ του Buffer
Πριν τα πρώτα posts:
```bash
docker compose run --rm sienna python -m ofm publish --dry-run
```
Σου δείχνει τι θα σταλεί, χωρίς να στείλει τίποτα. Για αυτόματη δημοσίευση στο Buffer: Instagram **Business ή Creator** συνδεδεμένο με Facebook Page, και στα κανάλια κλειστό το «notifications by default». Stories με μουσική/stickers και TikTok με ήχους της εφαρμογής γίνονται ειδοποίηση στο κινητό. Μετά τα πρώτα κανονικά posts, κοίτα στο Buffer ότι μπήκαν σωστά (Reel, Story, Feed). Αν έρθει μήνυμα σφάλματος στο Telegram, στείλε μου το κείμενο και το διορθώνω.

## Περισσότερες περσόνες
Ξεκίνα με μία. Όταν η πρώτη φτάσει ~50 συνδρομητές:
```bash
python3 scripts/new_persona.py ava     # personas/ava/persona.yaml, personas/ava/.env, και ενημερώνει το docker-compose.yml
nano personas/ava/persona.yaml         # όνομα, εμφάνιση, niche (διαφορετικά από τη Sienna)
nano personas/ava/.env                 # token του δικού της bot, τα κανάλια της στο Buffer
docker compose up -d --build           # τρέχουν και οι δύο
```
Μετά, στο bot της Ava: `/faces`, `/dataset`, `/train`, `/fanvue_login`, `/plan`.

Κάθε περσόνα έχει δικό της bot, δική της βάση, δικά της αρχεία και δικό της όριο εξόδων, για να μη «δένονται» οι λογαριασμοί. Ποτέ accounts δύο περσονών στο ίδιο κινητό. Το Fanvue επιτρέπει έως 15 AI προφίλ με το ίδιο KYC.

## Εντολές Telegram
`/status` · `/plan` · `/swipe` · `/fanvue` · `/report` · `/pause` · `/resume` · `/lock` · `/fanvue_login` · `/chat` · `/chat_approve` · `/chat_auto` · `/chat_off` · `/faces` · `/dataset` · `/train` · `/help`

## Ποιο μοντέλο κειμένου
| | Κόστος | Σημειώσεις |
|---|---|---|
| **Groq** (προεπιλογή) | δωρεάν | ~1.000 αιτήματα τη μέρα, αρκεί για την αρχή. Όταν μεγαλώσει το chat, θα φτάσεις το όριο |
| **Gemini** | δωρεάν | Η Google χρησιμοποιεί τα δεδομένα της δωρεάν έκδοσης για εκπαίδευση και τα διαβάζουν άνθρωποι: όχι καλή ιδέα για μηνύματα fans |
| **Claude** | ~$15–45/μήνα | Καλύτερες ιδέες, captions, chat και έλεγχος εικόνων |

Αλλάζει με μία γραμμή στο `persona.yaml` (`models.llm.provider`) και `docker compose restart`.

## Κόστος (περίπου)
| | ανά μήνα |
|---|---|
| fal.ai: ~150 εικόνες (Nano Banana $0,15 / LoRA $0,05) + ~30 βίντεο Kling 3.0 των 8″ | $40–60 |
| Πλάνα, captions, έλεγχος εικόνων, chat με Groq (δωρεάν) | €0 · με Claude: ~$15–45 |
| Buffer Essentials, 5 κανάλια ανά περσόνα | ~$30 |
| VPS | ~€5 |
| Supabase | δωρεάν (τα αρχεία σβήνονται 3 μέρες μετά το post) |

## Τι μένει χειροκίνητο (και γιατί)
- **Fanvue χωρίς σύνδεση API:** αν δεν έχεις κάνει `/fanvue_login`, τα αρχεία σου έρχονται κάθε Δευτέρα στο Telegram για χειροκίνητο ανέβασμα.
- **Τολμηρά chat (sexting):** το bot μένει σε flirty αλλά όχι άσεμνο ύφος. Ό,τι πάει πιο πέρα σου έρχεται στο Telegram.
- **Trending ήχοι σε Reels/TikTok:** δεν μπαίνουν μέσω API. Αν τους θες, 5 λεπτά από την εφαρμογή.
- **Reddit:** εκτός συστήματος. Τα αυτόματα posts εκεί φέρνουν ban.

## Αρχεία
- `personas/<όνομα>/persona.yaml`: περσόνα, πρόγραμμα, όριο εξόδων, μοντέλα
- `personas/<όνομα>/.env`: τα κλειδιά της περσόνας · `.env`: τα κοινά (κανένα δεν ανεβαίνει στο GitHub)
- `persona.example.yaml`: το πρότυπο για νέες περσόνες · `scripts/new_persona.py`: φτιάχνει νέα περσόνα
- `ofm/`: ο κώδικας (`llm` = Groq/Gemini/Claude, `planner` = πλάνο, `media` = fal.ai, `jobs` = η εβδομαδιαία ροή, `bot` = Telegram, `fanvue` = Fanvue API, `chat` = απαντήσεις σε fans)
- `personas/<όνομα>/data/`: βάση δεδομένων και αρχεία που φτιάχτηκαν
- Tests: `pip install -r requirements.txt pytest && pytest`

Αν το fal.ai αλλάξει όνομα σε κάποιο μοντέλο, άλλαξέ το στο `models:` του `persona.yaml` κάθε περσόνας.
