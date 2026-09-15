"""Entry evidence: only facts observed and received before the entry, every item listed, versioned and fingerprinted."""

import copy
import json

import pytest

from tradesync_core import paper_entry_evidence as evidence

ENTRY = 1_789_433_000.0


def record(observed, received, **extra):
    return {'observed_at': observed, 'received_at': received, **extra}


def test_evidence_received_after_the_entry_time_is_excluded():
    gathered = {'features': {'source': 'market-data /features', 'records': [
        record(ENTRY - 30, ENTRY - 29, feature_id='hl_spread_bps', value=0.13),
        record(ENTRY - 30, ENTRY + 1, feature_id='hl_return_1h_pct', value=-0.4),
        record(ENTRY + 2, ENTRY + 3, feature_id='coinbase_premium_bps', value=1.0),
    ]}}
    doc = evidence.document(gathered, ENTRY)
    features = doc['items']['features']
    assert [r['feature_id'] for r in features['records']] == ['hl_spread_bps']
    assert features['records'][0]['age_s'] == 30 and features['newest_age_s'] == 30
    assert sorted(e['reason'] for e in features['excluded']) == ['observed after entry', 'received after entry']
    assert doc['excluded_count'] == 2
    assert all(r['observed_at'] <= ENTRY and r['received_at'] <= ENTRY for item in doc['items'].values() for r in item['records'])


def test_every_item_is_listed_with_an_explicit_missing_marker():
    doc = evidence.document({
        'liquidations': {'source': 'market_liquidation_events', 'records': [], 'reason': 'no liquidation received in the hour before entry'},
        'funding': {'source': 'market-data /funding-history', 'records': [record(ENTRY + 5, ENTRY + 6)]},
    }, ENTRY)
    assert doc['item_order'] == [key for key, _ in evidence.ITEMS] and set(doc['items']) == set(doc['item_order'])
    assert json.loads(evidence.canonical_json(doc))['item_order'] == doc['item_order']
    assert doc['items']['liquidations']['status'] == 'missing'
    assert doc['items']['liquidations']['reason'] == 'no liquidation received in the hour before entry'
    assert doc['items']['funding']['reason'] == 'every record was observed or received after entry'
    assert doc['items']['thesis_edition']['status'] == 'missing' and doc['items']['thesis_edition']['reason'] == 'not gathered'
    assert doc['items']['thesis_edition']['label'] == 'Thesis edition'


def test_records_without_both_times_never_enter():
    doc = evidence.document({'open_interest': {'records': [{'observed_at': ENTRY - 60}, {'received_at': ENTRY - 1}, 'junk', record(True, ENTRY)]}}, ENTRY)
    assert [e['reason'] for e in doc['items']['open_interest']['excluded']] == [
        'received time unknown', 'observed time unknown', 'not a record', 'observed time unknown']
    assert doc['items']['open_interest']['status'] == 'missing'


def test_schema_version_digest_and_canonical_round_trip():
    doc = evidence.document({'opportunity': {'records': [record(ENTRY - 10, ENTRY - 10, id='o-1', bias=-0.0, oi=2e16)]}},
                            ENTRY, inputs={'atr': 1.5, 'entry_book': {'poll_ts': 1789432999000}})
    assert doc['schema_version'] == evidence.SCHEMA_VERSION and doc['cutoff_rule'] == evidence.CUTOFF_RULE
    text = evidence.canonical_json(doc)
    assert evidence.digest(json.loads(text)) == evidence.digest(doc) and len(evidence.digest(doc)) == 64
    assert '-0.0' not in text and 'e+16' not in text
    changed = copy.deepcopy(doc)
    changed['atr'] = 1.6
    assert evidence.digest(changed) != evidence.digest(doc)


def test_inputs_cannot_replace_the_cutoff_or_items():
    for field in ('items', 'item_order', 'entry_time'):
        with pytest.raises(ValueError):
            evidence.document({}, ENTRY, inputs={field: {}})
    with pytest.raises(ValueError):
        evidence.document({}, float('nan'))
