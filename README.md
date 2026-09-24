# Nestia — e-shop σε μία σελίδα

Το κατάστημα είναι ένα αρχείο HTML (χωρίς backend) με 16 προϊόντα, καλάθι, checkout, πολιτικές, chat βοήθειας και «Owner tools» που γράφουν posts για κάθε προϊόν και εξάγουν product feed.

Live (claude.ai artifact): https://claude.ai/artifact/5a1yyni8osm8XztdyPUJcX

## Αρχεία

| Αρχείο | Τι είναι |
| --- | --- |
| `src/v2-head.html` | CSS + HTML της σελίδας |
| `src/v2-script.html` | Ρυθμίσεις (`STORE`), προϊόντα (`P`, `DETAIL`, `VAR`, `SAFETY`) και όλη η λογική |
| `src/build-site.sh` | Φτιάχνει `v2.html` (για το artifact) και `site/index.html` (για κανονικό hosting) |
| `site/index.html` + `site/img/` | Έτοιμο για GitHub Pages / Cloudflare Pages / οποιονδήποτε web server |

Αλλαγές γίνονται **μόνο** στα `src/` και μετά `bash src/build-site.sh`.

## Πριν δεχτείς παραγγελίες

Όλα διαβάζονται από το block `STORE` στην αρχή του `src/v2-script.html`. Μέχρι να συμπληρωθούν **ταυτότητα + επικοινωνία + τρόπος πληρωμής**, το κουμπί παραγγελίας μένει κλειστό και το site λέει ότι δεν δέχεται ακόμη παραγγελίες.

```js
email: 'hello@nestia.gr',          // email υποστήριξης
phone: '+30 69 1234 5678',          // τηλέφωνο (υποχρεωτικό για ελληνικό e-shop)
whatsapp: '306912345678',           // ψηφία με κωδικό χώρας, χωρίς +
company: 'ΕΠΩΝΥΜΙΑ ΙΚΕ', address: 'Οδός 1, 10563 Αθήνα', vat: 'EL123456789', gemi: '123456789000',
payment: { paypalMe: 'nestia', stripeLink: '', iban: 'GR16 ... (Nestia)' },
```

Το checklist «Go-live» μέσα στα Owner tools δείχνει με πράσινο/κόκκινο τι λείπει.

## Πώς δουλεύει η παραγγελία χωρίς server

1. Ο πελάτης συμπληρώνει στοιχεία και πατάει «Order with obligation to pay».
2. Η σελίδα φτιάχνει αριθμό παραγγελίας (NST-XXXXXX) και το κείμενο της παραγγελίας.
3. Το στέλνει με WhatsApp (έτοιμο link) ή email και πληρώνει με PayPal.me / Stripe link / IBAN.
4. Εσύ επιβεβαιώνεις γραπτά, παραγγέλνεις από τον προμηθευτή (το link AliExpress κάθε προϊόντος είναι στα Owner tools › Margins) και στέλνεις το tracking.

Αν αργότερα βάλεις δικό σου checkout server (Stripe/PayPal hosted page), ορίζεις `payment.apiBase` και το checkout γίνεται «PAY» με κάρτα.

## Owner tools (μόνο για τον ιδιοκτήτη)

Φαίνονται όταν ανοίγεις το artifact συνδεδεμένος ως ιδιοκτήτης (ή τοπικά από file://):

- **Promote**: γράφει με ένα κλικ TikTok script, Instagram caption, Facebook post, Pinterest pin και X post για όλα τα προϊόντα (χρειάζεται το artifact στο claude.ai). Εξάγει `nestia-feed.csv` (Google Merchant / Meta / Pinterest), `nestia-posts.csv` (Publer / Metricool / Buffer) και `nestia-posts.md`.
- **Margins**: κόστος, κέρδος, break-even ROAS, max CPA, link προμηθευτή.
- **Go-live checklist**: τι λείπει νομικά και τεχνικά.

## Hosting σε δικό σου domain

`site/` είναι στατικό: ανέβασέ το σε GitHub Pages ή Cloudflare Pages (δωρεάν). Μετά άλλαξε `STORE.siteUrl` και `STORE.imageBase` στο domain σου και ξαναφτιάξε το feed.
