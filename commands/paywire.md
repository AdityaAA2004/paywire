---
description: Scaffold production-ready Stripe payment integration into the current project. Run /paywire for interactive setup or /paywire <description> to pre-fill from natural language.
argument-hint: "[optional: describe what you want, e.g. 'tiered subscriptions with 14-day trial']"
---

You are the paywire Stripe integration skill. Follow these steps exactly.

## Step 0 — Parse natural language intent (if arguments provided)

If `$ARGUMENTS` is non-empty, run:
```bash
python3 .claude/skills/stripe-payments/scripts/parse_intent.py "$ARGUMENTS"
```
Parse the JSON output. Any keys present are pre-filled answers — skip those questions in Step 2.

## Step 1 — Detect framework

```bash
python3 .claude/skills/stripe-payments/scripts/scaffold.py --detect
```

If the output is `unknown`, ask the user which framework their app uses (fastapi / django / nextjs).

## Step 2 — Gather business decisions

Ask ONLY the questions that were not pre-filled by Step 0. Present them all at once, not one at a time.

| Question | Key | Options / format |
|----------|-----|-----------------|
| Pricing model? | `pricing_model` | one_time / subscription / tiered / usage / per_seat |
| Trial period length in days (0 = no trial)? | `trial_days` | integer |
| Supported currencies (ISO codes)? | `currencies` | e.g. `usd, eur` |
| Which webhook events does your app need? | `events` | show them the enabled events from `config/default-events.yaml` |
| For each enabled event: what happens in your app? | per event | free text |

Show them the contents of `.claude/skills/stripe-payments/config/default-events.yaml` so they can see the options.

## Step 3 — Build config JSON

Write the config file at `.claude/paywire-config.json` (project-scoped, not /tmp) combining:
- The detected framework
- All answers from Step 2
- Events from `config/default-events.yaml` with `enabled: true` for selected events
- Pricing tiers from `config/pricing-tiers.example.yaml` as a starting template

## Step 4 — Render templates

```bash
python3 .claude/skills/stripe-payments/scripts/scaffold.py \
  --framework <detected_framework> \
  --config .claude/paywire-config.json \
  --out ./billing
```

## Step 5 — Fill LLM sections interactively

Read every generated file. For each `# LLM_SECTION_START` / `# LLM_SECTION_END` block:

1. Read the placeholder comment — it describes what the section should do.
2. Use the user's answer from Step 2 for the relevant event.
3. Write idiomatic Python code that:
   - Calls the correct `SubscriptionService` method
   - Updates the correct database models
   - Follows the app's existing patterns (read surrounding code for context)
4. Replace the entire LLM_SECTION block (including markers) with the generated code.

Do NOT leave any `# LLM_SECTION_START` / `# LLM_SECTION_END` markers in the final output.

## Step 6 — Provision Stripe (optional)

Ask: "Do you want to provision Stripe Products, Prices, and a webhook endpoint now? (Requires STRIPE_RESTRICTED_KEY in env)"

If yes AND `STRIPE_RESTRICTED_KEY` is set in the environment:
```bash
python3 .claude/skills/stripe-payments/scripts/provision_stripe.py \
  --config .claude/paywire-config.json
```

If yes BUT the key is not set, tell the user:
```
To provision Stripe resources, export your restricted key and run:

  export STRIPE_RESTRICTED_KEY=rk_test_...
  python3 .claude/skills/stripe-payments/scripts/provision_stripe.py \
    --config .claude/paywire-config.json

This creates Products, Prices, and a webhook endpoint in your Stripe account
and writes the resulting IDs to .env.stripe for you to merge into .env.
```

## Step 7 — Verify

```bash
python3 .claude/skills/stripe-payments/scripts/verify_setup.py
```

Show the user the pass/fail checklist.

## Step 8 — Wire app

Run the wiring script to mount routers, update requirements, and copy the env template:

```bash
python3 .claude/skills/stripe-payments/scripts/wire_app.py
```

This script is idempotent — safe to re-run. It will:
- Insert `billing_router` and `webhook_router` includes into the detected FastAPI entry point
- Append `stripe>=11.0` to `requirements.txt`
- Copy `billing/env.example` to `.env` (only if `.env` does not already exist)

If auto-detection fails (no `main.py` / `app.py` found), re-run with an explicit path:
```bash
python3 .claude/skills/stripe-payments/scripts/wire_app.py --app-file src/your_app.py
```

## Step 9 — Run Alembic migration

If `alembic.ini` exists in the project root, run the migration:

```bash
if [ -f alembic.ini ]; then
  alembic revision --autogenerate -m "add stripe billing tables"
  alembic upgrade head
fi
```

If Alembic is not yet initialised, tell the user:
```
Alembic is not initialised. To create the billing tables, run:

  alembic init alembic          # one-time setup
  # edit alembic/env.py to point at your SQLAlchemy Base
  alembic revision --autogenerate -m "add stripe billing tables"
  alembic upgrade head
```

## Step 10 — Done

Tell the user:
```
Billing wired. One manual step remains before local testing:

  stripe listen --forward-to localhost:8000/webhooks/stripe

Copy the whsec_... printed on startup to STRIPE_WEBHOOK_SECRET_TEST in .env,
then verify the integration end-to-end:

  stripe trigger checkout.session.completed
```

## Security rules — never override

- Always use `STRIPE_RESTRICTED_KEY` (rk_ prefix) — never sk_ in generated code.
- Never pass `payment_method_types` to checkout sessions.
- Always use Stripe Checkout or Payment Element — never raw card input fields (SAQ A).
- Webhook handler always reads raw bytes (`await request.body()`) before verification.
- Idempotency check + business logic always run in the same DB transaction.
- Generated code never stores PAN, CVV, or full card data.
