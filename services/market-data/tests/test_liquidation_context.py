from app.liquidation_context import normalize


def message(side='Buy', price='60000', size='0.2'):
    return {'topic': 'allLiquidation.BTCUSDT', 'ts': 1000000,
            'data': [{'s': 'BTCUSDT', 'S': side, 'p': price, 'v': size, 'T': 1000000}]}


def test_position_side_is_not_the_closing_order_side():
    long = normalize(message(), 1001)[0]
    short = normalize(message('Sell'), 1001)[0]
    assert long['position_side'] == 'long'
    assert short['position_side'] == 'short'
    assert long['bankruptcy_notional_usdt'] == 12000
    assert long['source'] == 'bybit'
    assert long['authority'] == 'context_only'
    assert 'fill_price' not in long


def test_rejects_invalid_price_side_and_future_events():
    for value in ['nan', 'inf', '-1', 'bad']:
        assert normalize(message(price=value), 1001) == []
    assert normalize(message('unknown'), 1001) == []
    assert normalize(message(), 999) == []
    assert normalize(message(), 5000) == []


def test_duplicate_rows_survive_but_batch_replay_has_stable_ids():
    payload = message()
    payload['data'].append(dict(payload['data'][0]))
    first, replay = normalize(payload, 1001), normalize(payload, 1002)
    assert first[0]['id'] != first[1]['id']
    assert [e['id'] for e in first] == [e['id'] for e in replay]


def test_topic_must_match_supported_symbol():
    payload = message()
    payload['topic'] = 'allLiquidation.ETHUSDT'
    assert normalize(payload, 1001) == []
