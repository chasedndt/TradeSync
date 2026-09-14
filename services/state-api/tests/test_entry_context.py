import pytest
from app.entry_context import liquidation_snapshot, book_snapshot


def payload(*rows):
    return {'receipt_schema':'first-received-v2', 'events':list(rows)}


def event(**changes):
    return {'id':'a','event_time':900,'received_at':950, **changes}


def test_later_receipt_cannot_enter_earlier_decision():
    result = liquidation_snapshot(payload(event(), event(id='b', received_at=1001)), 1000)
    assert len(result['events']) == 1
    assert result['excluded'] == 1
    assert result['scoring_influence'] is False


def test_unknown_receipts_and_invalid_time_order_are_excluded():
    result = liquidation_snapshot(payload(event(received_at=None), event(event_time=960), event(received_at=float('nan')), event(received_at=True)), 1000)
    assert result['events'] == []
    assert result['status'] == 'no_eligible_receipts'
    assert result['excluded'] == 4


def test_legacy_provenance_is_unavailable_not_zero():
    assert liquidation_snapshot({'events':[]}, 1000)['status'] == 'unavailable'


def test_duplicates_are_not_double_counted_and_inputs_not_mutated():
    original = event()
    result = liquidation_snapshot(payload(original, original), 1000)
    result['events'][0]['id'] = 'changed'
    assert original['id'] == 'a'
    assert result['excluded'] == 1


@pytest.mark.parametrize('cutoff', [None, True, float('inf'), -1])
def test_bad_cutoffs_fail_closed(cutoff):
    with pytest.raises(ValueError): liquidation_snapshot(payload(), cutoff)


def book(*times):
    return {'venue':'hyperliquid','symbol':'BTC-PERP','samples':[
        {'time':at,'levels':[{'side':side,'price':100,'notional_usd':200} for side in ('bids','asks')]} for at in times]}


def test_book_excludes_future_samples_without_filling_gaps():
    result = book_snapshot(book(900, 980, 1001), 1000, 'BTC-PERP')
    assert [s['time'] for s in result['samples']] == [900,980]
    assert result['status'] == 'observed' and result['excluded'] == 1


def test_book_stale_missing_and_wrong_symbol_are_distinct():
    assert book_snapshot(book(900), 1000, 'BTC-PERP')['status'] == 'stale'
    assert book_snapshot(book(), 1000, 'BTC-PERP')['status'] == 'no_eligible_samples'
    assert book_snapshot(book(990), 1000, 'ETH-PERP')['status'] == 'unavailable'


def test_book_rejects_bad_levels_and_does_not_share_nested_mutable_inputs():
    source = book(990, 995)
    source['samples'][1]['levels'][0]['price'] = float('nan')
    result = book_snapshot(source, 1000, 'BTC-PERP')
    assert result['excluded'] == 1
    result['samples'][0]['levels'][0]['price'] = 1
    assert source['samples'][0]['levels'][0]['price'] == 100
