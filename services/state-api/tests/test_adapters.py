import sys
import os
import pytest
from unittest.mock import MagicMock

# Hack to import from root executor folder for testing
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from executor.drift_exec import DriftExecutor
from executor.hyper_exec import HyperLiquidExecutor
from executor.exec_interface import OrderRequest

@pytest.mark.asyncio
async def test_drift_dry_run():
    exec = DriftExecutor(dry_run=True)
    order = OrderRequest(symbol="BTC-PERP", size=100.0, action="BUY")
    result = await exec.execute_order(order)
    
    assert result.status == "filled_dry_run"
    assert result.details["venue"] == "drift"

@pytest.mark.asyncio
async def test_hyper_dry_run():
    exec = HyperLiquidExecutor(dry_run=True)
    order = OrderRequest(symbol="ETH-PERP", size=50.0, action="SELL")
    result = await exec.execute_order(order)
    
    assert result.status == "filled_dry_run"
    assert result.details["venue"] == "hyperliquid"
