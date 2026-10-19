# Sienna Vale · Κατάσταση (19/10/2026)

## ✅ Έγινε

**Υποδομή**
- Server Hetzner CX23 (Helsinki) στο `2.29.102.240`, Docker, €7,43/μήνα (προπληρωμένα €25).
- Κλειδιά στη θέση τους: Groq (δωρεάν LLM), fal.ai, Telegram bot (@mia_manager_2026_bot), Telegram ID.
- Το σύστημα τρέχει 24/7 και ξέρει να σταματάει μόνο του όταν τελειώσουν τα credits.

**Η Sienna**
- Πρόσωπο επιλεγμένο, dataset 24 φωτογραφιών, LoRA εκπαιδευμένο, 10 references κλειδωμένες.
- Εμφάνιση: λευκή, μακριά σκούρα μπούκλες, μεγάλα καστανά μάτια, μεγάλα χείλη, φακίδες στα μάγουλα, slim-thick σώμα γυμναστηρίου (μεγάλο φυσικό στήθος, λεπτή μέση, μεγάλος σφιχτός πισινός). Σταθερά σημάδια και χρώμα δέρματος σε κάθε prompt.
- Ηλικία 21. Περσόνα από Miami, αγγλικά captions, κοινό ΗΠΑ.

**Τι κάνει το bot**
- Πλάνο κάθε Κυριακή: 1 story 08:00, reel 8″ 12:30, skit 15″ με φωνή 19:00, carousel Σάββατο, 20 Fanvue/εβδομάδα.
- Στέλνει τις ιδέες ως κείμενο και φτιάχνει **μόνο** όσες πατήσεις ✅. Τίποτα δεν ξοδεύει credits χωρίς δικό σου πάτημα (ούτε τα ξαναφτιαξίματα).
- Έλεγχος ποιότητας κάθε εικόνας (ίδιο πρόσωπο, χέρια, ενήλικη, όχι AI-look). Ό,τι κόβεται σου το δείχνει και αποφασίζεις.
- Ρεαλισμός: 10 «ατέλειες» φωτογραφίας κινητού σε κάθε εικόνα, κινητό στο χέρι το πολύ 1 στα 4, φυσική κίνηση στα βίντεο.
- Feed posts = carousel 3 φωτογραφιών 4:5. Stories/reels 9:16. Χωρίς hashtags, χωρίς «#aigenerated».
- Skits με φωνή: η φωνή της κλειδώνει από το πρώτο skit που εγκρίνεις.
- Στείλε βίντεο άλλης → το ξανακάνει η Sienna (ίδιο σκετς, δικός της χώρος) με το 🎬.
- Fanvue: 7 feed + 13 vault PPV την εβδομάδα, χωρίς φίλτρο NSFW, γωνίες/ρούχα που κολακεύουν τις καμπύλες. Chat με fans (approve → auto).
- Buffer-ready: IG κύριο + backup (3 ώρες μετά, άλλο caption), TikTok, YouTube Shorts, X.

**Έρευνα**: ποιο σώμα γίνεται viral (απάντηση: «πολύ όμορφη αλλά αληθοφανής», όχι υπερβολές), τι κόβει το IG/TikTok το 2026, τι κοστίζει τι.

## ⏳ Μένει (με τη σειρά)

1. **fal.ai credits** ($20–30). Χωρίς αυτό τίποτα δεν φτιάχνεται.
2. **Update στον server**: `ssh root@2.29.102.240` → `cd elite-bot/ai-ofm && git pull && docker compose up -d --build`
3. **Telegram**: `/resume` → `/replan` → ✅ σε 6–8 ιδέες → ✅ στα έτοιμα.
4. **Accounts της Sienna** στο παλιό κινητό (μετά από factory reset, νέο Gmail): Instagram @siennavale (Creator + ετικέτα AI-generated profile), TikTok @siennavale (Business). Ζέσταμα 2 μέρες, posting από τη μέρα 2–3. Backup IG σε 1–2 εβδομάδες.
5. **Buffer** (δωρεάν για 3 κανάλια): σύνδεση IG/TikTok/YouTube → API key → `python3 scripts/keys.py sienna --all` → `docker compose run --rm sienna python -m ofm buffer-channels` → στέλνεις screenshot.
6. **Link in bio**: σελίδα Beacons/Linktree με age gate → Fanvue. Όχι cloaking.
7. **Fanvue**: KYC με τη δική σου ταυτότητα, ένδειξη AI στο προφίλ, συνδρομή $9,99–14,99, αίτηση για API (`fanvue.com/developers`). Μέχρι τότε τα αρχεία έρχονται στο Telegram τη Δευτέρα.
8. Μετά τα πρώτα posts: **έλεγχος** στο Buffer ότι μπήκαν σωστά (Reel/Story/Feed), και screenshot από το πρώτο skit με φωνή για να το δούμε μαζί.

## 💶 Κόστος
- Server €7,43/μήνα · Groq, Telegram, Buffer (3 κανάλια) €0
- fal: reel 8″ ≈ $0,80 · skit 15″ με φωνή ≈ $2 · carousel ≈ $0,50 · Fanvue φωτογραφία ≈ $0,10 · story ≈ $0,20
- Με το πλήρες πλάνο ≈ $85/μήνα. Εσύ ορίζεις πόσα ✅ πατάς.

## ⚠️ Μην
- Ποτέ το δικό σου IG στο κινητό της Sienna. Ποτέ κλειδιά στο chat.
- Ποτέ `docker compose up` όσο τρέχει `/train` ή `/dataset` (τα σκοτώνει).
- Όχι γυμνό/ρώγες στα social (μόνο Fanvue και X). Όχι αστεία για φυλή/σεξουαλικότητα, όχι «κόρη» σε σκετς.
