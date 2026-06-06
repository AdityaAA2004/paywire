---
name: stripe-payments
description: >
  Scaffold production-ready Stripe payment integration into an existing FastAPI app.
  Generates idempotent webhook handlers, checkout session endpoints, customer portal,
  SQLAlchemy models, and Stripe-side provisioning. Follows SOLID principles throughout.
  Use when the user wants to add Stripe, billing, subscriptions, payments, or webhooks.
allowed-tools: Read Write Bash(python3:*, pip:*, stripe:*, docker:*, alembic:*)
compatibility: claude-code>=1.0
---

# stripe-payments

A deterministic scaffold skill for Stripe payment integration. ~70% of a correct Stripe
integration is always the same code (webhook verification, idempotency, raw-body handling).
This skill generates that part correctly every time. The remaining ~30% (business logic)
is filled interactively by Claude Code based on your answers.

## When to invoke

Trigger this skill when the user says any of the following:
- "add Stripe billing / payments / subscriptions"
- "integrate Stripe"
- "add payment processing"
- "set up webhooks for Stripe"
- "wire up Stripe checkout"
- "add a billing module"

Also triggered by the `/paywire` slash command.

## Orchestration flow

### Step 1 — Detect framework

```bash
python3 .claude/skills/stripe-payments/scripts/scaffold.py --detect
```

Prints: `fastapi` | `django` | `nextjs` | `unknown`
If unknown, ask the user which framework to target.

### Step 2 — Parse natural language (if /paywire was called with arguments)

```bash
python3 .claude/skills/stripe-payments/scripts/parse_intent.py "<user_arguments>"
```

Output is partial JSON. Keys present are pre-answered — skip those questions in Step 3.

### Step 3 — Gather business decisions

Collect the following. Ask only for what wasn't answered in Step 2. Present all at once.

**Required:**
1. **Pricing model** — one_time | subscription | tiered | usage | per_seat
2. **Trial length** — integer days (0 = no trial)
3. **Currencies** — ISO codes, e.g. `usd` or `usd,eur`
4. **Webhook events** — show `config/default-events.yaml` and ask which to enable
5. **Per-event business logic** — for each enabled event, ask: "What happens in your app when X fires?"

**Example per-event questions:**
- `checkout.session.completed`: "When a customer completes checkout, what should your app do? (e.g., mark user.subscription_active = True, grant feature flags)"
- `invoice.paid`: "When a subscription renews, what should your app do?"
- `invoice.payment_failed`: "When a payment fails, what's your grace period policy? How long before access is revoked?"
- `customer.subscription.deleted`: "When a subscription is cancelled, what should your app revoke?"

### Step 4 — Render templates

Write config to `.claude/paywire-config.json` (project-scoped — not /tmp), then:

```bash
python3 .claude/skills/stripe-payments/scripts/scaffold.py \
  --framework <framework> \
  --config .claude/paywire-config.json \
  --out ./billing
```

Generated files:
```
billing/
├── models.py               ← SQLAlchemy: StripeEvent, StripeCustomer, StripeSubscription
├── schemas.py              ← Pydantic I/O types
├── dependencies.py         ← FastAPI DI wiring
├── router.py               ← /billing/checkout + /billing/portal
├── webhook.py              ← Signature verification + idempotent dispatch
├── dispatcher.py           ← Handler registry (OCP)
├── handlers/
│   ├── base.py             ← StripeEventHandler protocol
│   ├── checkout_handler.py
│   ├── invoice_handler.py
│   └── subscription_handler.py
└── services/
    ├── billing_service.py      ← All Stripe SDK calls (DIP)
    └── subscription_service.py ← App-side logic (LLM sections here)
```

### Step 5 — Fill LLM sections

After scaffold.py runs, it prints the location of every `# LLM_SECTION_START` marker.

For each section:
1. Read the placeholder comment (it describes what's needed and provides context).
2. Use the user's answer from Step 3 for the relevant event.
3. Generate idiomatic, framework-appropriate Python code.
4. Replace the entire LLM_SECTION block (markers included) with the generated code.
5. Ensure filled code calls `SubscriptionService` methods — not Stripe SDK directly (DIP).

Do NOT leave any `# LLM_SECTION_START` / `# LLM_SECTION_END` markers in output files.

### Step 6 — Provision Stripe (optional)

Ask: "Provision Stripe Products/Prices/WebhookEndpoint now? (Needs STRIPE_RESTRICTED_KEY)"

If yes AND `STRIPE_RESTRICTED_KEY` is set:
```bash
python3 .claude/skills/stripe-payments/scripts/provision_stripe.py \
  --config .claude/paywire-config.json
```

Outputs `.env.stripe` with created IDs. If the key is not set, print the exact
`export STRIPE_RESTRICTED_KEY=rk_test_...` + command so the user can run it later.

### Step 7 — Generate test fixtures

```bash
python3 .claude/skills/stripe-payments/scripts/generate_fixtures.py --out ./fixtures
```

### Step 8 — Verify

```bash
python3 .claude/skills/stripe-payments/scripts/verify_setup.py
```

Show pass/fail checklist. If stripe-mock is not running, suggest:
```bash
docker compose -f billing/docker-compose.stripe-mock.yml up -d
```

### Step 9 — Wire app

```bash
python3 .claude/skills/stripe-payments/scripts/wire_app.py
```

Idempotent. Inserts router includes into the FastAPI entry point, appends `stripe>=11.0`
to `requirements.txt`, and copies `billing/env.example` to `.env` if it does not exist.
If auto-detection fails, re-run with `--app-file <path>`.

### Step 10 — Run Alembic migration

```bash
if [ -f alembic.ini ]; then
  alembic revision --autogenerate -m "add stripe billing tables"
  alembic upgrade head
fi
```

If `alembic.ini` is absent, print setup instructions (see `commands/paywire.md` Step 9).

### Step 11 — Done

Tell the user the one remaining manual step:
```
stripe listen --forward-to localhost:8000/webhooks/stripe
# Copy whsec_... → STRIPE_WEBHOOK_SECRET_TEST in .env
stripe trigger checkout.session.completed
```

---

## Reference material (load on demand)

Do NOT load these files by default — they are large. Load only when relevant:

| File | When to load |
|------|-------------|
| `references/webhook-events.md` | User asks about event ordering, which events to use, `invoice.paid` vs `invoice.payment_succeeded` |
| `references/pci-saq-decision.md` | User asks about PCI compliance, SAQ scope, card data storage |
| `references/api-version.md` | User asks about API versioning, upgrading Stripe API version |

---

## Security rules (non-negotiable — never deviate)

1. **Restricted keys only.** Generated code always reads `STRIPE_RESTRICTED_KEY` (rk_ prefix).
   Never generate code that uses `sk_` keys in application logic.
2. **No `payment_method_types`.** Never pass this parameter to Checkout Sessions.
   Dashboard-level dynamic payment methods control which methods appear.
3. **SAQ A only.** Always use Stripe Checkout (hosted), Payment Element, or Stripe Elements
   for card input. Never generate raw HTML card input fields. If asked, refuse and explain.
4. **Raw body before verification.** The webhook endpoint always reads `await request.body()`
   BEFORE any JSON parsing. Never generate code that reads `request.json()` for webhooks.
5. **Idempotency transaction.** The `StripeEvent` insert and the business side effect always
   run in the SAME database transaction. Never generate code that splits them.
6. **400 on signature failure.** Webhook handlers return 400, not 500, on verification errors.
   500 causes Stripe to retry; 400 stops retries for spoofed events.
7. **No PAN storage.** Generated models never store full card numbers, CVV/CVC, or full
   magnetic stripe data. Only: `last4`, `brand`, `exp_month`, `exp_year`, `customer.id`.

---

## SOLID principles — applied to all generated code

- **SRP**: `webhook.py` verifies + dispatches only. `billing_service.py` calls Stripe only.
  `subscription_service.py` updates app state only. Each handler class handles one event.
- **OCP**: `WebhookDispatcher` uses a registry. New events = new handler + register call.
  No changes to dispatcher logic.
- **LSP**: All handlers implement `StripeEventHandler` protocol with identical contract.
- **ISP**: Handlers depend on `StripeCheckoutProtocol` or `StripeSubscriptionProtocol`,
  not the full `BillingService`.
- **DIP**: `BillingService` receives `stripe.Stripe` via constructor. FastAPI `Depends()`
  wires everything. Tests override providers without touching business code.

---

## Event coverage

Events are defined in `config/default-events.yaml` with a `has_template` flag:

**`has_template: true` — dedicated, SOLID handler generated:**
- `checkout.session.completed` — provision access after checkout
- `invoice.paid` — activate or renew subscription
- `invoice.payment_failed` — begin dunning / grace period
- `customer.subscription.deleted` — revoke access
- `customer.subscription.updated` *(disabled by default)*
- `customer.subscription.trial_will_end` *(disabled by default)*

**`has_template: false` — generic stub generated, Claude Code fills logic:**
- `customer.created`, `customer.deleted`, `customer.updated`
- `charge.refunded`, `charge.dispute.created`
- `payment_intent.succeeded`, `payment_intent.payment_failed`

**Events not in `default-events.yaml`:** the dispatcher safely ignores them — logs a skip
message and returns 200 to Stripe. No failures. Users can always add a handler manually
following the OCP pattern (new class implementing `StripeEventHandler` + register it).

When the user enables an event with `has_template: false`, generate a `generic_handler.py`
from `templates/fastapi/handlers/generic_handler.py.j2` and fill its LLM_SECTION
based on the user's description of what that event should do in their app.

## Scope limits

**Do not scaffold (tell the user to consult Stripe docs instead):**
- Stripe Connect marketplace flows (destination charges, separate charges + transfers)
- Stripe Tax jurisdiction registration
- Stripe Terminal (in-person payments)
- Stripe Issuing
- Adyen, Braintree, Square, PayPal (Phase 2 of this skill)

For Connect onboarding boilerplate (Express accounts only), print a "limited support" note
and generate only the OAuth redirect + account status webhook handlers.
