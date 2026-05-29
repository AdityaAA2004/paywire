"""
Template rendering tests.

Renders every template with the canonical full-config.json and validates:
  - All expected files are produced
  - All generated Python is syntactically valid
  - LLM section markers are in the right files (and absent from the wrong ones)
  - Optional events disabled in config don't appear in output
"""

import ast
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from scaffold import render_framework  # noqa: E402

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "full-config.json"

OPTIONAL_EVENTS = {
    "customer.subscription.updated",
    "customer.subscription.trial_will_end",
}


@pytest.fixture(scope="module")
def full_config() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


@pytest.fixture(scope="module")
def rendered_output(full_config, tmp_path_factory) -> Path:
    """Render once per test session; all tests share the output directory."""
    out = tmp_path_factory.mktemp("billing")
    render_framework("fastapi", full_config, out)
    return out


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------

EXPECTED_FILES = [
    "webhook.py",
    "router.py",
    "dispatcher.py",
    "dependencies.py",
    "models.py",
    "schemas.py",
    "handlers/base.py",
    "handlers/checkout_handler.py",
    "handlers/invoice_handler.py",
    "handlers/subscription_handler.py",
    "services/billing_service.py",
    "services/subscription_service.py",
    "tests/conftest.py",
    "tests/test_webhook.py",
    "env.example",
    "docker-compose.stripe-mock.yml",
    "README.stripe.md",
]


@pytest.mark.parametrize("expected_file", EXPECTED_FILES)
def test_expected_file_is_generated(rendered_output, expected_file):
    assert (rendered_output / expected_file).exists(), f"Missing: {expected_file}"


# ---------------------------------------------------------------------------
# Python syntax validity
# ---------------------------------------------------------------------------

PYTHON_FILES = [f for f in EXPECTED_FILES if f.endswith(".py")]


@pytest.mark.parametrize("py_file", PYTHON_FILES)
def test_generated_python_is_valid_syntax(rendered_output, py_file):
    source = (rendered_output / py_file).read_text()
    try:
        ast.parse(source)
    except SyntaxError as exc:
        pytest.fail(f"{py_file} has a syntax error: {exc}")


# ---------------------------------------------------------------------------
# LLM section placement
# ---------------------------------------------------------------------------

# These files must contain LLM sections (business logic to fill)
FILES_WITH_LLM_SECTIONS = [
    "handlers/checkout_handler.py",
    "handlers/invoice_handler.py",
    "services/subscription_service.py",
    "models.py",
    "tests/test_webhook.py",
]

# These files must NEVER contain LLM sections (pure infrastructure)
FILES_WITHOUT_LLM_SECTIONS = [
    "webhook.py",
    "router.py",
    "dispatcher.py",
    "dependencies.py",
    "schemas.py",
    "handlers/base.py",
    "services/billing_service.py",
]


@pytest.mark.parametrize("py_file", FILES_WITH_LLM_SECTIONS)
def test_llm_sections_present_in_business_logic_files(rendered_output, py_file):
    src = (rendered_output / py_file).read_text()
    assert "LLM_SECTION_START" in src, f"{py_file} should have LLM sections but has none"


@pytest.mark.parametrize("py_file", FILES_WITHOUT_LLM_SECTIONS)
def test_no_llm_sections_in_infrastructure_files(rendered_output, py_file):
    src = (rendered_output / py_file).read_text()
    assert "LLM_SECTION_START" not in src, (
        f"{py_file} is pure infrastructure but contains LLM sections"
    )


# ---------------------------------------------------------------------------
# Optional events disabled — handler classes must not appear in output
# ---------------------------------------------------------------------------

def _config_with_optional_events_disabled(full_config: dict) -> dict:
    """Return a copy of full_config with all optional events set to enabled=False."""
    return {
        **full_config,
        "events": [
            {**event, "enabled": False}
            if event["name"] in OPTIONAL_EVENTS
            else event
            for event in full_config["events"]
        ],
    }


def test_disabled_optional_events_produce_no_handler_classes(full_config, tmp_path):
    config = _config_with_optional_events_disabled(full_config)
    render_framework("fastapi", config, tmp_path)

    sub_handler = (tmp_path / "handlers/subscription_handler.py").read_text()
    assert "TrialWillEndHandler" not in sub_handler
    assert "SubscriptionUpdatedHandler" not in sub_handler


def test_disabled_optional_events_produce_no_registrations(full_config, tmp_path):
    config = _config_with_optional_events_disabled(full_config)
    render_framework("fastapi", config, tmp_path)

    dependencies = (tmp_path / "dependencies.py").read_text()
    assert "TrialWillEndHandler" not in dependencies
    assert "SubscriptionUpdatedHandler" not in dependencies


def test_enabled_optional_events_do_appear(full_config, tmp_path):
    """Inverse check: when optional events are enabled, their classes are rendered."""
    config = {
        **full_config,
        "events": [
            {**event, "enabled": True}
            if event["name"] in OPTIONAL_EVENTS
            else event
            for event in full_config["events"]
        ],
    }
    render_framework("fastapi", config, tmp_path)

    sub_handler = (tmp_path / "handlers/subscription_handler.py").read_text()
    assert "TrialWillEndHandler" in sub_handler
    assert "SubscriptionUpdatedHandler" in sub_handler
