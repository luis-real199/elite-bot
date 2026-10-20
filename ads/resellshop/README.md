# resellshop.xyz — video ad για Meta Ads

Κάθετο video 15" (1080×1920, 30fps, H.264 + AAC) για Reels / Stories, και έκδοση 4:5 (1080×1350) για Feed.
Κύρια έκδοση στα αγγλικά. Όλα τα κείμενα, τα προϊόντα, οι τιμές και τα χρώματα αλλάζουν από ένα JSON, χωρίς να πειράξεις κώδικα.

## Αρχεία

| Αρχείο | Τι είναι |
| --- | --- |
| `out/resellshop-ad-9x16-en.mp4` | Αγγλικό, 9:16, με μουσική. **Αυτό ανεβάζεις στο Ads Manager** (Reels, Stories, Feed). |
| `out/resellshop-ad-9x16-en-silent.mp4` | Ίδιο, χωρίς ήχο, για να βάλεις μουσική από τη βιβλιοθήκη του Meta μέσα στο Ads Manager. |
| `out/resellshop-ad-4x5-en.mp4` | Αγγλικό, 4:5, για Facebook/Instagram Feed. |
| `out/resellshop-ad-9x16-el.mp4` | Ελληνικό, 9:16, με μουσική (για ελληνικό κοινό). |
| `out/cover-9x16.jpg` | Thumbnail (καρέ με τα 4 προϊόντα) για το cover του ad. |
| `ad.html` | Η σκηνή: animation σε καθαρό HTML/CSS/JS, οδηγείται από χρόνο (`seek(t)`). |
| `config.el.json`, `config.en.json` | Κείμενα, προϊόντα, τιμές, χρώματα. |
| `render.mjs` | Βγάζει καρέ-καρέ το `ad.html` με Chromium (Playwright) και τα κωδικοποιεί με ffmpeg. |
| `music.py` | Φτιάχνει το beat και τα sound effects (δικό μας, χωρίς δικαιώματα τρίτων), συγχρονισμένα με το timeline. |

## Σενάριο (15")

| Χρόνος | Σκηνή |
| --- | --- |
| 0.0–2.0 | Hook: «Still paying FULL PRICE? for Netflix, Spotify, ChatGPT & Claude?» |
| 2.0–7.0 | Τα 4 δημοφιλή: Claude Pro, ChatGPT Plus, Spotify Premium, Netflix Premium (με τιμές, αν δοθούν) |
| 7.0–9.6 | Γιατί εμάς: Instant delivery, Secure payment, Support |
| 9.6–11.9 | «+ many more»: marquee με τα υπόλοιπα προϊόντα |
| 11.9–15.0 | CTA: λογότυπο, «Buy now», resellshop.xyz |

## Πώς βάζεις τιμές

Στο `config.en.json` (ή στο `config.el.json` για το ελληνικό), σε κάθε προϊόν πρόσθεσε `price` (και προαιρετικά `was` για διαγραμμένη αρχική τιμή και `period`):

```json
{ "name": "Netflix", "plan": "Premium", "icon": "play", "color": "#e50914",
  "price": "4.99€", "period": "/mo", "was": "17.99€" }
```

Η λίστα `more.items` είναι τα chips του «+ πολλά ακόμα»: άφησε μόνο όσα πουλάς.

## Πώς ξαναβγάζεις το video

```bash
cd ads/resellshop
node render.mjs --config config.en.json --events out/events.json --stills 5.5 --out out/stills   # προαιρετικά: έλεγχος καρέ
python3 -I music.py --events out/events.json --out out/music.wav
node render.mjs --config config.en.json --size 1080x1920 --audio out/music.wav --out out/resellshop-ad-9x16-en.mp4
node render.mjs --config config.en.json --size 1080x1350 --audio out/music.wav --out out/resellshop-ad-4x5-en.mp4
ffmpeg -i out/resellshop-ad-9x16-en.mp4 -c:v copy -an out/resellshop-ad-9x16-en-silent.mp4
```

Χρειάζεται Node 18+, Playwright με Chromium, ffmpeg, Python 3 με numpy. Προεπισκόπηση στον browser: άνοιξε το `ad.html` από έναν τοπικό server (π.χ. `npx serve`), παίζει σε loop. Με `?t=5.5` σταματάει στο συγκεκριμένο δευτερόλεπτο.

## Tips για το Ads Manager

- Campaign objective **Sales** (conversions) με pixel στο resellshop.xyz, ή **Traffic** αν δεν έχεις pixel ακόμα.
- Placements: Advantage+ με το 9:16 για Reels/Stories και το 4:5 για Feed.
- Primary text π.χ.: «Netflix, Spotify, ChatGPT, Claude & 30+ subscriptions for way less. Instant delivery 👉 resellshop.xyz»
- CTA button: **Shop now**.
- Δοκίμασε 2–3 παραλλαγές hook (άλλαξε το `hook` στο JSON και ξαναβγάλε) και άφησε τον αλγόριθμο να βρει τη νικήτρια.
