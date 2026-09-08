"""Versioned task/response envelope for advisory agent harnesses.

Hermes, OpenClaw and a local Ollama may **explain, compare, and draft
proposals**. They may not score, gate, approve or execute. Until now that
boundary was documented — the pipeline inspector said in as many words that the
"Hermes/Ollama boundary is documented as advisory" — and a documented boundary
is one that holds until somebody wires a response straight into evidence.

This module makes it structural, in three ways:

**The response type cannot express authority.** There is no field on a harness
response for a score, a direction, an approval or an execution instruction. A
model that emits one is not partially honoured; the response is refused and the
attempted field is named. A model asked to produce JSON will happily produce
`{"approved": true}` if its prompt was poisoned by a document it read, and that
is the threat here, not a malicious operator.

**A response is never evidence.** Every accepted response goes to quarantine
with source ``agent_harness``, which means extraction, a proposed delta, and an
operator promotion before anything reaches the scoring path. Same route as a
TradingView alert, for the same reason.

**The task carries what it is allowed to ask for.** A task declares an
``intent`` from a closed set. There is no intent that means "decide"; the
vocabulary itself has no word for it.

The harness runtime is optional and TradeSync must work without it. Nothing here
requires a model to be reachable.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "agent_task_v1"
RESPONSE_SCHEMA_VERSION = "agent_response_v1"

# What a harness may be asked to do. Every one of these produces prose or a
# comparison for a human to read. None of them produces a decision, and the
# vocabulary deliberately has no word that would.
INTENTS = frozenset(
    {
        "explain",        # put a measurement into words
        "compare",        # set two things side by side
        "summarise",      # shorten something the operator already has
        "draft_proposal",  # write a change for an operator to consider
        "critique",       # argue against something, to be read not obeyed
    }
)

# Fields a response must never carry. A harness output that sets any of these is
# claiming an authority the harness does not have. Refused by name rather than
# stripped: a model emitting `approved: true` is a signal about the prompt it
# was given, and silently deleting it destroys that signal.
FORBIDDEN_RESPONSE_FIELDS = frozenset(
    {
        "admitted",
        "approved",
        "approval",
        "authority",
        "confidence_score",
        "direction",
        "execute",
        "execution_authority",
        "gate",
        "order",
        "score",
        "scoring_allowed",
        "side",
        "signal",
        "signal_kind",
        "tier",
        "trust",
        "weight",
    }
)

# A harness answer is prose for a person. A megabyte of it is a runaway
# generation, not an explanation.
MAX_RESPONSE_BYTES = 64 * 1024
MAX_PROMPT_BYTES = 32 * 1024


class HarnessError(ValueError):
    """A task or response failed the advisory-only contract."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def build_task(
    intent: str,
    prompt: str,
    *,
    context: Mapping[str, Any] | None = None,
    requested_by: str = "operator",
) -> dict[str, Any]:
    """Build a task envelope a harness is permitted to receive.

    ``context`` is evidence TradeSync already holds, passed so the answer is
    about this system rather than about the model's training data. It is copied
    in as data; nothing in it is executed or interpreted.
    """
    if intent not in INTENTS:
        raise HarnessError(
            "unknown_intent",
            f"intent {intent!r} is not one of: " + ", ".join(sorted(INTENTS)),
        )
    if not prompt or not prompt.strip():
        raise HarnessError("empty_prompt", "a task must state what is being asked")

    encoded = prompt.encode("utf-8")
    if len(encoded) > MAX_PROMPT_BYTES:
        raise HarnessError(
            "prompt_too_large",
            f"prompt is {len(encoded)} bytes, over the {MAX_PROMPT_BYTES} limit",
        )

    task = {
        "schema_version": SCHEMA_VERSION,
        "intent": intent,
        "prompt": prompt,
        "context": dict(context or {}),
        "requested_by": requested_by,
        # Stated on the task itself so a harness that logs what it received has
        # the boundary in its own records, not only in ours.
        "authority": {
            "advisory_only": True,
            "may_score": False,
            "may_approve": False,
            "may_execute": False,
            "response_routes_to": "quarantine",
        },
    }
    task["task_digest"] = _digest(
        {k: task[k] for k in ("schema_version", "intent", "prompt", "context")}
    )
    return task


def validate_response(
    response: Mapping[str, Any],
    task: Mapping[str, Any],
) -> dict[str, Any]:
    """Check a harness answer against the advisory-only contract.

    Raises ``HarnessError`` with a code. There is no partial acceptance and no
    quiet cleanup: a response that reached for authority is refused whole, so
    the attempt is visible rather than absorbed.
    """
    if not isinstance(response, Mapping):
        raise HarnessError("malformed_response", "response must be a JSON object")

    if response.get("schema_version") != RESPONSE_SCHEMA_VERSION:
        raise HarnessError(
            "unsupported_schema",
            f"expected {RESPONSE_SCHEMA_VERSION}, got {response.get('schema_version')!r}",
        )

    # The digest binds an answer to the question. Without it a stale or
    # substituted answer reads as a reply to whatever was asked most recently.
    if response.get("task_digest") != task.get("task_digest"):
        raise HarnessError(
            "task_mismatch",
            "response does not carry the digest of the task it answers",
        )

    reached_for = sorted(FORBIDDEN_RESPONSE_FIELDS.intersection(response))
    if reached_for:
        raise HarnessError(
            "authority_claimed",
            "harness response claims authority it does not have: "
            + ", ".join(reached_for)
            + ". A harness may explain, compare and draft; it may not decide.",
        )

    content = response.get("content")
    if not isinstance(content, str) or not content.strip():
        raise HarnessError("empty_content", "a response must carry prose content")

    encoded = content.encode("utf-8")
    if len(encoded) > MAX_RESPONSE_BYTES:
        raise HarnessError(
            "response_too_large",
            f"content is {len(encoded)} bytes, over the {MAX_RESPONSE_BYTES} limit",
        )

    # Nested objects get the same treatment. A model told to answer in JSON will
    # nest, and a boundary that only checks the top level is not a boundary.
    nested = _nested_forbidden(response)
    if nested:
        raise HarnessError(
            "authority_claimed",
            "harness response claims authority in a nested field: "
            + ", ".join(nested),
        )

    # The content itself, when it is JSON rather than prose.
    #
    # A completion runtime returns one string, so a model that answers
    # `{"approved": true, "side": "LONG"}` puts that claim *inside* the content
    # where a field check cannot see it. It is inert today — content is filed in
    # quarantine as an opaque string and nothing parses it — but "inert because
    # no current consumer parses it" is not a boundary, it is a coincidence
    # waiting for a consumer.
    #
    # It is also the single most useful signal available here: a model emitting
    # an approval means its prompt, or a document it read, tried to escalate.
    embedded = content_claims_authority(content)
    if embedded:
        raise HarnessError(
            "authority_claimed",
            "harness answered with a structured authority claim in its content: "
            + ", ".join(embedded)
            + ". This usually means the prompt or a document it read tried to "
            "escalate; the answer is refused rather than filed.",
        )

    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "task_digest": response["task_digest"],
        "intent": task.get("intent"),
        "content": content,
        "model": str(response.get("model") or "unknown"),
        "runtime": str(response.get("runtime") or "unknown"),
        "elapsed_ms": _optional_int(response.get("elapsed_ms")),
        # Restated on the accepted result. Anything downstream that reads this
        # sees what it is holding without having to know where it came from.
        "authority": "advisory_only",
        "routes_to": "quarantine",
    }


def content_claims_authority(content: str) -> list[str]:
    """Forbidden fields inside an answer that is itself JSON.

    Only fires when the whole answer parses as a JSON object or array — a
    sentence that happens to contain the word "approved" is prose, and refusing
    prose for using an English word would make the harness useless. The check is
    for structure, not vocabulary.
    """
    text = content.strip()
    # Models often fence their JSON. Unwrap one fence before giving up.
    if text.startswith("```"):
        without_fence = text.split("```")
        text = without_fence[1] if len(without_fence) > 1 else text
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    if not text or text[0] not in "{[":
        return []
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return []
    top = (
        sorted(FORBIDDEN_RESPONSE_FIELDS.intersection(parsed))
        if isinstance(parsed, Mapping)
        else []
    )
    return sorted(set(top) | set(_nested_forbidden(parsed)))


def _nested_forbidden(value: Any, path: str = "", depth: int = 0) -> list[str]:
    """Every forbidden key anywhere in the structure, with its path."""
    if depth > 8:
        return []
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            here = f"{path}.{key}" if path else str(key)
            if depth > 0 and key in FORBIDDEN_RESPONSE_FIELDS:
                found.append(here)
            found.extend(_nested_forbidden(child, here, depth + 1))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found.extend(_nested_forbidden(child, f"{path}[{index}]", depth + 1))
    return sorted(found)


def to_quarantine_submission(
    accepted: Mapping[str, Any],
    task: Mapping[str, Any],
) -> dict[str, Any]:
    """Shape an accepted response as a quarantine submission.

    A harness answer is not evidence. It takes the same route as any other
    material TradeSync did not measure: quarantine, extraction, proposed delta,
    operator promotion. The submission carries no field that could raise its own
    trust level — ``quarantine.evaluate_submission`` would reject it if it did.
    """
    return {
        "source": "agent_harness",
        "kind": f"agent_{task.get('intent', 'unknown')}",
        "payload": {
            "content": accepted["content"],
            "model": accepted["model"],
            "runtime": accepted["runtime"],
            "task_digest": accepted["task_digest"],
            "prompt": task.get("prompt"),
            "intent": task.get("intent"),
        },
    }


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
