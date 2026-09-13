from copy import deepcopy
import json

import pytest

from pheroos_bench import r3_pilot as pilot


def record(identity, version, proposal):
    return dict(id=identity, task_version=version, proposal_digest=proposal,
                agent='agent-0', valid=True, proposal='old', feedback='ok')


def test_version_filter_deduplicates_but_does_not_create_evidence():
    rows=[record('old',1,'a'),record('copy',2,'b'),record('new',2,'b')]
    assert pilot.memory_for('versioned_blackboard',rows,2)==rows[-1:]
    assert pilot.memory_for('blackboard',rows,2)==rows[-2:]
    assert pilot.memory_for('independent',rows,2)==[]
    assert pilot.memory_for('single',rows,2)==rows


def test_missing_or_duplicated_grid_aborts():
    with pytest.raises(ValueError,match='missing or duplicated'):
        pilot.summarize([])


class BrokenWorker:
    def request(self, payload):
        if payload['op']=='ledger':
            return dict(actual_tokens=0,reserved_tokens=0,unknown_tokens=400,calls=[])
        raise RuntimeError('response lost after dispatch')


def test_unknown_backend_response_is_not_zero_cost_success(tmp_path):
    config=dict(steps=4,episode_token_cap=8192,max_new_tokens=256,seed=37)
    result=pilot.episode(BrokenWorker(),config,'code_repair/clamp','single',0,tmp_path)
    assert result['outcome']=='INVALID_ABORT'
    assert result['accounting_status']=='UNRESOLVED'
    assert result['ledger']['unknown_tokens']==400
    assert result['completed_calls']==0
    trace=json.loads((tmp_path/'trace.jsonl').read_text())
    assert trace['status']=='INVALID_ABORT'


class PublicationFailure:
    def request(self, payload):
        if payload['op']=='ledger':
            return dict(actual_tokens=17,reserved_tokens=0,unknown_tokens=0,calls=[])
        if payload['op']=='publish':
            raise PermissionError('current authority refused')
        return dict(text=json.dumps({'code':'def clamp(value, lower, upper):\n    return max(lower,min(value,upper))'}),
                    prompt_tokens=10,completion_tokens=7,peak_cuda_bytes=1,
                    ledger=dict(actual_tokens=17,reserved_tokens=0,unknown_tokens=0,calls=[]))


def test_publication_failure_preserves_received_inference_usage(tmp_path):
    config=dict(steps=4,episode_token_cap=8192,max_new_tokens=256,seed=37)
    result=pilot.episode(PublicationFailure(),config,'code_repair/clamp','single',0,tmp_path)
    assert result['outcome']=='INVALID_ABORT'
    assert result['known_input_tokens']+result['known_output_tokens']==17
    assert result['ledger']['actual_tokens']==17


def test_messages_have_only_declared_view_and_selected_work():
    view={'source':'visible'}
    original=deepcopy(view)
    messages=pilot.messages_for(view,[],'solver')
    assert json.loads(messages[1]['content'])=={'task':view,'prior_work':[]}
    assert view==original
