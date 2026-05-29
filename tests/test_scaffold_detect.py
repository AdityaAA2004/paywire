import tempfile, os
from pathlib import Path
from scaffold import detect_framework

def test_detects_fastapi_via_requirements():
    with tempfile.TemporaryDirectory() as d:
        Path(d, "requirements.txt").write_text("fastapi==0.104.1\nuvicorn\n")
        assert detect_framework(Path(d)) == "fastapi"

def test_detects_django_via_manage():
    with tempfile.TemporaryDirectory() as d:
        Path(d, "manage.py").write_text("# django")
        assert detect_framework(Path(d)) == "django"

def test_returns_none_for_unknown():
    with tempfile.TemporaryDirectory() as d:
        Path(d, "main.go").write_text("package main")
        assert detect_framework(Path(d)) is None