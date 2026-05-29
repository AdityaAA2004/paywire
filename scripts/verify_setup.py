#!/usr/bin/env python3
"""
verify_setup.py — Smoke test for the Stripe billing integration.

Checks:
  1. Required environment variables are set.
  2. stripe-mock is reachable on :12111.
  3. Stripe SDK initializes correctly against stripe-mock.
  4. Webhook signature verification works with a synthetic payload.
  5. Billing module is importable (generated files are in place).

Usage:
    python3 scripts/verify_setup.py
    # Or with stripe-mock on a custom host:
    STRIPE_MOCK_HOST=http://localhost:12111 python3 scripts/verify_setup.py
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

STRIPE_MOCK_HOST = os.environ.get("STRIPE_MOCK_HOST", "http://localhost:12111")
PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
WARN = "\033[33m⚠\033[0m"


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = PASS if ok else FAIL
    print(f"  {status}  {label}" + (f"\n     {detail}" if detail and not ok else ""))
    return ok


def run_checks() -> bool:
    results: list[bool] = []

    print("\npaywire setup verification\n")

    # 1. Environment variables.
    print("Environment variables:")
    has_key = bool(
        os.environ.get("STRIPE_RESTRICTED_KEY") or os.environ.get("STRIPE_SECRET_KEY")
    )
    results.append(check(
        "STRIPE_RESTRICTED_KEY (or STRIPE_SECRET_KEY)",
        has_key,
        "Set STRIPE_RESTRICTED_KEY=rk_test_... in your .env file",
    ))

    has_webhook_secret = bool(
        os.environ.get("STRIPE_WEBHOOK_SECRET_TEST") or
        os.environ.get("STRIPE_WEBHOOK_SECRET_LIVE")
    )
    results.append(check(
        "STRIPE_WEBHOOK_SECRET_TEST (or _LIVE)",
        has_webhook_secret,
        "Run 'stripe listen' to get a local whsec_... secret",
    ))

    # 2. stripe-mock reachability.
    print("\nstripe-mock:")
    try:
        with urlopen(f"{STRIPE_MOCK_HOST}/v1/charges", timeout=3) as resp:
            stripe_mock_ok = resp.status in (200, 401)  # 401 = no auth key — expected
    except (URLError, OSError):
        stripe_mock_ok = False

    results.append(check(
        f"stripe-mock reachable at {STRIPE_MOCK_HOST}",
        stripe_mock_ok,
        "Start with: docker compose -f docker-compose.stripe-mock.yml up -d",
    ))

    # 3. Stripe SDK init against stripe-mock.
    print("\nStripe SDK:")
    try:
        import stripe as stripe_module

        client = stripe_module.Stripe("sk_test_xxx")
        client.api_base = STRIPE_MOCK_HOST
        client.api_version = "2026-04-22.dahlia"

        # Create a charge (stripe-mock accepts any valid request).
        try:
            client.charges.list(limit=1)
            sdk_ok = True
        except stripe_module.StripeError:
            sdk_ok = False

        results.append(check("SDK initialises and can call stripe-mock", sdk_ok))
    except ImportError:
        results.append(check("stripe package installed", False, "pip install stripe"))

    # 4. Webhook signature verification.
    print("\nWebhook signature verification:")
    try:
        import stripe as stripe_module

        test_secret = "whsec_test_verify_secret"
        payload = json.dumps({"id": "evt_test", "type": "invoice.paid", "data": {"object": {}}}).encode()
        timestamp = str(int(time.time()))
        signed = f"{timestamp}.{payload.decode()}"
        sig = hmac.new(test_secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
        header = f"t={timestamp},v1={sig}"

        client = stripe_module.Stripe("sk_test_xxx")
        event = stripe_module.Webhook.construct_event(
            payload=payload,
            sig_header=header,
            secret=test_secret,
        )
        sig_ok = event["type"] == "invoice.paid"
        results.append(check("construct_event validates HMAC-SHA256 correctly", sig_ok))

        # Test replay protection (timestamp > 5 minutes old).
        old_timestamp = str(int(time.time()) - 400)
        old_signed = f"{old_timestamp}.{payload.decode()}"
        old_sig = hmac.new(test_secret.encode(), old_signed.encode(), hashlib.sha256).hexdigest()
        old_header = f"t={old_timestamp},v1={old_sig}"
        try:
            stripe_module.Webhook.construct_event(payload, old_header, test_secret)
            replay_blocked = False
        except stripe_module.SignatureVerificationError:
            replay_blocked = True
        results.append(check("Replay protection blocks events > 5 minutes old", replay_blocked))

    except Exception as exc:
        results.append(check("Webhook signature verification", False, str(exc)))

    # 5. Billing module importability.
    print("\nGenerated billing module:")
    try:
        import billing.models  # noqa: F401
        results.append(check("billing.models importable", True))
    except ImportError as exc:
        results.append(check(
            "billing.models importable",
            False,
            f"{exc}\nRun scaffold.py first: python3 scripts/scaffold.py --framework fastapi --config ... --out .",
        ))

    try:
        from billing.handlers.base import StripeEventHandler  # noqa: F401
        results.append(check("billing.handlers.base importable", True))
    except ImportError as exc:
        results.append(check("billing.handlers.base importable", False, str(exc)))

    # Summary.
    passed = sum(results)
    total = len(results)
    print(f"\n{'=' * 40}")
    print(f"  {passed}/{total} checks passed")

    if passed == total:
        print(f"\n  {PASS} Ready! Next step:")
        print("  stripe listen --forward-to localhost:8000/webhooks/stripe")
    else:
        print(f"\n  {FAIL} Fix the failing checks above before proceeding.")

    return passed == total


if __name__ == "__main__":
    ok = run_checks()
    sys.exit(0 if ok else 1)
