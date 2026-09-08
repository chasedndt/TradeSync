"""Track how long each pipeline stage has been in its current state.

A state without a duration is half a fact. "Scorer offline" reads the same
whether it dropped out ten seconds ago or has been down since yesterday, and
those call for completely different responses.

This module is pure. It compares the states just observed against the states
last recorded and reports what changed; persistence and clocks belong to the
caller so the comparison stays testable.

It also exists to make future alerting safe. A stage that flaps between two
states every poll would otherwise generate a notification per transition, so
the flap counter here is what lets a router suppress that.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "node_state_history_v1"

# A stage changing state more often than this within the flap window is
# oscillating rather than genuinely transitioning.
DEFAULT_FLAP_WINDOW_SECONDS = 900
DEFAULT_FLAP_THRESHOLD = 4


@dataclass(frozen=True)
class StateTransition:
    """One stage moving from one state to another."""

    node_id: str
    previous_state: str | None
    new_state: str
    at_epoch_s: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "at_epoch_s": self.at_epoch_s,
        }


def detect_transitions(
    observed: Mapping[str, str],
    last_known: Mapping[str, str],
    now_epoch_s: int,
) -> list[StateTransition]:
    """Return transitions for stages whose state differs from the last record.

    A stage seen for the first time is a transition from ``None``: its history
    starts now rather than pretending it has always been in this state.
    """

    transitions: list[StateTransition] = []
    for node_id in sorted(observed):
        new_state = observed[node_id]
        previous = last_known.get(node_id)
        if previous == new_state:
            continue
        transitions.append(
            StateTransition(
                node_id=node_id,
                previous_state=previous,
                new_state=new_state,
                at_epoch_s=now_epoch_s,
            )
        )
    return transitions


def describe_duration(seconds: float | int | None) -> str:
    """Human phrasing for how long a state has held.

    Deliberately coarse. "Offline for about 3 hours" is what an operator acts
    on; second-level precision on a multi-hour outage is noise.
    """

    if seconds is None:
        return "unknown"
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    return f"{days}d {hours}h" if hours else f"{days}d"


def count_flaps(
    transitions: Sequence[Mapping[str, Any]],
    now_epoch_s: int,
    window_seconds: int = DEFAULT_FLAP_WINDOW_SECONDS,
) -> int:
    """How many transitions a stage made inside the flap window."""

    cutoff = now_epoch_s - window_seconds
    return sum(
        1
        for item in transitions
        if isinstance(item, Mapping)
        and isinstance(item.get("at_epoch_s"), int)
        and item["at_epoch_s"] >= cutoff
    )


def is_flapping(
    transitions: Sequence[Mapping[str, Any]],
    now_epoch_s: int,
    window_seconds: int = DEFAULT_FLAP_WINDOW_SECONDS,
    threshold: int = DEFAULT_FLAP_THRESHOLD,
) -> bool:
    """Whether a stage is oscillating rather than settling.

    A flapping stage should not generate one alert per transition, and its
    current state should be read with suspicion: it is about to change again.
    """

    return count_flaps(transitions, now_epoch_s, window_seconds) >= threshold


def annotate_node(
    node: Mapping[str, Any],
    entered_at_epoch_s: int | None,
    now_epoch_s: int,
    recent_transitions: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Return the node with ageing and flap information attached."""

    enriched = dict(node)
    if entered_at_epoch_s is None:
        # Never observed before, or history was cleared. Say so rather than
        # implying the state is brand new.
        enriched["state_since_epoch_s"] = None
        enriched["state_duration_seconds"] = None
        enriched["state_age"] = "unknown"
    else:
        duration = max(0, now_epoch_s - entered_at_epoch_s)
        enriched["state_since_epoch_s"] = entered_at_epoch_s
        enriched["state_duration_seconds"] = duration
        enriched["state_age"] = describe_duration(duration)

    flaps = count_flaps(recent_transitions, now_epoch_s)
    enriched["recent_transitions"] = flaps
    enriched["flapping"] = is_flapping(recent_transitions, now_epoch_s)
    return enriched
