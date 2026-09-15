from dataclasses import replace
import json
import sqlite3

import pytest

from pheroos_interaction.runner.driver import SessionDriver
from pheroos_interaction.runner.evidence import CoordinationSession
from pheroos_interaction.records import BudgetExceeded, LeaseLost, StateError


BODY = dict(source_id='x', source_version=1, value=7)


def make_session(tmp_path, name='one', *, readers=None, token_cap=1000, max_calls=8):
    from hashlib import sha256
    from pheroos_interaction.runner.session import _wire
    readers = ['a', 'b'] if readers is None else readers
    fingerprint = sha256(_wire(BODY).encode()).hexdigest()
    work = [dict(id='tool-'+a, version=1, dependencies=[], agents=[a], actions=['tool.evaluate']) for a in ['a', 'b']]
    work += [dict(id='model-'+a, version=1, dependencies=[], agents=[a], actions=['model.generate', 'tool.evaluate']) for a in ['a', 'b']]
    source = dict(id='x', version=1, readers=readers, state_fingerprint=fingerprint)
    inspections = [dict(work_id='tool-'+a, source_id='x', source_version=1, tool_ref='inspect', tool_version='v1',
        arguments={'source_id':'x'}, state_fingerprint=fingerprint, readers=readers) for a in ['a','b']]
    session = CoordinationSession.create(tmp_path/(name+'.sqlite'), name, agents=['a','b'], sources=[source],
        work=work, inspections=inspections, token_cap=token_cap, max_calls=max_calls)
    return session


def publish(session, *, agent='a'):
    lease = session.claim_inspection(agent, 'tool-'+agent, reuse=False)['lease']
    driver = SessionDriver(session, tools={'inspect': lambda args: dict(BODY)})
    response = driver.evaluate(lease, 'check-'+agent, 'inspect', {'source_id':'x'})
    ref = session.publish(lease, 'check-'+agent, response['artifact'], verify=lambda _, value: value == BODY)
    return ref


def test_current_read_private_access_foreign_scope_and_cross_session_lease(tmp_path):
    one = make_session(tmp_path, readers=['a'])
    ref = publish(one)
    a, b = one.claim('a','model-a'), one.claim('b','model-b')
    assert one.read(a,ref)['value'] == BODY
    with pytest.raises(PermissionError): one.read(b,ref)
    two = make_session(tmp_path,'two')
    other = two.claim('a','model-a')
    with pytest.raises(PermissionError): two.read(other,ref)
    with pytest.raises(LeaseLost): two.read(a,ref)
    assert one.context(a)['private'] == {}
    one.checkpoint(a, {'prior_output':'known'})
    assert one.context(a)['private'] == {'prior_output':'known'}
    with pytest.raises(ValueError): one.checkpoint(a, {'huge':'x'*5000})


def test_stale_receipt_requires_explicit_historical_read_and_keeps_status(tmp_path):
    session = make_session(tmp_path)
    ref = publish(session)
    lease = session.claim('b','model-b')
    session.source_update('x',2,['a','b'],'new-v2-fingerprint')
    with pytest.raises(StateError): session.read(lease,ref)
    historical = session.read(lease,ref,allow_superseded=True)
    assert historical['value'] == BODY
    assert historical['metadata']['current'] is False
    assert historical['metadata']['superseded'] is True
    with pytest.raises(ValueError): session.read(lease,ref,allow_superseded=1)
    assert session.claim_inspection('b','tool-b',reuse=False)['status'] == 'stale'


def test_equivalent_cache_and_busy_state_do_not_execute_tools(tmp_path):
    session = make_session(tmp_path)
    claimed = session.claim_inspection('a','tool-a',reuse=True)
    assert session.claim_inspection('b','tool-b',reuse=True)['status'] == 'busy'
    session.release_inspection(claimed['lease'])
    ref = publish(session)
    before = session.snapshot()['call_count']
    assert session.claim_inspection('b','tool-b',reuse=True)['artifact_ref'] == ref
    assert session.snapshot()['call_count'] == before == 1
    assert session.claim_inspection('b','tool-b',reuse=False)['status'] == 'claimed'


class Model:
    identity = {'model_id':'offline-fixture', 'paid':False}
    def __init__(self, *, fail=False, on_count=None):
        self.calls, self.fail, self.on_count = 0, fail, on_count
    def count_tokens(self, messages):
        if self.on_count: self.on_count()
        return 10
    def generate(self,messages,max_new_tokens,seed):
        self.calls += 1
        if self.fail: raise TimeoutError('synthetic failure')
        return dict(text='{}',prompt_tokens=10,completion_tokens=2)


def test_duplicate_dispatch_and_budget_refusal_never_call_model_again(tmp_path):
    session = make_session(tmp_path, max_calls=1)
    model = Model()
    driver = SessionDriver(session, models={'m':model})
    lease = session.claim('a','model-a')
    args = (lease,'unique','m',[{'role':'user','content':'hello'}])
    driver.generate(*args,max_new_tokens=4,seed=1)
    with pytest.raises(StateError): driver.generate(*args,max_new_tokens=4,seed=1)
    with pytest.raises(BudgetExceeded): driver.generate(lease,'second','m',args[-1],max_new_tokens=4,seed=1)
    assert model.calls == 1
    small = make_session(tmp_path,'small',token_cap=5)
    with pytest.raises(BudgetExceeded):
        SessionDriver(small,models={'m':model}).generate(small.claim('a','model-a'),'x','m',args[-1],max_new_tokens=4,seed=1)
    assert model.calls == 1


def test_cancellation_before_dispatch_and_unknown_after_dispatch(tmp_path):
    session = make_session(tmp_path)
    model = Model(on_count=session.cancel)
    lease = session.claim('a','model-a')
    with pytest.raises(LeaseLost):
        SessionDriver(session,models={'m':model}).generate(lease,'never','m',[],max_new_tokens=4,seed=1)
    assert model.calls == 0 and session.claim('b','model-b') is None
    other = make_session(tmp_path,'unknown')
    failing = Model(fail=True)
    driver = SessionDriver(other,models={'m':failing})
    lease = other.claim('a','model-a')
    with pytest.raises(TimeoutError): driver.generate(lease,'lost','m',[],max_new_tokens=4,seed=1)
    other.cancel()
    snapshot = other.snapshot()
    assert snapshot['unknown_calls'] == 1 and snapshot['unknown_tokens'] == 14
    with pytest.raises(LeaseLost): driver.generate(lease,'lost','m',[],max_new_tokens=4,seed=1)
    assert failing.calls == 1


def test_declared_tool_arguments_and_verified_publication_remain_real(tmp_path):
    session = make_session(tmp_path)
    called = []
    driver = SessionDriver(session, tools={'inspect':lambda args: called.append(args) or dict(BODY)})
    lease = session.claim_inspection('a','tool-a',reuse=False)['lease']
    with pytest.raises(KeyError): driver.evaluate(lease,'bad-tool','shell',{})
    with pytest.raises(StateError): driver.evaluate(lease,'bad-target','inspect',{'source_id':'foreign'})
    assert called == []
    reply = driver.evaluate(lease,'good','inspect',{'source_id':'x'})
    with pytest.raises(StateError):
        session.publish(lease,'good',{'source_id':'x','source_version':1,'value':999}, verify=lambda _,v:v==BODY)
    assert reply['artifact'] == BODY and len(called) == 1
    session.publish(lease,'good',reply['artifact'],verify=lambda _,v:v==BODY)
