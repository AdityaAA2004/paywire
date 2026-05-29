import sys; 
sys.path.insert(0, "scripts")
from parse_intent import extract

def test_tiered_with_trial():
    r = extract("add tiered subscriptions with a 14-day free trial")
    assert r["pricing_model"] == "tiered"
    assert r["trial_days"] == 14

def test_no_trial():
    r = extract("one-time payment, no trial")
    assert r["pricing_model"] == "one_time"
    assert r["trial_days"] == 0

def test_currencies():
    r = extract("billing in USD and EUR")
    assert set(r["currencies"]) == {"usd", "eur"}

def test_connect():
    r = extract("marketplace payments with Stripe Connect")
    assert r["with_connect"] is True

def test_empty_returns_empty():
    assert extract("") == {}

def test_conflicting_signals_first_wins():
    # "subscription" pattern appears before "one_time"
    r = extract("monthly subscription, one-time setup fee")
    assert r["pricing_model"] == "subscription"