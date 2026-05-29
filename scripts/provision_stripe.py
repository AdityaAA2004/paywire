#!/usr/bin/env python3
"""
provision_stripe.py — Idempotent Stripe-side configuration.

Creates Products, Prices, and a WebhookEndpoint in your Stripe account.
Idempotent: uses metadata.app_sku to find existing objects before creating new ones.

Outputs: .env.stripe with the created IDs ready to paste into your .env file.

Usage:
    STRIPE_RESTRICTED_KEY=rk_test_... python3 provision_stripe.py --config pricing-tiers.yaml
    python3 provision_stripe.py --config pricing-tiers.yaml --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    import stripe
except ImportError:
    print("stripe package not found. Run: pip install stripe", file=sys.stderr)
    sys.exit(1)


def get_client() -> stripe.Stripe:
    key = os.environ.get("STRIPE_RESTRICTED_KEY") or os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        print(
            "Error: set STRIPE_RESTRICTED_KEY (or STRIPE_SECRET_KEY) in your environment.",
            file=sys.stderr,
        )
        sys.exit(1)
    if key.startswith("sk_"):
        print(
            "Warning: using a secret key (sk_). Use a restricted key (rk_) in production.",
            file=sys.stderr,
        )
    client = stripe.Stripe(key)
    client.api_version = "2026-04-22.dahlia"
    return client


# --- Idempotent helpers ---

def find_product_by_sku(client: stripe.Stripe, app_sku: str) -> dict | None:
    products = client.products.search(query=f'metadata["app_sku"]:"{app_sku}"')
    return products.data[0] if products.data else None


def find_price_by_sku(client: stripe.Stripe, product_id: str, app_sku: str) -> dict | None:
    prices = client.prices.list(product=product_id, active=True)
    for price in prices.data:
        if price.metadata.get("app_sku") == app_sku:
            return price
    return None


def find_webhook_endpoint(client: stripe.Stripe, url: str) -> dict | None:
    endpoints = client.webhook_endpoints.list()
    for ep in endpoints.data:
        if ep.url == url:
            return ep
    return None


# --- Provisioning ---

def provision_product(client: stripe.Stripe, tier: dict, dry_run: bool) -> tuple[str, bool]:
    """Returns (product_id, created)."""
    app_sku = tier["app_sku"]
    existing = find_product_by_sku(client, app_sku)
    if existing:
        print(f"  product  [{app_sku}] already exists: {existing['id']}")
        return existing["id"], False

    if dry_run:
        print(f"  product  [{app_sku}] would create: {tier['display_name']}")
        return f"prod_DRY_{app_sku}", False

    product = client.products.create(
        name=tier["display_name"],
        metadata={"app_sku": app_sku},
    )
    print(f"  product  [{app_sku}] created: {product['id']}")
    return product["id"], True


def provision_price(
    client: stripe.Stripe, product_id: str, tier: dict, dry_run: bool
) -> tuple[str, bool]:
    """Returns (price_id, created)."""
    app_sku = tier["app_sku"]
    existing = find_price_by_sku(client, product_id, app_sku)
    if existing:
        print(f"  price    [{app_sku}] already exists: {existing['id']}")
        return existing["id"], False

    if dry_run:
        print(f"  price    [{app_sku}] would create: {tier['amount']} {tier['currency']}/{tier.get('interval', 'month')}")
        return f"price_DRY_{app_sku}", False

    params: dict[str, Any] = {
        "product": product_id,
        "unit_amount": tier["amount"],
        "currency": tier["currency"],
        "metadata": {"app_sku": app_sku},
    }
    billing_model = tier.get("billing_model") or "subscription"
    if billing_model != "one_time":
        params["recurring"] = {
            "interval": tier.get("interval", "month"),
            "interval_count": tier.get("interval_count", 1),
        }

    price = client.prices.create(**params)
    print(f"  price    [{app_sku}] created: {price['id']}")
    return price["id"], True


def provision_webhook(
    client: stripe.Stripe, url: str, events: list[str], dry_run: bool
) -> tuple[str, str | None]:
    """Returns (endpoint_id, signing_secret_or_None)."""
    existing = find_webhook_endpoint(client, url)
    if existing:
        print(f"  webhook  already registered: {existing['id']} → {url}")
        print("  Note: signing secret is not retrievable after creation — check your .env file.")
        return existing["id"], None

    if dry_run:
        print(f"  webhook  would register: {url} with {len(events)} events")
        return "we_DRY", None

    endpoint = client.webhook_endpoints.create(
        url=url,
        enabled_events=events,
        api_version="2026-04-22.dahlia",
    )
    print(f"  webhook  created: {endpoint['id']} → {url}")
    return endpoint["id"], endpoint["secret"]


# --- Main ---

def main() -> None:
    parser = argparse.ArgumentParser(description="Provision Stripe products, prices, and webhook endpoint")
    parser.add_argument("--config", required=True, help="Path to pricing-tiers.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without calling Stripe")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    client = get_client()

    print("\nProvisioning Stripe resources...")
    if args.dry_run:
        print("(dry-run — no API calls will be made)\n")

    env_lines: list[str] = []
    webhook_events: list[str] = []

    # Read enabled events from default-events.yaml if present.
    events_config_path = config_path.parent / "default-events.yaml"
    if events_config_path.exists():
        with open(events_config_path) as f:
            events_config = yaml.safe_load(f)
        webhook_events = [e["name"] for e in events_config.get("events", []) if e.get("enabled")]
    else:
        # Sensible defaults.
        webhook_events = [
            "checkout.session.completed",
            "invoice.paid",
            "invoice.payment_failed",
            "customer.subscription.deleted",
        ]

    # Provision products and prices.
    for tier in config.get("tiers", []):
        product_id, _ = provision_product(client, tier, args.dry_run)
        price_id, _ = provision_price(client, product_id, tier, args.dry_run)
        env_key = f"STRIPE_PRICE_ID_{tier['name'].upper()}"
        env_lines.append(f"{env_key}={price_id}")

    # Provision webhook endpoint.
    webhook_url = config.get("webhook_url", "")
    if not webhook_url or "your-domain" in webhook_url:
        print("\n  webhook  skipped — set webhook_url in your config to a real URL")
    else:
        _, secret = provision_webhook(client, webhook_url, webhook_events, args.dry_run)
        if secret:
            env_lines.append(f"STRIPE_WEBHOOK_SECRET_LIVE={secret}")
        else:
            env_lines.append("# STRIPE_WEBHOOK_SECRET_LIVE=<retrieve from Stripe Dashboard>")

    # Write .env.stripe output.
    if not args.dry_run:
        env_output = Path(".env.stripe")
        env_output.write_text("\n".join(env_lines) + "\n")
        print(f"\nWrote {env_output} — copy values into your .env file.")
    else:
        print("\nWould write .env.stripe:")
        for line in env_lines:
            print(f"  {line}")


if __name__ == "__main__":
    main()
