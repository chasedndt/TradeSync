"""A change reaches its route only from the Cockpit's pages or a non-browser caller, and with the token when one is set."""

import asyncio
import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import main
from app.access_guard import DEFAULT_ORIGINS, EXEMPT_PATHS, ORIGINS_ENV, POLICY_PATH, AccessGuard
from tradesync_core.state_api_access import MIN_TOKEN_CHARS, TOKEN_ENV, TOKEN_HEADER

TOKEN = "s" * MIN_TOKEN_CHARS
FOREIGN = "https://example.invalid"
SERVICE = Path(__file__).resolve().parents[1]
CHANGES = ("post", "put", "patch", "delete")


def _probe(**guard):
    """A guarded app whose routes record that they ran."""
    reached = []
    inner = FastAPI()

    @inner.api_route("/state/change", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def change(request: Request):
        reached.append(request.method)
        return {"ok": True}

    @inner.post("/webhook/tradingview")
    async def webhook():
        reached.append("webhook")
        return {"ok": True}

    return TestClient(AccessGuard(inner, **guard)), reached


def test_without_a_token_a_non_browser_change_passes_as_before():
    client, reached = _probe(token="", allowed_origins=[])
    for method in CHANGES:
        assert getattr(client, method)("/state/change").status_code == 200
    assert reached == ["POST", "PUT", "PATCH", "DELETE"]


def test_the_cockpit_origins_may_make_changes():
    client, reached = _probe(token="", allowed_origins=[])
    for origin in ("http://127.0.0.1:3000", "http://localhost:3000", "http://LOCALHOST:3000/"):
        assert client.post("/state/change", headers={"Origin": origin}).status_code == 200
    assert len(reached) == 3


@pytest.mark.parametrize("origin", [FOREIGN, "null", "http://127.0.0.1:3001", "http://localhost.example.invalid:3000"])
def test_a_change_from_any_other_web_page_is_refused_before_its_route(origin):
    client, reached = _probe(token="", allowed_origins=[])
    for method in CHANGES:
        response = getattr(client, method)("/state/change", headers={"Origin": origin})
        assert response.status_code == 403
        assert POLICY_PATH in response.json()["detail"]
    assert reached == []


def test_reads_are_not_guarded():
    client, reached = _probe(token=TOKEN, allowed_origins=[])
    assert client.get("/state/change", headers={"Origin": FOREIGN}).status_code == 200
    assert reached == ["GET"]


def test_extra_origins_come_from_configuration():
    client, _ = _probe(token="", allowed_origins=["HTTP://Studio.Local:5173/"])
    assert client.post("/state/change", headers={"Origin": "http://studio.local:5173"}).status_code == 200
    with patch.dict(os.environ, {ORIGINS_ENV: " http://127.0.0.1:3001 , ", TOKEN_ENV: ""}):
        from_env = TestClient(AccessGuard(FastAPI()))
        assert "http://127.0.0.1:3001" in from_env.get(POLICY_PATH).json()["allowed_origins"]


def test_a_wildcard_origin_switches_the_origin_check_off_and_leaves_the_token_in_force():
    client, reached = _probe(token="", allowed_origins=["*"])
    assert client.post("/state/change", headers={"Origin": FOREIGN}).status_code == 200
    policy = client.get(POLICY_PATH).json()
    assert policy["origin_check"] == "disabled" and "*" not in policy["allowed_origins"]
    guarded, _ = _probe(token=TOKEN, allowed_origins=["*"])
    assert guarded.post("/state/change", headers={"Origin": FOREIGN}).status_code == 401
    assert reached == ["POST"]


def test_with_a_token_every_change_must_carry_it():
    client, reached = _probe(token=TOKEN, allowed_origins=[])
    assert client.post("/state/change").status_code == 401
    assert client.post("/state/change", headers={TOKEN_HEADER: "s" * (MIN_TOKEN_CHARS + 1)}).status_code == 401
    assert client.delete("/state/change", headers={TOKEN_HEADER: TOKEN[:-1]}).status_code == 401
    assert client.post("/state/change", headers={"Origin": "http://127.0.0.1:3000"}).status_code == 401
    assert reached == []
    assert client.post("/state/change", headers={TOKEN_HEADER: TOKEN}).status_code == 200
    assert client.put("/state/change", headers={TOKEN_HEADER.lower(): TOKEN, "Origin": "http://localhost:3000"}).status_code == 200
    assert reached == ["POST", "PUT"]


def test_a_token_from_the_environment_is_enforced():
    with patch.dict(os.environ, {TOKEN_ENV: TOKEN}):
        guarded = TestClient(AccessGuard(FastAPI()))
    assert guarded.post("/anything").status_code == 401


def test_a_too_short_token_refuses_every_change_instead_of_switching_the_guard_off():
    client, reached = _probe(token="short", allowed_origins=[])
    response = client.post("/state/change", headers={TOKEN_HEADER: "short"})
    assert response.status_code == 503
    assert TOKEN_ENV in response.json()["detail"]
    assert client.get("/state/change").status_code == 200
    assert reached == ["GET"]


def test_a_refusal_is_logged_without_any_header_value(caplog):
    client, _ = _probe(token=TOKEN, allowed_origins=[])
    wrong = "w" * (MIN_TOKEN_CHARS + 8)
    with caplog.at_level(logging.WARNING, logger="state-api"):
        client.post("/state/change", headers={TOKEN_HEADER: wrong})
    assert "change refused: POST '/state/change' -> HTTP 401" in caplog.text
    assert wrong not in caplog.text and TOKEN not in caplog.text


def test_the_tradingview_webhook_authenticates_itself_and_is_exempt():
    assert EXEMPT_PATHS == frozenset({"/webhook/tradingview"})
    client, reached = _probe(token=TOKEN, allowed_origins=[])
    assert client.post("/webhook/tradingview", headers={"Origin": FOREIGN}).status_code == 200
    assert reached == ["webhook"]


@pytest.mark.parametrize("token,state", [("", "disabled"), (TOKEN, "required"), ("short", "misconfigured")])
def test_the_policy_reports_what_is_enforced_but_never_the_token(token, state):
    client, _ = _probe(token=token, allowed_origins=[])
    response = client.get(POLICY_PATH)
    assert response.status_code == 200
    policy = response.json()
    assert policy["operator_token"] == state
    assert policy["origin_check"] == "enforced"
    assert policy["token_header"] == TOKEN_HEADER
    assert set(DEFAULT_ORIGINS) <= set(policy["allowed_origins"])
    assert not token or token not in response.text


def test_lifespan_and_other_scopes_pass_through_untouched():
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["type"])

    asyncio.run(AccessGuard(inner, token=TOKEN)({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]


def test_the_deployed_entry_point_is_the_guarded_app():
    from app import asgi

    assert isinstance(asgi.app, AccessGuard)
    assert asgi.app.app is main.app


def test_the_real_routes_refuse_a_cross_site_change_before_running():
    client = TestClient(AccessGuard(main.app, token="", allowed_origins=[]))
    body = {"entries_paused": False, "reason": "cross-site change"}
    assert client.post("/state/paper-control", json=body, headers={"Origin": FOREIGN}).status_code == 403
    # With no browser origin the route answers for itself, exactly as it did before the guard.
    assert client.post("/state/paper-control", json=body).status_code not in (401, 403)


def test_with_a_token_the_real_routes_refuse_an_unauthenticated_fleet_directive():
    client = TestClient(AccessGuard(main.app, token=TOKEN, allowed_origins=[]))
    directive = {"job_id": "any", "kind": "set_workdir", "workdir": "/tmp"}
    assert client.post("/state/fleet/directives", json=directive).status_code == 401


def test_the_container_serves_the_guarded_entry_point():
    commands = [line.strip() for line in (SERVICE / "Dockerfile").read_text(encoding="utf-8").splitlines() if line.startswith("CMD ")]
    assert commands == ['CMD ["uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "8000"]']
