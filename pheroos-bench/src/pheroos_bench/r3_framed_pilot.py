"""R3 v3 framing-adapter pilot; no core changes or implicit model escalation.

The finite episode loop has a new identity because v2 hardcodes its scope and
method. Frozen v1/v2 are retained for exact reproduction. Actual context fitting,
tool semantics, final scoring, and artifact withholding remain shared with v2.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from pheroos.kernel import RuntimeScope
import pheroos
from . import r3_pilot, r3_tasks, r3_tool_pilot, r3_tool_tasks as tasks
from .r3_pilot import ARMS, append, canonical, digest, save
from .r3_tool_pilot import ToolWorker, final_ledger, prepared_run, withheld

METHOD = "r3_framed_action_pilot_v3"
PROBE_STEPS = (2, 4)
REQUEST_FIELDS = ('task_id', 'version', 'call_id', 'messages', 'max_new_tokens', 'seed')
MODEL = {"repository": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
         "revision": "2e1fd397ee46e1388853d2af2c993145b0f1098a",
         "precision": "float16", "quantization": None}
MODEL_MANIFEST_SHA256 = "6cd1118d77ca168de77066bf7479020136a0fb66f206bf49171aff0ec900ede3"


def configuration():
    return dict(method_version=METHOD, arms=list(ARMS), worlds=tasks.world_ids(),
                steps=6, max_new_tokens=256, episode_token_cap=12288,
                probe_steps=list(PROBE_STEPS), probe_token_cap=4096, seed=1073,
                model=dict(MODEL), counts_toward_verdict=False)


def frame(text):
    """Accept bare strict JSON or one exact LF/lower-case json fence; no repairs."""
    if type(text) is not str or len(text) > 16_384:
        return text, {"admitted": False, "kind": "rejected", "reason": "invalid text type or length",
                      "parse_operations": 0, "parse_bytes": 0}
    stripped = text.strip(" \t\r\n")
    match = re.fullmatch(r"```json\n([\s\S]*?)\n```", stripped)
    fenced = bool(match and not re.search(r"(?m)^[ \t]*```", match[1]))
    body = match[1] if fenced else stripped
    kind = "sole_json_fence" if fenced else "bare_json"
    parsing = {"parse_operations": 1, "parse_bytes": len(body.encode())}
    try:
        value = json.loads(body, object_pairs_hook=r3_tasks._object, parse_constant=r3_tasks._nonfinite)
        if type(value) is not dict:
            raise ValueError("action JSON must be an object")
    except (ValueError, TypeError, RecursionError) as exc:
        return text, {"admitted": False, "kind": "rejected", "reason": str(exc), **parsing}
    return body, {"admitted": True, "kind": kind, "reason": None, **parsing}


def _wire_bytes(value):
    return len(canonical(value).encode())


def _raw_response(response):
    original = {key: value for key, value in response.items()
                if key not in ("raw_text", "framing", "processing_cost", "raw_reply_sha256")}
    original["text"] = response["raw_text"]
    return original


class FramedWorker:
    """One common generate-response adapter; durable runtime receipts remain raw."""

    def __init__(self, backend):
        self.backend = backend
        self.received = {}
        self.transport = []

    @property
    def transport_failed(self):
        return getattr(self.backend, "transport_failed", False)

    @property
    def identity(self):
        return self.backend.identity

    def close(self):
        self.backend.close()

    def request(self, request):
        entry = {"request_bytes": _wire_bytes(request), "response_bytes": 0,
                 "operation": request["op"], "response_received": False}
        self.transport.append(entry)
        reply = self.backend.request(request)
        entry.update(response_bytes=_wire_bytes(reply), response_received=True)
        if request["op"] != "generate":
            return reply
        # Preserve a detached received response before any validation failure.
        response = deepcopy(reply)
        self.received[request["call_id"]] = response
        raw_text = reply.get("text")
        response["raw_text"] = raw_text
        response["raw_reply_sha256"] = digest(reply)
        text, diagnostic = frame(raw_text)
        response.update(text=text, framing=diagnostic)
        # This records logical input/output processing, including failed formats.
        # Meter metadata is accounted in serialized trace storage, avoiding a
        # self-referential byte counter inside its own response size.
        counts = {"response_copy_operations": 1, "response_copy_bytes": _wire_bytes(reply),
                  "frame_read_operations": 1, "frame_read_bytes": _wire_bytes(raw_text),
                  "json_parse_operations": diagnostic['parse_operations'],
                  "json_parse_bytes": diagnostic['parse_bytes'],
                  "frame_write_operations": 1, "frame_write_bytes": _wire_bytes(text) + _wire_bytes(diagnostic),
                  "receipt_check_operations": 1, "receipt_check_bytes": 0}
        response["processing_cost"] = counts
        calls = reply.get("ledger", {}).get("calls", [])
        matching = [call for call in calls if call.get("id") == request["call_id"]]
        raw_receipt = {key: value for key, value in reply.items() if key not in ("authority", "ledger")}
        expected_request = {key: request[key] for key in REQUEST_FIELDS}
        counts["receipt_check_bytes"] = _wire_bytes(raw_receipt) + _wire_bytes(matching) + _wire_bytes(expected_request)
        counts["total_operations"] = sum(value for key, value in counts.items() if key.endswith("_operations"))
        counts["total_bytes"] = sum(value for key, value in counts.items() if key.endswith("_bytes"))
        if (len(matching) != 1 or matching[0].get("state") != "received"
                or canonical(matching[0].get("response")) != canonical(raw_receipt)
                or canonical(matching[0].get("request")) != canonical(expected_request)):
            raise ValueError("generated raw receipt differs from durable ledger")
        for key in ("prompt_tokens", "completion_tokens"):
            if type(reply.get(key)) is not int or reply[key] < 0:
                raise ValueError("malformed received token accounting")
        return response


def _prepared(worker, request, world, step, memory, *, trim):
    retained, run = prepared_run(worker, request, world, step, memory, trim=trim)
    # A framing/receipt validation exception must not erase already received usage.
    if run["response"] is None and request["call_id"] in worker.received:
        run["response"] = worker.received[request["call_id"]]
    return retained, run


def _usage(rows):
    return {name: sum(row["response"].get(key, 0) for row in rows
                      if row.get("response") and type(row["response"].get(key)) is int
                      and row["response"][key] >= 0)
            for name, key in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"))}


def _parser_counts(rows):
    replies = [row["response"] for row in rows if row.get("response")]
    return {"received": len(replies),
            "admitted": sum(reply.get("framing", {}).get("admitted") is True for reply in replies),
            "public_valid_actions": sum(row.get("result", {}).get("valid") is True
                                        for row in rows if row.get("result"))}


def episode(worker, config, world, arm, ordinal, output):
    if canonical(config) != canonical(configuration()):
        raise ValueError('unsupported pilot configuration')
    if not isinstance(worker, FramedWorker):
        worker = FramedWorker(worker)
    transport_start = len(worker.transport)
    identity = f'{ordinal:03d}-{arm}'
    records, trace, probes, curve = [], [], [], []
    main_request, probe_request = None, None
    error = None
    started = time.monotonic_ns()
    for step in range(config['steps']):
        version = tasks.version(world, step)
        agent = tasks.agent_for(arm, step)
        memory = tasks.memory_for(arm, records, step, version)
        main_request = dict(op='generate', messages=tasks.messages_for(world, step, memory),
            scope=RuntimeScope('r3-framed-pilot-v3', identity, 'episode').to_dict(),
            task_id=world, version=version, call_id=f'{identity}:{step}',
            ledger_path=str(output/f'{identity}.sqlite'), token_cap=config['episode_token_cap'],
            max_calls=config['steps'], max_new_tokens=config['max_new_tokens'],
            seed=config['seed'] + tasks.world_ids().index(world)*100 + step)
        memory, run = _prepared(worker, main_request, world, step, memory, trim=True)
        row = dict(episode_id=identity, world_id=world, arm=arm, step=step, agent=agent,
                   task_version=version, consumed_ids=[r['id'] for r in memory],
                   request=main_request, **run)
        if run['status'] == 'received':
            result = run['result']
            record = dict(id=f'{identity}:artifact:{step}', agent=agent, step=step,
                task_version=version, **{k:result[k] for k in
                ('valid','feedback','artifact','action','semantic_action')},
                receipt_digest=digest(result['artifact']))
            row['record'] = record
            records.append(record)
        append(output/'trace.jsonl', row)
        trace.append(row)
        if run['status'] != 'received':
            error = run['error']
            break
        # Hidden final checks are recorded for prefix curves, never used as feedback.
        curve.append(dict(calls=step+1, task_version=version,
            success=tasks.score(world, step, records),
            tokens=sum(t['response']['prompt_tokens']+t['response']['completion_tokens'] for t in trace),
            elapsed_ns=sum(t['elapsed_ns'] for t in trace)))
        if step in config['probe_steps']:
            fork_memory, removed = withheld(memory, agent, version)
            probe_request = main_request | dict(
                messages=tasks.messages_for(world, step, fork_memory),
                scope=RuntimeScope('r3-framed-pilot-v3', identity+'-probe', 'episode').to_dict(),
                call_id=f'{identity}:probe:{step}', ledger_path=str(output/f'{identity}-probe.sqlite'),
                token_cap=config['probe_token_cap'], max_calls=len(config['probe_steps']))
            _, probe = _prepared(worker, probe_request, world, step, fork_memory, trim=False)
            comparable = probe['status']=='received'
            pair = dict(episode_id=identity, world_id=world, arm=arm, step=step,
                removed_ids=removed, eligible=bool(removed), request=probe_request,
                actual_semantic_action=result['semantic_action'],
                semantic_action_changed=(result['semantic_action'] != probe['result']['semantic_action']) if comparable else None,
                actual_valid=result['valid'], **probe)
            append(output/'probes.jsonl', pair)
            probes.append(pair)
            if not comparable:
                error = probe['error']
                break
    main_ledger = final_ledger(worker, main_request) if main_request else None
    probe_ledger = final_ledger(worker, probe_request) if probe_request else None
    for ledger, required in ((main_ledger, True), (probe_ledger, bool(probe_request))):
        if required and (ledger is None or ledger['unknown_tokens'] or ledger['reserved_tokens']):
            error = error or 'unresolved or unavailable final ledger'
    complete = len(trace)==config['steps'] and len(probes)==len(config['probe_steps'])
    if not complete:
        error = error or 'incomplete declared episode/probe grid'
    for ledger, values in ((main_ledger, trace), (probe_ledger, probes)):
        if ledger is not None and not ledger['unknown_tokens'] and not ledger['reserved_tokens']:
            known = [row for row in values if row.get('response')]
            if (ledger['call_count'] != len(known)
                    or ledger['actual_tokens'] != sum(_usage(values).values())):
                error = error or 'final ledger does not match received cost'
    processing = [row['response'].get('processing_cost', {}) for row in trace + probes if row.get('response')]
    transport = worker.transport[transport_start:]
    return dict(method_version=METHOD, phase='engineering_pilot', counts_toward_verdict=False,
        episode_id=identity, world_id=world, arm=arm, error=error,
        outcome='INVALID_ABORT' if error else ('success' if tasks.score(world,config['steps']-1,records) else 'failed'),
        main_calls=len(trace), probe_calls=len(probes), main_usage=_usage(trace), probe_usage=_usage(probes),
        main_parser=_parser_counts(trace), probe_parser=_parser_counts(probes),
        main_ledger=main_ledger, probe_ledger=probe_ledger, curve=curve,
        accounting_status='KNOWN' if not error else 'CHECK_ABORT',
        eligible_probes=sum(p['eligible'] for p in probes),
        valid_action_changes=sum(p['eligible'] and p['semantic_action_changed'] is True and
                                 p['actual_valid'] and p['result']['valid'] for p in probes if p['result']),
        elapsed_ns=time.monotonic_ns()-started,
        peak_cuda_bytes=max((r['response'].get('peak_cuda_bytes', 0) for r in trace+probes if r['response']), default=0),
        transport_accounting=transport,
        transport_bytes=sum(r['request_bytes'] + r['response_bytes'] for r in transport),
        processing_operations=sum(cost.get('total_operations', 0) for cost in processing),
        processing_bytes=sum(cost.get('total_bytes', 0) for cost in processing),
        serialized_trace_bytes=sum(_wire_bytes(row) + 1 for row in trace + probes),
        tool_receipt_bytes=sum(len(canonical(r['result']).encode()) for r in trace+probes if r['result'] is not None))


def _nonnegative_counts(value, fields):
    if type(value) is not dict or any(type(value.get(field)) is not int or value[field] < 0
                                    for field in fields):
        raise ValueError('accounting counters require exact nonnegative integers')


def _validate_summary_row(row):
    if (row.get('method_version') != METHOD or row.get('counts_toward_verdict') is not False
            or row.get('phase') != 'engineering_pilot'
            or row.get('outcome') not in ('success', 'failed', 'INVALID_ABORT')):
        raise ValueError('invalid episode metadata')
    complete = row['outcome'] != 'INVALID_ABORT'
    _nonnegative_counts(row, ('main_calls', 'probe_calls', 'processing_operations', 'processing_bytes',
                             'transport_bytes', 'serialized_trace_bytes', 'tool_receipt_bytes',
                             'elapsed_ns', 'peak_cuda_bytes', 'eligible_probes', 'valid_action_changes'))
    if row['main_calls'] > 6 or row['probe_calls'] > 2:
        raise ValueError('episode exceeds declared call counts')
    if not 0 <= row['valid_action_changes'] <= row['eligible_probes'] <= row['probe_calls']:
        raise ValueError('invalid probe counters')
    transport = row.get('transport_accounting')
    if type(transport) is not list:
        raise ValueError('missing transport accounting')
    for item in transport:
        _nonnegative_counts(item, ('request_bytes', 'response_bytes'))
        if type(item.get('response_received')) is not bool:
            raise ValueError('invalid transport receipt flag')
    if row['transport_bytes'] != sum(item['request_bytes'] + item['response_bytes'] for item in transport):
        raise ValueError('transport byte total mismatch')
    curve = row.get('curve')
    if type(curve) is not list or len(curve) > row['main_calls']:
        raise ValueError('invalid prefix curve')
    for index, point in enumerate(curve):
        _nonnegative_counts(point, ('calls', 'task_version', 'tokens', 'elapsed_ns'))
        if point['calls'] != index + 1 or type(point.get('success')) is not bool:
            raise ValueError('invalid prefix curve counters')
    for kind, limit, cap in (('main', 6, 12288), ('probe', 2, 4096)):
        usage = row.get(kind + '_usage')
        _nonnegative_counts(usage, ('input_tokens', 'output_tokens'))
        if set(usage) != {'input_tokens', 'output_tokens'}:
            raise ValueError('unexpected usage counters')
        parser = row.get(kind + '_parser')
        _nonnegative_counts(parser, ('received', 'admitted', 'public_valid_actions'))
        if not parser['public_valid_actions'] <= parser['admitted'] <= parser['received'] <= row[kind + '_calls']:
            raise ValueError('inconsistent parser counters')
        ledger = row.get(kind + '_ledger')
        if ledger is None:
            if complete:
                raise ValueError('incomplete episode or unresolved costs')
            continue
        _nonnegative_counts(ledger, ('call_count', 'actual_tokens', 'reserved_tokens', 'unknown_tokens'))
        _nonnegative_counts(ledger.get('config'), ('token_cap', 'max_calls'))
        if ledger['config'] != {'token_cap': cap, 'max_calls': limit}:
            raise ValueError('ledger configuration mismatch')
        calls = ledger.get('calls')
        if type(calls) is not list or ledger['call_count'] != len(calls) or len(calls) > row[kind + '_calls']:
            raise ValueError('ledger call count mismatch')
        identities, actual, reserved, unknown = set(), 0, 0, 0
        receipt_usage = {'input_tokens': 0, 'output_tokens': 0}
        for index, call in enumerate(calls):
            _nonnegative_counts(call, ('reserved',))
            if type(call.get('id')) is not str or not call['id'] or call['id'] in identities:
                raise ValueError('duplicate or invalid ledger call identity')
            identities.add(call['id'])
            state = call.get('state')
            if state not in ('reserved', 'dispatched', 'received', 'denied'):
                raise ValueError('invalid ledger call state')
            if type(call.get('request')) is not dict:
                raise ValueError('missing ledger request')
            request = call['request']
            step = index if kind == 'main' else PROBE_STEPS[index]
            expected_id = f"{row['episode_id']}:{step}" if kind == 'main' else f"{row['episode_id']}:probe:{step}"
            _nonnegative_counts(request, ('version', 'seed', 'max_new_tokens'))
            if (set(request) != set(REQUEST_FIELDS) or call['id'] != expected_id
                    or request['call_id'] != expected_id or request['task_id'] != row['world_id']
                    or request['version'] != tasks.version(row['world_id'], step)
                    or request['seed'] != 1073 + tasks.world_ids().index(row['world_id']) * 100 + step
                    or request['max_new_tokens'] != 256
                    or type(request['messages']) is not list or not request['messages']):
                raise ValueError('ledger request does not match declared episode call')
            if state in ('reserved', 'dispatched'):
                if complete or call.get('actual') is not None or call.get('response') is not None:
                    raise ValueError('incomplete episode or unresolved costs')
                if state == 'reserved':
                    reserved += call['reserved']
                else:
                    unknown += call['reserved']
                continue
            _nonnegative_counts(call, ('actual',))
            actual += call['actual']
            if state == 'denied':
                if complete or call['actual'] != 0 or call.get('response') is not None:
                    raise ValueError('complete episode contains unsettled or denied call')
                continue
            response = call.get('response')
            _nonnegative_counts(response, ('prompt_tokens', 'completion_tokens'))
            _nonnegative_counts(call['request'], ('max_new_tokens',))
            if (call['actual'] != response['prompt_tokens'] + response['completion_tokens']
                    or call['reserved'] != response['prompt_tokens'] + call['request']['max_new_tokens']
                    or response['completion_tokens'] > call['request']['max_new_tokens']):
                raise ValueError('settled call usage or reservation mismatch')
            receipt_usage['input_tokens'] += response['prompt_tokens']
            receipt_usage['output_tokens'] += response['completion_tokens']
        if (actual, reserved, unknown) != (ledger['actual_tokens'], ledger['reserved_tokens'], ledger['unknown_tokens']):
            raise ValueError('ledger aggregate accounting mismatch or unresolved costs')
        if actual + reserved + unknown > cap:
            raise ValueError('ledger exceeds declared token cap')
        if complete:
            if (row[kind + '_calls'] != limit or ledger['call_count'] != limit or parser['received'] != limit
                    or reserved or unknown or receipt_usage != usage or actual != sum(usage.values())):
                raise ValueError('complete episode usage or call count mismatch')
            if kind == 'main' and any(point['tokens'] != sum(call['actual'] for call in calls[:index + 1])
                                      for index, point in enumerate(curve)):
                raise ValueError('prefix token accounting mismatch')
    if complete and (len(curve) != 6 or row['accounting_status'] != 'KNOWN'):
        raise ValueError('incomplete episode or unresolved costs')


def summarize(rows):
    expected={(w,a) for w in tasks.world_ids() for a in ARMS}
    if (type(rows) is not list or len(rows) != len(expected)
            or any(type(row) is not dict or type(row.get('world_id')) is not str
                   or type(row.get('arm')) is not str or type(row.get('episode_id')) is not str
                   or not row['episode_id'] for row in rows)
            or {(row['world_id'], row['arm']) for row in rows} != expected):
        raise ValueError('missing or duplicated paired episodes')
    if len({row['episode_id'] for row in rows}) != len(rows):
        raise ValueError('duplicated episode identity')
    for row in rows:
        _validate_summary_row(row)
    arms={}
    for arm in ARMS:
        group=[r for r in rows if r['arm']==arm]
        arms[arm]=dict(episodes=len(group), successes=sum(r['outcome']=='success' for r in group),
            invalid=sum(r['outcome']=='INVALID_ABORT' for r in group),
            main_tokens=sum(sum(r['main_usage'].values()) for r in group),
            probe_tokens=sum(sum(r['probe_usage'].values()) for r in group),
            parser_admissions={kind: sum(r[kind + '_parser']['admitted'] for r in group)
                               for kind in ('main', 'probe')},
            public_valid_actions={kind: sum(r[kind + '_parser']['public_valid_actions'] for r in group)
                                  for kind in ('main', 'probe')},
            processing_operations=sum(r['processing_operations'] for r in group),
            processing_bytes=sum(r['processing_bytes'] for r in group),
            transport_bytes=sum(r['transport_bytes'] for r in group),
            serialized_trace_bytes=sum(r['serialized_trace_bytes'] for r in group),
            eligible_probes=sum(r['eligible_probes'] for r in group),
            valid_action_changes=sum(r['valid_action_changes'] for r in group),
            curve=[dict(calls=k, observed=sum(len(r['curve'])>=k for r in group),
                successes=sum(r['curve'][k-1]['success'] for r in group if len(r['curve'])>=k),
                tokens=sum(r['curve'][k-1]['tokens'] for r in group if len(r['curve'])>=k),
                elapsed_ns=sum(r['curve'][k-1]['elapsed_ns'] for r in group if len(r['curve'])>=k))
                for k in range(1,7)])
    return dict(method_version=METHOD, counts_toward_verdict=False,
        status='INVALID_ABORT' if any(a['invalid'] for a in arms.values()) else 'PILOT_COMPLETE', arms=arms,
        invalid_episode_accounting=[deepcopy({key: row.get(key) for key in
            ('episode_id', 'world_id', 'arm', 'error', 'accounting_status',
             'main_usage', 'probe_usage', 'main_ledger', 'probe_ledger')})
            for row in rows if row['outcome'] == 'INVALID_ABORT'],
        limitations=['four previously observed worlds; engineering pilot, not held-out efficacy',
            'framing adapter selected after the v2 posthoc audit; v2 outcomes are unchanged',
            'parser admission, public tool validity, final success, and collaboration benefit are separate',
            'sequential GPU inference; no hardware or agent-count scaling',
            'prefix quality uses current source version; evidence changes at call 4',
            'paired probe changes access to current verified other-agent receipts; no downstream branch rollout',
            'no-eligible probes are retained controls; action difference is not necessarily improvement',
            'logical JSON bytes exclude physical device/storage IO',
            'runtime development authority and trusted-host verification remain unchanged'])


def _file_sha(path):
    value = sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def process_identity():
    """Bind the bench interpreter's actual core import as well as the backend."""
    core_root = Path(pheroos.__file__).resolve().parent
    return {'python': sys.version, 'executable': str(Path(sys.executable).resolve()),
            'core_version': importlib.metadata.version('pheroos'),
            'core_files': {str(path): _file_sha(path) for path in sorted(core_root.rglob('*'))
                           if path.is_file() and path.suffix in ('.py', '.json')}}


_INSTALLED_INVENTORY = '''
import hashlib, importlib.metadata as md, json
from pathlib import Path
result = {"packages": {}, "files": {}}
for name in ("pheroos-runtime", "pheroos", "torch", "transformers", "tokenizers", "safetensors", "numpy"):
    distribution = md.distribution(name)
    result["packages"][name] = distribution.version
    if name in ("pheroos-runtime", "pheroos"):
        result["files"][name] = {
            str(entry): {"path": str(Path(distribution.locate_file(entry)).resolve()),
                         "sha256": hashlib.sha256(Path(distribution.locate_file(entry)).read_bytes()).hexdigest()}
            for entry in distribution.files
            if str(entry).endswith((".py", ".json", "METADATA", "RECORD"))}
print(json.dumps(result, sort_keys=True))
'''


def verify_inputs(runtime_python, runtime_source, model_path):
    """Verify installed code and local model bytes without loading CUDA/models."""
    environment = dict(os.environ)
    environment.pop('PYTHONPATH', None)
    process = subprocess.run([str(runtime_python), '-I', '-c', _INSTALLED_INVENTORY],
                             check=True, capture_output=True, text=True, timeout=60,
                             env=environment)
    installed = json.loads(process.stdout)
    runtime_files = installed['files']['pheroos-runtime']
    source_files = {str(path.relative_to(runtime_source / 'src')): path
                    for path in (runtime_source / 'src/pheroos_runtime').rglob('*.py')}
    actual = {name: item for name, item in runtime_files.items() if name.startswith('pheroos_runtime/')
              and name.endswith('.py')}
    if not source_files or set(actual) != set(source_files):
        raise ValueError('installed runtime source inventory mismatch')
    if any(item['sha256'] != _file_sha(source_files[name]) for name, item in actual.items()):
        raise ValueError('installed runtime differs from declared source')
    manifest = json.loads((model_path / 'manifest.json').read_text())
    if (digest(manifest) != MODEL_MANIFEST_SHA256
            or any(manifest.get(key) != value for key, value in MODEL.items())):
        raise ValueError('undeclared model or precision; explicit new experiment required')
    if not manifest.get('sha256') or any(
            Path(name).name != name or _file_sha(model_path / name) != value
            for name, value in manifest['sha256'].items()):
        raise ValueError('local model manifest digest mismatch')
    return installed, manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config', 'output', 'runtime-python', 'runtime-source', 'model-path'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args(argv)
    for name in ('runtime_python', 'runtime_source', 'model_path'):
        setattr(args, name, getattr(args, name).resolve())
    config = json.loads(args.config.read_text(), object_pairs_hook=r3_tasks._object,
                        parse_constant=r3_tasks._nonfinite)
    if canonical(config) != canonical(configuration()):
        raise ValueError('unsupported pilot configuration')
    if args.output.exists():
        raise ValueError('exclusive output required')
    installed, model = verify_inputs(args.runtime_python, args.runtime_source, args.model_path)
    bench_process = process_identity()
    bench = Path(__file__).resolve().parents[2]
    paths = [Path(module.__file__) for module in (r3_pilot, r3_tasks, r3_tool_pilot, tasks)]
    paths += [Path(__file__), args.config, bench / 'R3-framed-v3-contract.md',
              Path(__file__).with_name('__init__.py'),
              bench / 'tests/test_r3_framed_pilot.py', args.model_path / 'manifest.json']
    paths += [bench / 'tests' / name for name in ('test_r3_pilot.py', 'test_r3_tasks.py',
                                               'test_r3_tool_pilot.py', 'test_r3_tool_tasks.py')]
    paths += sorted((args.runtime_source / 'src/pheroos_runtime').rglob('*.py'))
    frozen = {str(path.resolve()): _file_sha(path) for path in paths}
    args.output.mkdir(parents=True, exist_ok=False)
    output = args.output.resolve()
    save(output / 'freeze.json', dict(method_version=METHOD, counts_toward_verdict=False,
         config=config, source_sha256=frozen, installed=installed, bench_process=bench_process,
         model=model, frozen_before_calls=True))
    worker, rows = None, []
    try:
        worker = FramedWorker(ToolWorker(args.runtime_python, args.model_path, output))
        if worker.identity.get('model_manifest') != model:
            raise ValueError('loaded model identity differs from frozen model')
        save(output / 'environment.json', worker.identity)
        for index, world in enumerate(tasks.world_ids()):
            for arm in ARMS[index:] + ARMS[:index]:
                row = episode(worker, config, world, arm, len(rows), output)
                rows.append(row)
                append(output / 'episodes.jsonl', row)
                print(world, arm, row['outcome'], row['main_usage'], row['probe_usage'], flush=True)
                if row['outcome'] == 'INVALID_ABORT':
                    raise RuntimeError(row['error'])
        if any(_file_sha(path) != expected for path, expected in frozen.items()):
            raise RuntimeError('frozen source changed during experiment')
        current, current_model = verify_inputs(args.runtime_python, args.runtime_source, args.model_path)
        if current != installed or current_model != model or process_identity() != bench_process:
            raise RuntimeError('installed package or model changed during experiment')
        save(output / 'summary.json', summarize(rows))
    except BaseException as error:
        save(output / 'abort.json', dict(method_version=METHOD, status='INVALID_ABORT',
             counts_toward_verdict=False, error=f'{type(error).__name__}: {error}',
             completed_episodes=len(rows), known_episodes=rows,
             accounting_status='UNRESOLVED_OR_UNAVAILABLE', unknown_tokens=None,
             received_calls=worker.received if worker else {},
             transport_accounting=worker.transport if worker else []))
        raise
    finally:
        if worker:
            worker.close()


if __name__ == '__main__':
    main()
