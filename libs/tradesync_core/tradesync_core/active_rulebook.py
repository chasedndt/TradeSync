"""Which adopted rulebook is active: one query every service reads the same way.

The paper scorer (core-scorer) and the operator surfaces (state-api) must agree
on the active rulebook, so the query and the validation of its stored config
live here rather than in two services that could drift apart.
"""

from __future__ import annotations

import json
from typing import Any

from .regime_weights import RegimeRulebook, validate_rulebook

ACTIVE_RULEBOOK_SQL = """
SELECT a.id AS activation_id, a.activated_at, a.activated_by, a.approval_reference,
       r.id AS rulebook_row_id, r.config, r.config_digest, r.version
FROM regime_weight_activations a
JOIN regime_rulebooks r ON r.id = a.regime_rulebook_id
WHERE a.environment = 'paper' AND a.deactivated_at IS NULL AND r.rulebook_id = $1
ORDER BY a.activated_at DESC
LIMIT 1
"""


def config_of(value: Any) -> dict[str, Any]:
    """A stored rulebook config; jsonb arrives as text or as a mapping."""
    return json.loads(value) if isinstance(value, (str, bytes)) else dict(value)


def rulebook_from_config(value: Any) -> RegimeRulebook:
    """Validate a stored config. Raises RulebookValidationError, ValueError or TypeError."""
    return validate_rulebook(config_of(value))
