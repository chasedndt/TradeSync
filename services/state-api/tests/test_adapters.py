import sys
import os
import pytest
from unittest.mock import MagicMock

# Hack to import from root executor folder for testing
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from executor.hyper_exec import HyperLiquidExecutor
from executor.exec_interface import OrderRequest

@pytest.mark.asyncio
async def test_hyperliquid_dry_run():
    executor = HyperLiquidExecutor(dry_run=True)
    order = OrderRequest(symbol="BTC-PERP", size=100.0, action="BUY")
    result = await executor.execute_order(order)

    assert result.status == "filled_dry_run"
    assert result.details["venue"] == "hyperliquid"
