#!/usr/bin/env python3
"""
wire_app.py — Wire billing routers into the FastAPI application entry point.

Actions (all idempotent):
  1. Detect and patch the FastAPI entry point (main.py / app.py) to include
     billing.router and billing.webhook routers.
  2. Add stripe>=11.0 to requirements.txt (creates the file if absent).
  3. Copy billing/env.example to .env when .env does not yet exist.

Usage:
    python3 wire_app.py
    python3 wire_app.py --app-file src/main.py --billing-dir ./billing
    python3 wire_app.py --dry-run
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROUTER_IMPORTS = (
    "from billing.router import router as billing_router\n"
    "from billing.webhook import router as webhook_router\n"
)

ROUTER_INCLUDES = (
    'app.include_router(billing_router, prefix="/billing")\n'
    'app.include_router(webhook_router, prefix="/webhooks")\n'
)

REQUIREMENTS_LINE = "stripe>=11.0\n"

PASS = "\033[32m✓\033[0m"
SKIP = "\033[33m—\033[0m"
FAIL = "\033[31m✗\033[0m"

# Candidate entry-point paths, checked in order.
APP_FILE_CANDIDATES = [
    "main.py",
    "app.py",
    "application.py",
    "src/main.py",
    "src/app.py",
    "app/main.py",
    "app/app.py",
]


def find_app_file() -> Path | None:
    for candidate in APP_FILE_CANDIDATES:
        p = Path(candidate)
        if p.exists():
            return p
    # Broader scan — first .py file that instantiates FastAPI.
    for p in sorted(Path(".").rglob("*.py")):
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        if re.search(r"=\s*FastAPI\s*\(", text):
            return p
    return None


def patch_app_file(app_file: Path, dry_run: bool) -> bool:
    text = app_file.read_text()

    already_wired = "billing_router" in text and "webhook_router" in text
    if already_wired:
        print(f"  {SKIP}  {app_file}: routers already wired")
        return True

    # --- locate where to insert imports ---
    # Find the end of the last top-level import line.
    import_matches = list(re.finditer(r"^(?:from|import)\s[^\n]*", text, re.MULTILINE))
    if import_matches:
        last_import_end = text.index("\n", import_matches[-1].end()) + 1
    else:
        last_import_end = 0

    # --- locate where to insert include_router calls ---
    # Match `app = FastAPI(...)` allowing the closing paren to be on a later line.
    app_match = re.search(r"app\s*=\s*FastAPI\s*\(", text)
    if not app_match:
        print(f"  {FAIL}  {app_file}: `app = FastAPI(...)` not found — add routers manually")
        return False

    # Walk forward from the opening paren to find its matching close paren.
    open_paren_pos = app_match.end() - 1  # position of '('
    depth = 0
    close_paren_pos = open_paren_pos
    for i, ch in enumerate(text[open_paren_pos:], start=open_paren_pos):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                close_paren_pos = i
                break

    newline_after_app = text.find("\n", close_paren_pos)
    if newline_after_app == -1:
        newline_after_app = len(text) - 1
    insert_includes_at = newline_after_app + 1

    if dry_run:
        print(f"  {PASS}  {app_file}: would insert imports at line "
              f"{text[:last_import_end].count(chr(10)) + 1} and routers after app instantiation")
        return True

    # Build patched content, being careful not to double-insert if positions overlap.
    if last_import_end <= insert_includes_at:
        new_text = (
            text[:last_import_end]
            + ROUTER_IMPORTS
            + text[last_import_end:insert_includes_at]
            + "\n"
            + ROUTER_INCLUDES
            + text[insert_includes_at:]
        )
    else:
        # Edge case: no existing imports, app is at top of file.
        new_text = ROUTER_IMPORTS + "\n" + text[:insert_includes_at] + "\n" + ROUTER_INCLUDES + text[insert_includes_at:]

    app_file.write_text(new_text)
    print(f"  {PASS}  {app_file}: billing routers wired")
    return True


def patch_requirements(dry_run: bool) -> bool:
    req_file = Path("requirements.txt")
    if not req_file.exists():
        if dry_run:
            print(f"  {PASS}  requirements.txt: would create with stripe>=11.0")
        else:
            req_file.write_text(REQUIREMENTS_LINE)
            print(f"  {PASS}  requirements.txt: created with stripe>=11.0")
        return True

    text = req_file.read_text()
    if re.search(r"^\s*stripe\b", text, re.MULTILINE):
        print(f"  {SKIP}  requirements.txt: stripe already listed")
        return True

    if dry_run:
        print(f"  {PASS}  requirements.txt: would append stripe>=11.0")
        return True

    with open(req_file, "a") as f:
        if text and not text.endswith("\n"):
            f.write("\n")
        f.write(REQUIREMENTS_LINE)
    print(f"  {PASS}  requirements.txt: appended stripe>=11.0")
    return True


def copy_env_example(billing_dir: Path, dry_run: bool) -> bool:
    env_example = billing_dir / "env.example"
    env_file = Path(".env")

    if not env_example.exists():
        print(f"  {SKIP}  .env: {env_example} not found — skipping")
        return True

    if env_file.exists():
        print(f"  {SKIP}  .env: already exists — not overwriting "
              f"(manually merge from {env_example} if needed)")
        return True

    if dry_run:
        print(f"  {PASS}  .env: would copy from {env_example}")
        return True

    shutil.copy(env_example, env_file)
    print(f"  {PASS}  .env: copied from {env_example} — fill in STRIPE_RESTRICTED_KEY and other values")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Wire billing routers into FastAPI app")
    parser.add_argument(
        "--app-file",
        help="Path to FastAPI entry point (auto-detected when omitted)",
    )
    parser.add_argument(
        "--billing-dir",
        default="./billing",
        help="Path to the generated billing directory (default: ./billing)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without touching any files",
    )
    args = parser.parse_args()

    billing_dir = Path(args.billing_dir)

    print("\nWiring billing into app...")
    if args.dry_run:
        print("(dry-run — no files will be changed)\n")

    results: list[bool] = []

    # 1. Patch FastAPI app file.
    app_file = Path(args.app_file) if args.app_file else find_app_file()
    if app_file is None:
        print(f"  {FAIL}  Could not locate a FastAPI entry point. "
              "Pass --app-file to specify one.")
        results.append(False)
    else:
        results.append(patch_app_file(app_file, args.dry_run))

    # 2. requirements.txt
    results.append(patch_requirements(args.dry_run))

    # 3. .env
    results.append(copy_env_example(billing_dir, args.dry_run))

    passed = sum(results)
    total = len(results)
    print(f"\n  {passed}/{total} steps completed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
