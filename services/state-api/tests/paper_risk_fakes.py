"""Fakes for the paper risk tests: a pool whose connection records statements and counts savepoints."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock


class FakeConn:
    def __init__(self, fetchrow=None, fetchval=None, fetch=None):
        self.statements = []
        self.transactions = 0
        self.fetchrow = AsyncMock(return_value=fetchrow)
        self.fetchval = AsyncMock(return_value=fetchval)
        self.fetch = AsyncMock(return_value=fetch if fetch is not None else [])
        self.execute = AsyncMock(side_effect=self._execute)

    async def _execute(self, sql, *args):
        self.statements.append((sql, args))
        return "OK"

    def transaction(self, **kwargs):
        @asynccontextmanager
        async def tx():
            self.transactions += 1
            yield

        return tx()


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        @asynccontextmanager
        async def acquired():
            yield self.conn

        return acquired()


def pool_of(conn):
    @asynccontextmanager
    async def acquire():
        yield conn

    return MagicMock(acquire=acquire)
