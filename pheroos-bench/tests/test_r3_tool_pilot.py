from copy import deepcopy
import json

import pytest

from pheroos_bench import r3_tool_pilot as pilot


def test_withholding_only_current_verified_other_agent_artifacts():
    memory=[dict(id=str(i),valid=valid,agent=agent,task_version=version) for i,(valid,agent,version)
            in enumerate([(True,'other',2),(False,'other',2),(True,'self',2),(True,'other',1)])]
    original=deepcopy(memory)
    retained, removed=pilot.withheld(memory,'self',2)
    assert removed==['0']
    assert retained==memory[1:]
    assert memory==original


def test_incomplete_or_duplicate_grid_cannot_summarize():
    with pytest.raises(ValueError,match='missing or duplicated'):
        pilot.summarize([])


class FakeWorker:
    def __init__(self):
        self.requests=[]
        self.ledgers={}

    def request(self, request):
        self.requests.append(deepcopy(request))
        if request['op']=='tokenize':
            return {'prompt_tokens':10}
        if request['op']=='publish':
            return {'authority':'fake-test-only'}
        ledger=self.ledgers.setdefault(request['ledger_path'],dict(
            config={k:request[k] for k in ('token_cap','max_calls')},calls=[],
            actual_tokens=0,reserved_tokens=0,unknown_tokens=0,call_count=0))
        if request['op']=='ledger':
            return deepcopy(ledger)
        ledger['actual_tokens']+=17
        ledger['call_count']+=1
        ledger['calls'].append({'id':request['call_id']})
        text=json.dumps({'action':'submit','candidate':{'code_lines':[
            'def clamp(value, lower, upper):','    return max(lower,min(value,upper))']}})
        return dict(text=text,prompt_tokens=10,completion_tokens=7,peak_cuda_bytes=1,
                    ledger=deepcopy(ledger))


def test_fixed_probes_are_counted_without_entering_main_history(tmp_path):
    worker=FakeWorker()
    result=pilot.episode(worker,pilot.configuration(),'code_repair/clamp','blackboard',0,tmp_path)
    assert result['outcome']=='success'
    assert (result['main_calls'],result['probe_calls'])==(6,2)
    assert sum(result['main_usage'].values())==102
    assert sum(result['probe_usage'].values())==34
    assert result['main_ledger']['actual_tokens']==102
    assert result['probe_ledger']['actual_tokens']==34
    assert result['eligible_probes']==2
    assert result['valid_action_changes']==0
    traces=[json.loads(s) for s in (tmp_path/'trace.jsonl').read_text().splitlines()]
    probes=[json.loads(s) for s in (tmp_path/'probes.jsonl').read_text().splitlines()]
    assert [p['step'] for p in probes]==[2,4]
    for probe in probes:
        main=traces[probe['step']]
        assert probe['request']['seed']==main['request']['seed']
        assert probe['request']['scope']!=main['request']['scope']
        assert probe['removed_ids']==main['consumed_ids']
    assert all('probe' not in identity for t in traces for identity in t['consumed_ids'])
    assert all(c['success'] for c in result['curve'])


def test_no_eligible_probe_keeps_identical_messages(tmp_path):
    worker=FakeWorker()
    result=pilot.episode(worker,pilot.configuration(),'code_repair/clamp','single',0,tmp_path)
    assert result['eligible_probes']==result['valid_action_changes']==0
    generation=[r for r in worker.requests if r['op']=='generate']
    for step in (2,4):
        main=next(r for r in generation if r['call_id']==f'000-single:{step}')
        probe=next(r for r in generation if r['call_id']==f'000-single:probe:{step}')
        assert main['messages']==probe['messages']


class PublicationFailure(FakeWorker):
    def request(self, request):
        if request['op']=='publish':
            raise PermissionError('current publication denied')
        return super().request(request)


def test_received_cost_survives_publication_failure(tmp_path):
    result=pilot.episode(PublicationFailure(),pilot.configuration(),'code_repair/clamp','single',0,tmp_path)
    assert result['outcome']=='INVALID_ABORT'
    assert sum(result['main_usage'].values())==17
    assert result['main_ledger']['actual_tokens']==17
    assert result['probe_calls']==0


class LateResponse:
    def request(self, request):
        if request['op']=='tokenize':
            return {'prompt_tokens':10}
        if request['op']=='generate':
            raise TimeoutError('no timely response')
        # A late generation response must never be mistaken for a ledger.
        return dict(text='late',prompt_tokens=10,completion_tokens=7,ledger={})


def test_late_response_cannot_drop_aborted_episode(tmp_path):
    result=pilot.episode(LateResponse(),pilot.configuration(),'code_repair/clamp','single',0,tmp_path)
    assert result['outcome']=='INVALID_ABORT'
    assert result['main_ledger'] is None
    assert 'TimeoutError' in result['error']
    assert (tmp_path/'trace.jsonl').exists()


def test_transport_timeout_quarantines_before_ledger_rpc(monkeypatch):
    class Process:
        killed=False
        def poll(self):
            return None
        def kill(self):
            self.killed=True
    worker=object.__new__(pilot.ToolWorker)
    worker.process=Process()
    def timeout(self,payload):
        raise TimeoutError('late')
    monkeypatch.setattr(pilot.Worker,'request',timeout)
    with pytest.raises(TimeoutError):
        worker.request({'op':'generate'})
    assert worker.transport_failed and worker.process.killed
    assert pilot.final_ledger(worker,{}) is None
    with pytest.raises(RuntimeError,match='quarantined'):
        worker.request({'op':'ledger'})


def test_context_evicts_whole_oldest_receipts_before_generation(monkeypatch):
    class Counter(FakeWorker):
        def request(self, request):
            if request['op']=='tokenize':
                count=len(json.loads(request['messages'][1]['content'])['tool_receipts'])
                return {'prompt_tokens':2000 if count>1 else 10}
            return super().request(request)
    records=[dict(id=str(i),agent='agent0',step=i,task_version=1,valid=False,
                  feedback='invalid',artifact=None) for i in range(3)]
    request=dict(op='generate',ledger_path='test',token_cap=12288,max_calls=6,max_new_tokens=256,
                 call_id='id',scope={},version=1)
    retained, run=pilot.prepared_run(Counter(),request,'code_repair/clamp',3,records,trim=True)
    assert [r['id'] for r in retained]==['2']
    assert run['context_dropped_ids']==['0','1']
    assert len(run['context_preflight'])==3
    assert run['status']=='received'
    assert records[0]['id']=='0'


def test_probe_does_not_silently_change_intervention_when_context_too_long():
    class Long:
        def request(self, request):
            assert request['op']=='tokenize'
            return {'prompt_tokens':2000}
    request=dict(max_new_tokens=256)
    _, run=pilot.prepared_run(Long(),request,'code_repair/clamp',0,[],trim=False)
    assert run['status']=='INVALID_ABORT'
    assert run['response'] is None
    assert run['context_dropped_ids']==[]
