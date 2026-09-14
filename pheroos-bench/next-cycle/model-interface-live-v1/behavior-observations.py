#!/usr/bin/env python3
"""Post-run descriptive classification of retained output objects; no rescoring.

Standard library only. Requires a passing independent accounting audit and all
64 complete known records. Writes a fresh JSON file outside the raw campaign.
"""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return sha256(wire(value).encode()).hexdigest()


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def nonfinite(value):
    raise ValueError('nonfinite JSON')


def parse_response(raw):
    text = raw.strip()
    if text.startswith('```json\n') and text.endswith('\n```') and text.count('```') == 2:
        text = text[8:-4]
    try:
        return json.loads(text, object_pairs_hook=strict_pairs, parse_constant=nonfinite), True
    except (ValueError, TypeError, RecursionError):
        return None, False


def declared_answer_shape(row, answer):
    """Classify the declared answer nesting; never correct or score content."""
    payload = json.loads(row['messages'][1]['content'])
    family = row['family']
    bounded = lambda value: type(value) is int and abs(value) <= 10**9
    if type(answer) is not dict:
        return False
    if family in {'interval_intersection', 'version_correction'}:
        key = 'selection' if family == 'interval_intersection' else 'value'
        return set(answer) == {key} and bounded(answer[key])
    if family == 'dependency_readiness':
        ready = answer.get('ready')
        return (set(answer) == {'ready'} and type(ready) is list
                and all(type(v) is str and v in payload['task_ids'] for v in ready)
                and len(set(ready)) == len(ready))
    totals = answer.get('totals')
    return (set(answer) == {'totals'} and type(totals) is dict and set(totals) == set(payload['item_ids'])
            and all(bounded(v) for v in totals.values()))


def run(campaign, audit_path):
    audit_bytes = audit_path.read_bytes()
    audit = json.loads(audit_bytes)
    records_path = campaign / 'records.json'
    records_bytes = records_path.read_bytes()
    if (audit['status'] != 'PASS' or audit['campaign_status'] != 'COMPLETE'
            or sha256(records_bytes).hexdigest() != audit['input_sha256'][str(records_path.resolve())]):
        raise ValueError('passing audit must bind exact complete records')
    records = json.loads(records_bytes)
    if len(records) != 64 or any(r['status'] != 'VALID_KNOWN' or r['complete'] is not True for r in records):
        raise ValueError('no behavior subset from incomplete or unresolved records')
    refs, source_hashes = {}, {str(records_path): sha256(records_bytes).hexdigest()}
    for ordinal, row in enumerate(records):
        relative = f"episode-{ordinal:03d}-{row['arm']}/episode.json"
        path = campaign / relative
        data = path.read_bytes()
        if json.loads(data) != row:
            raise ValueError('episode differs from records')
        source_hashes[str(path)] = sha256(data).hexdigest()
        refs[(row['world_id'], row['arm'], row['seed'])] = dict(relative_raw_episode=relative,
            raw_sha256=sha256(data).hexdigest(), world_id=row['world_id'], arm=row['arm'], seed=row['seed'])
    index = {(r['world_id'], r['arm'], r['seed']): r for r in records}
    if len(index) != 64:
        raise ValueError('duplicate cell')
    envelope_pairs = []
    for row in records:
        if row['arm'] != 'envelope_256':
            continue
        other = index[(row['world_id'], 'envelope_1024', row['seed'])]
        left, right = row['response'], other['response']
        envelope_pairs.append(dict(world_id=row['world_id'], seed=row['seed'],
            short_ref=refs[(row['world_id'], row['arm'], row['seed'])],
            long_ref=refs[(other['world_id'], other['arm'], other['seed'])],
            byte_identical_messages=wire(row['messages']) == wire(other['messages']),
            identical_prompt_token_ids_sha256=left['prompt_token_ids_sha256'] == right['prompt_token_ids_sha256'],
            generated_256_prefix_identical=len(left['generated_token_ids']) == 256
                and left['generated_token_ids'] == right['generated_token_ids'][:256],
            short_generated_ids_sha256=digest(left['generated_token_ids']),
            long_generated_prefix256_sha256=digest(right['generated_token_ids'][:256]),
            short_output_tokens=left['completion_tokens'], long_output_tokens=right['completion_tokens']))
    envelope_rows, compact_rows = [], []
    for row in records:
        ref = refs[(row['world_id'], row['arm'], row['seed'])]
        value, parseable = parse_response(row['response']['text'])
        if row['arm'] in {'envelope_256', 'envelope_1024'}:
            starts_agent = bool(re.match(r'^\s*(?:```json\s*)?\{\s*"agent"\s*:\s*"agent0"', row['response']['text']))
            envelope_rows.append(dict(**ref, starts_with_agent0_envelope=starts_agent,
                parseable_json=parseable, parseable_object=type(value) is dict,
                object_keys=sorted(value) if type(value) is dict else None,
                action_field_present='action' in value if type(value) is dict else None,
                public_accepted=row['public_accepted'], validation_stage=row['validation']['stage'],
                output_at_cap=row['output_at_cap']))
        if row['arm'] == 'compact_action_256':
            is_action = type(value) is dict and value.get('action') == 'submit'
            citations = value.get('citations') if type(value) is dict else None
            citation_shape = (type(citations) is list and len(citations) <= 4
                and all(type(c) is dict and set(c) == {'source_id', 'source_version'}
                        and type(c['source_id']) is str and type(c['source_version']) is int for c in citations))
            expected = [{k: r[k] for k in ('source_id', 'source_version')} for r in row['materialized']]
            current_citations = citation_shape and wire(sorted(citations, key=wire)) == wire(sorted(expected, key=wire))
            compact_rows.append(dict(**ref, parseable_json=parseable, submit_action_object=is_action,
                answer_matches_declared_shape=declared_answer_shape(row, value.get('answer')) if is_action else False,
                citation_objects_match_declared_shape=citation_shape, citations_exactly_current=current_citations,
                public_accepted=row['public_accepted'], validation_stage=row['validation']['stage']))
    direct = [r for r in records if r['arm'] == 'direct_json_256']
    families = {}
    for family in sorted({r['family'] for r in direct}):
        group = [r for r in direct if r['family'] == family]
        families[family] = dict(episodes=len(group), worlds=len({r['world_id'] for r in group}),
            public_accepted=sum(r['public_accepted'] for r in group), objective_correct=sum(r['objective_success'] for r in group),
            failures=dict(Counter(r['validation']['stage'] for r in group if not r['public_accepted'])),
            raw_refs=[refs[(r['world_id'], r['arm'], r['seed'])] for r in group])
    for path, expected in source_hashes.items():
        if sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('raw input changed during classification')
    long = [r for r in envelope_rows if r['arm'] == 'envelope_1024']
    return dict(profile='model_interface_postrun_behavior_observations_v1', counts_toward_verdict=False,
        classification_status='POSTRUN_DESCRIPTIVE_NO_RESCORE', audit_sha256=sha256(audit_bytes).hexdigest(),
        records_sha256=sha256(records_bytes).hexdigest(), script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        definitions={
            'envelope_prefix': 'After optional opening json fence and whitespace, first object property is agent with literal value agent0.',
            'parseable': 'Strict JSON decode after the same single complete json fence; rejects duplicate keys and nonfinite constants.',
            'wrong_object': 'Parseable object with original public_accepted false; original validator stage retained, no answer extracted or repaired.',
            'generated_prefix': 'All generated IDs from 256 arm (exactly 256 IDs) equal the first 256 generated IDs in matched 1024 arm.',
            'citation_shape': 'List of at most four objects, each exactly source_id string and source_version integer.',
            'answer_shape': 'Original nested answer fields/types/bounds and declared IDs; only structure checked, no new quality score.',
            'direct_family_counts': 'Counts retain original public acceptance and objective scoring already independently audited; no latent-answer credit.'},
        totals=dict(envelope_pairs=len(envelope_pairs), identical_prompt_pairs=sum(r['byte_identical_messages'] for r in envelope_pairs),
            identical_prompt_id_digest_pairs=sum(r['identical_prompt_token_ids_sha256'] for r in envelope_pairs),
            identical_generated_prefix_pairs=sum(r['generated_256_prefix_identical'] for r in envelope_pairs),
            envelope_rows=len(envelope_rows), starts_agent_rows=sum(r['starts_with_agent0_envelope'] for r in envelope_rows),
            envelope1024_parseable_wrong_objects=sum(r['parseable_object'] and not r['public_accepted'] for r in long),
            compact_rows=len(compact_rows), compact_submit_objects=sum(r['submit_action_object'] for r in compact_rows),
            compact_wrong_answer_shape=sum(not r['answer_matches_declared_shape'] for r in compact_rows),
            compact_valid_citation_shape=sum(r['citation_objects_match_declared_shape'] for r in compact_rows),
            compact_exact_current_citations=sum(r['citations_exactly_current'] for r in compact_rows)),
        envelope_pairs=envelope_pairs, envelope_rows=envelope_rows, compact_rows=compact_rows, direct_by_family=families,
        input_sha256=source_hashes, limitations=[
            'These classifications were added after seeing the completed data and are descriptive observations, not preregistered endpoints.',
            'No output repair, answer extraction for credit, rescoring, hidden-answer lookup, model replay or token decoding occurred.',
            'Matching generated prefixes in these 16 pairs does not establish general CUDA determinism or general reproducibility.',
            'Prompt token identity is a retained digest comparison, not raw prompt-token reconstruction.',
            'Envelope prefix copying is an observable output pattern, not proof of its internal model cause.',
            'Eight already observed worlds with two repeats each do not establish generalization, collaboration efficacy or revised admission.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve().is_relative_to(args.campaign.resolve()):
        parser.error('fresh output outside campaign required')
    report = run(args.campaign.resolve(), args.audit.resolve())
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(wire(dict(status=report['classification_status'], totals=report['totals'], output=str(args.output))))


if __name__ == '__main__':
    main()
