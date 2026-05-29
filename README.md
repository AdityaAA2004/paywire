# paywire

A Claude Code skill that scaffolds production-ready Stripe payment integration into an existing FastAPI app.

---

## The idea

Wiring Stripe correctly is repetitive and easy to get wrong — raw body parsing, webhook signature verification, idempotency, and event ordering all follow the same pattern every time. **paywire handles that ~70% deterministically via templates.** The remaining ~30% — what your app actually does when a payment succeeds — is filled in by Claude Code based on your answers.

```
Templates (always correct)          You decide
──────────────────────────          ──────────
Webhook signature verification  +   What happens when invoice.paid fires?
Idempotency table + check       +   Grace period on payment failure?
Raw body middleware              +   Which DB columns to update?
Checkout session endpoint       +   What emails to send?
Customer portal endpoint
SDK initialization
```

---

## Install

```bash
# From your project root
npx skills add github.com/your-org/paywire
```

Or manually copy this directory into `.claude/skills/stripe-payments/`.

---

## Usage

In Claude Code, either:

```
/paywire
```
→ Starts an interactive setup (Claude asks you the billing questions one by one)

```
/paywire subscription billing, 14-day trial, USD only
```
→ Pre-fills what it can from your description, asks only for the gaps

Or just say it in plain language:
> "add Stripe billing to this app"
> "set up Stripe subscriptions with a free trial"

---

## What gets generated

Running the skill scaffolds a complete `billing/` module into your project:

```
billing/
├── models.py                   SQLAlchemy models (StripeEvent, StripeCustomer, StripeSubscription)
├── schemas.py                  Pydantic request/response types
├── dependencies.py             FastAPI DI wiring
├── router.py                   POST /billing/checkout, POST /billing/portal
├── webhook.py                  Stripe webhook endpoint (all security requirements enforced)
├── dispatcher.py               Event handler registry
├── handlers/
│   ├── base.py                 StripeEventHandler protocol
│   ├── checkout_handler.py     checkout.session.completed
│   ├── invoice_handler.py      invoice.paid, invoice.payment_failed
│   └── subscription_handler.py customer.subscription.deleted (+ updated, trial_will_end if enabled)
└── services/
    ├── billing_service.py      All Stripe SDK calls (isolated here, nowhere else)
    └── subscription_service.py Your app's subscription logic (filled by Claude Code)
```

Plus shared files: `.env.example`, `docker-compose.stripe-mock.yml`, `README.stripe.md`.

---

## How the skill works

```
/paywire "14-day trial subscriptions"
        │
        ▼
parse_intent.py          Extracts trial_days=14, pricing_model=subscription from your text
        │
        ▼
scaffold.py --detect     Sniffs requirements.txt for fastapi / manage.py / next.config.js
        │
        ▼
Claude asks questions     Only for what wasn't in your description
(pricing model, events, what your app does per event)
        │
        ▼
scaffold.py --render     Jinja2 renders all templates with your config
        │
        ▼
Claude fills LLM sections  Writes the event handler bodies based on your answers
        │
        ▼
provision_stripe.py      Creates Products, Prices, WebhookEndpoint in your Stripe account
        │
        ▼
verify_setup.py          Smoke-tests the wiring against stripe-mock
```

---

## What the skill will not do

- **Stripe Connect** marketplace flows (destination charges, split payments) — too varied to template safely
- **Stripe Tax** jurisdiction registration — requires manual steps
- **Raw card input forms** — by design; generated code always uses Stripe Checkout or Payment Element (keeps you in SAQ A PCI scope)
- **Other payment providers** (Braintree, PayPal, Adyen) — planned for a future phase

---

## Repository structure

```
paywire/backend/
├── SKILL.md                    The skill manifest — Claude Code reads this to orchestrate everything
├── commands/paywire.md         The /paywire slash command definition
├── scripts/
│   ├── parse_intent.py         Natural language → structured config (no API calls, regex only)
│   ├── scaffold.py             Framework detection + Jinja2 template rendering
│   ├── provision_stripe.py     Idempotent Stripe Product/Price/Webhook creation
│   ├── generate_fixtures.py    stripe-mock + Stripe CLI fixture JSON for testing
│   └── verify_setup.py         Smoke test checklist
├── templates/
│   ├── fastapi/                Jinja2 templates for FastAPI (current supported framework)
│   └── shared/                 env.example, docker-compose, README
├── config/
│   ├── default-events.yaml     Webhook event list with enable/disable flags
│   └── pricing-tiers.example.yaml  Starter pricing config template
└── references/                 Detailed docs loaded by Claude Code on demand
    ├── webhook-events.md       Event ordering, invoice.paid vs invoice.payment_succeeded
    ├── pci-saq-decision.md     SAQ A vs A-EP scope guide
    └── api-version.md          Stripe API version notes
```

---

## Extending the skill

**Add a new webhook event:**
1. Add it to `config/default-events.yaml`
2. Add a handler class to the relevant template in `templates/fastapi/handlers/`
3. Register it in `templates/fastapi/dependencies.py.j2`

**Add a new framework (Django, Next.js):**
1. Create `templates/<framework>/` mirroring the `fastapi/` structure
2. Update `scaffold.py` to include it in `SUPPORTED_FRAMEWORKS`
3. Update `SKILL.md` detection + render steps

---

## Testing

```bash
# Script unit tests (no external dependencies)
pytest tests/test_parse_intent.py tests/test_scaffold_detect.py

# Template rendering + syntax validation
pytest tests/test_template_rendering.py tests/test_security_invariants.py

# Integration test against stripe-mock
docker compose -f templates/shared/docker-compose.stripe-mock.yml up -d
python3 scripts/verify_setup.py
```

See [`tests/e2e/`](tests/e2e/) for end-to-end Claude Code skill testing setup.
