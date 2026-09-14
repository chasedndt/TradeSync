from tradesync_core.source_comparison import compare, book_alignment


def row(identity='a', net=1, bid=70, ask=30):
    return {'id': identity, 'position_state': {'status':'closed','observation_gap':False,'side':'long','entry_time':1000,'notional':100,'net_estimate_usdc':net},
            'entry_evidence': {'external_context': {'hyperliquid_book_history': {'status':'observed','cutoff':995,'samples':[{'time':990,'levels':[{'side':'bids','notional_usd':bid},{'side':'asks','notional_usd':ask}]}]}}}}


def test_same_denominator_and_abstention_are_explicit():
    result = compare([row(), row('b', -2, 30, 70)])
    assert result['baseline_mean_bps_per_opportunity'] == -50
    assert result['filter_mean_bps_per_opportunity'] == 50
    assert result['paired_mean_difference_bps'] == 100
    assert result['selected'] == result['abstained'] == 1
    assert result['promotion_allowed'] is False


def test_missing_context_is_not_neutral_or_zero_outcome():
    record = row(); record['entry_evidence'] = {}
    result = compare([record])
    assert result['context_available'] == 0 and result['abstained'] == 1
    assert result['baseline_mean_bps_per_opportunity'] == 100


def test_future_context_and_wrong_side_fail_closed():
    record = row()
    context = record['entry_evidence']['external_context']['hyperliquid_book_history']
    context['cutoff'] = 1001
    assert book_alignment(record['entry_evidence'], record['position_state']) is None
    context['cutoff'] = 995
    record['position_state']['side'] = 'short'
    assert book_alignment(record['entry_evidence'], record['position_state']) == -.4


def test_gap_duplicates_and_empty_are_not_clean_performance():
    record = row(); record['position_state']['observation_gap'] = True
    assert compare([record])['eligible'] == 0
    assert compare([row(), row()])['excluded']['duplicate_or_missing_id'] == 1
    assert compare([])['paired_mean_difference_bps'] is None


def test_malformed_records_and_context_fail_closed():
    assert compare([None, {'position_state':None}])['excluded']['invalid_record'] == 2
    record = row(); record['entry_evidence'] = {'external_context':None}
    assert compare([record])['context_available'] == 0
    record['id'] = []
    assert compare([record])['eligible'] == 0
