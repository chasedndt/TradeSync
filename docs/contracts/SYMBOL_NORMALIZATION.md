# Symbol Normalization Contract

> **Purpose**: Define canonical symbol format and venue-specific mappings.
> **Invariant**: UI and internal systems only see canonical symbols.
> **Last Updated**: 2026-01-21

---

## 1. Canonical Format

**Format**: `{BASE}-PERP`

**Examples**:
- `BTC-PERP`
- `ETH-PERP`
- `SOL-PERP`

**Rules**:
1. Base asset in UPPERCASE
2. Always suffixed with `-PERP` for perpetual contracts
3. No quote currency in canonical symbol (USDT/USDC/USD abstracted)
4. No venue prefix/suffix

---

## 2. Supported Symbols (V1)

| Canonical | Display Name | Description |
|-----------|-------------|-------------|
| `BTC-PERP` | Bitcoin Perp | BTC perpetual contract |
| `ETH-PERP` | Ethereum Perp | ETH perpetual contract |
| `SOL-PERP` | Solana Perp | SOL perpetual contract |

### Future Additions

| Canonical | Notes |
|-----------|-------|
| `DOGE-PERP` | After V1 |
| `ARB-PERP` | After V1 |
| `OP-PERP` | After V1 |
| `AVAX-PERP` | After V1 |

---

## 3. Venue Symbol Mappings

### 3.1 Hyperliquid

| API Symbol | Canonical | Notes |
|------------|-----------|-------|
| `BTC` | `BTC-PERP` | Base only |
| `ETH` | `ETH-PERP` | Base only |
| `SOL` | `SOL-PERP` | Base only |

**Transformation**:
```python
def hl_to_canonical(hl_symbol: str) -> str:
    """Hyperliquid uses base-only symbols."""
    return f"{hl_symbol.upper()}-PERP"

def canonical_to_hl(canonical: str) -> str:
    """Convert back to HL format for API calls."""
    return canonical.replace("-PERP", "")
```

### 3.2 Drift

| API Symbol | Canonical | Notes |
|------------|-----------|-------|
| `BTC-PERP` | `BTC-PERP` | Already canonical |
| `ETH-PERP` | `ETH-PERP` | Already canonical |
| `SOL-PERP` | `SOL-PERP` | Already canonical |

**Transformation**:
```python
def drift_to_canonical(drift_symbol: str) -> str:
    """Drift uses canonical format already."""
    return drift_symbol.upper()

def canonical_to_drift(canonical: str) -> str:
    """No transformation needed."""
    return canonical
```

### 3.3 Future: Binance Futures

| API Symbol | Canonical | Notes |
|------------|-----------|-------|
| `BTCUSDT` | `BTC-PERP` | Quote suffix |
| `ETHUSDT` | `ETH-PERP` | Quote suffix |
| `SOLUSDT` | `SOL-PERP` | Quote suffix |

**Transformation**:
```python
def binance_to_canonical(binance_symbol: str) -> str:
    """Binance uses BASEUSDT format."""
    # Remove common quote suffixes
    for suffix in ["USDT", "USDC", "BUSD", "USD"]:
        if binance_symbol.upper().endswith(suffix):
            base = binance_symbol.upper()[:-len(suffix)]
            return f"{base}-PERP"
    return f"{binance_symbol.upper()}-PERP"
```

---

## 4. Normalization Function

```python
# File: services/shared/normalize.py

from typing import Literal

Venue = Literal["hyperliquid", "drift", "binance"]

VENUE_MAPPINGS = {
    "hyperliquid": {
        # HL symbol -> canonical
        "BTC": "BTC-PERP",
        "ETH": "ETH-PERP",
        "SOL": "SOL-PERP",
    },
    "drift": {
        # Drift already canonical
        "BTC-PERP": "BTC-PERP",
        "ETH-PERP": "ETH-PERP",
        "SOL-PERP": "SOL-PERP",
    },
}

REVERSE_MAPPINGS = {
    "hyperliquid": {v: k for k, v in VENUE_MAPPINGS["hyperliquid"].items()},
    "drift": {v: k for k, v in VENUE_MAPPINGS["drift"].items()},
}


def normalize_symbol(symbol: str, venue: Venue = None) -> str:
    """
    Normalize any symbol to canonical BASE-PERP format.

    Args:
        symbol: Raw symbol from venue or user input
        venue: Optional venue hint for accurate mapping

    Returns:
        Canonical symbol (e.g., "BTC-PERP")
    """
    if not symbol:
        return symbol

    s = symbol.upper().strip()

    # If venue provided, use direct mapping
    if venue and venue in VENUE_MAPPINGS:
        if s in VENUE_MAPPINGS[venue]:
            return VENUE_MAPPINGS[venue][s]

    # Generic normalization
    # 1. Handle common quote suffixes
    for suffix in ["USDT", "USDC", "BUSD", "USD"]:
        if s.endswith(suffix):
            s = s[:-len(suffix)] + "-PERP"
            break

    # 2. Handle slash separators
    s = s.replace("/", "-")

    # 3. Ensure -PERP suffix
    if not s.endswith("-PERP"):
        if "-" in s:
            base = s.split("-")[0]
            s = f"{base}-PERP"
        else:
            s = f"{s}-PERP"

    return s


def denormalize_symbol(canonical: str, venue: Venue) -> str:
    """
    Convert canonical symbol back to venue-specific format.

    Args:
        canonical: Canonical symbol (e.g., "BTC-PERP")
        venue: Target venue

    Returns:
        Venue-specific symbol
    """
    if not canonical:
        return canonical

    c = canonical.upper().strip()

    if venue in REVERSE_MAPPINGS and c in REVERSE_MAPPINGS[venue]:
        return REVERSE_MAPPINGS[venue][c]

    # Fallback: assume venue uses canonical
    return c


def normalize_venue(venue: str) -> str:
    """
    Normalize venue names.

    Accepts: hl, hyperliquid, drift, HL, DRIFT
    Returns: hyperliquid, drift
    """
    if not venue:
        return venue

    v = venue.lower().strip()

    aliases = {
        "hl": "hyperliquid",
        "hyper": "hyperliquid",
        "hyperliquid": "hyperliquid",
        "drift": "drift",
    }

    return aliases.get(v, v)
```

---

## 5. Validation

```python
import re

CANONICAL_PATTERN = re.compile(r"^[A-Z]{2,10}-PERP$")
SUPPORTED_SYMBOLS = {"BTC-PERP", "ETH-PERP", "SOL-PERP"}


def is_valid_canonical(symbol: str) -> bool:
    """Check if symbol matches canonical format."""
    return bool(CANONICAL_PATTERN.match(symbol))


def is_supported_symbol(symbol: str) -> bool:
    """Check if symbol is in supported list."""
    return symbol in SUPPORTED_SYMBOLS


def validate_symbol(symbol: str) -> tuple[bool, str]:
    """
    Validate a symbol.

    Returns:
        (is_valid, error_message)
    """
    if not symbol:
        return False, "Symbol is empty"

    if not is_valid_canonical(symbol):
        return False, f"Invalid format: {symbol}. Expected BASE-PERP"

    if not is_supported_symbol(symbol):
        return False, f"Unsupported symbol: {symbol}"

    return True, ""
```

---

## 6. UI Display

| Canonical | Short Display | Full Display |
|-----------|---------------|--------------|
| `BTC-PERP` | `BTC` | `Bitcoin Perpetual` |
| `ETH-PERP` | `ETH` | `Ethereum Perpetual` |
| `SOL-PERP` | `SOL` | `Solana Perpetual` |

```typescript
// UI display helper
const SYMBOL_DISPLAY: Record<string, { short: string; full: string }> = {
  "BTC-PERP": { short: "BTC", full: "Bitcoin Perpetual" },
  "ETH-PERP": { short: "ETH", full: "Ethereum Perpetual" },
  "SOL-PERP": { short: "SOL", full: "Solana Perpetual" },
};

function displaySymbol(canonical: string, format: "short" | "full" = "short"): string {
  const display = SYMBOL_DISPLAY[canonical];
  if (!display) return canonical;
  return display[format];
}
```

---

## 7. Venue Display

| Internal | Display |
|----------|---------|
| `hyperliquid` | `Hyperliquid` |
| `drift` | `Drift` |

```typescript
const VENUE_DISPLAY: Record<string, string> = {
  hyperliquid: "Hyperliquid",
  drift: "Drift",
};
```

---

## 8. Cross-Reference: Where Normalization Happens

| Location | Direction | Notes |
|----------|-----------|-------|
| `market-poller` | raw → norm | First normalization point |
| `market-normalizer` | verify | Double-check canonical |
| `state-api` | verify | Validate incoming requests |
| `cockpit-ui` | display | Show user-friendly names |
| `exec-*-svc` | norm → raw | Denormalize for venue API |

---

## 9. Error Handling

When encountering unknown symbols:

1. **Log warning** with raw symbol and venue
2. **Attempt generic normalization** (add -PERP suffix)
3. **Mark as unsupported** in response if not in supported list
4. **Never crash** - gracefully degrade

```python
def safe_normalize(symbol: str, venue: str = None) -> tuple[str, bool]:
    """
    Normalize with fallback.

    Returns:
        (normalized_symbol, is_supported)
    """
    try:
        normalized = normalize_symbol(symbol, venue)
        supported = is_supported_symbol(normalized)
        return normalized, supported
    except Exception as e:
        logger.warning(f"Failed to normalize {symbol} from {venue}: {e}")
        return f"{symbol.upper()}-PERP", False
```

---

*Last updated: 2026-01-21*
*Phase: 3B — Market Data Expansion*
