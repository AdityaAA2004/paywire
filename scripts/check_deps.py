#!/usr/bin/env python3
"""
check_deps.py — Pre-flight dependency check for paywire.

Verifies that the Stripe Python SDK and supporting libraries are present in
the target project before any templates are rendered. Exits 0 if all required
deps are satisfied; exits 1 if any are missing so the caller can decide
whether to abort or auto-install.

Usage:
    python3 check_deps.py                  # report only
    python3 check_deps.py --install        # install any missing deps via pip
    python3 check_deps.py --json           # machine-readable JSON output
    python3 check_deps.py --dir /path/to/project  # target a specific directory
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Required dependencies and the packages that satisfy them.
# "spec" is what's written in requirements files; "import_name" is what you
# import in Python (they differ for e.g. python-jose → jose).
# ---------------------------------------------------------------------------

REQUIRED_DEPS: list[dict] = [
    {
        "spec": "stripe",
        "import_name": "stripe",
        "reason": "Stripe Python SDK — core of the billing integration",
        "pip_install": "stripe>=5.0.0",
    },
    {
        "spec": "sqlalchemy",
        "import_name": "sqlalchemy",
        "reason": "SQLAlchemy — ORM for StripeEvent / StripeCustomer / StripeSubscription models",
        "pip_install": "sqlalchemy[asyncio]>=2.0.0",
    },
    {
        "spec": "alembic",
        "import_name": "alembic",
        "reason": "Alembic — database migrations for the billing tables",
        "pip_install": "alembic>=1.13.0",
    },
]

# Colour helpers (disabled when not a TTY or on Windows without ANSI support)
_USE_COLOUR = sys.stdout.isatty()


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m" if _USE_COLOUR else s


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m" if _USE_COLOUR else s


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m" if _USE_COLOUR else s


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m" if _USE_COLOUR else s


# ---------------------------------------------------------------------------
# Dependency file inspection
# ---------------------------------------------------------------------------

def _find_dep_files(project_dir: Path) -> list[Path]:
    """Return all dependency declaration files found in project_dir."""
    candidates = [
        "requirements.txt",
        "requirements-base.txt",
        "requirements/base.txt",
        "requirements/common.txt",
        "pyproject.toml",
        "setup.cfg",
        "setup.py",
        "Pipfile",
    ]
    return [project_dir / c for c in candidates if (project_dir / c).exists()]


def _spec_in_file(spec: str, path: Path) -> bool:
    """Return True if `spec` appears as a dependency in the given file."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    # Match the package name case-insensitively at a word boundary, followed by
    # optional version specifier, comma, bracket, or end-of-line.
    # Handles: stripe, stripe>=5, stripe==11.1.0, "stripe", 'stripe', stripe[extra]
    pattern = rf"(?i)(^|[\"'\s])({re.escape(spec)})([^a-z0-9_.-]|$)"
    return bool(re.search(pattern, text, re.MULTILINE))


def _is_importable(import_name: str) -> bool:
    """Return True if the package can be imported in the current Python env."""
    return importlib.util.find_spec(import_name) is not None


def _detect_primary_req_file(project_dir: Path) -> Path | None:
    """Return the most appropriate requirements file to append to, or None."""
    for name in ("requirements.txt", "requirements-base.txt"):
        p = project_dir / name
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# Core check logic
# ---------------------------------------------------------------------------

def check_deps(project_dir: Path) -> list[dict]:
    """
    For each required dep, return a result dict:
        {
          "spec": str,
          "in_dep_file": bool,       # found in requirements.txt / pyproject.toml etc.
          "dep_file": str | None,    # which file it was found in (if any)
          "importable": bool,        # can be imported right now
          "ok": bool,                # True if both in_dep_file AND importable
          "reason": str,
          "pip_install": str,
        }
    """
    dep_files = _find_dep_files(project_dir)
    results = []

    for dep in REQUIRED_DEPS:
        spec = dep["spec"]
        import_name = dep["import_name"]

        # Check dep files
        found_in: str | None = None
        for f in dep_files:
            if _spec_in_file(spec, f):
                found_in = str(f.relative_to(project_dir))
                break

        importable = _is_importable(import_name)
        ok = found_in is not None and importable

        results.append({
            "spec": spec,
            "in_dep_file": found_in is not None,
            "dep_file": found_in,
            "importable": importable,
            "ok": ok,
            "reason": dep["reason"],
            "pip_install": dep["pip_install"],
        })

    return results


# ---------------------------------------------------------------------------
# Install missing deps
# ---------------------------------------------------------------------------

def _in_virtual_env() -> bool:
    """Return True if running inside a virtual environment or conda env."""
    return (
        sys.prefix != sys.base_prefix
        or "VIRTUAL_ENV" in __import__("os").environ
        or "CONDA_DEFAULT_ENV" in __import__("os").environ
    )


def install_missing(results: list[dict], project_dir: Path) -> list[dict]:
    """
    For each result that is not ok:
      1. Run `python -m pip install <pip_install>` (always uses the current interpreter's pip).
      2. If a primary requirements file exists, append the spec.
      3. Update result["importable"] and result["ok"] after install.
    Returns updated results.
    """
    if not _in_virtual_env():
        print()
        print(_yellow("  ⚠  Not running inside a virtual environment."))
        print("     Auto-install skipped to avoid polluting your system Python.")
        print()
        print("  Recommended: activate your project venv first, then re-run:")
        print("    python3 -m venv .venv")
        print("    source .venv/bin/activate   # Windows: .venv\\Scripts\\activate")
        print("    pip install -r requirements.txt")
        print("    /paywire --install")
        print()
        return results

    req_file = _detect_primary_req_file(project_dir)
    updated = []

    for r in results:
        if r["ok"]:
            updated.append(r)
            continue

        print(f"  installing {r['pip_install']} …", flush=True)
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", r["pip_install"]],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            if "externally-managed-environment" in stderr:
                print(
                    f"  {_yellow('⚠')}  pip blocked by PEP 668 (externally-managed Python).\n"
                    f"     Activate a virtual environment and re-run with --install.",
                    file=sys.stderr,
                )
            else:
                print(f"  {_red('✗')} pip install failed:\n{stderr}", file=sys.stderr)
            updated.append(r)
            continue

        # Re-check importability after install
        r["importable"] = _is_importable(r["import_name"])

        # Append to requirements file if not already there
        if req_file and not r["in_dep_file"]:
            with req_file.open("a", encoding="utf-8") as f:
                f.write(f"\n{r['spec']}\n")
            r["in_dep_file"] = True
            r["dep_file"] = str(req_file.relative_to(project_dir))
            print(f"  appended {r['spec']} to {r['dep_file']}")

        r["ok"] = r["in_dep_file"] and r["importable"]
        updated.append(r)

    return updated


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(results: list[dict], project_dir: Path) -> None:
    dep_files = _find_dep_files(project_dir)
    print()
    print(_bold("paywire dependency pre-flight"))
    print()

    if dep_files:
        print(f"  Scanned: {', '.join(str(f.relative_to(project_dir)) for f in dep_files)}")
    else:
        print(f"  {_yellow('⚠')}  No requirements files found in {project_dir}")
    print()

    for r in results:
        icon = _green("✓") if r["ok"] else _red("✗")
        label = r["spec"]
        notes = []

        if r["in_dep_file"]:
            notes.append(f"declared in {r['dep_file']}")
        else:
            notes.append(_red("not in any dependency file"))

        if r["importable"]:
            notes.append("importable ✓")
        else:
            notes.append(_red("not importable — not installed?"))

        print(f"  {icon}  {label:20s}  {', '.join(notes)}")
        if not r["ok"]:
            print(f"          {r['reason']}")
            print(f"          Fix: pip install {r['pip_install']}")
        print()

    all_ok = all(r["ok"] for r in results)
    if all_ok:
        print(_green("  All dependencies satisfied — ready to scaffold.\n"))
    else:
        missing = [r["spec"] for r in results if not r["ok"]]
        print(_red(f"  Missing: {', '.join(missing)}"))
        print()
        print("  Run with --install to install them automatically, or add them")
        print("  to your requirements file and re-run without --install.\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pre-flight check: verify Stripe SDK dependencies before scaffolding."
    )
    parser.add_argument(
        "--dir",
        default=".",
        help="Project root to inspect (default: current directory)",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install missing dependencies via pip and append to requirements.txt",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON instead of human-readable report",
    )
    args = parser.parse_args()

    project_dir = Path(args.dir).resolve()

    results = check_deps(project_dir)

    if args.install:
        missing = [r for r in results if not r["ok"]]
        if missing:
            print(f"\nInstalling {len(missing)} missing dep(s)…")
            results = install_missing(results, project_dir)

    if args.json_output:
        print(json.dumps(results, indent=2))
    else:
        print_report(results, project_dir)

    all_ok = all(r["ok"] for r in results)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
