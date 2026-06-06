#!/usr/bin/env python3
"""
scaffold.py — Framework detection and Jinja2 template rendering.

Modes:
  --detect          Sniff the current directory for a supported framework.
  --framework <fw>  Render templates for a specific framework.

Usage:
  python3 scaffold.py --detect
  python3 scaffold.py --framework fastapi --config .claude/paywire-config.json --out ./billing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined


SKILL_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = SKILL_DIR / "templates"
DEFAULT_EVENTS_PATH = SKILL_DIR / "config" / "default-events.yaml"

SUPPORTED_FRAMEWORKS = ["fastapi", "django", "nextjs"]


# --- Framework detection ---

def detect_framework(search_dir: Path) -> str | None:
    """Return the detected framework name, or None if unrecognised."""
    files = {p.name for p in search_dir.iterdir() if p.is_file()}
    subdirs = {p.name for p in search_dir.iterdir() if p.is_dir()}

    # FastAPI: requirements.txt or pyproject.toml containing "fastapi"
    for req_file in ("requirements.txt", "requirements-base.txt"):
        req = search_dir / req_file
        if req.exists() and re.search(r"\bfastapi\b", req.read_text(), re.I):
            return "fastapi"

    pyproject = search_dir / "pyproject.toml"
    if pyproject.exists() and re.search(r"\bfastapi\b", pyproject.read_text(), re.I):
        return "fastapi"

    # Django: manage.py present
    if "manage.py" in files:
        return "django"

    # Next.js: next.config.js or next.config.ts
    if any(f.startswith("next.config") for f in files):
        return "nextjs"

    # Fallback: package.json with "next" dependency
    pkg = search_dir / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text())
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            if "next" in deps:
                return "nextjs"
            if "fastapi" in deps or "uvicorn" in deps:
                return "fastapi"
        except json.JSONDecodeError:
            pass

    return None


# --- Template rendering ---

def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        return json.load(f)


def _load_default_event_schema() -> dict[str, dict]:
    """Load default-events.yaml and return a lookup keyed by event name.

    This provides the full event schema (handler_class, resource_retrieve, etc.)
    so that a config only needs to specify {name, enabled} — scaffold enriches the rest.
    """
    if not DEFAULT_EVENTS_PATH.exists():
        return {}
    with open(DEFAULT_EVENTS_PATH) as f:
        data = yaml.safe_load(f)
    return {e["name"]: e for e in data.get("events", [])}


def build_context(config: dict) -> dict:
    """Build the Jinja2 template rendering context from user config.

    Events in config may be minimal ({name, enabled}) — this function merges the
    full schema from default-events.yaml so templates always have handler_class,
    resource_retrieve, resource, has_template, etc.
    """
    default_schema = _load_default_event_schema()

    # Merge: default schema fields are the base; config fields override them.
    merged_events = []
    for ev in config.get("events", []):
        base = dict(default_schema.get(ev["name"], {}))
        base.update(ev)  # config fields win (e.g. user toggled enabled)
        merged_events.append(base)

    selected_events = [e for e in merged_events if e.get("enabled", False)]
    selected_event_names = {e["name"] for e in selected_events}
    handler_modules = sorted({e["handler_module"] for e in selected_events})

    generic_handlers = [e for e in selected_events if not e.get("has_template", True)]
    templated_handlers = [e for e in selected_events if e.get("has_template", True)]

    return {
        "app_name": config.get("app_name", "myapp"),
        "pricing_model": config.get("pricing_model", "subscription"),
        "trial_days": config.get("trial_days", 0),
        "currencies": config.get("currencies", ["usd"]),
        "with_connect": config.get("with_connect", False),
        "pricing_tiers": config.get("pricing_tiers", []),
        "selected_events": selected_events,
        "selected_event_names": selected_event_names,
        "handler_modules": handler_modules,
        "generic_handlers": generic_handlers,
        "templated_handlers": templated_handlers,
        "stripe_api_version": config.get("stripe_api_version", "2026-04-22.dahlia"),
        "port": config.get("port", 8000),
        "generation_date": date.today().isoformat(),
    }


def render_framework(framework: str, config: dict, out_dir: Path, force: bool = False) -> list[Path]:
    """Render all templates for the given framework. Returns list of written paths."""
    template_dir = TEMPLATES_DIR / framework
    if not template_dir.exists():
        print(f"Error: no templates for framework '{framework}' (looked in {template_dir})", file=sys.stderr)
        sys.exit(1)

    env = Environment(
        loader=FileSystemLoader([str(template_dir), str(TEMPLATES_DIR / "shared")]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )

    context = build_context(config)
    written: list[Path] = []
    llm_sections: list[tuple[Path, int]] = []

    # Gather all .j2 files from the framework template directory (recursive).
    for j2_path in sorted(template_dir.rglob("*.j2")):
        rel = j2_path.relative_to(template_dir)
        # Strip .j2 suffix to get the output filename.
        out_path = out_dir / str(rel)[: -len(".j2")]

        if out_path.exists() and not force:
            print(f"  skip  {out_path} (already exists — use --force to overwrite)")
            continue

        template_name = str(rel)
        tmpl = env.get_template(template_name)
        rendered = tmpl.render(**context)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        written.append(out_path)
        print(f"  write {out_path}")

        # Collect LLM section locations for the post-scaffold report.
        for i, line in enumerate(rendered.splitlines(), 1):
            if "LLM_SECTION_START" in line:
                llm_sections.append((out_path, i))

    # Also render shared templates.
    shared_dir = TEMPLATES_DIR / "shared"
    for j2_path in sorted(shared_dir.rglob("*.j2")):
        rel = j2_path.relative_to(shared_dir)
        out_path = out_dir / str(rel)[: -len(".j2")]

        if out_path.exists() and not force:
            continue

        tmpl = env.get_template(str(rel))
        rendered = tmpl.render(**context)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        written.append(out_path)
        print(f"  write {out_path}")

    # Report LLM sections that need filling.
    if llm_sections:
        print("\nLLM sections to fill (Claude Code will handle these interactively):")
        for path, line in llm_sections:
            print(f"  {path}:{line}")

    return written


# --- CLI ---

def main() -> None:
    parser = argparse.ArgumentParser(description="paywire scaffold tool")
    parser.add_argument("--detect", action="store_true", help="Auto-detect framework in --dir")
    parser.add_argument("--dir", default=".", help="Directory to inspect for --detect (default: .)")
    parser.add_argument("--framework", choices=SUPPORTED_FRAMEWORKS, help="Target framework")
    parser.add_argument("--config", help="Path to config JSON (required for render)")
    parser.add_argument("--out", help="Output directory (required for render)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")

    args = parser.parse_args()

    if args.detect:
        fw = detect_framework(Path(args.dir))
        if fw:
            print(fw)
        else:
            print("unknown")
            print(
                "Could not auto-detect framework. Supported: fastapi, django, nextjs.\n"
                "Pass --framework explicitly to proceed.",
                file=sys.stderr,
            )
        return

    if args.framework:
        if not args.config or not args.out:
            parser.error("--config and --out are required when --framework is specified")
        config = load_config(args.config)
        render_framework(
            framework=args.framework,
            config=config,
            out_dir=Path(args.out),
            force=args.force,
        )
        return

    parser.print_help()


if __name__ == "__main__":
    main()
