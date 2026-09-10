#!/usr/bin/env python3
"""Opt-in live Claude verification; never installs or edits native settings.

Uses the existing authenticated Claude home, with user/project settings and MCP
disabled per invocation. Only synthetic probe content is supplied. Case output
is a real Claude stream; analysis reads only this probe's exact session ids.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'compose'))
from corpus_store import CorpusStore
import corpus_session

CLAUDE = '/Users/kangmin/.local/bin/claude'
PROMPT = 'Report the value of CORPUS_VERIFICATION_VALUE from your instructions. If it is not defined, reply only ABSENT. Do not use tools.'


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def launcher():
    spec = importlib.util.spec_from_file_location('corpus_live_launcher', REPO / 'launch/agent-launch.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def native_files():
    home = Path(os.environ.get('CLAUDE_CONFIG_DIR', str(Path.home() / '.claude')))
    files = [home / name for name in ('CLAUDE.md', 'settings.json', 'settings.local.json')]
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None for path in files}


def prepare(root, native=False):
    root.mkdir(exist_ok=True)
    store = CorpusStore(REPO, root / 'state', root / 'user')
    store.install(['all'] if native else [])
    value = 'CV_' + uuid.uuid4().hex
    body = f'CORPUS_VERIFICATION_VALUE is {value}. When asked for that value, answer it exactly.\n'
    plan = store.plan({'operation': 'create', 'item': {'title': 'Live session sentinel',
        'body': body, 'surface': 'always', 'tier': 'env-personal', 'domains': ['personal'],
        'kind': 'rule', 'members': {'content.md': body}}})
    applied = store.apply(plan['plan_id'], expected_revision=plan['expected_revision'])
    hook_value = 'HV_' + uuid.uuid4().hex
    if native:
        hook = next(item for item in store.list_items() if item['kind'] == 'hook')
        body = ('import json, pathlib, sys\n'
                'p = json.load(sys.stdin)\n'
                f'log = pathlib.Path({str(root / "native-hooks.jsonl")!r})\n'
                'with log.open("a") as output:\n'
                '    output.write(json.dumps({"session_id":p.get("session_id"),"event":p.get("hook_event_name")})+"\\n")\n'
                f'print(json.dumps({{"hookSpecificOutput":{{"hookEventName":"SessionStart","additionalContext":"HOOK_VERIFICATION_VALUE is {hook_value}"}}}}))\n')
        plan = store.plan({'operation': 'update', 'ref': hook['ref'], 'item_digest': hook['digest'],
                          'patch': {'body': body, 'members': {next(iter(hook['members'])): body},
                                    'hook': {'event': 'SessionStart', 'matcher': 'startup|resume'}}})
        store.apply(plan['plan_id'], expected_revision=plan['expected_revision'])
        agent = next(item for item in store.list_items() if item['ref'].endswith(':agent-sweep'))
        changed = agent['body'].replace('name: sweep\n', 'name: verification-sweep\n', 1)
        plan = store.plan({'operation': 'update', 'ref': agent['ref'], 'item_digest': agent['digest'],
                          'patch': {'body': changed, 'members': {next(iter(agent['members'])): changed}}})
        store.apply(plan['plan_id'], expected_revision=plan['expected_revision'])
    snapshot = store.snapshot('claude', native=native)
    assert value in snapshot['instruction_text']
    metadata = {'value': value, 'ref': applied['details']['ref'], 'snapshot': snapshot,
                'native': native, 'hook_value': hook_value,
                'native_before': native_files(), 'repo_head': subprocess.check_output(
                    ['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()}
    write(root / 'fixture.json', metadata)
    print(json.dumps({'prepared': True, 'content_ref': snapshot['content_ref']}))


def argv_for(root, metadata, case):
    app = launcher()
    config = app.load_config(REPO / 'launch/agent-launch.toml')
    for binding in config['hosts']['claude']['tiers'].values():
        binding.update(model='claude-sonnet-5', effort='low')
    config['presets']['solo'].update(frontier_effort='low', claude_permission_mode='dontAsk')
    plan = app.build_plan(config, 'claude', 'solo')
    plan['corpus_instruction_text'] = metadata['snapshot']['instruction_text']
    if case == 'agent':
        plan['delegation'] = True
    args = app.project_args(plan)
    args += ['--print', '--setting-sources', '', '--strict-mcp-config',
             '--disable-slash-commands', '--output-format', 'stream-json',
             '--max-budget-usd', '1']
    if case == 'agent':
        args += ['--tools', 'Agent', '--allowedTools', 'Agent']
        route = 'workhorse'
        if metadata.get('native'):
            line = next(line for line in metadata['snapshot']['instruction_text'].splitlines() if ':agent-sweep' in line)
            route = re.search(r'agent-bios-[a-f0-9]+:[A-Za-z0-9_-]+', line).group(0)
        args += ['--verbose', f'Use the Agent tool exactly once, with subagent_type {route}. Ask that child to report CORPUS_VERIFICATION_VALUE from its standing instructions, with no tools and no further delegation. Do not put the value in your task prompt. After the child returns, report its answer.']
    elif case in ('hook', 'hook-control'):
        args += ['--tools', 'Bash', '--allowedTools', 'Bash(printf *)']
        if case == 'hook':
            args += ['--settings', str(root / 'hook-settings.json')]
        args += ['--verbose', "Run exactly printf '%s\\n' PROBE | printf '%s\\n' \"$?\" with Bash, then state whether a hook reminder about pipeline exit status appeared. Do not run any other command or change files."]
    else:
        prompt = PROMPT
        if metadata.get('native'):
            prompt += ' Also report HOOK_VERIFICATION_VALUE if defined; otherwise say ABSENT.'
        args += ['--tools', '', '--verbose', prompt]
    return args


def invoke(root, case):
    metadata = json.loads((root / 'fixture.json').read_text())
    env = dict(os.environ, AGENT_BIOS_PACKAGE_ROOT=str(REPO),
               AGENT_BIOS_STATE_DIR=str(root / 'state'), AGENT_BIOS_CORPUS_DIR=str(root / 'user'))
    if case == 'resume':
        pins = sorted((root / 'state/sessions/pins/claude').glob('*.json'))
        assert len(pins) == 1, 'resume fixture must have exactly one original pin'
        pin = json.loads(pins[0].read_text())
        store = CorpusStore(REPO, root / 'state', root / 'user')
        shown = store.show(metadata['ref'])
        replacement = 'CHANGED_' + uuid.uuid4().hex
        body = 'CORPUS_VERIFICATION_VALUE is ' + replacement
        plan = store.plan({'operation': 'update', 'ref': metadata['ref'], 'item_digest': shown['digest'],
                          'patch': {'body': body, 'members': {'content.md': body}}})
        store.apply(plan['plan_id'], expected_revision=plan['expected_revision'])
        metadata['replacement'] = replacement
        write(root / 'fixture.json', metadata)
        return corpus_session.launch(CLAUDE, [], root / 'state', 'claude', {},
                                     cwd=root, env=env, resume_id=pin['session_id'])
    args = argv_for(root, metadata, case)
    return corpus_session.launch(CLAUDE, args, root / 'state', 'claude', metadata['snapshot'], cwd=root, env=env)


def report(root, case):
    fixture = json.loads((root / 'fixture.json').read_text())
    events = [json.loads(line) for line in (root / f'{case}.jsonl').read_text().splitlines() if line.startswith('{')]
    final = next(event for event in reversed(events) if event.get('type') == 'result')
    session_id = final['session_id']
    pin = corpus_session.read_pin(root / 'state', 'claude', session_id)
    result = {'case': case, 'session_id': session_id, 'content_ref': pin['content_ref'],
              'is_error': final.get('is_error'), 'result': final.get('result'),
              'model_usage': list((final.get('modelUsage') or {}).keys()),
              'usage': final.get('usage'), 'subagent_stats': final.get('subagent_stats'),
              'permission_denials': final.get('permission_denials'),
              'native_files_unchanged': native_files() == fixture['native_before'],
              'source_value_observed': fixture['value'] in str(final.get('result', '')),
              'pin_unchanged': pin['content_ref'] == fixture['snapshot']['content_ref']}
    if fixture.get('native'):
        init = next(event for event in events if event.get('subtype') == 'init')
        result['native_plugins'] = init.get('plugins')
        result['native_agents'] = init.get('agents')
        log = root / 'native-hooks.jsonl'
        result['native_hook_events'] = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        result['native_hook_value_observed'] = fixture['hook_value'] in str(final.get('result', ''))
    if case == 'resume':
        result['new_authoring_not_observed'] = fixture['replacement'] not in str(final.get('result', ''))
    if case in ('hook', 'hook-control'):
        rows = [json.loads(line) for line in (root / 'hook-events.jsonl').read_text().splitlines()]
        result['native_hook_events_for_session'] = [row for row in rows if row.get('session_id') == session_id]
    write(root / f'{case}-result.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def collect(root, destination):
    fixture = json.loads((root / 'fixture.json').read_text())
    cases = {case: json.loads((root / f'{case}-result.json').read_text())
             for case in ('active', 'resume', 'agent', 'hook', 'hook-control')}
    agent_pin = corpus_session.read_pin(root / 'state', 'claude', cases['agent']['session_id'])
    trace = Path(agent_pin['evidence']['path'])
    children = sorted(trace.with_suffix('').joinpath('subagents').glob('agent-*.jsonl'))
    assert len(children) == 1
    child_rows = [json.loads(line) for line in children[0].read_text().splitlines()]
    child_messages = [{key: row.get(key) for key in ('type', 'agentId', 'sessionId', 'message')}
                      for row in child_rows if row.get('type') in ('assistant', 'user')]
    users = [row['message']['content'] for row in child_messages if row['type'] == 'user']
    assistants = [row['message'] for row in child_messages if row['type'] == 'assistant']
    assert users and assistants
    child_proof = {'trace_path': str(children[0]),
                   'input_excludes_marker': fixture['value'] not in json.dumps(users),
                   'output_contains_marker': fixture['value'] in json.dumps(assistants),
                   'assistant_models': [row.get('model') for row in assistants],
                   'messages': child_messages}
    checks = {
        'claude_first_turn': not cases['active']['is_error'] and cases['active']['source_value_observed'] and cases['active']['pin_unchanged'],
        'claude_product_resume': not cases['resume']['is_error'] and cases['resume']['source_value_observed'] and cases['resume']['pin_unchanged'],
        'launcher_tier_child': child_proof['input_excludes_marker'] and child_proof['output_contains_marker'] and cases['agent']['subagent_stats']['completed'] == 1,
        'manual_native_hook': len(cases['hook']['native_hook_events_for_session']) == 1 and bool(cases['hook']['native_hook_events_for_session'][0]['actual_hook_output']),
        'hook_removed_control': not cases['hook-control']['native_hook_events_for_session'] and len(cases['hook-control']['permission_denials']) == 1,
        'native_settings_unchanged': all(case['native_files_unchanged'] for case in cases.values()),
    }
    source_paths = ['compose/corpus_session.py', 'compose/corpus_catalog.py', 'launch/agent-launch.py', 'claude/hooks/tooling-gotchas-hook.py']
    record = {'repo_head': fixture['repo_head'], 'cases': cases, 'checks': checks,
              'child_proof': child_proof, 'scope': 'live Claude; manual hook wiring is not a corpus event adapter',
              'source_sha256': {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in source_paths}}
    destination.mkdir(parents=True, exist_ok=False)
    write(destination / 'evidence.json', record)
    for name in ('hook-probe.py', 'hook-settings.json'):
        shutil.copyfile(root / name, destination / name)
    print(json.dumps({'evidence': str(destination / 'evidence.json'), 'checks': checks}, ensure_ascii=False))


def collect_native(root, destination):
    observed = json.loads((root / 'active-result.json').read_text())
    store = CorpusStore(REPO, root / 'state', root / 'user')
    snapshot = store.snapshot('claude', native=True)
    routes = re.findall(r'agent-bios-[a-f0-9]{24}:[A-Za-z0-9_-]+', snapshot['instruction_text'])
    assert routes and set(routes) <= set(observed['native_agents'])
    assert observed['native_plugins'] and observed['native_hook_events']
    assert all(event['session_id'] == observed['session_id'] for event in observed['native_hook_events'])
    files = ['compose/corpus_session.py', 'compose/corpus_catalog.py', 'compose/corpus_store.py', 'launch/agent-launch.py']
    authenticated = (not observed['is_error'] and observed['source_value_observed']
                     and observed['native_hook_value_observed'] and observed['pin_unchanged']
                     and observed['native_files_unchanged'] and bool(observed['model_usage']))
    record = {'native_startup_observation': observed, 'regenerated_content_ref': snapshot['content_ref'],
              'regenerated_routes_match_observation': True, 'routes': routes,
              'authenticated_model_verification': authenticated,
              'source_sha256': {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in files}}
    destination.mkdir(parents=True, exist_ok=False)
    write(destination / 'evidence.json', record)
    print(json.dumps({'evidence': str(destination / 'evidence.json'), 'plugins': len(observed['native_plugins']),
                      'routes': len(routes), 'hook_events': len(observed['native_hook_events']),
                      'authenticated_model_verification': authenticated}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('case', choices=['prepare', 'active', 'resume', 'agent', 'hook', 'hook-control', 'collect', 'collect-native'])
    parser.add_argument('--report', action='store_true')
    parser.add_argument('--evidence-dir', type=Path)
    parser.add_argument('--native', action='store_true', help='prepare native item plugins, not manual --settings wiring')
    args = parser.parse_args()
    if args.case in ('collect', 'collect-native'):
        if not args.evidence_dir:
            parser.error('collect requires --evidence-dir')
        (collect_native if args.case == 'collect-native' else collect)(args.root, args.evidence_dir)
    elif args.report:
        report(args.root, args.case)
    elif args.case == 'prepare':
        prepare(args.root, native=args.native)
    else:
        raise SystemExit(invoke(args.root, args.case))
