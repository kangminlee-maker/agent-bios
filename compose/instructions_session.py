"""Per-call instructions delivery and durable host-session bindings.

Native homes stay native. The only files this module writes are private activation
records and pins; no global instructions, auth, or discovery registration is copied.
"""
from __future__ import annotations
try:
    from host_platform import codex_protocol_for, sync_directory, cli_argv
except ImportError:
    from .host_platform import codex_protocol_for, sync_directory, cli_argv

import hashlib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
import unicodedata

# What a Codex activation's `rollout_method` says when it tried to resolve the rollout the host
# writes and could not. A pin that carries no rollout keys at all was written before this binding
# existed, which is a different fact and must never share this name.
ROLLOUT_UNRESOLVED = 'rollout_unresolved'


class SessionError(RuntimeError):
    pass


def validate_working_directory_argv(host, argv):
    """Keep a private Codex snapshot and its native session in the same directory."""
    if host != 'codex':
        return
    if not isinstance(argv, (list, tuple)) or not all(isinstance(token, str) for token in argv):
        raise SessionError('private Codex activation requires a valid argument list')
    for token in argv:
        if token == '--':
            break
        if token == '--cd' or token.startswith('--cd=') or token.startswith('-C'):
            raise SessionError(
                'private Codex instructions activation cannot include --cd/-C: the selected instructions and '
                'session pin use the launch working directory. cd into the target directory first, '
                'then start a new activated session without a working-directory override'
            )


def _global_instruction_choice(host, include_global_instructions):
    if type(include_global_instructions) is not bool:
        raise SessionError('include_global_instructions must be a boolean')
    if not include_global_instructions and host != 'claude':
        raise SessionError(
            'excluding global instruction files is not supported by the current Codex adapter; '
            'keep global instructions included. The native CLI has no selective source control, '
            'and the OS-level workaround interferes with its execution sandbox'
        )
    return include_global_instructions


def _claude_global_instruction_patterns(env, cwd, check_paths=True):
    """Match Claude's user-scope lookup without redirecting its configuration home."""
    configured = env.get('CLAUDE_CONFIG_DIR')
    if configured is None:
        home = env.get('HOME')
        if home is None:
            import pwd
            home = pwd.getpwuid(os.getuid()).pw_dir
        if not isinstance(home, str) or not home or not pathlib.Path(home).is_absolute():
            raise SessionError('global instruction exclusion requires an absolute native home; keep inclusion enabled')
        configured = str(pathlib.Path(home) / '.claude')
    if not isinstance(configured, str) or not configured or not pathlib.Path(configured).is_absolute():
        raise SessionError(
            'global instruction exclusion does not support an empty or relative CLAUDE_CONFIG_DIR; '
            'keep inclusion enabled without changing the existing login/configuration identity'
        )
    path = pathlib.Path(os.path.normpath(unicodedata.normalize('NFC', configured))) / 'CLAUDE.md'
    # Claude's exclusion API uses globs and adds resolved-path variants. Restrict
    # the adapter to literal, unambiguous roots so it cannot exclude project files.
    if any(char in str(path) for char in '*?[]{}()!+@|\\'):
        raise SessionError('global instruction exclusion does not support glob metacharacters in the config path; keep inclusion enabled')
    rules = path.parent / 'rules'
    if check_paths:
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise SessionError('global instruction exclusion does not support a symlinked global instruction path; keep inclusion enabled')
        if rules.is_symlink() or (rules.is_dir() and any(member.is_symlink() for member in rules.rglob('*'))):
            raise SessionError('global instruction exclusion does not support symlinked user rules; keep inclusion enabled')
        directory = pathlib.Path(cwd).resolve()
        parents = (directory, *directory.parents)
        project_root = next((parent for parent in parents if (parent / '.git').exists()), directory)
        for parent in parents:
            for relative in ('CLAUDE.md', 'CLAUDE.local.md', '.claude/CLAUDE.md'):
                project = parent / relative
                if project == path:
                    if directory.is_relative_to(path.parent) or path.is_relative_to(project_root):
                        raise SessionError(f'global instructions also belong to this project: {path}; keep inclusion enabled')
                elif project.is_file() and (
                    (path.is_file() and project.samefile(path)) or project.resolve().is_relative_to(rules)
                ):
                    raise SessionError(f'global and project instructions refer to the same file: {project}; keep inclusion enabled')
    # User rules are a separate native instruction source, not imports of CLAUDE.md.
    return [str(path), str(rules) + '/**']


def _claude_exclusion_version(command, cwd, env):
    try:
        result = subprocess.run([command, '--version'], cwd=cwd, env=env, input='',
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SessionError('could not verify Claude support for global instruction exclusion; keep inclusion enabled') from exc
    version = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:\s|$)', result.stdout.strip())
    if result.returncode or version is None or tuple(map(int, version.groups())) < (2, 1, 263):
        raise SessionError('global instruction exclusion requires Claude Code 2.1.263 or newer; keep inclusion enabled')


def _settings_values(argv):
    if not isinstance(argv, (list, tuple)) or not all(isinstance(token, str) for token in argv):
        raise SessionError('global instruction exclusion requires a valid argument list')
    options = argv[:argv.index('--')] if '--' in argv else argv
    values = []
    for index, token in enumerate(options):
        if token == '--settings':
            values.append(options[index + 1] if index + 1 < len(options) else None)
        elif token.startswith('--settings='):
            values.append(token.split('=', 1)[1])
    return values


def _record_instruction_choice(record, env, check_paths=True):
    validate_working_directory_argv(record['host'], record.get('argv'))
    include = _global_instruction_choice(record['host'], record.get('include_global_instructions', True))
    if not include:
        values = _settings_values(record['argv'])
        expected = {'claudeMdExcludes': _claude_global_instruction_patterns(env, record['cwd'], check_paths)}
        try:
            valid = len(values) == 1 and json.loads(values[0]) == expected
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise SessionError('session pin does not carry its declared global instruction exclusion; start a new session')
    return include


def atomic_json(path, data):
    path = pathlib.Path(path)
    if path.parent.is_symlink():
        raise SessionError(f"refusing symlink directory: {path.parent}")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise SessionError(f"refusing symlink: {path}")
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with open(tmp, 'x', encoding='utf-8', newline='\n') as out:
            os.chmod(tmp, 0o600)
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
        sync_directory(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


def raise_on_termination():
    """For the launcher, before it composes or resumes a session: a SIGTERM or SIGHUP that arrives while
    a CodexServer is open ends the server's process group before the launcher ends by that signal, and
    one that arrives at any other time ends the launcher as before (codex_protocol.raise_on_termination)."""
    codex_protocol_for(__file__).raise_on_termination()


def _no_server_running():
    """Refuse to open the user's session while a Codex app-server this process started is unreaped. The
    launcher's SIGTERM and SIGHUP end the process at once only while it owns no such server, and the
    session must see them so (codex_protocol.raise_on_termination): a server left open would turn them
    into an exception that subprocess.call answers by killing the session."""
    left = codex_protocol_for(__file__).unreaped()
    if left:
        raise SessionError(f"a Codex app-server this launch started is still running (process "
                           f"{', '.join(str(pid) for pid in left)}), so the session does not start")


class CodexServer:
    """One owned stdio server. No turn/start or model generation is used.

    Before it starts, the installed Codex's generated protocol schema must carry every name the
    session code uses (wrappers/codex_protocol.py, D-20261102-d8310f); the verdict is kept under the
    state root when the caller names one. Every result is checked for the shape its reader expects."""

    def __init__(self, command, config_args=(), cwd=None, env=None, state_root=None):
        self.command, self.config_args, self.cwd, self.env = command, config_args, cwd, env
        self.state_root = state_root
        self.protocol = codex_protocol_for(__file__)

    def __enter__(self):
        cache = pathlib.Path(self.state_root) / 'codex-protocol' if self.state_root is not None else None
        try:
            self.protocol.ensure_schema(self.command, self.env, cache)
        except self.protocol.ProtocolError as exc:
            raise SessionError(str(exc)) from exc
        self.client = self.protocol.Client([self.command, *self.config_args, 'app-server', '--stdio'],
                                           cwd=self.cwd, env=self.env)
        try:
            self.call('initialize', {'clientInfo': {'name': 'agent-bios', 'version': '1'},
                                     'capabilities': {'experimentalApi': True}})
            self.client.notify('initialized')
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def call(self, method, params, timeout=45):
        try:
            return self.protocol.check_result(method, self.client.call(method, params, timeout))
        except self.protocol.ProtocolError as exc:
            raise SessionError(str(exc)) from exc

    def __exit__(self, *unused):
        self.client.close()


def config_flags(argv, exclude_developer=False):
    argv = argv[:argv.index('--')] if '--' in argv else argv
    result = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in ('--enable', '--disable'):
            if index + 1 >= len(argv):
                raise SessionError(f"missing value for {token}")
            result += ['-c', f"features.{argv[index + 1]}={'true' if token == '--enable' else 'false'}"]
            index += 2
            continue
        if token.startswith(('--enable=', '--disable=')):
            name, feature = token.split('=', 1)
            result += ['-c', f"features.{feature}={'true' if name == '--enable' else 'false'}"]
        if token in ('-c', '--config'):
            if index + 1 >= len(argv):
                raise SessionError(f"missing value for {token}")
            value = argv[index + 1]
            if not (exclude_developer and value.split('=', 1)[0] == 'developer_instructions'):
                result += ['-c', value]
            index += 2
            continue
        if token.startswith('--config='):
            value = token[len('--config='):]
            if not (exclude_developer and value.split('=', 1)[0] == 'developer_instructions'):
                result += ['-c', value]
        if token in ('-p', '--profile') and index + 1 < len(argv):
            result += ['--profile', argv[index + 1]]
            index += 1
        if token.startswith('--profile='):
            result += ['--profile', token.split('=', 1)[1]]
        index += 1
    return result


def named_profile(argv):
    """Return the one native profile requested by a Codex argv, if any.

    Profiles are a top-level Codex runtime feature.  The app-server used below
    for ``config/read`` deliberately has no profile input, so treating a
    profile as ``-c profile=...`` either changes its meaning or makes the
    server reject the request.  Keep this parser narrow and fail before a host
    process is started rather than silently reading the base configuration.
    """
    profile = None
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in ('-p', '--profile'):
            if index + 1 >= len(argv):
                raise SessionError(f'missing value for {token}')
            value = argv[index + 1]
            index += 2
        elif token.startswith('--profile='):
            value = token.split('=', 1)[1]
            index += 1
        else:
            index += 1
            continue
        if not value:
            raise SessionError('invalid empty Codex profile')
        if profile is not None and profile != value:
            raise SessionError('multiple Codex profiles are not supported')
        profile = value
    return profile


def replace_developer(argv, text):
    boundary = argv.index('--') if '--' in argv else len(argv)
    argv, tail = argv[:boundary], argv[boundary:]
    result, index = [], 0
    while index < len(argv):
        token = argv[index]
        if token in ('-c', '--config') and index + 1 < len(argv):
            if argv[index + 1].split('=', 1)[0] == 'developer_instructions':
                index += 2
                continue
        if token.startswith('--config=developer_instructions='):
            index += 1
            continue
        result.append(token)
        index += 1
    return [*result, '-c', 'developer_instructions=' + json.dumps(text), *tail]


def instruction_value(argv, host):
    argv = list(argv[:argv.index('--')]) if '--' in argv else argv
    if host == 'claude':
        values = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == '--append-system-prompt']
        return '\n\n'.join(values)
    for i, a in enumerate(argv[:-1]):
        if a in ('-c', '--config') and argv[i + 1].startswith('developer_instructions='):
            return json.loads(argv[i + 1].split('=', 1)[1])
    return ''


def _native_assets(snapshot):
    assets = snapshot.get('assets') or {}
    if not isinstance(assets, dict) or set(assets) - {'claude_plugins', 'codex_hooks'}:
        raise SessionError('invalid native snapshot assets')
    return assets


def _claude_plugin_paths(snapshot):
    assets = _native_assets(snapshot)
    values = assets.get('claude_plugins', [])
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise SessionError('invalid native plugin paths')
    if not values:
        return []
    root = pathlib.Path(snapshot['path']).resolve()
    result = []
    for value in values:
        relative = pathlib.PurePosixPath(value)
        if relative.is_absolute() or '..' in relative.parts or relative.as_posix() != value:
            raise SessionError('native plugin is outside the pinned snapshot')
        path = root / relative
        if not path.resolve().is_relative_to(root) or path == root:
            raise SessionError('native plugin is outside the pinned snapshot')
        result.append(str(path))
    if len(result) != len(set(result)):
        raise SessionError('duplicate native plugin')
    return result


def _codex_hook_config(snapshot):
    from instructions_catalog import CatalogError, validate_native_hook_config
    hooks = _native_assets(snapshot).get('codex_hooks', {})
    try:
        validate_native_hook_config(hooks, 'codex')
    except CatalogError as exc:
        raise SessionError(f'invalid native snapshot hooks: {exc}') from exc
    return hooks


def _toml_value(value):
    """Serialize the JSON values used by hook config as TOML inline values."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return '[' + ', '.join(_toml_value(item) for item in value) + ']'
    if isinstance(value, dict):
        return '{' + ', '.join(_toml_value(key) + ' = ' + _toml_value(item)
                               for key, item in value.items()) + '}'
    raise SessionError('hook config contains a value that TOML cannot represent')


def _with_codex_hooks(argv, hooks, config):
    if not hooks:
        return argv
    # Codex loads every config layer's hooks independently. Copy only existing
    # session-flag groups; copying effective user/project groups would run them twice.
    layers = config.get('layers')
    if not isinstance(layers, list):
        raise SessionError('Codex native hooks require config/read layer provenance')
    session_layers = [layer for layer in layers if layer.get('name', {}).get('type') == 'sessionFlags']
    if len(session_layers) > 1:
        raise SessionError('Codex reported ambiguous session hook configuration')
    existing = session_layers[0].get('config', {}).get('hooks', {}) if session_layers else {}
    if not isinstance(existing, dict):
        raise SessionError('Codex session hooks are not an event mapping')
    flags = []
    for event, groups in sorted(hooks.items()):
        prior = existing.get(event, [])
        if not isinstance(prior, list):
            raise SessionError(f'Codex session hooks.{event} is not a matcher list')
        flags += ['-c', f'hooks.{event}={_toml_value(prior + groups)}']
    boundary = argv.index('--') if '--' in argv else len(argv)
    return [*argv[:boundary], *flags, *argv[boundary:]]


def validate_codex_hooks(command, snapshot, argv, cwd, env, state_root=None):
    """Prove discovery on this runtime; preserve native enablement and trust."""
    hooks = _codex_hook_config(snapshot)
    if not hooks:
        return
    expected = {(event[0].lower() + event[1:], group['matcher'], handler['command'])
                for event, groups in hooks.items() for group in groups for handler in group['hooks']}
    with CodexServer(command, config_flags(argv), cwd, env, state_root) as server:
        result = server.call('hooks/list', {'cwds': [str(cwd)]})
        config = server.call('config/read', {'cwd': str(cwd), 'includeLayers': False})
    rows = result.get('data')
    if not isinstance(rows, list) or len(rows) != 1 or rows[0].get('errors'):
        raise SessionError('Codex could not discover the selected session hooks')
    found = {(row.get('eventName'), row.get('matcher'), row.get('command')): row
             for row in rows[0].get('hooks', []) if row.get('source') == 'sessionFlags'}
    if not expected.issubset(found):
        raise SessionError('Codex did not discover every selected session hook; check host hook policy and runtime support')
    if config.get('config', {}).get('features', {}).get('hooks') is False:
        print('agent-bios: selected Codex hooks are disabled by the effective native hooks feature setting.', file=sys.stderr)
    pending = sum(not found[key].get('enabled') or found[key].get('trustStatus') != 'trusted'
                  for key in expected)
    if pending:
        print(f'agent-bios: {pending} selected Codex hook(s) need native review or enablement; '
              'open /hooks in this session. Registration does not establish execution.', file=sys.stderr)


def validate_claude_plugins(command, snapshot, cwd, env):
    """Native validation is manifest-only; assert actual carriers separately."""
    for raw in _claude_plugin_paths(snapshot):
        root = pathlib.Path(raw)
        agents = list((root / 'agents').glob('*.md'))
        hooks = root / 'hooks/hooks.json'
        if bool(agents) == hooks.is_file():
            raise SessionError('native item plugin must have one agent or hook carrier')
        if agents and len(agents) != 1:
            raise SessionError('native item plugin has unexpected agents')
        completed = subprocess.run([command, 'plugin', 'validate', '--json', str(root)],
                                   cwd=cwd, env=env, input='', capture_output=True, text=True, timeout=30)
        try:
            result = json.loads(completed.stdout)
        except ValueError as exc:
            raise SessionError('Claude must support plugin validate --json for native instructions activation') from exc
        manifest = result.get('manifest') if isinstance(result, dict) else None
        if completed.returncode or not isinstance(result, dict) or result.get('success') is not True or not isinstance(manifest, dict) or manifest.get('errors') != []:
            raise SessionError(f'Claude rejected native instructions plugin {root.name}: {completed.stdout[-1500:]}')
        for warning in manifest.get('warnings', []):
            print(f"agent-bios: native plugin warning: {warning.get('message', warning)}", file=sys.stderr)


def _verified_launch_snapshot(state_root, snapshot):
    from instructions_store import verify_snapshot
    ref = snapshot.get('content_ref')
    if not isinstance(ref, str) or not re.fullmatch('[0-9a-f]{64}', ref):
        raise SessionError('invalid instructions content ref')
    root = pathlib.Path(state_root) / 'sessions/snapshots' / ref
    if pathlib.Path(snapshot.get('path', '')).resolve() != root.resolve():
        raise SessionError('activation snapshot is not owned by this private store')
    verified = verify_snapshot(root, ref)
    return {**verified['output'], 'path': str(root), 'content_ref': ref,
            'assets': verified['output'].get('assets', {})}


def compose_argv(command, argv, host, snapshot, cwd=None, env=None, include_global_instructions=True, state_root=None):
    """Preserve native instructions before the selected instructions and launch contract."""
    validate_working_directory_argv(host, argv)
    _global_instruction_choice(host, include_global_instructions)
    native_env = dict(os.environ if env is None else env)
    native_cwd = pathlib.Path(cwd or pathlib.Path.cwd()).resolve()
    exclusion = []
    if not include_global_instructions:
        if _settings_values(argv):
            raise SessionError(
                'global instruction exclusion cannot be combined with an existing --settings argument: '
                'Claude would replace it; keep inclusion enabled to preserve those settings'
            )
        patterns = _claude_global_instruction_patterns(native_env, native_cwd)
        _claude_exclusion_version(command, native_cwd, native_env)
        exclusion = ['--settings', json.dumps({'claudeMdExcludes': patterns}, ensure_ascii=False)]
    content = snapshot['instruction_text']
    contract = instruction_value(argv, host)
    if host == 'codex':
        profile = named_profile(argv)
        if profile is not None:
            raise SessionError(
                f'named Codex profile {profile!r} cannot be used with private instructions activation: '
                'the native app-server config/read route does not accept --profile, so its '
                'effective developer instructions cannot be read without rebuilding native '
                'profile semantics'
            )
        hooks = _codex_hook_config(snapshot)
        with CodexServer(command, config_flags(argv, exclude_developer=True), cwd, env, state_root) as server:
            config = server.call('config/read', {'cwd': str(cwd or pathlib.Path.cwd()), 'includeLayers': True})
        # Held to the layers that state it (D-20261102-efc529): null and "" are the user's none and
        # empty value; an omitted key, or a value the layers do not give, refuses by name.
        try:
            native = server.protocol.developer_instructions(config)
        except server.protocol.ProtocolError as exc:
            raise SessionError(str(exc)) from exc
        result = replace_developer(argv, '\n\n'.join(x for x in (native, content, contract) if x))
        return _with_codex_hooks(result, hooks, config)
    boundary = argv.index('--') if '--' in argv else len(argv)
    options, tail = argv[:boundary], argv[boundary:]
    result, index = [], 0
    while index < len(options):
        if options[index] == '--append-system-prompt':
            index += 2
        else:
            result.append(options[index])
            index += 1
    for path in _claude_plugin_paths(snapshot):
        result += ['--plugin-dir', path]
    return [*result, *exclusion, '--append-system-prompt', '\n\n'.join(x for x in (content, contract) if x), *tail]


def session_paths(state_root):
    root = pathlib.Path(state_root)
    for relative in ('', 'runtime', 'runtime/activations', 'sessions', 'sessions/pins',
                     'sessions/pins/codex', 'sessions/pins/claude', 'sessions/snapshots'):
        if (root / relative).is_symlink():
            raise SessionError(f'refusing symlink state directory: {root / relative}')
    return root / 'runtime' / 'activations', root / 'sessions' / 'pins'


def validate_session_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{3,127}', value):
        raise SessionError('invalid host session id')
    return value


def native_home(host, env, cwd=None):
    key, default = ('CODEX_HOME', '.codex') if host == 'codex' else ('CLAUDE_CONFIG_DIR', '.claude')
    base = pathlib.Path(cwd or pathlib.Path.cwd())
    configured = env.get(key)
    if configured:
        path = pathlib.Path(configured)
    else:
        home = pathlib.Path(env.get('HOME', str(pathlib.Path.home())))
        path = home / default
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def environment_provenance(host, env):
    """Capture only the native-home representation, never credential contents."""
    if host not in ('codex', 'claude'):
        raise SessionError('unknown host')
    key = 'CODEX_HOME' if host == 'codex' else 'CLAUDE_CONFIG_DIR'
    value = env.get(key)
    if key in env and not isinstance(value, str):
        raise SessionError(f'invalid {key} environment value')
    variables = {key: {'state': 'set', 'value': value} if key in env else {'state': 'unset'}}
    # HOME affects a native default when the host variable is absent or empty.
    if value in (None, ''):
        home = env.get('HOME')
        if 'HOME' in env and not isinstance(home, str):
            raise SessionError('invalid HOME environment value')
        variables['HOME'] = {'state': 'set', 'value': home} if 'HOME' in env else {'state': 'unset'}
    return {'schema_version': 1, 'variables': variables}


def restore_environment(record, env):
    """Restore an exact captured set/unset native-home representation."""
    host = record.get('host')
    key = 'CODEX_HOME' if host == 'codex' else 'CLAUDE_CONFIG_DIR' if host == 'claude' else None
    provenance = record.get('environment')
    if key is None or not isinstance(provenance, dict) or set(provenance) != {'schema_version', 'variables'} or type(provenance.get('schema_version')) is not int or provenance['schema_version'] != 1:
        raise SessionError('pin lacks environment provenance; start a new activated session or run an explicit future migration')
    variables = provenance.get('variables')
    if not isinstance(variables, dict) or key not in variables:
        raise SessionError('pin has invalid environment provenance; start a new activated session or run an explicit future migration')
    host_entry = variables[key]
    if not isinstance(host_entry, dict):
        raise SessionError('pin has invalid native-home environment entry')
    needs_home = host_entry.get('state') == 'unset' or host_entry.get('value') == ''
    if set(variables) != ({key, 'HOME'} if needs_home else {key}):
        raise SessionError('pin has incomplete or unknown native-home environment entries')
    restored = dict(env)
    for name in (key, 'HOME'):
        if name not in variables:
            continue
        entry = variables[name]
        if not isinstance(entry, dict) or set(entry) - {'state', 'value'} or entry.get('state') not in {'set', 'unset'}:
            raise SessionError('pin has invalid environment provenance; start a new activated session or run an explicit future migration')
        if entry['state'] == 'unset':
            if 'value' in entry:
                raise SessionError('pin has invalid environment provenance; start a new activated session or run an explicit future migration')
            restored.pop(name, None)
        elif not isinstance(entry.get('value'), str):
            raise SessionError('pin has invalid environment provenance; start a new activated session or run an explicit future migration')
        else:
            restored[name] = entry['value']
    return restored


def prepare(state_root, host, snapshot, argv, cwd=None, env=None, include_global_instructions=True):
    if host not in ('codex', 'claude'):
        raise SessionError('unknown host')
    _global_instruction_choice(host, include_global_instructions)
    intents, _ = session_paths(state_root)
    cwd = pathlib.Path(cwd or pathlib.Path.cwd()).resolve()
    intent_id = uuid.uuid4().hex
    record = {'schema_version': 1, 'intent_id': intent_id, 'state': 'PREPARED',
              'host': host, 'content_ref': snapshot['content_ref'], 'snapshot_path': str(snapshot['path']),
              'config_home': str(native_home(host, os.environ if env is None else env, cwd)),
              'environment': environment_provenance(host, os.environ if env is None else env),
              'include_global_instructions': include_global_instructions,
              'argv': list(argv), 'cwd': str(cwd or pathlib.Path.cwd()), 'created': time.time()}
    _record_instruction_choice(record, dict(os.environ if env is None else env))
    atomic_json(intents / intent_id / 'journal.json', record)
    return record


def recorded_cwd(record):
    value = record.get('cwd')
    if not isinstance(value, str) or not pathlib.Path(value).is_absolute():
        raise SessionError('session pin lacks an absolute working directory; start a new activated session')
    try:
        canonical = str(pathlib.Path(value).resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise SessionError('session working directory cannot be resolved') from exc
    if canonical != value:
        raise SessionError('session working directory is no longer canonical; start a new activated session')
    return value


def resolve_codex_rollout(state_root, host_id, thread, env):
    """The rollout file the Codex CLI writes for this thread: `{'path', 'id', 'how'}`, or None.

    Without this, a pin named only by the app-server's thread id names no transcript a reader can find,
    and a session's selection and delivery can only ever be reported unknown — measured over the
    owner's state on 2026-10-23: 15 pins, 2,631 rollouts, 0 joins.

    Order (lead, 2026-11-11, from the measurement under a temporary CODEX_HOME): `thread.path` first,
    because with the installed host it IS the rollout and no file has to be read to say so; the host's
    thread index second, for a host that gives no usable path; `rollout_unresolved` last, naming both
    attempts. A time-window or cwd match is ruled out at every step: a wrong join attributes one
    session's delivered bytes to another, which is worse than unknown, and nothing in the data tells a
    right guess from a wrong one.

    `rollout_id` is taken from the file NAME, never by reading the rollout: an activation that read the
    file would be reading the host's transcript to write its own pin. The census keeps its own rule
    (the first record's `session_meta.id`, else the name), so a census id that differs from the pinned
    one — a fork, a rename — is a named reason there rather than a silent miss here.
    """
    rejected = []
    # (1) The path the thread itself returned, and (2) the host's index row for exactly this thread id.
    # BOTH go through the same test, because the index gives a path and nothing more: a path alone is not
    # an association (X r1 F2), and neither is a name inside a directory that only looks like the
    # configured home (X r2 F6).
    for step, candidate in (('thread.path', (thread or {}).get('path')),
                            ('index', codex_index_rollout(env, host_id))):
        accepted, why = _rollout_of_thread(candidate, host_id, env)
        if accepted:
            return {**accepted, 'how': step}
        rejected.append(f'{step}: {why}')
    print('agent-bios: no rollout resolved for this Codex thread; its pin records no transcript. '
          + '; '.join(rejected), file=sys.stderr)
    return None


def _rollout_of_thread(path, host_id, env):
    """`({'path', 'id'}, None)` when `path` is PROVABLY this thread's rollout inside the configured
    home, else `(None, why not)`.

    Four things are asked, and each was a way in that the first realization left open:
    the file exists and is named as a rollout; it lies inside the *resolved* configured home's sessions
    tree, reached through a sessions root that resolves to that home's own (a `sessions` symlink
    otherwise makes any foreign tree the boundary); it has exactly one link, since a hard link makes one
    file two threads' with nothing on disk to tell them apart; and its name carries exactly one id,
    which is this thread's, compared without case because a uuid is the same id in either case.

    The last check is applied to the index row too. The row IS an association, but it carries only a
    path, so a row naming a fork-shaped file costs this resolution a miss — the safe direction, since a
    wrong join attributes one session's delivered bytes to another.
    """
    found = rollout_identity(path)
    if found is None:
        return None, 'no existing rollout file was named'
    resolved, ids = found
    home = native_home('codex', env or {})
    try:
        sessions = (home / 'sessions')
        anchored = sessions.resolve() == (home.resolve() / 'sessions')
        links = pathlib.Path(resolved).stat().st_nlink
    except OSError as problem:
        return None, f'its home or the file could not be read ({type(problem).__name__})'
    if not anchored:
        return None, "the configured home's sessions root resolves elsewhere, so it bounds nothing"
    if not _under(resolved, sessions):
        return None, 'it resolves outside the configured home'
    if links > 1:
        return None, f'it has {links} links, so which thread it belongs to is not decided'
    if len(ids) != 1:
        return None, f'its name carries {len(ids)} ids, so which thread it belongs to is not decided'
    if ids[0].lower() != str(host_id).lower():
        return None, "its name is another thread's id"
    return {'path': resolved, 'id': ids[0]}, None


# A rollout as the host names it on disk.  Declared here and not imported: the reader that owns this
# shape (session distill's `runlib/sources.py`) is author-side and the payload may not depend on it.
ROLLOUT_NAME = re.compile(r'^rollout-.*\.jsonl(\.zst)?$')
ROLLOUT_UUID = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')


def rollout_identity(path):
    """`(resolved path, [ids its name carries])` when `path` names an existing rollout file, else None.

    Every id in the name is returned, not just one: a fork is written as two ids in one name, and
    which thread such a file belongs to is for the caller to decide rather than for this to guess.
    The comparison is by resolved path because a temporary or linked home answers through a symlink
    (macOS `/var` is one), and an unresolved string compares unequal to the same file.
    """
    if not isinstance(path, str) or not path:
        return None
    try:
        here = pathlib.Path(path).resolve()
    except OSError:
        return None
    if not ROLLOUT_NAME.match(here.name) or not here.is_file():
        return None
    found = ROLLOUT_UUID.findall(here.name)
    return (str(here), found) if found else None


def _under(path, directory):
    """Is `path` (already resolved) inside `directory`, comparing both as the filesystem resolves them?"""
    try:
        return pathlib.Path(path).resolve().is_relative_to(pathlib.Path(directory).resolve())
    except OSError:
        return False


STATE_DATABASE = re.compile(r'^state_(\d+)\.sqlite$')


def codex_state_databases(home):
    """The host's thread databases, the highest version first.

    The version is PARSED, not sorted as text: `state_9.sqlite` sorts after `state_10.sqlite`
    lexically, which would have read provenance out of an older store (X r1 F7).
    """
    found = []
    for path in home.glob('state_*.sqlite') if home.is_dir() else []:
        match = STATE_DATABASE.match(path.name)
        if match and path.is_file() and not path.is_symlink():
            found.append((int(match.group(1)), path))
    return [path for _version, path in sorted(found, key=lambda row: row[0], reverse=True)]


def codex_index_rollout(env, host_id):
    """The `rollout_path` the host's own thread index holds for this thread id, or None.

    The index is read from a COPY. A read-only sqlite open of a live WAL database still moves the
    host's `-shm` file, and this module writes nothing outside its own activation records and pins, so
    the database and its sidecars are copied into a temporary directory and the copy is opened. A copy
    taken while the host writes can be a moment old; that costs this resolution a miss, never a wrong
    join, and the miss is reported as `rollout_unresolved`.
    """
    home = native_home('codex', env or {})
    for database in codex_state_databases(home):
        with tempfile.TemporaryDirectory(prefix='agent-bios-threads-') as scratch:
            copy = pathlib.Path(scratch) / database.name
            try:
                for part in (database, *(database.with_name(database.name + suffix) for suffix in ('-wal', '-shm'))):
                    if part.is_file() and not part.is_symlink():
                        shutil.copy2(part, pathlib.Path(scratch) / part.name)
                connection = sqlite3.connect(f'file:{copy}?mode=ro', uri=True, timeout=5)
            except (OSError, sqlite3.Error):
                continue              # a database this process cannot read says nothing, so the next is asked
            try:
                if not connection.execute("select name from sqlite_master where type='table' "
                                          "and name='threads'").fetchone():
                    continue
                row = connection.execute('select rollout_path from threads where id = ?', (host_id,)).fetchone()
            except sqlite3.Error:
                continue
            finally:
                connection.close()
            # The highest version this process could READ is the authority, whether or not it holds the
            # thread: an older store's row for a thread the current one does not list is a stale
            # association, and reading it resurrected one (X r2 F7).
            return row[0] if row and isinstance(row[0], str) else None
    return None


def pin_codex_rollout(record, rollout):
    """Record on the activation what rollout it resolved, and how — null fields when it resolved none.

    The keys are always written for a Codex activation, because their ABSENCE is what tells a reader
    that a pin predates this binding, and their presence with null values that the activation tried.
    """
    record['rollout_path'] = (rollout or {}).get('path')
    record['rollout_id'] = (rollout or {}).get('id')
    record['rollout_method'] = (rollout or {}).get('how') or ROLLOUT_UNRESOLVED
    return record


def observe_and_pin(state_root, record, host_id, evidence):
    if not isinstance(record.get('intent_id'), str) or not re.fullmatch('[0-9a-f]{32}', record['intent_id']):
        raise SessionError('invalid activation journal identity')
    recorded_cwd(record)
    native_env = restore_environment(record, {})
    _record_instruction_choice(record, native_env, check_paths=False)
    host_id = validate_session_id(host_id)
    intents, pins = session_paths(state_root)
    pin_path = pins / record['host'] / f'{host_id}.json'
    if pin_path.exists():
        existing = read_pin(state_root, record['host'], host_id)
        if existing['intent_id'] != record['intent_id'] or existing['content_ref'] != record['content_ref']:
            raise SessionError('host session already belongs to a different instructions activation')
    record.update(state='HOST_OBSERVED', session_id=host_id, evidence=evidence)
    atomic_json(intents / record['intent_id'] / 'journal.json', record)
    atomic_json(pin_path, record)
    record['state'] = 'PINNED'
    atomic_json(intents / record['intent_id'] / 'journal.json', record)
    return record


def read_pin(state_root, host, session_id):
    if host not in ('codex', 'claude'):
        raise SessionError('unknown host')
    session_id = validate_session_id(session_id)
    _, pins = session_paths(state_root)
    path = pins / host / f'{session_id}.json'
    if path.is_symlink() or not path.is_file():
        raise SessionError(f'no instructions pin for {host} session {session_id}')
    record = json.loads(path.read_text())
    if record.get('host') != host or record.get('session_id') != session_id:
        raise SessionError('session pin identity mismatch')
    recorded_cwd(record)
    native_env = restore_environment(record, {})
    _record_instruction_choice(record, native_env, check_paths=False)
    snapshot = pathlib.Path(record['snapshot_path'])
    allowed = (pathlib.Path(state_root) / 'sessions' / 'snapshots').resolve()
    if not snapshot.resolve().is_relative_to(allowed) or snapshot.is_symlink():
        raise SessionError('session pin names an unowned snapshot')
    if not snapshot.is_dir():
        raise SessionError('pinned instructions snapshot missing; recover it before resuming')
    from instructions_store import verify_snapshot
    verify_snapshot(snapshot, record['content_ref'])
    return record


def claude_evidence(record, env):
    requested = record.get('requested_session_id')
    if not requested:
        return None
    validate_session_id(requested)
    home = native_home('claude', restore_environment(record, env), recorded_cwd(record))
    from instructions_store import _reject_symlink_path
    _reject_symlink_path(home / 'projects')
    for trace in (home / 'projects').glob(f'*/{requested}.jsonl'):
        _reject_symlink_path(trace.parent)
        _reject_symlink_path(trace)
        with trace.open(encoding='utf-8') as source:
            for line in source:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict) and event.get('sessionId') == requested:
                    if event.get('cwd') and pathlib.Path(event['cwd']).resolve() != pathlib.Path(record['cwd']).resolve():
                        continue
                    return {'method': 'native-session-log', 'path': str(trace)}
    return None


def recover_activations(state_root, command=None, host=None, env=None):
    """Reconcile exact recorded ids against host evidence; retain unresolved intents."""
    env = dict(os.environ if env is None else env)
    intents, _ = session_paths(state_root)
    result = {'pinned': [], 'pending': []}
    for path in sorted(intents.glob('*/journal.json')):
        if path.is_symlink() or path.parent.is_symlink():
            raise SessionError('symlink activation journal')
        record = json.loads(path.read_text())
        if not isinstance(record, dict) or record.get('intent_id') != path.parent.name or not re.fullmatch('[0-9a-f]{32}', path.parent.name):
            raise SessionError('activation journal identity does not match its owned directory')
        if record.get('state') in ('PREPARED', 'HOST_OBSERVED'):
            try:
                recorded_cwd(record)
                native_env = restore_environment(record, env)
                _record_instruction_choice(record, native_env, check_paths=False)
            except SessionError as exc:
                print(f"agent-bios: activation {record.get('intent_id', path.parent.name)} remains pending: {exc}", file=sys.stderr)
                result['pending'].append(record.get('intent_id', path.parent.name))
                continue
        if record.get('state') == 'HOST_OBSERVED':
            observe_and_pin(state_root, record, record['session_id'], record['evidence'])
            result['pinned'].append(record['session_id'])
        elif record.get('state') == 'PREPARED':
            evidence = None
            requested = record.get('requested_session_id')
            if requested and record['host'] == 'claude':
                try:
                    evidence = claude_evidence(record, env)
                except SessionError as exc:
                    print(f"agent-bios: activation {record.get('intent_id', '?')} remains pending: {exc}", file=sys.stderr)
            elif requested and record['host'] == 'codex' and host == 'codex' and command:
                validate_session_id(requested)
                try:
                    native_env = restore_environment(record, env)
                    with CodexServer(command, config_flags(record['argv']), record['cwd'], native_env, state_root) as server:
                        observed = server.call('thread/read', {'threadId': requested, 'includeTurns': False})
                    if observed.get('thread', {}).get('id') == requested:
                        # A recovered activation resolves the rollout too, or its pin would carry no
                        # rollout keys and read as one written before this binding existed.
                        pin_codex_rollout(record, resolve_codex_rollout(
                            state_root, requested, observed.get('thread', {}), native_env))
                        evidence = {'method': 'recovered-thread/read+' + record['rollout_method']}
                except SessionError as exc:
                    print(f"agent-bios: activation {record['intent_id']} remains pending: {exc}", file=sys.stderr)
            if evidence:
                observe_and_pin(state_root, record, requested, evidence)
                result['pinned'].append(requested)
            else:
                result['pending'].append(record['intent_id'])
    return result


def create_codex_session(command, argv, state_root, record, cwd, env):
    validate_working_directory_argv('codex', argv)
    with CodexServer(command, config_flags(argv), cwd, env, state_root) as server:
        params = {'cwd': str(cwd), 'developerInstructions': instruction_value(argv, 'codex'),
                  'ephemeral': False, 'experimentalRawEvents': False}
        for index, token in enumerate(argv[:-1]):
            if token in ('--model', '-m'):
                params['model'] = argv[index + 1]
        result = server.call('thread/start', params)
        thread = result['thread']
        host_id = validate_session_id(thread['id'])
        # thread/start alone may return an id before persisting a resumable thread.
        # Retain the exact id in PREPARED before recording a small developer item;
        # inject_items persists history without generating a model turn.
        record['requested_session_id'] = host_id
        intents, _ = session_paths(state_root)
        atomic_json(intents / record['intent_id'] / 'journal.json', record)
        server.call('thread/inject_items', {'threadId': host_id, 'items': [
            {'type': 'message', 'role': 'developer', 'content': [
                {'type': 'input_text', 'text': f"agent-bios session snapshot: {record['content_ref']}"}]}]})
    with CodexServer(command, config_flags(argv), cwd, env, state_root) as server:
        persisted = server.call('thread/read', {'threadId': host_id, 'includeTurns': False})
        if persisted.get('thread', {}).get('id') != host_id:
            raise SessionError('host did not persist the requested instructions session')
    pin_codex_rollout(record, resolve_codex_rollout(state_root, host_id, thread, env))
    observe_and_pin(state_root, record, host_id,
                    {'method': 'thread/start+inject_items+read+' + record['rollout_method'],
                     'thread_path': thread.get('path')})
    return host_id


def launch(command, argv, state_root, host, snapshot, cwd=None, env=None, resume_id=None,
           include_global_instructions=True):
    """Start a pinned native session, returning its exit status."""
    validate_working_directory_argv(host, argv)
    cwd = pathlib.Path(cwd or pathlib.Path.cwd()).resolve()
    env = dict(os.environ if env is None else env)
    if resume_id and include_global_instructions is not True:
        raise SessionError('resume uses its recorded global instruction choice; omit the override or start a new session')
    if not resume_id:
        _global_instruction_choice(host, include_global_instructions)
    elif host == 'codex':
        _, pins = session_paths(state_root)
        session_id = validate_session_id(resume_id)
        pin_path = pins / host / f'{session_id}.json'
        if pin_path.exists() or pin_path.is_symlink():
            read_pin(state_root, host, session_id)
    recovered = recover_activations(state_root, command, host, env)
    if recovered['pending']:
        print(f"agent-bios: {len(recovered['pending'])} activation(s) lack host evidence; their snapshots remain retained.", file=sys.stderr)
    if resume_id:
        record = read_pin(state_root, host, resume_id)
        env = restore_environment(record, env)
        if not _record_instruction_choice(record, env):
            _claude_exclusion_version(command, record['cwd'], env)
        pinned = _verified_launch_snapshot(state_root, {'path': record['snapshot_path'], 'content_ref': record['content_ref']})
        if host == 'claude':
            validate_claude_plugins(command, pinned, record['cwd'], env)
        else:
            validate_codex_hooks(command, pinned, record['argv'], record['cwd'], env, state_root)
        argv = record['argv']
        native = ['resume', resume_id, *argv] if host == 'codex' else ['--resume', resume_id, *argv]
        _no_server_running()
        return subprocess.call([command, *native], cwd=record['cwd'], env=env)
    snapshot = _verified_launch_snapshot(state_root, snapshot)
    argv = compose_argv(command, argv, host, snapshot, cwd, env, include_global_instructions, state_root)
    if host == 'codex':
        validate_codex_hooks(command, snapshot, argv, cwd, env, state_root)
    if host == 'claude':
        validate_claude_plugins(command, snapshot, cwd, env)
    record = prepare(state_root, host, snapshot, argv, cwd, env, include_global_instructions)
    if host == 'codex':
        # Create the durable thread before opening the native resume UI. The returned
        # id comes from the real host and is pinned before any user turn is possible.
        create_codex_session(command, argv, state_root, record, cwd, env)
        native = ['resume', record['session_id'], *argv]
        _no_server_running()
        return subprocess.call([command, *native], cwd=cwd, env=env)
    requested_id = str(uuid.uuid4())
    record['requested_session_id'] = requested_id
    intents, _ = session_paths(state_root)
    atomic_json(intents / record['intent_id'] / 'journal.json', record)
    native = ['--session-id', requested_id, *argv]
    _no_server_running()
    child = subprocess.Popen([command, *native], cwd=cwd, env=env)
    try:
        while True:
            if record['state'] == 'PREPARED':
                evidence = claude_evidence(record, env)
                if evidence:
                    observe_and_pin(state_root, record, requested_id, evidence)
            if child.poll() is not None:
                if record['state'] != 'PINNED':
                    print(f"agent-bios: no host session evidence; activation {record['intent_id']} retained for recovery.", file=sys.stderr)
                return child.returncode
            time.sleep(0.15)
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
