"""A harness may explain, compare and draft. It may not decide."""

from __future__ import annotations

import pytest

from tradesync_core.agent_harness import (
    FORBIDDEN_RESPONSE_FIELDS,
    INTENTS,
    MAX_PROMPT_BYTES,
    MAX_RESPONSE_BYTES,
    RESPONSE_SCHEMA_VERSION,
    HarnessError,
    build_task,
    to_quarantine_submission,
    validate_response,
)
from tradesync_core.quarantine import evaluate_submission


def task(intent: str = "explain"):
    return build_task(intent, "Why did BTC-PERP refuse a direction at 19:54?")


def response(task_doc, **over):
    base = {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "task_digest": task_doc["task_digest"],
        "content": "The directional score sat inside the hold deadband.",
        "model": "llama3.1:8b",
        "runtime": "ollama",
        "elapsed_ms": 812,
    }
    base.update(over)
    return base


def test_the_intent_vocabulary_has_no_word_for_deciding() -> None:
    """The boundary starts at what can even be asked.

    Every intent produces prose or a comparison for a human to read.
    """
    assert INTENTS == {
        "explain",
        "compare",
        "summarise",
        "draft_proposal",
        "critique",
    }
    for forbidden in ("decide", "score", "approve", "execute", "gate", "rank"):
        assert forbidden not in INTENTS


def test_an_unknown_intent_is_refused_and_the_options_are_named() -> None:
    with pytest.raises(HarnessError) as excinfo:
        build_task("approve", "please approve this")
    assert excinfo.value.code == "unknown_intent"
    assert "explain" in str(excinfo.value)


def test_a_task_states_the_boundary_in_its_own_body() -> None:
    """So a harness logging what it received records the limit too."""
    doc = task()
    assert doc["authority"] == {
        "advisory_only": True,
        "may_score": False,
        "may_approve": False,
        "may_execute": False,
        "response_routes_to": "quarantine",
    }


def test_a_well_formed_response_is_accepted() -> None:
    doc = task()
    accepted = validate_response(response(doc), doc)
    assert accepted["authority"] == "advisory_only"
    assert accepted["routes_to"] == "quarantine"
    assert accepted["model"] == "llama3.1:8b"


@pytest.mark.parametrize("field", sorted(FORBIDDEN_RESPONSE_FIELDS))
def test_a_response_claiming_authority_is_refused_by_name(field: str) -> None:
    """Refused whole, not stripped.

    A model emitting `approved: true` is telling you something about the prompt
    it was given — very possibly a document it read. Silently deleting the field
    destroys exactly the signal worth seeing.
    """
    doc = task()
    with pytest.raises(HarnessError) as excinfo:
        validate_response(response(doc, **{field: True}), doc)
    assert excinfo.value.code == "authority_claimed"
    assert field in str(excinfo.value)


def test_authority_nested_inside_the_answer_is_also_refused() -> None:
    """A model told to answer in JSON will nest.

    A boundary that only checks the top level is not a boundary.
    """
    doc = task()
    poisoned = response(
        doc,
        analysis={"verdict": {"approved": True, "side": "LONG"}},
    )
    with pytest.raises(HarnessError) as excinfo:
        validate_response(poisoned, doc)
    assert excinfo.value.code == "authority_claimed"
    assert "analysis.verdict.approved" in str(excinfo.value)


def test_authority_inside_a_list_is_refused() -> None:
    doc = task()
    with pytest.raises(HarnessError) as excinfo:
        validate_response(response(doc, steps=[{"note": "ok"}, {"score": 0.9}]), doc)
    assert "steps[1].score" in str(excinfo.value)


def test_a_response_must_carry_the_digest_of_the_task_it_answers() -> None:
    """Otherwise a stale or substituted answer reads as a reply to the last question."""
    doc = task()
    other = build_task("compare", "a completely different question")
    with pytest.raises(HarnessError) as excinfo:
        validate_response(response(doc, task_digest=other["task_digest"]), doc)
    assert excinfo.value.code == "task_mismatch"

    with pytest.raises(HarnessError):
        validate_response(response(doc, task_digest=None), doc)


def test_the_task_digest_covers_the_question_not_the_asker() -> None:
    """The same question asked twice binds identically; a changed prompt does not."""
    first = build_task("explain", "why?")
    second = build_task("explain", "why?", requested_by="someone_else")
    assert first["task_digest"] == second["task_digest"]

    changed = build_task("explain", "why not?")
    assert changed["task_digest"] != first["task_digest"]


def test_an_empty_or_oversized_answer_is_refused() -> None:
    doc = task()
    for bad in ("", "   ", None, 42):
        with pytest.raises(HarnessError):
            validate_response(response(doc, content=bad), doc)

    with pytest.raises(HarnessError) as excinfo:
        validate_response(response(doc, content="x" * (MAX_RESPONSE_BYTES + 1)), doc)
    assert excinfo.value.code == "response_too_large"


def test_an_oversized_prompt_is_refused() -> None:
    with pytest.raises(HarnessError) as excinfo:
        build_task("explain", "x" * (MAX_PROMPT_BYTES + 1))
    assert excinfo.value.code == "prompt_too_large"


def test_a_wrong_schema_version_is_refused() -> None:
    doc = task()
    with pytest.raises(HarnessError) as excinfo:
        validate_response(response(doc, schema_version="agent_response_v2"), doc)
    assert excinfo.value.code == "unsupported_schema"


def test_an_accepted_answer_still_goes_through_quarantine() -> None:
    """A harness answer is not evidence.

    It takes the same route as a TradingView alert: quarantine, extraction,
    proposed delta, operator promotion. This asserts the submission it produces
    actually passes the quarantine contract rather than merely claiming to.
    """
    doc = task()
    accepted = validate_response(response(doc), doc)
    submission = to_quarantine_submission(accepted, doc)

    assert submission["source"] == "agent_harness"
    verdict = evaluate_submission(
        submission["source"],
        submission["payload"],
        received_at_ms=1_788_900_000_000,
    )
    assert verdict.accepted, verdict.reasons
    # Accepted into quarantine confers nothing. The verdict says so itself.
    assert verdict.to_dict()["authority"] == "none"
    assert verdict.to_dict()["tier"] == "B"


def test_the_submission_carries_no_field_that_raises_its_own_trust() -> None:
    doc = task()
    accepted = validate_response(response(doc), doc)
    submission = to_quarantine_submission(accepted, doc)
    from tradesync_core.quarantine import FORBIDDEN_FIELDS

    assert not FORBIDDEN_FIELDS.intersection(submission["payload"])
    assert not FORBIDDEN_FIELDS.intersection(submission)


def test_a_json_answer_claiming_approval_is_refused() -> None:
    """A completion runtime returns one string.

    A model answering `{"approved": true}` puts the claim inside the content,
    where a field check cannot see it. Inert today because nothing parses that
    string — but inert-by-coincidence is not a boundary, and it is the clearest
    available sign that something tried to escalate through the prompt.
    """
    doc = task()
    with pytest.raises(HarnessError) as excinfo:
        validate_response(
            response(doc, content='{"approved": true, "side": "LONG"}'), doc
        )
    assert excinfo.value.code == "authority_claimed"
    assert "approved" in str(excinfo.value)


def test_a_fenced_json_answer_is_unwrapped_before_checking() -> None:
    doc = task()
    fenced = '```json\n{"analysis": {"score": 0.91}}\n```'
    with pytest.raises(HarnessError) as excinfo:
        validate_response(response(doc, content=fenced), doc)
    assert "analysis.score" in str(excinfo.value)


def test_prose_that_merely_uses_the_words_is_still_accepted() -> None:
    """The check is for structure, not vocabulary.

    Refusing an explanation for containing the word "approved" would make the
    harness useless at the one thing it is for.
    """
    doc = task()
    prose = (
        "The signal was not approved because its score sat below the entry "
        "threshold, so no direction or side was emitted and no order followed."
    )
    accepted = validate_response(response(doc, content=prose), doc)
    assert accepted["content"] == prose


def test_a_json_answer_with_no_authority_claim_is_fine() -> None:
    doc = task()
    accepted = validate_response(
        response(doc, content='{"summary": "below threshold", "hops": 3}'), doc
    )
    assert "summary" in accepted["content"]
