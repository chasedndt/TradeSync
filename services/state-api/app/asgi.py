"""The state-api process as deployed: every route in ``app.main``, behind the access guard.

``services/state-api/Dockerfile`` runs ``uvicorn app.asgi:app``. The guard wraps
the whole application instead of being added inside ``app.main``, so the rule
for changes lives in one small module and covers routes registered anywhere.
Tests that import ``app.main.app`` exercise the routes without it;
``tests/test_access_guard.py`` pins the Dockerfile to this entry point.
"""

from app.access_guard import AccessGuard
from app.main import app as routes

app = AccessGuard(routes)
