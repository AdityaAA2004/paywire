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

Write a temporary config file at `/tmp/paywire-config.json` combining:
- The detected framework
- All answers from Step 2
- Events from `config/default-events.yaml` with `enabled: true` for selected events
- Pricing tiers from `config/pricing-tiers.example.yaml` as a starting template

## Step 4 — Render templates

```bash
python3 .claude/skills/stripe-payments/scripts/scaffold.py \
  --framework <detected_framework> \
  --config /tmp/paywire-config.json \
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

If yes:
```bash
python3 .claude/skills/stripe-payments/scripts/provision_stripe.py \
  --config /tmp/paywire-config.json
```

## Step 7 — Verify

```bash
python3 .claude/skills/stripe-payments/scripts/verify_setup.py
```

Show the user the pass/fail checklist.

## Step 8 — Done

Print:
```
Stripe billing scaffolded. Next steps:

1. Mount the routers in your FastAPI app:
   from billing.router import router as billing_router
   from billing.webhook import router as webhook_router
   app.include_router(billing_router, prefix="/billing")
   app.include_router(webhook_router, prefix="/webhooks")

2. Run Alembic migration:
   alembic revision --autogenerate -m "add stripe billing tables"
   alembic upgrade head

3. Forward webhooks locally:
   stripe listen --forward-to localhost:8000/webhooks/stripe
   (copy the whsec_... to STRIPE_WEBHOOK_SECRET_TEST in .env)

4. Trigger a test event:
   stripe trigger checkout.session.completed
```

## Security rules — never override

- Always use `STRIPE_RESTRICTED_KEY` (rk_ prefix) — never sk_ in generated code.
- Never pass `payment_method_types` to checkout sessions.
- Always use Stripe Checkout or Payment Element — never raw card input fields (SAQ A).
- Webhook handler always reads raw bytes (`await request.body()`) before verification.
- Idempotency check + business logic always run in the same DB transaction.
- Generated code never stores PAN, CVV, or full card data.
