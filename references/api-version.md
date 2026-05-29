# Stripe API Version Reference

Current pinned version: **2026-04-22.dahlia**

## How Stripe API Versioning Works

- Stripe pins the API version to the date your account first called the API (or the version
  set in your Stripe Dashboard under Developers → API version).
- The SDK uses the account-level pinned version by default.
- You can override per-request with `stripe_version="2026-04-22.dahlia"`.
- Webhook event payloads use the version set at the time the webhook endpoint was created,
  NOT the SDK version. Always set the endpoint version when registering via API.

## Version Set in Generated Code

paywire pins the API version explicitly in SDK initialization:

```python
stripe.api_version = "2026-04-22.dahlia"
```

And in webhook endpoint creation:

```python
stripe.WebhookEndpoint.create(
    url=webhook_url,
    enabled_events=events,
    api_version="2026-04-22.dahlia",
)
```

## Upgrading API Versions

Use the official `stripe/upgrade-stripe` Claude Code skill to migrate generated code between
API versions. That skill performs a dry-run diff of API changes between versions.

Key considerations:
- Upgrade the webhook endpoint's API version in your Stripe Dashboard AND in your code together.
- Test against Stripe testmode after every version bump — stripe-mock may not reflect all changes.
- Stripe provides an API changelog at: https://stripe.com/docs/upgrades

## Breaking Changes in Recent Versions

### 2026-04-22.dahlia
- `payment_method_configuration` replaces some legacy `payment_method_types` flows.
- Dynamic payment methods (no explicit `payment_method_types`) is now the recommended default.

### 2024-06-20
- `Checkout Session` line_items now require explicit `quantity`.
- `PaymentIntent.automatic_payment_methods` enabled by default for new integrations.

## stripe-mock Limitations

`stripe-mock` serves the OpenAPI spec but does not simulate behavioral nuances:
- It will not simulate retry backoff for failed payments.
- It will not simulate Test Clock time advancement.
- It accepts any API version header without validation.

Always run a final integration test against Stripe **testmode** before going to production.
