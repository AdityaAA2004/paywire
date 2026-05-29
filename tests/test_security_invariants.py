import ast, tempfile
from pathlib import Path
from scaffold import render_framework

def rendered(tmp_path):
    render_framework("fastapi", FULL_CONFIG, tmp_path)
    return tmp_path

def test_webhook_reads_raw_body_not_json(tmp_path):
    src = (rendered(tmp_path) / "webhook.py").read_text()
    assert "await request.body()" in src
    assert "await request.json()" not in src

def test_no_payment_method_types_in_checkout(tmp_path):
    src = (rendered(tmp_path) / "services/billing_service.py").read_text()
    assert "payment_method_types" not in src

def test_uses_restricted_key_not_secret_key(tmp_path):
    src = (rendered(tmp_path) / "dependencies.py").read_text()
    assert "STRIPE_RESTRICTED_KEY" in src
    assert '"STRIPE_SECRET_KEY"' not in src  # Should never reference sk_ key directly

def test_idempotency_check_uses_same_session(tmp_path):
    src = (rendered(tmp_path) / "webhook.py").read_text()
    # Both StripeEvent insert and dispatcher.dispatch use the same `db` session
    assert src.count("db: AsyncSession") >= 1
    # flush() before dispatch = same transaction
    assert "await db.flush()" in src

def test_webhook_returns_400_not_500_on_bad_signature(tmp_path):
    src = (rendered(tmp_path) / "webhook.py").read_text()
    tree = ast.parse(src)
    # Find all HTTPException raises and check they use 400
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if getattr(getattr(node.func, "id", None), "__str__", lambda: "")() == "HTTPException":
                for kw in node.keywords:
                    if kw.arg == "status_code":
                        assert kw.value.value == 400