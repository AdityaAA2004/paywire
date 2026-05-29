#!/usr/bin/env python3
"""
generate_fixtures.py — Stripe test fixtures for offline replay and stripe-mock.

Outputs:
  fixtures/stripe_events/<event_type>.json  — Frozen evt_* payloads for offline replay.
  fixtures/stripe-fixtures.json             — Stripe CLI fixture format for stripe trigger --add.

Usage:
    python3 generate_fixtures.py --out ./fixtures
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


# Minimal frozen payloads for each supported event type.
# These match the real Stripe webhook payload structure at API version 2026-04-22.dahlia.
FIXTURES: dict[str, dict] = {
    "checkout.session.completed": {
        "id": "evt_test_checkout_completed",
        "object": "event",
        "type": "checkout.session.completed",
        "livemode": False,
        "data": {
            "object": {
                "id": "cs_test_xxx",
                "object": "checkout.session",
                "mode": "subscription",
                "customer": "cus_test_xxx",
                "subscription": "sub_test_xxx",
                "payment_status": "paid",
                "client_reference_id": None,  # Set this to your user ID when creating sessions.
                "metadata": {},
            }
        },
    },
    "invoice.paid": {
        "id": "evt_test_invoice_paid",
        "object": "event",
        "type": "invoice.paid",
        "livemode": False,
        "data": {
            "object": {
                "id": "in_test_xxx",
                "object": "invoice",
                "customer": "cus_test_xxx",
                "subscription": "sub_test_xxx",
                "status": "paid",
                "amount_paid": 999,
                "currency": "usd",
                "next_payment_attempt": None,
            }
        },
    },
    "invoice.payment_failed": {
        "id": "evt_test_invoice_payment_failed",
        "object": "event",
        "type": "invoice.payment_failed",
        "livemode": False,
        "data": {
            "object": {
                "id": "in_test_failed",
                "object": "invoice",
                "customer": "cus_test_xxx",
                "subscription": "sub_test_xxx",
                "status": "open",
                "amount_due": 999,
                "attempt_count": 1,
                "next_payment_attempt": int(time.time()) + 86400,  # 24h from now
            }
        },
    },
    "customer.subscription.deleted": {
        "id": "evt_test_sub_deleted",
        "object": "event",
        "type": "customer.subscription.deleted",
        "livemode": False,
        "data": {
            "object": {
                "id": "sub_test_xxx",
                "object": "subscription",
                "customer": "cus_test_xxx",
                "status": "canceled",
                "current_period_end": int(time.time()) + 30 * 86400,
                "items": {"data": [{"price": {"id": "price_test_xxx"}}]},
            }
        },
    },
    "customer.subscription.updated": {
        "id": "evt_test_sub_updated",
        "object": "event",
        "type": "customer.subscription.updated",
        "livemode": False,
        "data": {
            "object": {
                "id": "sub_test_xxx",
                "object": "subscription",
                "customer": "cus_test_xxx",
                "status": "active",
                "current_period_end": int(time.time()) + 30 * 86400,
                "items": {"data": [{"price": {"id": "price_test_pro"}}]},
            }
        },
    },
    "customer.subscription.trial_will_end": {
        "id": "evt_test_trial_will_end",
        "object": "event",
        "type": "customer.subscription.trial_will_end",
        "livemode": False,
        "data": {
            "object": {
                "id": "sub_test_xxx",
                "object": "subscription",
                "customer": "cus_test_xxx",
                "status": "trialing",
                "trial_end": int(time.time()) + 3 * 86400,  # 3 days from now
                "items": {"data": [{"price": {"id": "price_test_starter"}}]},
            }
        },
    },
}


def generate_individual_fixtures(out_dir: Path) -> None:
    """Write one JSON file per event type for offline replay."""
    events_dir = out_dir / "stripe_events"
    events_dir.mkdir(parents=True, exist_ok=True)

    for event_type, payload in FIXTURES.items():
        file_name = event_type.replace(".", "_") + ".json"
        out_path = events_dir / file_name
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"  write {out_path}")


def generate_stripe_cli_fixtures(out_dir: Path) -> None:
    """
    Write a stripe-fixtures.json for use with:
        stripe trigger --add stripe-fixtures.json checkout.session.completed
    """
    # The Stripe CLI fixture format for custom overrides.
    cli_fixtures = {
        "_meta": {"template_version": 0},
        "fixtures": [
            {
                "name": f"fixture_{event_type.replace('.', '_')}",
                "path": f"/v1/test/event",
                "method": "post",
                "params": {
                    "type": event_type,
                },
            }
            for event_type in FIXTURES
        ],
    }
    out_path = out_dir / "stripe-fixtures.json"
    out_path.write_text(json.dumps(cli_fixtures, indent=2) + "\n", encoding="utf-8")
    print(f"  write {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Stripe test fixtures")
    parser.add_argument("--out", default="./fixtures", help="Output directory")
    args = parser.parse_args()

    out_dir = Path(args.out)
    print(f"Generating test fixtures → {out_dir}/")
    generate_individual_fixtures(out_dir)
    generate_stripe_cli_fixtures(out_dir)
    print("\nDone. Replay a fixture against your local server:")
    print("  stripe trigger checkout.session.completed")
    print("  # Or use the frozen fixture:")
    print("  stripe trigger --load fixtures/stripe_events/checkout_session_completed.json")


if __name__ == "__main__":
    main()
