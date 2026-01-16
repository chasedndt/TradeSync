import json
from datetime import datetime
import uuid

def calculate_score(event):
    """
    Analyzes an event and returns a list of Opportunity dicts (or empty list).
    """
    payload = event.get("payload", {})
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except:
            pass
            
    symbol = event.get("symbol")
    timeframe = event.get("timeframe")
    
    # Simple logic: If payload has "bias" or "action", use it.
    # Example TV payload: {"symbol": "BTCUSDT", "bias": "LONG", "confidence": 80}
    
    bias_str = payload.get("bias", "").upper()
    action = payload.get("action", "").upper()
    
    direction = None
    if "LONG" in bias_str or "BUY" in action:
        direction = "LONG"
    elif "SHORT" in bias_str or "SELL" in action:
        direction = "SHORT"
        
    if not direction:
        return []
        
    confidence = float(payload.get("confidence", 50))
    
    # Create Opportunity
    opp = {
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "timeframe": timeframe,
        "snapshot_ts": datetime.now(),
        "bias": confidence, # Mapping confidence to bias score for now
        "quality": confidence, # Placeholder
        "dir": direction,
        "confluence": {"source": "tradingview"},
        "status": "new"
    }
    
    return [opp]