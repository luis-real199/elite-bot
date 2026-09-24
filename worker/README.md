# Nestia checkout server (Cloudflare Worker, δωρεάν)

Δίνει στο site πραγματικό checkout με κάρτα μέσω Stripe Checkout. Τα κλειδιά μένουν εδώ, ποτέ στη σελίδα.

## Βήματα (μία φορά, ~20 λεπτά)

1. Λογαριασμός Stripe (stripe.com) → Developers → API keys → αντέγραψε το **Secret key**.
2. Λογαριασμός Cloudflare (δωρεάν) και `npm i -g wrangler` → `wrangler login`.
3. Στον φάκελο `worker/`:
   ```
   wrangler secret put STRIPE_SECRET_KEY
   wrangler secret put OWNER_EMAIL          # πού έρχονται οι παραγγελίες
   wrangler secret put BREVO_API_KEY        # προαιρετικό: brevo.com free (300 email/μέρα) για ειδοποίηση παραγγελίας
   wrangler deploy
   ```
   Σου δίνει μια διεύθυνση τύπου `https://nestia-api.<user>.workers.dev`.
4. Stripe → Developers → Webhooks → Add endpoint `https://nestia-api.<user>.workers.dev/api/stripe/webhook`, event `checkout.session.completed` → αντέγραψε το signing secret → `wrangler secret put STRIPE_WEBHOOK_SECRET`.
5. Στο `src/v2-script.html` βάλε `payment.apiBase: 'https://nestia-api.<user>.workers.dev'`, ξαναχτίσε (`bash src/build-site.sh`) και ανέβασε το `site/`.
6. Στο `wrangler.toml` βάλε `SITE_URL` και `ALLOWED_ORIGIN` = το domain του site.

Οι τιμές διαβάζονται από `worker/src/products.json` (όχι από τον browser). Όταν αλλάζεις τιμή στο site, άλλαξέ την και εδώ.

Προαιρετικά: KV namespace `ORDERS` για το «Track your order», `ANTHROPIC_API_KEY` για το chat.
