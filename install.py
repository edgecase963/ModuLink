#!/usr/bin/env python3
"""
ModuLink installer / packager

Goals:
- `python3 install.py --dev`  → editable install + packaging tools
- `python3 install.py`        → build a wheel using `python -m build --wheel`

Same workflow as Avalink, tailored to this project's `modulink/` + `pyproject.toml` layout.
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_NAME = "modulink"


def _load_project_version(project_root: Path) -> str:
    version_path = project_root / "modulink" / "__version__.py"
    namespace: dict[str, object] = {}
    exec(version_path.read_text(encoding="utf-8"), namespace)
    v = namespace.get("__version__")
    if not isinstance(v, str) or not v:
        raise RuntimeError(f"Could not determine __version__ from {version_path}")
    return v


def read_requirements(requirements_path: Path) -> list[str]:
    if not requirements_path.exists():
        return []
    reqs: list[str] = []
    for line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        reqs.append(line)
    return reqs


def _pip_cmd(args: list[str]) -> list[str]:
    if shutil.which("uv"):
        return ["uv", "pip", *args]
    return [sys.executable, "-m", "pip", *args]


def run_dev_install(project_root: Path) -> None:
    """Install packaging extras, then ModuLink in editable mode."""
    version = _load_project_version(project_root)
    requirements_path = project_root / "requirements.txt"
    extras = read_requirements(requirements_path)
    if extras:
        cmd = _pip_cmd(["install", "-r", str(requirements_path)])
        print("Running:", " ".join(cmd))
        subprocess.check_call(cmd)

    cmd = _pip_cmd(["install", "-e", str(project_root)])
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)
    print(
        f"Successfully installed {PROJECT_NAME} {version} "
        "in development (editable) mode."
    )


def build_wheel(project_root: Path) -> None:
    """Build a wheel for ModuLink using `python -m build --wheel`.

    The resulting wheel is written under `dist/`.
    """
    version = _load_project_version(project_root)
    print(f"Building {PROJECT_NAME} {version} wheel")

    try:
        if importlib.util.find_spec("build.__main__") is None:
            raise ImportError("build.__main__ not found")
    except Exception:
        print(
            "PyPI `build` package not found (or shadowed).\n"
            "Install packaging extras first:\n"
            "  python3 install.py --dev\n"
            "or: python -m pip install -r requirements.txt\n"
        )
        raise SystemExit(2)

    dist_dir = project_root / "dist"
    dist_dir.mkdir(exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "build",
        "--wheel",
        "--outdir",
        str(dist_dir),
        str(project_root),
    ]
    print("Running:", " ".join(cmd))
    # Run from the parent dir so a local `build/` artifact cannot shadow the tool.
    subprocess.check_call(cmd, cwd=str(project_root.parent))

    wheels = sorted(dist_dir.glob("*.whl"))
    if wheels:
        print("Built wheel(s):")
        for wheel in wheels:
            print("  ", wheel)
    else:
        print("Build completed, but no wheel was found in dist/.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install / package ModuLink")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Install ModuLink in editable (development) mode in the current environment",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    if args.dev:
        run_dev_install(project_root)
    else:
        build_wheel(project_root)


if __name__ == "__main__":
    main()
