import json
from pathlib import Path

import pytest

from pheroos_interaction import policy
from pheroos_interaction.runner.host import MockModel, run_episode


@pytest.mark.parametrize('world', policy.WORLDS)
@pytest.mark.parametrize('condition', policy.CONDITIONS)
def test_current_finite_mock_path_and_required_inspection_counts(tmp_path,world,condition):
    result = run_episode(tmp_path/'run',world_id=world,condition=condition)
    assert result['complete'], result['error_type']
    state = world.split('/')[1]
    assert result['mode'] == 'mock' and result['final_grounded'] == 2
    assert result['inspection_intents'] == (0 if state == 'complete' else 2)
    assert result['actual_tool_executions'] == {'complete':2,'missing':4,'stale':6}[state]
    assert result['cache_hits'] == 0 and len(result['calls']) == 4
    assert all(r['response']['receipt_kind'] == 'mock' for r in result['calls'])
    for r in result['calls']:
        assert r['session_call']['request']['messages'] == r['context']['messages']
        assert all('permission' not in c for c in r['context']['messages'])
    snapshot = json.loads((tmp_path/'run/session-snapshot.json').read_text())
    assert snapshot['run']['status'] == 'cancelled' and not snapshot['unknown_calls']
    with pytest.raises(FileExistsError): run_episode(tmp_path/'run')


def test_failure_retains_unstarted_positions_and_unknown_reservation(tmp_path):
    class Failing(MockModel):
        def __init__(self): self.calls=0
        def generate(self,*args):
            self.calls+=1
            raise TimeoutError('synthetic network-free failure')
    model = Failing()
    result=run_episode(tmp_path/'run',model=model)
    assert not result['complete'] and result['error_type']=='TimeoutError'
    assert model.calls==1 and result['unknown_tokens']>0
    assert sum(r['status']=='UNSTARTED' for r in result['calls'])==3
    assert all(r['quality'] is None for r in result['calls'])


def test_invalid_model_target_is_recorded_but_never_executed(tmp_path):
    class Invalid(MockModel):
        def generate(self,messages,max_new_tokens,seed):
            return dict(text='{"action":"inspect","target":"shell"}',
                        prompt_tokens=self.count_tokens(messages),completion_tokens=10,receipt_kind='mock')
    result=run_episode(tmp_path/'run',world_id='fresh_a/missing',model=Invalid())
    assert result['complete'] and result['final_grounded']==0
    assert result['actual_tool_executions']==2 and result['inspection_intents']==0
    assert all(not r['parsed']['valid'] for r in result['calls'])


def test_api_dry_run_never_reads_credentials_or_opens_money_database(tmp_path,monkeypatch):
    from pheroos_interaction.runner import adapters, accounting
    from pheroos_interaction.runner.cli import main
    def denied(*args,**kwargs): raise AssertionError('forbidden dry-run effect')
    monkeypatch.setattr(adapters,'_credential',denied)
    monkeypatch.setattr(adapters.KimiCNAdapter,'_http',denied)
    monkeypatch.setattr(accounting.MoneyLedger,'__init__',denied)
    assert main(['api-dry-run','--output',str(tmp_path/'dry')]) == 0
    report=json.loads((tmp_path/'dry/api-dry-run.json').read_text())
    assert report['provider_calls']==0 and not report['credentials_read'] and not report['ledger_opened']
    assert len(report['requests'])==4
    assert all(r['payload']['model']=='kimi-k2.6' for r in report['requests'])


def test_live_requires_separate_exact_cell_authorization_before_adapter(tmp_path,monkeypatch):
    from pheroos_interaction.runner import adapters
    from pheroos_interaction.runner.cli import main
    def denied(*args,**kwargs): raise AssertionError('adapter must not be constructed')
    monkeypatch.setattr(adapters.KimiCNAdapter,'__init__',denied)
    grant=tmp_path/'not-authorized.json';grant.write_text('{}')
    with pytest.raises(SystemExit):
        main(['live','--output',str(tmp_path/'live'),'--ledger',str(tmp_path/'missing.sqlite'),'--authorization',str(grant)])
    assert not (tmp_path/'live').exists()
