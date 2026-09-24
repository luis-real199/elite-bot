/* Nestia checkout server: one Cloudflare Worker (free tier).
   Routes the shop page already calls:
     POST /api/checkout  -> creates a Stripe Checkout Session, returns {url}
     POST /api/stripe/webhook -> Stripe tells us a session was paid; we email the order to the owner
     GET  /api/track?order=NST-...&email=... -> order status from KV (if bound)
     POST /api/support   -> replies through the Claude API (optional)
   Secrets (wrangler secret put): STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, OWNER_EMAIL,
   BREVO_API_KEY (optional, order emails), ANTHROPIC_API_KEY (optional, chat).
   Vars in wrangler.toml: SITE_URL, ALLOWED_ORIGIN, SHIP_FEE, FREE_SHIP_OVER, EXPRESS_FEE. */

import PRODUCTS from './products.json';

const json = (data, status = 200, origin = '*') => new Response(JSON.stringify(data), {
  status, headers: { 'content-type': 'application/json', 'access-control-allow-origin': origin, 'access-control-allow-headers': 'content-type' }
});
const tierDisc = q => q >= 3 ? .15 : q === 2 ? .10 : 0;
const cents = n => Math.round(n * 100);

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const origin = env.ALLOWED_ORIGIN || '*';
    if (req.method === 'OPTIONS') return json({}, 204, origin);

    if (url.pathname === '/api/checkout' && req.method === 'POST') return checkout(req, env, origin);
    if (url.pathname === '/api/stripe/webhook' && req.method === 'POST') return webhook(req, env);
    if (url.pathname === '/api/track') return track(url, env, origin);
    if (url.pathname === '/api/support' && req.method === 'POST') return support(req, env, origin);
    return json({ error: 'Not found' }, 404, origin);
  }
};

async function checkout(req, env, origin) {
  let order;
  try { order = await req.json(); } catch { return json({ error: 'Bad request' }, 400, origin); }
  if (!order || !Array.isArray(order.items) || !order.items.length || !order.email) return json({ error: 'Empty order' }, 400, origin);

  // Prices come from our own list, never from the browser.
  const lines = [];
  let sub = 0;
  for (const it of order.items) {
    const p = PRODUCTS[it.product];
    const qty = Math.min(20, Math.max(1, Number(it.qty) || 1));
    if (!p) return json({ error: `Unknown product ${it.product}` }, 400, origin);
    const unit = Math.round(p.price * (1 - tierDisc(qty)) * 100) / 100;
    sub += unit * qty;
    lines.push({
      quantity: qty,
      price_data: { currency: 'eur', unit_amount: cents(unit), product_data: { name: p.name + (it.variant ? ` (${it.variant})` : ''), metadata: { sku: it.sku || '', supplier: p.supplier || '' } } }
    });
  }
  const shipFee = Number(env.SHIP_FEE || 3.90), freeOver = Number(env.FREE_SHIP_OVER || 39), express = Number(env.EXPRESS_FEE || 6.90);
  const ship = (sub >= freeOver ? 0 : shipFee) + (order.shipping === 'express' ? express : 0);

  const ref = 'NST-' + Date.now().toString(36).toUpperCase().slice(-6);
  const body = new URLSearchParams();
  body.set('mode', 'payment');
  body.set('customer_email', order.email);
  body.set('success_url', `${env.SITE_URL}?paid=${ref}`);
  body.set('cancel_url', `${env.SITE_URL}?cancelled=1`);
  body.set('client_reference_id', ref);
  body.set('shipping_address_collection[allowed_countries][0]', 'GR');
  ['CY','AT','BE','BG','HR','CZ','DK','EE','FI','FR','DE','HU','IE','IT','LV','LT','LU','MT','NL','PL','PT','RO','SK','SI','ES','SE'].forEach((c, i) => body.set(`shipping_address_collection[allowed_countries][${i + 1}]`, c));
  body.set('shipping_options[0][shipping_rate_data][type]', 'fixed_amount');
  body.set('shipping_options[0][shipping_rate_data][fixed_amount][amount]', String(cents(ship)));
  body.set('shipping_options[0][shipping_rate_data][fixed_amount][currency]', 'eur');
  body.set('shipping_options[0][shipping_rate_data][display_name]', order.shipping === 'express' ? 'Faster shipping (5-8 days)' : 'Standard delivery (8-13 days)');
  body.set('phone_number_collection[enabled]', 'true');
  body.set('metadata[ref]', ref);
  body.set('metadata[note]', String(order.note || '').slice(0, 400));
  body.set('metadata[items]', JSON.stringify(order.items.map(i => [i.sku, i.qty])).slice(0, 490));
  lines.forEach((l, i) => {
    body.set(`line_items[${i}][quantity]`, String(l.quantity));
    body.set(`line_items[${i}][price_data][currency]`, 'eur');
    body.set(`line_items[${i}][price_data][unit_amount]`, String(l.price_data.unit_amount));
    body.set(`line_items[${i}][price_data][product_data][name]`, l.price_data.product_data.name);
    body.set(`line_items[${i}][price_data][product_data][metadata][sku]`, l.price_data.product_data.metadata.sku);
  });

  const r = await fetch('https://api.stripe.com/v1/checkout/sessions', {
    method: 'POST', headers: { authorization: `Bearer ${env.STRIPE_SECRET_KEY}`, 'content-type': 'application/x-www-form-urlencoded' }, body
  });
  const s = await r.json();
  if (!r.ok) return json({ error: s.error?.message || 'Stripe refused the session' }, 502, origin);
  if (env.ORDERS) await env.ORDERS.put(ref, JSON.stringify({ ref, email: order.email, status: 'awaiting_payment', created: new Date().toISOString(), session: s.id, order }), { expirationTtl: 60 * 60 * 24 * 90 });
  return json({ url: s.url, ref }, 200, origin);
}

async function webhook(req, env) {
  const payload = await req.text();
  const sig = req.headers.get('stripe-signature') || '';
  if (!(await verifyStripe(payload, sig, env.STRIPE_WEBHOOK_SECRET))) return new Response('bad signature', { status: 400 });
  const ev = JSON.parse(payload);
  if (ev.type !== 'checkout.session.completed') return new Response('ok');
  const s = ev.data.object;
  const ref = s.client_reference_id || s.metadata?.ref || s.id;
  const addr = s.shipping_details?.address || s.customer_details?.address || {};
  const summary = [
    `Order ${ref} PAID ${(s.amount_total / 100).toFixed(2)} ${s.currency.toUpperCase()}`,
    `Items: ${s.metadata?.items || ''}`,
    `Name: ${s.shipping_details?.name || s.customer_details?.name || ''}`,
    `Address: ${[addr.line1, addr.line2, addr.postal_code, addr.city, addr.country].filter(Boolean).join(', ')}`,
    `Phone: ${s.customer_details?.phone || ''}`, `Email: ${s.customer_details?.email || ''}`,
    s.metadata?.note ? `Note: ${s.metadata.note}` : ''
  ].filter(Boolean).join('\n');
  if (env.ORDERS) {
    const prev = JSON.parse((await env.ORDERS.get(ref)) || '{}');
    await env.ORDERS.put(ref, JSON.stringify({ ...prev, ref, status: 'paid', paid: new Date().toISOString(), summary }), { expirationTtl: 60 * 60 * 24 * 180 });
  }
  if (env.BREVO_API_KEY && env.OWNER_EMAIL) {
    await fetch('https://api.brevo.com/v3/smtp/email', {
      method: 'POST', headers: { 'api-key': env.BREVO_API_KEY, 'content-type': 'application/json' },
      body: JSON.stringify({ sender: { email: env.OWNER_EMAIL, name: 'Nestia orders' }, to: [{ email: env.OWNER_EMAIL }], subject: `New paid order ${ref}`, textContent: summary })
    });
  }
  return new Response('ok');
}

async function verifyStripe(payload, header, secret) {
  if (!secret) return false;
  const parts = Object.fromEntries(header.split(',').map(kv => kv.split('=')));
  if (!parts.t || !parts.v1) return false;
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const mac = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(`${parts.t}.${payload}`));
  const hex = [...new Uint8Array(mac)].map(b => b.toString(16).padStart(2, '0')).join('');
  return hex === parts.v1 && Math.abs(Date.now() / 1000 - Number(parts.t)) < 300;
}

async function track(url, env, origin) {
  const ref = (url.searchParams.get('order') || '').trim().toUpperCase(), email = (url.searchParams.get('email') || '').trim().toLowerCase();
  if (!env.ORDERS) return json({ error: 'Tracking is not set up yet.' }, 404, origin);
  const o = JSON.parse((await env.ORDERS.get(ref)) || 'null');
  if (!o || (o.email || '').toLowerCase() !== email) return json({ error: 'Order not found.' }, 404, origin);
  const steps = [
    { title: 'Order received', note: o.status === 'awaiting_payment' ? 'Waiting for payment' : 'Paid', done: true },
    { title: 'Dispatched', note: o.tracking ? `Tracking ${o.tracking}` : 'Leaves the warehouse within 3 working days of payment', done: !!o.tracking },
    { title: 'Delivered', note: '', done: o.status === 'delivered' }
  ];
  return json({ steps, tracking: o.tracking || null }, 200, origin);
}

async function support(req, env, origin) {
  if (!env.ANTHROPIC_API_KEY) return json({ error: 'Assistant not configured' }, 503, origin);
  const { messages } = await req.json();
  const r = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST', headers: { 'x-api-key': env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01', 'content-type': 'application/json' },
    body: JSON.stringify({ model: 'claude-haiku-4-5-20251001', max_tokens: 300, system: env.SUPPORT_RULES || 'You are the help assistant of a small EU online shop. Answer briefly and only about delivery, returns and payment.', messages: (messages || []).slice(-10) })
  });
  const d = await r.json();
  if (!r.ok) return json({ error: d.error?.message || 'Assistant unavailable' }, 502, origin);
  return json({ reply: d.content?.map(c => c.text).join('') || '' }, 200, origin);
}
