# PCI DSS Scope and SAQ Decision Guide

Loaded on demand by SKILL.md when the user asks about compliance or payment form options.

## SAQ A — Target scope for all paywire-generated integrations

**Eligible when:**
- Card data entry is entirely handled by Stripe-hosted pages or Stripe.js/Elements.
- Your server never sees raw card numbers, CVVs, or full magnetic stripe data.
- Covered by: Stripe Checkout (hosted), Payment Element, Stripe Elements (card tokenized client-side).

**PCI DSS 4.0 changes (effective March 2025):**
- SAQ A merchants now must complete an annual **Self-Assessment Questionnaire** AND perform
  **quarterly Approved Scanning Vendor (ASV) scans** of internet-facing IPs.
- Even for fully outsourced integrations, you are responsible for the SAQ A attestation.
- paywire's generated README includes a checklist of SAQ A obligations.

## SAQ A-EP — Avoid this scope

**Triggered when:**
- Your page directly loads and submits a payment form (even if Stripe.js tokenizes server-side).
- You use `payment_method_types` to restrict methods in a way that bypasses Stripe's hosted validation.
- You use the deprecated `stripe.createToken()` (old Stripe.js v2) instead of Payment Element.

**paywire enforces SAQ A:** The skill will refuse to generate raw card input fields.
The `STRIPE_CHECKOUT_MODE` is always `hosted` or `payment_element`.

## SAQ D — Do not approach

**Triggered when:**
- Your server stores, processes, or transmits raw cardholder data (PANs, CVVs).
- You implement your own payment gateway.

paywire templates never generate code that handles raw card data.

## What you CAN store (not PCI-scoped)

Per Stripe's official guidance, these fields are safe to store in your database:
- `card.last4` — last 4 digits of card number
- `card.brand` — visa, mastercard, amex, etc.
- `card.exp_month` / `card.exp_year`
- `customer.id` — the `cus_...` identifier
- `payment_method.id` — the `pm_...` identifier
- `subscription.id`, `invoice.id`, etc.

Do NOT store: full PAN, CVV/CVC, magnetic stripe data, PIN.

## Restricted API Keys (mandatory)

Always use a **Restricted Key** (`rk_` prefix) with only the permissions your app needs:
- Checkout Sessions: write
- Customers: read/write
- Invoices: read
- Subscriptions: read
- Webhook Endpoints: write (provisioning only — use a separate key or CLI)

Never use a secret key (`sk_`) in application code.
