def test_full_scaffold_produces_expected_file_set(tmp_path):
    """Regression test: scaffolding always produces exactly these files."""
    render_framework("fastapi", FULL_CONFIG, tmp_path)
    expected = {
        "webhook.py", "router.py", "dispatcher.py", "dependencies.py",
        "models.py", "schemas.py",
        "handlers/base.py", "handlers/checkout_handler.py",
        "handlers/invoice_handler.py", "handlers/subscription_handler.py",
        "services/billing_service.py", "services/subscription_service.py",
        "tests/conftest.py", "tests/test_webhook.py",
        "env.example", "docker-compose.stripe-mock.yml", "README.stripe.md",
    }
    actual = {str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file()}
    assert expected == actual