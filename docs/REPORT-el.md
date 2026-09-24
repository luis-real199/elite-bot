# Nestia — τι έγινε και τι να κάνεις μετά

Site: https://claude.ai/artifact/5a1yyni8osm8XztdyPUJcX
Κώδικας: branch `claude/adoring-faraday-0y34ko` στο repo `luis-real199/elite-bot` (`src/` πηγή, `site/` έτοιμο για hosting)

## 1. Δωρεάν εργαλεία — τι αξίζει (Σεπτέμβριος 2026)

Σημείωση: οι επίσημες σελίδες τιμών ήταν αποκλεισμένες από το περιβάλλον έρευνας, οπότε τα όρια προέρχονται από αποσπάσματα των επίσημων σελίδων και επίσημα GitHub repos. Πριν βασιστείς σε αριθμό, δες τη σελίδα του εργαλείου.

### Προμηθευτές / εκτέλεση παραγγελιών (χωρίς Shopify)
| Εργαλείο | Δωρεάν; | Γιατί |
|---|---|---|
| **CJdropshipping** | Ναι (0 €/μήνα, πληρώνεις μόνο προϊόν+μεταφορικά) | Μαζική εισαγωγή παραγγελιών με Excel (Dropshipping Center → Imported Orders → Import Excel Orders), δωρεάν API, αποθήκες ΕΕ (3–7 μέρες), IOSS/DDP routes ώστε ο πελάτης να μην πληρώνει τίποτα στην πόρτα |
| **AliExpress** (χειροκίνητη αγορά) | Ναι | Για ό,τι δεν βρίσκει το CJ. Για παραγγελίες ≤150 € το AliExpress εισπράττει τον ΦΠΑ (IOSS) στο checkout |
| **EPROLO** | Ναι (free forever) | Μαζική εισαγωγή παραγγελιών με Excel, API κατόπιν αιτήματος |
| Printful / Printify | Ναι | Μόνο αν βάλεις print-on-demand (μπλουζάκια κ.λπ.) |
| DSers, Zendrop, Spocket, AutoDS, Sellvia, Syncee, BigBuy | Όχι ή μόνο με Shopify/Woo | Δεν δουλεύουν με custom HTML site ή δεν έχουν χρήσιμο free plan |

### Κοινωνικά δίκτυα — «ένα κλικ, παντού»
| Εργαλείο | Free plan | Μαζική εισαγωγή |
|---|---|---|
| **Pinterest Bulk create Pins** (native) | Ναι, business account | CSV έως 200 Pins ανά αρχείο — το site το βγάζει έτοιμο |
| **Buffer** | 3 κανάλια, 10 προγραμματισμένα posts/κανάλι | CSV (Text, Image URL, Tags, Posting Time) — το site βγάζει ένα αρχείο ανά κανάλι |
| **Publer** | 3 λογαριασμοί (όχι X), 10 pending/λογαριασμό | CSV 12 στηλών — έτοιμο από το site (5 γραμμές/upload στο free) |
| **Metricool** | 1 brand, 20 posts/μήνα, φτάνει TikTok+IG Reels+FB+Pinterest+YouTube | CSV στο δικό του template 18 στηλών (το κατεβάζεις από Metricool και κάνεις paste) |
| **Meta Business Suite planner** | Ναι | Χωρίς CSV, αλλά προγραμματίζει FB+IG posts/Reels/Stories δωρεάν |
| **TikTok Studio / YouTube Studio** | Ναι | Προγραμματισμός ανά βίντεο (TikTok έως 10 μέρες μπροστά) |
| Postiz (open source) | Δωρεάν μόνο self-hosted | Χρειάζεται δικό σου server· η cloud έκδοση δεν έχει free |
| Later, Hootsuite, SocialBee, Zoho Social bulk | Όχι | Χωρίς αξιόπιστο free ή χωρίς CSV στο free |

### Feeds προϊόντων (όλα τα προϊόντα «παντού» με ένα αρχείο)
- **Google Merchant Center free listings** (δωρεάν, υποστηρίζει Ελλάδα/EUR) — απαιτεί επαληθευμένο domain, πολιτική επιστροφών, στοιχεία επικοινωνίας, μεταφορικά για GR.
- **Meta Commerce Manager** catalog + Facebook/Instagram Shop με «checkout στο site σου» (δωρεάν).
- **Pinterest Catalogs** (δωρεάν· το Verified Merchant Program δεν δέχεται Ελλάδα).
- Microsoft Merchant Center: ίδιο αρχείο, μηδενική επιπλέον δουλειά.
- Όχι: Skroutz (496 €/χρόνο), idealo/Klarna (CPC), TikTok catalog (θέλει διαφημιστικό budget).
Το site βγάζει ένα CSV σε μορφή Google που δέχονται και τα τρία.

### AI περιεχόμενο & αυτοματισμός (0 €)
- Κείμενα: **Claude Free** (ή ChatGPT/Gemini free) — και μέσα στο site: το κουμπί «Write posts» γράφει TikTok script, IG caption, FB post, Pinterest pin και X post για όλα τα προϊόντα.
- Βίντεο: **CapCut Free** (1080p χωρίς watermark με δικά σου πλάνα/free templates). Runway, Pika, Kling, HeyGen, Vidnoz, InVideo free = watermark και συχνά μη εμπορική χρήση — όχι για διαφημίσεις.
- Εικόνες: Gemini app (Nano Banana) για backgrounds· remove.bg δωρεάν μόνο σε χαμηλή ανάλυση· Photoroom free = watermark.
- Glue: **Make Free** (1.000 credits/μήνα, 2 σενάρια) ή **n8n** self-hosted (δωρεάν για δική σου επιχείρηση). Zapier free = 100 tasks, μόνο 2 βήματα.

### Πληρωμές & hosting (0 €/μήνα)
- **Hosting**: Cloudflare Pages (δωρεάν, επιτρέπεται εμπορική χρήση) + Cloudflare Worker (100.000 req/μέρα) όταν θες πραγματικό checkout με κάρτα. GitHub Pages απαγορεύει e-commerce, Vercel Hobby απαγορεύει εμπορική χρήση.
- **Πληρωμές τώρα, χωρίς server**: PayPal.me / Stripe Payment Link / IBAN (το site τα υποστηρίζει ήδη). Ενδεικτικές χρεώσεις ανά συναλλαγή (μη επαληθευμένες σήμερα): Stripe κάρτες ΕΟΧ ~1,5 % + 0,25 €, PayPal Ελλάδα ~3,4 % + 0,35 €, Viva.com ~1,35 %.
- **Πληρωμές μετά**: Stripe Checkout από Worker (~40 γραμμές) — το site έχει ήδη το hook (`STORE.payment.apiBase`).
- Email επιβεβαίωσης: Brevo free (300/μέρα) ή Resend free (3.000/μήνα) — χρειάζεται τον Worker.

### Νομικά που ΠΡΕΠΕΙ να ξέρεις (επαληθευμένα στα κείμενα των νόμων)
- Απαγορεύονται: ψεύτικες κριτικές/«Verified», «μόνο 3 έμειναν», countdown, διαγραμμένες τιμές χωρίς 30ήμερο ιστορικό (πρόστιμο από 20.000 €), «eco/βιώσιμο» χωρίς απόδειξη (από 27/9/2026).
- Υποχρεωτικά στο site: επωνυμία, διεύθυνση, ΑΦΜ, ΓΕΜΗ, email **και** τηλέφωνο· 14ήμερη υπαναχώρηση με υπόδειγμα εντύπου· ποιος πληρώνει την επιστροφή· κουμπί «Παραγγελία με υποχρέωση πληρωμής»· διετής εγγύηση· ADR: Συνήγορος του Καταναλωτή (η πλατφόρμα ODR έκλεισε 20/7/2025).
- GPSR (από 12/2024): σε κάθε προϊόν κατασκευαστής + υπεύθυνος στην ΕΕ (εσύ, ως εισαγωγέας) + προειδοποιήσεις.
- Τελωνείο: από 1/7/2026 δασμός 3 €/τεμάχιο σε δέματα ≤150 € από Κίνα — στείλε DDP/IOSS αλλιώς ο πελάτης πληρώνει στην πόρτα.
- Cookies: χωρίς analytics/pixels δεν χρειάζεται banner (το site δεν έχει). Αν βάλεις Meta Pixel/GA4: Klaro ή tarteaucitron (δωρεάν, έχουν ελληνικά).

## 2. Τι άλλαξε στο site (91 ευρήματα από 4 ελέγχους, όλα επαληθευμένα από δεύτερο agent)

**Έφυγαν τα demo/ψεύτικα**: sample reviews + «Verified», αστέρια, «10K+ sold», «Only N left», «Bestseller», κουτί «Store mockup», «add before going live», «connect server.js», ODR link (η πλατφόρμα έκλεισε 2025), «unused» ως όρος επιστροφής, ιατρικοί ισχυρισμοί (νεφρά γάτας, «physio», «de-puff»), αντιφάσεις specs/επιλογών (One size vs 2 μεγέθη, 400ml vs 600ml).

**Νομικά σωστό πλέον**: στοιχεία πωλητή (επωνυμία/διεύθυνση/ΑΦΜ/ΓΕΜΗ/email/τηλέφωνο) σε Terms/About/Privacy/Contact, διεύθυνση επιστροφών + υπόδειγμα υπαναχώρησης, «μπορείς να το ανοίξεις και να το δοκιμάσεις», ποιος πληρώνει την επιστροφή, επιστροφή και των μεταφορικών, διετής εγγύηση, Συνήγορος Καταναλωτή, «Παραγγελία με υποχρέωση πληρωμής», GPSR ενότητα «Manufacturer and safety» σε κάθε προϊόν, Privacy με νομική βάση/μεταφορά Κίνα/Anthropic chat, Cookies χωρίς banner (δεν χρειάζεται), διαγραμμένες τιμές κλειστές (Omnibus).

**Λειτουργικά bugs που διορθώθηκαν**: sticky «Add to cart» σκέπαζε το checkout, κουμπιά chat/owner σκέπαζαν footer και τελευταία προϊόντα, focus χανόταν σε κάθε αλλαγή επιλογής/ποσότητας και σε φωλιασμένα παράθυρα, η σελίδα πίσω από modal δεν ήταν inert, Enter δεν υποβάλλει το checkout, λάθη φόρμας δεν ανακοινώνονταν, το κείμενο παραγγελίας «πάγωνε» λάθος ή ξαναεμφανιζόταν παλιά παραγγελία, διπλοί αριθμοί παραγγελίας, ποσότητα χωρίς όριο, στρογγυλοποίηση συνόλων, chat που απαντούσε «έκπτωση» στο «my network is slow», διπλό «Hello» στο chat, αντίθεση μικρών γκρι γραμμάτων < 4.5:1, κουμπιά ποσότητας 26px, search στο κινητό χωρίς ορατό αποτέλεσμα, χρώματα swatch αόρατα σε dark mode.

**Κινητό/ταχύτητα**: 4.8 MB → 159 KB σελίδα, 128 φωτογραφίες WebP που φορτώνουν μόνο όταν φαίνονται, 2 στήλες προϊόντων, χωρίς blur/animations, safe-area για iPhone, τιμή κάτω από τον τίτλο στο προϊόν, χωρίς οριζόντιο scroll σε 360/390/768/1366, light+dark.

**Owner tools** (μόνο εσύ τα βλέπεις): Promote (AI posts + εξαγωγές Pinterest/Buffer/Publer/feed), Margins (κόστος, κέρδος, break-even ROAS, max CPA, link προμηθευτή), Go-live checklist.

## 3. Τι να κάνεις εσύ (με σειρά)
1. Άνοιξε `src/v2-script.html` → block `STORE`: email, τηλέφωνο, WhatsApp, επωνυμία, διεύθυνση, ΑΦΜ, ΓΕΜΗ, PayPal.me (ή Stripe link / IBAN). Μέχρι τότε το checkout είναι κλειδωμένο («not taking orders yet»).
2. Owner tools → Go-live checklist: πρέπει όλα πράσινα.
3. Owner tools → Promote → «Write posts» (ανοίγεις το artifact συνδεδεμένος) → κατέβασε Pinterest CSV, Buffer CSVs, Publer CSV, Feed CSV.
4. Λογαριασμοί (όλοι δωρεάν): CJdropshipping, Pinterest business, Buffer, Metricool ή Publer, Google Merchant Center, Meta Commerce Manager.
5. Κάνε το share του artifact «anyone with the link» για να βλέπουν οι feeds τις φωτογραφίες· καλύτερα, ανέβασε το `site/` σε Cloudflare Pages με δικό σου domain και άλλαξε `STORE.siteUrl` / `STORE.imageBase`.
6. Επιβεβαίωσε με τον προμηθευτή: χρόνο παράδοσης Ελλάδα (το site λέει 8–13 ημέρες), IOSS/DDP, CE έγγραφα για θερμοφόρα/μασάζ/υγραντήρα.
