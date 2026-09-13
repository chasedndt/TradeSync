"""Line endings are restored only where the vault re-point introduced CRLF."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "restore_hermes_line_endings", Path(__file__).resolve().parents[1] / "tools" / "restore_hermes_line_endings.py"
)
tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tool)


def test_a_file_the_repoint_rewrote_goes_back_to_lf_with_its_path_edit_kept() -> None:
    original = b"#!/usr/bin/env bash\nset -euo pipefail\ncd /mnt/c/Users/chaseos/Documents/chaseos_obsidian\n"
    live = b"#!/usr/bin/env bash\r\nset -euo pipefail\r\ncd /mnt/c/Users/chaseos/Documents/chaseos_chaseintech\r\n"
    assert tool.restored(live, original) == b"#!/usr/bin/env bash\nset -euo pipefail\ncd /mnt/c/Users/chaseos/Documents/chaseos_chaseintech\n"


def test_files_that_were_crlf_before_or_never_touched_or_already_lf_are_left_alone() -> None:
    windows_launcher = b"@echo off\r\ncd C:\\Users\\chaseos\\Documents\\chaseos_obsidian\r\n"
    assert tool.restored(b"@echo off\r\ncd x\r\n", windows_launcher) is None
    untouched = b"print('no vault here')\n"
    assert tool.restored(b"print('no vault here')\r\n", untouched) is None
    already_lf = b"cd /mnt/c/Users/chaseos/Documents/chaseos_obsidian\n"
    assert tool.restored(b"cd /mnt/c/Users/chaseos/Documents/chaseos_chaseintech\n", already_lf) is None


def test_scripts_go_to_lf_whatever_their_history_and_other_files_do_not() -> None:
    crlf = b"#!/usr/bin/env python3\r\nprint(1)\r\n"
    assert tool.normalised(crlf, "scripts/strikezone/step6b_cycle.py") == b"#!/usr/bin/env python3\nprint(1)\n"
    assert tool.normalised(b"set -euo pipefail\r\n", "scripts/watchdog.sh") == b"set -euo pipefail\n"
    assert tool.normalised(b"#!/bin/bash\r\necho hi\r\n", "scripts/no_suffix") == b"#!/bin/bash\necho hi\n"
    assert tool.normalised(b"@echo off\r\n", "scripts/open-profile.cmd") is None
    assert tool.normalised(b'{"a": 1}\r\n', "scripts/policy.json") is None
    assert tool.normalised(b"print(1)\n", "scripts/clean.py") is None


def test_a_lone_carriage_return_inside_a_line_is_not_touched() -> None:
    original = b"x = 'chaseos_obsidian'\n"
    live = b"x = 'a\rb'\r\ny = 1\r\n"
    assert tool.restored(live, original) == b"x = 'a\rb'\ny = 1\n"
