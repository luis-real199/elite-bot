# Blacklist Records — Demo Portal

Site όπου οι καλλιτέχνες ανεβάζουν τα κομμάτια τους, και dashboard όπου τα ακούς εσύ.

- `index.html`: δημόσια σελίδα με την υδρόγειο που γυρίζει (Ελλάδα και Κύπρος φωτισμένες) και φόρμα για demos
- `admin.html`: το δικό σου dashboard, όπου ακούς, βάζεις αστέρια, κάνεις shortlist και κρατάς σημειώσεις
- `config.js`: εδώ μπαίνουν τα στοιχεία του Supabase
- `supabase/setup.sql`: δημιουργεί τη βάση και τον χώρο για τα αρχεία

Δεν χρειάζεται build: είναι σκέτο HTML/CSS/JS, οπότε ανεβαίνει οπουδήποτε.

## Στήσιμο (περίπου 10 λεπτά, δωρεάν)

### 1. Supabase (βάση και αρχεία)
1. Κάνε λογαριασμό στο https://supabase.com και μετά **New project**.
2. Άνοιξε το `supabase/setup.sql` και άλλαξε στην τελευταία γραμμή το `to-email-sou@example.com` με το email σου.
3. Supabase, **SQL Editor**, **New query**: επικόλλησε όλο το αρχείο και πάτα **Run**.
4. **Authentication**, **Users**, **Add user**: βάλε το ίδιο email και έναν κωδικό, με ενεργό το **Auto Confirm User**.
5. **Authentication**, **Sign In / Providers**: κλείσε το **Allow new users to sign up**.
6. **Project Settings**, **API**: αντέγραψε το **Project URL** και το **anon / publishable key** στο `config.js`.

### 2. Ανέβασμα του site
- **Vercel:** https://vercel.com, **Add New Project**, διάλεξε αυτό το repo, Framework **Other**, **Deploy**.
- **Netlify:** σύρε τον φάκελο στο https://app.netlify.com/drop.

Το dashboard σου είναι στο `https://to-site-sou/admin.html`.

## Dashboard: συντομεύσεις (σε υπολογιστή)
`Space` play/pause · `N`/`P` επόμενο/προηγούμενο · `←`/`→` ±10s · `S` shortlist · `X` απόρριψη · `1–5` αστέρια

Όταν τελειώνει ένα κομμάτι, παίζει αυτόματα το επόμενο. Τα demos με κατάσταση «Νέο» γίνονται «Ακούστηκε» μόλις τα πατήσεις play.

## Όρια του δωρεάν Supabase
- 1 GB αποθήκευση: περίπου 100 MP3 ή 20 WAV. Μετά υπάρχει το Pro (25$ τον μήνα, 100 GB).
- Έως 50 MB ανά αρχείο. Για μεγαλύτερα WAV, οι καλλιτέχνες στέλνουν link.
- Αν δεν μπει κανείς για μία εβδομάδα, το project «κοιμάται». Το ξυπνάς με ένα κλικ από το Supabase.
