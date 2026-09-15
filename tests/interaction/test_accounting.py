import json
from pathlib import Path

import pytest

from pheroos_interaction.runner import adapters
from pheroos_interaction.runner.accounting import MoneyLedger, BudgetExceeded, DuplicateCall, RemoteKimiError


def receipt(cached=None):
    usage = dict(prompt_tokens=100, completion_tokens=10, total_tokens=110)
    if cached is not None: usage['cached_tokens'] = cached
    return dict(usage=usage, response_id='synthetic', returned_model='kimi-k2.6')


def test_exact_tariff_unknown_cache_and_existing_history_are_preserved(tmp_path):
    ledger = MoneyLedger(tmp_path/'money.sqlite')
    ledger.reserve('first',prompt_bound=262144,output_bound=512)
    assert ledger.settle('first',receipt()) == '0.0009200'
    original = ledger.call('first')
    reopened = MoneyLedger(ledger.path)
    assert reopened.call('first') == original
    reopened.reserve('second',prompt_bound=262144,output_bound=512)
    assert reopened.settle('second',receipt(50)) == '0.0006500'
    assert reopened.call('first') == original
    assert 'cached_tokens' not in original['receipt']['usage']
    with pytest.raises(ValueError): MoneyLedger(ledger.path,budget_cny='49')
    with pytest.raises(DuplicateCall): reopened.reserve('first',prompt_bound=262144,output_bound=512)


def test_unknown_money_retains_full_reservation_and_request_slot(tmp_path):
    ledger = MoneyLedger(tmp_path/'money.sqlite',max_http_requests=1)
    ledger.reserve('pending',prompt_bound=262144,output_bound=512)
    reserved = ledger.summary()['unresolved_reserved_cny']
    ledger.unknown('pending','timeout')
    snapshot = MoneyLedger(ledger.path,max_http_requests=1).summary()
    assert snapshot['unresolved_calls'] == 1 and snapshot['unresolved_reserved_cny'] == reserved
    with pytest.raises(BudgetExceeded): ledger.reserve('next',prompt_bound=262144,output_bound=512)
    assert ledger.call('pending')['state'] == 'unknown'
    small = MoneyLedger(tmp_path/'small.sqlite',budget_cny='0.1')
    with pytest.raises(BudgetExceeded): small.reserve('too-much',prompt_bound=262144,output_bound=512)
    assert small.summary()['http_requests'] == 0


def test_transport_is_lazy_and_reserves_before_http_without_retry(tmp_path,monkeypatch):
    def denied(): raise AssertionError('Credential access forbidden')
    monkeypatch.setattr(adapters,'_credential',denied)
    adapter = adapters.KimiCNAdapter()
    messages = [{'role':'user','content':'synthetic'}]
    assert adapter.count_tokens(messages) == 262144
    assert json.loads(adapter._payload(messages,512))['thinking'] == {'type':'disabled'}
    with pytest.raises(RemoteKimiError,match='live_ledger_required'):
        adapter.generate(messages,512,1,call_id='not-live')
    ledger = MoneyLedger(tmp_path/'fixture.sqlite')
    adapter = adapters.KimiCNAdapter(ledger)
    # A fixed test sentinel, not a read of any environment or user's credential.
    monkeypatch.setattr(adapters,'_credential',lambda: 'offline-test-sentinel')
    calls = []
    def http(endpoint,data,key):
        calls.append(endpoint)
        assert ledger.call('timeout')['state'] == 'reserved'
        raise TimeoutError('synthetic fault')
    monkeypatch.setattr(adapter,'_http',http)
    with pytest.raises(RemoteKimiError,match='timeout'):
        adapter.generate(messages,512,1,call_id='timeout')
    assert calls == ['/chat/completions']
    assert ledger.call('timeout')['state'] == 'unknown'
    with pytest.raises(DuplicateCall): adapter.generate(messages,512,1,call_id='timeout')
    assert len(calls) == 1


def test_invalid_usage_keeps_money_unknown_and_does_not_fake_tokens(tmp_path,monkeypatch):
    ledger = MoneyLedger(tmp_path/'fixture.sqlite')
    adapter = adapters.KimiCNAdapter(ledger)
    monkeypatch.setattr(adapters,'_credential',lambda:'offline-test-sentinel')
    monkeypatch.setattr(adapter,'_http',lambda *args: ({'usage':dict(prompt_tokens=100,completion_tokens=10,total_tokens=99)},None))
    with pytest.raises(RemoteKimiError):
        adapter.generate([{'role':'user','content':'x'}],512,1,call_id='invalid')
    assert ledger.call('invalid')['state'] == 'unknown'
    assert ledger.call('invalid')['actual'] is None
