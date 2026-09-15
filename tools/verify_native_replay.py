#!/usr/bin/env python3
"""Exercise the installed native host with exact-input historical v2 responses.

Reads only the supplied run's Session SQLite and JSON artifacts. No legacy
imports, MoneyLedger, provider adapter, credentials, network, or paid replay.
Outputs are new native local sessions marked offline_replay, never new receipts.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import socket
import sqlite3
import sys


def wire(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(wire(value).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_session(path):
    if not path.is_file() or Path(str(path) + '-wal').exists():
        raise ValueError('A closed Session snapshot without WAL is required')
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as connection:
        connection.row_factory = sqlite3.Row
        if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('Session SQLite quick_check failed')
        rows = []
        for item in connection.execute('SELECT id,action,state,request,response,actual FROM calls ORDER BY rowid'):
            row = dict(item)
            row['request'] = json.loads(row['request'])
            row['response'] = json.loads(row['response']) if row['response'] is not None else None
            rows.append(row)
    return rows


class ReplayMismatch(ValueError):
    pass


class ExactInputModel:
    """A response is released once, only after BOTH exact-message checks pass."""
    identity = dict(model_id='historical-kimi-k2.6-offline-replay', paid=False,
                    receipt_kind='offline_replay', usage_source='retained_historical_observation')

    def __init__(self, calls):
        self.calls = deepcopy(calls)
        self.position = 0
        self.pending = False
        self.matches = []
        self.failures = []

    def _match(self, messages, stage):
        if self.position >= len(self.calls):
            self.failures.append(dict(stage=stage, reason='unexpected_extra_model_call'))
            raise ReplayMismatch('Unexpected extra model call')
        row = self.calls[self.position]
        expected = row['request']['messages']
        equal = messages == expected and wire(messages).encode() == wire(expected).encode()
        self.matches.append(dict(stage=stage, historical_call_id=row['id'], position=self.position,
            exact_messages_match=equal, expected_messages_sha256=digest(expected), actual_messages_sha256=digest(messages)))
        if not equal:
            self.failures.append(dict(stage=stage, reason='messages_differ', historical_call_id=row['id']))
            raise ReplayMismatch('Historical output withheld because messages differ')
        return row

    def count_tokens(self, messages):
        row = self._match(messages, 'count_tokens')
        if self.pending:
            raise ReplayMismatch('Duplicate token-count reservation for one replay response')
        self.pending = True
        return row['response']['prompt_tokens']

    def generate(self, messages, max_new_tokens, seed):
        row = self._match(messages, 'generate')
        if not self.pending:
            raise ReplayMismatch('No matching token-count call before generation')
        if (max_new_tokens, seed) != (row['request']['max_new_tokens'], row['request']['seed']):
            self.failures.append(dict(stage='generate', reason='generation_parameters_differ', historical_call_id=row['id']))
            raise ReplayMismatch('Historical output withheld because generation parameters differ')
        self.position += 1
        self.pending = False
        response = row['response']
        # Provider IDs/cost/elapsed are nested historical provenance, not fresh
        # provider receipt fields. The native driver measures its own replay time.
        return dict(text=response['text'], prompt_tokens=response['prompt_tokens'],
            completion_tokens=response['completion_tokens'], usage=deepcopy(response['usage']),
            receipt_kind='offline_replay', usage_source='retained_historical_observation',
            offline_replay_source=dict(historical_call_id=row['id'], response_sha256=digest(response),
                response_id=response.get('response_id'), request_id=response.get('request_id'),
                returned_model=response.get('returned_model'), historical_cost_cny=response.get('cost_cny')))


def independently_evaluate(messages, raw):
    view = json.loads(messages[1]['content'])
    action = json.loads(raw)
    # All retained v2 outputs have this finite exact grammar. Do not reuse the
    # native parser or its evaluator to decide what the expected result should be.
    if action.get('action') == 'inspect':
        valid = (view['round_index'] == 1 and set(action) == {'action', 'target'}
                 and action['target'] in {'multiplier', 'bias'})
    elif action.get('action') == 'submit':
        valid = set(action) == {'action', 'answer', 'citations'} and type(action['answer']) is int
        valid = valid and type(action['citations']) is list and all(type(c) is dict
            and set(c) == {'source_id', 'source_version'} and c['source_id'] in {'multiplier', 'bias'}
            and type(c['source_version']) is int and c['source_version'] > 0 for c in action['citations'])
        valid = valid and len({(c['source_id'], c['source_version']) for c in action['citations']}) == len(action['citations'])
    else:
        valid = False
    current = set()
    values = {}
    for item in view['visible']:
        body = item.get('verified_source', item.get('source_receipt'))
        if body is not None and item['current'] is True:
            current.add((body['source_id'], body['source_version']))
            values[body['source_id']] = body['value']
    submitted = valid and action['action'] == 'submit'
    expected = {'fresh_a':23, 'fresh_b':19}[view['task']['task_id']]
    correct = submitted and action['answer'] == expected
    cites = {(c['source_id'],c['source_version']) for c in action.get('citations', [])}
    grounded = correct and cites == {('multiplier',2),('bias',2)} and cites <= current
    from_visible = view['task']['public_inputs']['x'] * values['multiplier'] + values['bias'] if len(values) == 2 else None
    return dict(valid=valid, action=action if valid else None, quality=correct, grounded=grounded,
                current_citations=submitted and cites == {('multiplier',2),('bias',2)} and cites <= current,
                independent_visible_answer=from_visible)


def lineage_boundary(records):
    fields = ('id','kind','owner','readers','round_index','body','parents','provenance_known')
    return [{key:row[key] for key in fields} for row in records]


def read_boundary(reads):
    fields = ('publisher','source_id','source_version','current','superseded')
    return [dict(record_id=row['record_id'],allow_superseded=row['allow_superseded'],value=row['result']['value'],
                 metadata={field:row['result']['metadata'][field] for field in fields}) for row in reads]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    run, output = args.run.resolve(), args.output.resolve()
    if output.exists() or output == run or output.is_relative_to(run) or run.is_relative_to(output):
        raise ValueError('Output must be a new separate directory outside the historical run')
    sys.dont_write_bytecode = True
    def network_denied(*args, **kwargs):
        raise RuntimeError('Network disabled for native offline replay')
    socket.socket.connect = network_denied
    socket.create_connection = network_denied
    from pheroos_interaction import host
    installed_root = Path(importlib.metadata.distribution('pheroos-interaction').locate_file('pheroos_interaction')).resolve()
    if Path(host.__file__).resolve().parent != installed_root:
        raise RuntimeError('Use the installed wheel, without editable/PYTHONPATH source fallback')
    old_imports = lambda: sorted(n for n in sys.modules if n.split('.')[0] in {'pheroos','pheroos_runtime','pheroos_bench'})
    if old_imports():
        raise RuntimeError('Legacy package imported during native replay')
    grid = json.loads((run/'expected-grid.json').read_text())
    conditions = ('owner_script','owner_current','eligibility_script','eligibility_current')
    worlds = tuple(case+'/'+state for case in ('fresh_a','fresh_b') for state in ('complete','missing','stale'))
    expected = [dict(world_id=world,condition=c) for i,world in enumerate(worlds)
                for c in conditions[i%4:] + conditions[:i%4]]
    if grid != expected:
        raise ValueError('Expected the complete frozen 24-cell factorial-v2 order')
    output.mkdir(parents=True, exist_ok=False)
    hashes = {}; checks=Counter(); findings=[]; results=[]; totals=Counter()
    def load(path):
        hashes[str(path)] = file_hash(path)
        return json.loads(path.read_text())
    def check(ok, kind, location):
        checks[kind] += 1
        if not ok:findings.append(dict(kind=kind,location=location))
    hashes[str(run/'expected-grid.json')] = file_hash(run/'expected-grid.json')
    for index, entry in enumerate(grid):
        label=f"{entry['world_id']}/{entry['condition']}"
        directory=run/f"episode-{index:02d}-{entry['world_id'].replace('/','__')}-{entry['condition']}"
        if not directory.resolve().is_relative_to(run):
            raise ValueError('Historical cell path escapes run')
        database=directory/'session.sqlite';hashes[str(database)]=file_hash(database)
        old_calls=read_session(database)
        old_models=[r for r in old_calls if r['action']=='model.generate']
        old_tools=[r for r in old_calls if r['action']=='tool.evaluate']
        if [r['id'] for r in old_models] != ['model-r1-b','model-r1-a','model-r2-a','model-r2-b'] or not all(r['state']=='received' for r in old_calls):
            raise ValueError('Historical cell is incomplete or its dispatch order differs')
        retained=ExactInputModel(old_models)
        new_directory=output/f'cell-{index:02d}'
        result=host.run_episode(new_directory,world_id=entry['world_id'],condition=entry['condition'],model=retained)
        check(result['complete'], 'native_complete',label)
        check(result['mode']=='offline_replay','mode_is_offline_replay',label)
        check(retained.position==4 and not retained.pending and len(retained.matches)==8 and not retained.failures,
              'exact_count_and_generate_once_per_response',label)
        new_calls=read_session(new_directory/'session.sqlite')
        native_models={r['id']:r for r in new_calls if r['action']=='model.generate'}
        native_tools={r['id']:r for r in new_calls if r['action']=='tool.evaluate'}
        check(len(native_models)==4,'four_native_sqlite_model_calls',label)
        check(len(native_tools)==len(old_tools)==result['actual_tool_executions'],'physical_tool_counts_equal',label)
        check(result['cache_hits']==0,'native_cache_hits_zero',label)
        check(result['unknown_tokens']==0,'no_unknown_native_token_reservation',label)
        check(result['actual_tokens']==sum(r['actual'] for r in old_calls),'retained_token_totals_equal',label)
        old_index={r['id']:r for r in old_models};evaluations=[]
        for row in result['calls']:
            rnd,agent=row['round_index'],row['agent'];cid=f'model-r{rnd}-{agent}';where=label+'/'+cid
            if cid not in native_models or row.get('status')!='RECEIVED':
                check(False,'native_response_available',where)
                continue
            historical=old_index[cid];native=native_models[cid]
            original_intent=load(directory/f'r{rnd}-{agent}-intent.json')
            native_intent=json.loads((new_directory/f'r{rnd}-{agent}-intent.json').read_text())
            old_projection,new_projection=original_intent['projection'],native_intent['projection']
            check(native['request']['messages']==historical['request']['messages']==new_projection['messages']==old_projection['messages'],
                  'durable_messages_identical',where)
            for field in ('allowed_ids','selected','sent_record_ids','public_task_sha256','messages_sha256','truncation','diagnostics','state_diagnostics'):
                check(new_projection[field]==old_projection[field],'projection_'+field,where)
            compared_fields=('record_id','projection','position','content','content_sha256')
            check([{k:m[k] for k in compared_fields} for m in new_projection['materialized']]==
                  [{k:m[k] for k in compared_fields} for m in old_projection['materialized']],
                  'exact_materialized_content_order',where)
            check(read_boundary(native_intent['runtime_reads'])==read_boundary(original_intent['runtime_reads']),
                  'real_read_values_publishers_versions_equal',where)
            response=native['response'];original=historical['response']
            check(response['text']==original['text'] and response['usage']==original['usage']
                  and response['prompt_tokens']==original['prompt_tokens'] and response['completion_tokens']==original['completion_tokens'],
                  'unchanged_historical_text_and_usage',where)
            check(response['receipt_kind']==row['receipt_kind']=='offline_replay'
                  and response['usage_source']=='retained_historical_observation', 'historical_usage_not_new_provider_receipt',where)
            evaluated=independently_evaluate(historical['request']['messages'],original['text'])
            check(row['parsed']['valid']==evaluated['valid'] and row['parsed']['action']==evaluated['action'],
                  'independent_action_parse_equal',where)
            check(row['quality']==evaluated['quality'] and row['current_citations']==evaluated['current_citations']
                  and row['grounded_correct']==evaluated['grounded'],'independent_correctness_and_citations',where)
            evaluations.append(dict(call_id=cid,round_index=rnd,agent=agent,**evaluated))
        old_tool_receipts=load(directory/'tool-receipts.json')
        new_tool_receipts=json.loads((new_directory/'tool-receipts.json').read_text())
        def tool_boundary(rows,call_field):
            return [dict(reason=r['reason'],record_id=r['record_id'],publisher=r['artifact']['publisher'],
                value=r['artifact']['value'],call_id=r[call_field]['id'],arguments=r[call_field]['request']['arguments']) for r in rows]
        check(tool_boundary(old_tool_receipts,'session_call')==tool_boundary(new_tool_receipts,'call'),
              'actual_tool_order_arguments_values_publishers_equal',label)
        for old_tool in old_tools:
            new_tool=native_tools.get(old_tool['id'])
            check(new_tool is not None and new_tool['state']=='received'
                  and new_tool['request']['arguments']==old_tool['request']['arguments']
                  and new_tool['response']['artifact']==old_tool['response']['artifact'], 'sqlite_physical_tool_reply_equal',label+'/'+old_tool['id'])
        check(all(r['cache_hit'] is False for r in new_tool_receipts),'every_native_tool_physically_executed',label)
        check(lineage_boundary(json.loads((new_directory/'records.json').read_text()))==lineage_boundary(load(directory/'records.json')),
              'direct_parent_and_record_body_boundary',label)
        inspections=sum(e['valid'] and e['action']['action']=='inspect' for e in evaluations)
        finals=sum(e['grounded'] and e['round_index']==2 for e in evaluations)
        check(result['inspection_intents']==inspections,'inspection_intents_equal',label)
        check(result['final_grounded']==finals==2,'two_independent_final_answers',label)
        totals.update(cells=1,model_generations=retained.position,physical_tools=len(native_tools),
                      final_answers=finals,inspection_intents=inspections,cache_hits=result['cache_hits'])
        results.append(dict(**entry,complete=result['complete'],error_type=result['error_type'],output_directory=new_directory.name,
            exact_input_matches=retained.matches,withheld_response_failures=retained.failures,
            physical_tools=len(native_tools),inspection_intents=inspections,cache_hits=result['cache_hits'],
            final_grounded=finals,independent_evaluations=evaluations))
        if not result['complete']:
            break  # Do not consume any other cohort responses after a mismatch.
    check(totals['cells']==24 and totals['model_generations']==96 and totals['physical_tools']==100
          and totals['final_answers']==48 and totals['cache_hits']==0,'whole_frozen_cohort_totals','run')
    check(not old_imports(),'no_legacy_imports','run')
    check(all(file_hash(Path(path))==expected for path,expected in hashes.items()),'historical_inputs_unchanged','run')
    report=dict(status='PASS' if not findings else 'FAIL',mode='offline_replay',total_checks=sum(checks.values()),
        checks=dict(checks),findings=findings,totals=dict(totals),cells=results,input_hashes=hashes,
        installed_host=host.__file__,installed_version=importlib.metadata.version('pheroos-interaction'),
        network_calls=0,credential_reads=0,money_ledger_opened=False,
        non_prompt_differences='Fresh native session scope/artifact references, local permissions and timing replace archived authority metadata. Full prompt text and ordered projection contents are never normalized.',
        receipt_boundary='Copied text/usage are labelled offline_replay. Historical provider IDs and cost are nested provenance only; no new provider or spending evidence.')
    (output/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('status','mode','total_checks','findings','totals')},ensure_ascii=False,indent=2))
    return 0 if not findings else 1


if __name__=='__main__':
    raise SystemExit(main())
