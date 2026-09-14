"""Retired execution wording stays out of the Cockpit and out of backend text it shows verbatim.

TradeSync is paper-only by construction: execution is not connected. Labels such
as "demo", "observe mode", "dry run" or "simulated" describe no state an operator
can act on, and they had come to sit on every page. The rendered Cockpit strings
are checked by parsing the TypeScript (services/cockpit-ui/tests/ui-wording.test.mjs);
the backend notes the Cockpit prints as they arrive are checked here.
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _service_import import load_service_module  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COCKPIT = ROOT / "services" / "cockpit-ui"
RETIRED = re.compile(r"\bdemo\b|\bobserve\b|dry[\s_-]?run|\bsimulat\w*", re.IGNORECASE)


def _module_constant(relative: str, name: str) -> object:
    """A module-level literal, read from source for modules that need the app package to import."""
    for node in ast.parse((ROOT / relative).read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{relative} no longer defines {name}")


def test_rehearsal_notes_the_cockpit_prints_avoid_retired_wording() -> None:
    rehearsal = load_service_module("state_api_app", "state-api", "rehearsal")
    for text in (rehearsal.PAPER_NOTE, rehearsal.LIST_NOTE, *rehearsal.LEGACY_NOTES.values()):
        assert not RETIRED.search(text), text


def test_stored_rehearsals_with_the_old_default_note_read_in_current_wording() -> None:
    rehearsal = load_service_module("state_api_app", "state-api", "rehearsal")
    legacy = next(iter(rehearsal.LEGACY_NOTES))
    row = {"id": "r-1", "opportunity_id": "o-1", "created_at": datetime(2026, 9, 14, tzinfo=timezone.utc),
           "note": legacy, "plan": "{}", "risk_verdict": "{}", "fill": None, "market": "{}"}
    assert rehearsal._row_to_dict(row)["note"] == rehearsal.PAPER_NOTE


def test_the_managed_paper_note_avoids_retired_wording() -> None:
    note = _module_constant("services/state-api/app/managed_paper.py", "POSITIONS_NOTE")
    assert isinstance(note, str) and not RETIRED.search(note)


@pytest.mark.skipif(
    shutil.which("node") is None or not (COCKPIT / "node_modules" / "typescript").exists(),
    reason="node and the Cockpit's TypeScript are needed to parse the UI sources",
)
def test_rendered_cockpit_strings_avoid_retired_wording() -> None:
    result = subprocess.run(
        ["node", "--test", "tests/ui-wording.test.mjs"],
        cwd=COCKPIT, capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, (result.stdout[-4000:] + result.stderr[-2000:])
