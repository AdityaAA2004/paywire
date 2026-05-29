# Stripe Webhook Event Reference

Loaded on demand by SKILL.md when the user asks about event selection or ordering.

## Subscription Lifecycle — Correct Event Order

Stripe does **not** guarantee event delivery order. Design handlers to be idempotent and
independently complete (fetch the resource fresh from Stripe — never trust payload data).

### New Subscription (with trial)
```
customer.subscription.created        status=trialing
customer.subscription.trial_will_end  (3 days before trial end)
invoice.created                       (at trial end — zero-amount)
invoice.finalized
invoice.paid                          status=paid, amount_paid=0
customer.subscription.updated        status=active
```

### New Subscription (no trial, immediate payment)
```
customer.subscription.created        status=active
invoice.created
invoice.finalized
payment_intent.created
payment_intent.processing
payment_intent.succeeded
invoice.paid
checkout.session.completed           (if using Stripe Checkout)
```

### Monthly Renewal (successful)
```
invoice.created
invoice.finalized
invoice.upcoming                     (sent ~1 hour before finalization on some plans)
payment_intent.created
payment_intent.succeeded
invoice.paid
customer.subscription.updated        current_period_end advances
```

### Payment Failure + Retry
```
invoice.payment_failed               attempt_count=1
invoice.payment_action_required      (if SCA/3DS required)
--- (Stripe retries per dunning schedule) ---
invoice.payment_failed               attempt_count=2
invoice.payment_failed               attempt_count=3
customer.subscription.updated        status=past_due → unpaid (after max retries)
```

### Cancellation (immediate)
```
customer.subscription.updated        cancel_at_period_end=true (if scheduled)
customer.subscription.deleted        status=canceled
invoice.voided                       (if unpaid invoices existed)
```

## Critical Distinctions

### `invoice.paid` vs `invoice.payment_succeeded`
- **Use `invoice.paid`** to trigger access provisioning. It fires on both successful payment
  AND zero-amount invoices (trials, 100% coupons) — it's the only reliable signal that a
  billing period is covered.
- `invoice.payment_succeeded` only fires when money actually moves. It misses free trials.

### `checkout.session.completed` vs `payment_intent.succeeded`
- For subscription flows: use `checkout.session.completed` to create the Customer/Subscription
  records in your DB. The session contains `customer` and `subscription` IDs.
- For one-time payments: `checkout.session.completed` is sufficient — payment is already confirmed
  by the time this fires (mode=payment sessions wait for payment before completing).

### `customer.subscription.updated` — when to act
- This fires on every field change: plan upgrade, quantity change, trial-to-active transition,
  payment method update, `cancel_at_period_end` toggle.
- Don't use it as a sole trigger for access changes — use `invoice.paid` for "access is paid"
  and `customer.subscription.deleted` for "access is revoked."
- Safe to use for updating your local subscription record's status field.

## Idempotency

Every handler MUST:
1. Check `StripeEvent` table for the event ID before processing.
2. Perform the idempotency INSERT and the business side effect in the **same DB transaction**.
3. Return 200 even for duplicate events (don't return 4xx or Stripe will stop retrying).

## Replay / Recovery

Stripe retries failed webhook deliveries with exponential backoff for up to **3 days**.
For outages beyond 3 days, use `stripe.events.list(type=..., created=...)` to replay events.
The skill generates a `scripts/replay_events.py` stub for this.
