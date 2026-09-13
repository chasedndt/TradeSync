"""Background loops start under the lifespan, survive a failing loop, and stop cleanly."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from app import background

APP_DIR = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(background, "_factories", [])
    monkeypatch.setattr(background, "_tasks", [])
    monkeypatch.setenv("STATE_API_BACKGROUND_LOOPS", "true")


def test_no_module_relies_on_ignored_startup_hooks():
    # The app uses a lifespan handler; FastAPI never runs on_event("startup") hooks then.
    offenders = [p.name for p in APP_DIR.glob("*.py") if re.search(r"on_event\(\s*[\"']startup", p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_register_once_start_and_stop():
    ticks: list[str] = []

    async def loop():
        while True:
            ticks.append("tick")
            await asyncio.sleep(0.01)

    async def scenario():
        background.add("beat", loop)
        background.add("beat", loop)
        assert background.registered() == ["beat"]
        assert background.start_all() == ["beat"]
        assert background.start_all() == []  # already running
        await asyncio.sleep(0.05)
        assert background.running() == ["beat"]
        await background.stop_all()
        assert background.running() == []

    asyncio.run(scenario())
    assert ticks


def test_failing_loop_is_contained():
    async def broken():
        raise RuntimeError("boom")

    async def fine():
        await asyncio.sleep(0.05)

    async def scenario():
        background.add("broken", broken)
        background.add("fine", fine)
        assert background.start_all() == ["broken", "fine"]
        await asyncio.sleep(0.01)
        assert background.running() == ["fine"]
        await background.stop_all()

    asyncio.run(scenario())


def test_disabled_by_environment(monkeypatch):
    monkeypatch.setenv("STATE_API_BACKGROUND_LOOPS", "false")

    async def loop():
        await asyncio.sleep(1)

    async def scenario():
        background.add("beat", loop)
        assert background.start_all() == []

    asyncio.run(scenario())


def test_app_registers_its_loops():
    sources = "".join(p.read_text(encoding="utf-8") for p in APP_DIR.glob("*.py"))
    names = set(re.findall(r"background\.add\(\s*\"([a-z_]+)\"", sources))
    assert {"hermes_link", "event_outlook", "thesis_editions"} <= names
    assert "background.start_all()" in (APP_DIR / "main.py").read_text(encoding="utf-8")
