"""One concrete factorial-v2 loop, extracted from visibility_factorial_run_v2.

The schedule, source preparation, prompts and one-inspection window are retained.
This trusted local host owns execution; evaluators run only after the loop closes.
No provider or credential is loaded by the default mock path.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

from pheroos_interaction import policy as design
from .driver import SessionDriver
from .evidence import CoordinationSession
from pheroos_interaction.experiments.current.fixtures import source_values_v2
from pheroos_interaction.experiments.current.evaluation import score_v2


def _source_identity():
    """Cover all installed or editable source roots, using portable module paths."""
    import pheroos_interaction
    from pheroos_interaction import runner, experiments
    from pheroos_interaction.experiments import current

    identity = {}
    for package in (pheroos_interaction, runner, experiments, current):
        for directory in package.__path__:
            base = Path(directory)
            for path in sorted(base.rglob('*.py')):
                key = package.__name__.replace('.', '/') + '/' + path.relative_to(base).as_posix()
                value = sha256(path.read_bytes()).hexdigest()
                if key in identity and identity[key] != value:
                    raise RuntimeError('conflicting source identity')
                identity[key] = value
    return dict(sorted(identity.items()))


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def declarations(world_id):
    """Copied declaration semantics, with no alternative policy or task fixture."""
    stale = world_id.endswith('/stale')
    version = 1 if stale else 2
    sources = [dict(id=s, version=version, readers=list(design.AGENTS), state_fingerprint=design.digest(body))
               for s, body in source_values_v2(world_id, version=version).items()]
    def work_item(identifier, agents, actions):
        return dict(id=identifier, version=1, dependencies=[], agents=agents, actions=actions)
    work = [work_item(f'model-r{r}-{a}', [a], ['model.generate', 'tool.evaluate'])
            for r in design.ROUNDS for a in design.AGENTS]
    inspections, lookup, preparations = [], {}, []
    def declare(identifier, agent, source_id, version, reason=None):
        body = source_values_v2(world_id, version=version)[source_id]
        arguments = dict(source_id=source_id, source_version=version)
        work.append(work_item(identifier, [agent], ['tool.evaluate']))
        inspections.append(dict(work_id=identifier, source_id=source_id, source_version=version,
            tool_ref='inspect_source', tool_version='visibility-source-v1', arguments=arguments,
            state_fingerprint=design.digest(body), readers=list(design.AGENTS)))
        lookup[identifier] = arguments
        if reason is not None:
            preparations.append(dict(work_id=identifier, agent=agent, reason=reason, version=version))
    if stale:
        for source_id, agent in design.publishers(world_id).items():
            declare(f'historical-{agent}-{source_id}', agent, source_id, 1, 'historical_fixture')
    for agent, source_ids in design.initial_sources(world_id).items():
        for source_id in source_ids:
            declare(f'initial-{agent}-{source_id}', agent, source_id, 2, 'current_fixture')
    for agent in design.AGENTS:
        for source_id in source_values_v2(world_id, version=2):
            declare(f'inspect-r1-{agent}-{source_id}', agent, source_id, 2)
    return sources, work, inspections, lookup, preparations


class MockModel:
    """Visible-input-only arithmetic instrument; not model research evidence."""
    identity = dict(model_id='visible-input-mock', paid=False, receipt_kind='mock')

    def count_tokens(self, messages):
        return len(design.wire(messages).encode())  # explicit byte-unit mock, not tokenizer usage

    def generate(self, messages, max_new_tokens, seed):
        view = json.loads(messages[1]['content'])
        sources = {}
        for c in view['visible']:
            body = c.get('source_receipt', c.get('verified_source'))
            if body is not None and c['current']:
                sources[body['source_id']] = body
        missing = sorted(set(view['task']['required_sources']) - set(sources))
        if missing:
            action = dict(action='inspect', target=missing[0])
        else:
            answer = view['task']['public_inputs']['x'] * sources['multiplier']['value'] + sources['bias']['value']
            action = dict(action='submit', answer=answer, citations=[
                dict(source_id=s, source_version=sources[s]['source_version']) for s in sorted(sources)])
        raw = design.wire(action)
        return dict(text=raw, prompt_tokens=self.count_tokens(messages), completion_tokens=len(raw.encode()),
                    receipt_kind='mock', usage_unit='utf8_bytes_mock_only')


def run_episode(output, *, world_id='fresh_a/stale', condition='eligibility_current', model=None):
    if world_id not in design.WORLDS or condition not in design.CONDITIONS:
        raise ValueError('undeclared current experiment cell')
    model = MockModel() if model is None else model
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    config = design.configuration()
    frozen_sources = _source_identity()
    def unchanged():
        if _source_identity() != frozen_sources:
            raise RuntimeError('source changed during fixed rollout')
    sources, work, inspections, lookup, preparations = declarations(world_id)
    session = CoordinationSession.create(output / 'session.sqlite', 'interaction-' + uuid4().hex,
        agents=list(design.AGENTS), sources=sources, work=work, inspections=inspections,
        token_cap=config['session_token_cap'], max_calls=32, context_bytes=65536, artifact_bytes=65536,
        max_index_entries=128, max_control_operations=4096)
    environment = dict(version=sources[0]['version'], tool_executions=0)
    def inspect(arguments):
        environment['tool_executions'] += 1
        body = source_values_v2(world_id, version=environment['version'])[arguments['source_id']]
        if arguments['source_version'] != body['source_version']:
            raise ValueError('source version changed')
        return deepcopy(body)
    driver = SessionDriver(session, models={'study_model': model}, tools={'inspect_source': inspect},
                           context_tokens=config['context_tokens'])
    records = [dict(id='root:task:' + world_id, kind='root', owner='host', readers=list(design.AGENTS),
                    round_index=0, body={}, parents=[], provenance_known=True)]
    for version in (1, 2):
        for source in source_values_v2(world_id, version=version):
            records.append(dict(id=f'root:{world_id}:{source}:v{version}', kind='root', owner='host',
                readers=list(design.AGENTS), round_index=0, body=dict(source_id=source, source_version=version),
                parents=[], provenance_known=True))
    calls = [dict(round_index=r, agent=a, status='UNSTARTED', quality=None, grounded_correct=None)
             for r in design.ROUNDS for a in design.AGENTS]
    tools = []
    save(output / 'initial.json', dict(experiment=config, world_id=world_id, condition=condition,
        model_identity=model.identity, expected_calls=deepcopy(calls), preparation=preparations,
        profile='trusted-host-interaction-v1', frozen_behavior='visibility-factorial-v2',
        source_sha256=frozen_sources))

    def publish(work_id, agent, rnd, reason):
        unchanged()
        claim = session.claim_inspection(agent, work_id, reuse=False, lease_seconds=3600)
        if claim['status'] != 'claimed':
            raise RuntimeError('inspection not newly claimed')
        lease, cid = claim['lease'], 'tool-' + work_id
        response = driver.evaluate(lease, cid, 'inspect_source', lookup[work_id])
        expected = source_values_v2(world_id, version=environment['version'])[lookup[work_id]['source_id']]
        ref = session.publish(lease, cid, response['artifact'], verify=lambda _, value: value == expected)
        body = response['artifact']
        records.append(dict(id='source:' + work_id, kind='source', owner=agent, readers=list(design.AGENTS),
            round_index=rnd, body=body, provenance_known=True,
            parents=[f"root:{world_id}:{body['source_id']}:v{body['source_version']}"],
            artifact_ref=ref, call_id=cid, session_path=str(Path(session.path).resolve())))
        tools.append(dict(reason=reason, record_id='source:' + work_id, cache_hit=False,
                          call=session.call(cid), artifact=session.artifact(ref)))

    error = None
    try:
        for item in preparations:
            if item['version'] != environment['version']:
                for source, value in source_values_v2(world_id, version=2).items():
                    session.source_update(source, 2, list(design.AGENTS), design.digest(value))
                environment['version'] = 2
            publish(item['work_id'], item['agent'], 0, item['reason'])
        for rnd in design.ROUNDS:
            leases, contexts = {}, {}
            barrier = deepcopy(records)
            for agent in design.AGENTS:
                lease = session.claim(agent, f'model-r{rnd}-{agent}', lease_seconds=3600)
                if lease is None:
                    raise RuntimeError('model work unavailable')
                leases[agent] = lease
                reads = []
                def materialize(record):
                    if record['kind'] != 'source':
                        return deepcopy(record['body'])
                    historical = record['body']['source_version'] != 2
                    result = session.read(lease, record['artifact_ref'], allow_superseded=historical)
                    reads.append(dict(record_id=record['id'], allow_superseded=historical, result=result))
                    return result
                context = design.build_request(world_id, agent, condition, rnd, barrier, materialize)
                contexts[agent] = context
                save(output / f'r{rnd}-{agent}-intent.json', dict(projection=context, runtime_reads=reads))
            pending = []
            for agent in (('b', 'a') if rnd == 1 else ('a', 'b')):
                unchanged()
                row = next(c for c in calls if (c['round_index'], c['agent']) == (rnd, agent))
                row['status'] = 'DISPATCH_ATTEMPT'
                context, cid = contexts[agent], f'model-r{rnd}-{agent}'
                response = driver.generate(leases[agent], cid, 'study_model', context['messages'],
                                           max_new_tokens=512, seed=config['seed'] + rnd)
                actual = session.call(cid)
                if actual['request']['messages'] != context['messages']:
                    raise RuntimeError('actual request differs from materialized context')
                parsed = design.parse_action(response['text'], rnd, list(design.public_task(world_id)['source_versions']),
                                             world_id=world_id)
                row.update(status='RECEIVED', response=response, parsed=parsed, context=context, session_call=actual,
                    receipt_kind='provider' if model.identity.get('paid') else model.identity.get('receipt_kind', 'mock'))
                records.append(dict(id=f'proposal:r{rnd}:{agent}', kind='proposal', owner=agent,
                    readers=list(design.AGENTS), round_index=rnd,
                    body=dict(raw=response['text'], parsed=parsed, task_version=2),
                    parents=[*context['sent_record_ids'], 'root:task:' + world_id], provenance_known=True))
                session.checkpoint(leases[agent], dict(last_action=response['text']))
                if rnd == 1 and parsed['valid'] and parsed['action']['action'] == 'inspect':
                    pending.append((agent, parsed['action']['target']))
            for agent, source in pending:
                publish(f'inspect-r1-{agent}-{source}', agent, 1, 'model_requested_inspection')
        unchanged()
    except Exception as exc:
        error = type(exc).__name__  # exception text may contain secrets; do not log it
    finally:
        session.cancel()
        snapshot = session.snapshot()
        save(output / 'session-snapshot.json', snapshot)
        save(output / 'records.json', records)
        save(output / 'tool-receipts.json', tools)
    complete = error is None and all(c['status'] == 'RECEIVED' for c in calls) and not snapshot['unknown_calls']
    if complete:
        for row in calls:
            row['quality'] = score_v2(world_id, row['parsed'])
            row['current_citations'] = design.current_citations(world_id, row['parsed'], row['context'])
            row['grounded_correct'] = row['quality'] and row['current_citations']
    mode = 'live' if model.identity.get('paid') else model.identity.get('receipt_kind', 'mock')
    result = dict(mode=mode, complete=complete, error_type=error,
        world_id=world_id, condition=condition, calls=calls, actual_tool_executions=environment['tool_executions'],
        inspection_intents=sum(c.get('parsed', {}).get('action', {}).get('action') == 'inspect'
                              for c in calls if c.get('parsed', {}).get('valid')),
        cache_hits=0, final_grounded=sum(c['grounded_correct'] is True for c in calls if c['round_index'] == 2),
        actual_tokens=snapshot['actual_tokens'], unknown_tokens=snapshot['unknown_tokens'],
        evidence_note={'mock': 'Synthetic instruments, not provider receipts or algorithm evidence.',
            'offline_replay': 'Retained responses supplied only to exactly matching messages; no new provider evidence.',
            'live': 'New live cohort; separate authorization is required.'}[mode])
    save(output / 'result.json', result)
    return result
