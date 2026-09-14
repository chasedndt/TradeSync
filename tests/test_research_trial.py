import pytest
from tradesync_core.research_trial import specification, fingerprint, evaluate


def test_definition_is_repeatable_and_separates_holding_styles():
    assert fingerprint(specification('scalp')) == fingerprint(specification('scalp'))
    assert fingerprint(specification('scalp')) != fingerprint(specification('swing'))
    assert len(fingerprint(specification('intraday'))) == 64


def test_changed_rule_requires_new_fingerprint():
    original = specification('scalp')
    changed = {**original, 'threshold': .3}
    assert fingerprint(original) != fingerprint(changed)
    assert specification('scalp')['threshold'] == .2


def test_unsupported_style_cannot_register():
    with pytest.raises(ValueError): specification('autonomous-live')


def record(at, status='closed', exit_at=1100):
    return {'id':str(at),'symbol':'BTC-PERP','position_state':{'style':'scalp','entry_time':at,'exit_time':exit_at,'status':status,'observation_gap':False,'notional':100,'net_estimate_usdc':1}}


def test_registration_boundary_and_future_outcomes():
    result = evaluate(specification('scalp'), 1000, 1200, [record(999), record(1000), record(1050), record(1060, exit_at=1300)])
    assert result['outside_population'] == 2
    assert result['comparison']['eligible'] == 1
    assert result['pending_outcomes'] == 1 and result['state'] == 'collecting'


def test_window_end_waits_for_open_positions_and_never_promotes():
    spec = specification('scalp'); now = 1000+31*86400
    assert evaluate(spec,1000,now,[record(1050,'open')])['state'] == 'awaiting_outcomes'
    result = evaluate(spec,1000,now,[record(1050)])
    assert result['state'] == 'insufficient_clean_sample'
    assert result['promotion_allowed'] is False


def test_changed_specification_cannot_silently_reuse_evaluator():
    with pytest.raises(ValueError): evaluate({**specification('scalp'),'threshold':.4},1000,1200,[])
