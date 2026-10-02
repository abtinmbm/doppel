"""Runs every assert-based check in scripts/*_test.py as a pytest test.

The checks live in scripts/ as plain scripts so each can also be run on its
own (uv run python scripts/collector_test.py) and print its own summary.
This file lets pytest, and the GitHub Actions workflow, run them all.

How it works:
    1. Collect every scripts/*_test.py. That pattern is reserved for safe
       checks: scripts that hook the real keyboard are named *_demo.py and
       are never collected.
    2. Make one pytest case per script (parametrize), named after the file.
    3. Run each script with runpy from the repository root, because the
       scripts use relative paths such as data/... . A failing assert inside
       the script fails that case, with the script's own traceback.
"""

import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = sorted((ROOT / "scripts").glob("*_test.py"))


def test_scripts_were_found() -> None:
    """Guard against the glob silently matching nothing."""
    assert SCRIPTS, "no scripts/*_test.py found"


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.stem)
def test_script(script: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run one check script; any failing assert fails this test."""
    monkeypatch.chdir(ROOT)  # the scripts use paths relative to the repository root
    runpy.run_path(str(script), run_name="__main__")
