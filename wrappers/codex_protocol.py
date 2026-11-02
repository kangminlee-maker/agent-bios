"""The Codex app-server as agent-bios speaks it: one client, the names it uses, and two checks.

The vendor marks the app-server and its schema command experimental, and agent-bios relies on them for
private activation and for codex-run's context evidence (D-20261102-d8310f). So:

- Every method, field and enum value the code sends or reads is listed once, in USED, and checked per
  installed Codex version against the protocol schema that version generates offline
  (`codex app-server generate-json-schema --experimental`). A missing name refuses by name and
  version. The verdict is kept per version under `<state dir>/codex-protocol/` when the caller names
  a state directory, and in the process otherwise.
- Every result the code reads is checked for its shape, in SHAPES, before it is read; a wrong or
  missing shape refuses naming the method and the field. The effective `developer_instructions`
  is read only through developer_instructions(), which holds it to the layers that state it
  (D-20261102-efc529): null is the user's "none", and "" the user's own empty value.
- The client reads the server on a thread into a queue. A select() on the text stream missed a
  line Python had already buffered, so a notification and the response in one write left the
  response unread until the timeout; on POSIX the thread reads the descriptor itself, keeping its
  own partial line, so nothing is buffered where select() cannot see it.
- The server runs in a process group of its own and is ended with that group (Owned), which
  session-distill's dispatcher also uses for its server-policy probe (author-side imports shipped,
  never the reverse).

Loaded by path: beside codex_frame_filter.py, deployed together, and by compose from the package's
wrappers/ directory (host_platform.codex_protocol_for).
"""
from __future__ import annotations

import atexit
import contextlib
import hashlib
import json
import os
import pathlib
import queue
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time


class ProtocolError(Exception):
    """The app-server, its schema, or a result is not what agent-bios was checked against."""


# (method, side, path). A path walks object fields by name, `[]` into array items, and a last
# `=value` names an enum value the code compares against.
USED = (
    ("initialize", "params", "clientInfo.name"),
    ("initialize", "params", "clientInfo.title"),
    ("initialize", "params", "clientInfo.version"),
    ("initialize", "params", "capabilities.experimentalApi"),
    ("hooks/list", "params", "cwds"),
    ("hooks/list", "result", "data[].errors"),
    ("hooks/list", "result", "data[].hooks[].eventName"),
    ("hooks/list", "result", "data[].hooks[].matcher"),
    ("hooks/list", "result", "data[].hooks[].command"),
    ("hooks/list", "result", "data[].hooks[].source=sessionFlags"),
    ("hooks/list", "result", "data[].hooks[].enabled"),
    ("hooks/list", "result", "data[].hooks[].trustStatus=trusted"),
    ("config/read", "params", "cwd"),
    ("config/read", "params", "includeLayers"),
    ("config/read", "result", "config.developer_instructions"),
    ("config/read", "result", "config.features"),
    ("config/read", "result", "layers[].name.type=sessionFlags"),
    ("config/read", "result", "layers[].config"),
    ("thread/start", "params", "cwd"),
    ("thread/start", "params", "developerInstructions"),
    ("thread/start", "params", "ephemeral"),
    ("thread/start", "params", "experimentalRawEvents"),
    ("thread/start", "params", "model"),
    ("thread/start", "params", "approvalPolicy"),
    ("thread/start", "params", "sandbox"),
    ("thread/start", "params", "config"),
    ("thread/start", "result", "thread.id"),
    ("thread/start", "result", "thread.path"),
    ("thread/start", "result", "instructionSources"),
    ("thread/start", "result", "model"),
    ("thread/start", "result", "cwd"),
    ("thread/start", "result", "reasoningEffort"),
    ("thread/inject_items", "params", "threadId"),
    ("thread/inject_items", "params", "items"),
    ("thread/read", "params", "threadId"),
    ("thread/read", "params", "includeTurns"),
    ("thread/read", "result", "thread.id"),
)
USED_DIGEST = hashlib.sha256(json.dumps(USED).encode()).hexdigest()

# Per reading: (path, accepted types, required). A path's `[]` checks every item.
SHAPES = {
    "hooks/list": (
        ("data", "list", True), ("data[]", "dict", True), ("data[].errors", "list", True),
        ("data[].hooks", "list", True), ("data[].hooks[]", "dict", True),
        ("data[].hooks[].eventName", "str", False), ("data[].hooks[].matcher", "str|null", False),
        ("data[].hooks[].command", "str", False), ("data[].hooks[].source", "str", False),
        ("data[].hooks[].enabled", "bool", False), ("data[].hooks[].trustStatus", "str", False),
    ),
    "config/read": (
        ("config", "dict", True), ("config.developer_instructions", "str|null", True),
        ("config.features", "dict", False), ("config.features.hooks", "bool", False),
        ("layers", "list|null", False), ("layers[]", "dict", True), ("layers[].name", "dict", True),
        ("layers[].name.type", "str", True), ("layers[].config", "dict", False),
        ("layers[].config.developer_instructions", "str|null", False),
    ),
    "thread/start": (("thread", "dict", True), ("thread.id", "str", True), ("thread.path", "str|null", False)),
    "thread/start#sources": (
        ("instructionSources", "list", True), ("instructionSources[]", "str", True), ("model", "str", False),
        ("cwd", "str", False), ("reasoningEffort", "str|null", False),
    ),
    "thread/read": (("thread", "dict", True), ("thread.id", "str", True)),
    "thread/inject_items": (),
    "initialize": (),
}
TYPES = {"str": str, "bool": bool, "list": list, "dict": dict, "null": type(None)}


_ABSENT = object()


def _steps(path):
    return [step for part in path.split(".") for step in re.findall(r"[^\[\]]+|\[\]", part)]


def shape_problems(reading, result):
    """What in `result` does not have the shape SHAPES[reading] declares, as "<path>: <problem>"."""
    problems = []

    def walk(value, steps, where, kinds, required):
        if not steps:
            if value is _ABSENT:
                if required:
                    problems.append(f"{where}: missing")
            elif not isinstance(value, tuple(TYPES[k] for k in kinds)) or (isinstance(value, bool) and "bool" not in kinds):
                problems.append(f"{where}: {type(value).__name__}, not {'|'.join(kinds)}")
            return
        if value is _ABSENT or value is None:
            return
        step, rest = steps[0], steps[1:]
        if step == "[]":
            if isinstance(value, list):
                for index, item in enumerate(value):
                    walk(item, rest, f"{where}[{index}]", kinds, required)
        elif isinstance(value, dict):
            walk(value.get(step, _ABSENT), rest, f"{where}.{step}" if where else step, kinds, required)

    if not isinstance(result, dict):
        return [f"result: {type(result).__name__}, not dict"]
    for path, kinds, required in SHAPES[reading]:
        walk(result, _steps(path), "", kinds.split("|"), required)
    return problems


def check_result(method, result, reading=None):
    """Raise ProtocolError naming every field of `result` whose shape is not the declared one. A
    reading SHAPES does not declare is refused too: what the code reads has one owner, here."""
    if (reading or method) not in SHAPES:
        raise ProtocolError(f"app-server {method}: agent-bios declares no shape for {reading or method} "
                            f"(wrappers/codex_protocol.py SHAPES)")
    problems = shape_problems(reading or method, result)
    if problems:
        raise ProtocolError(f"app-server {method} answered in a shape agent-bios does not read: {'; '.join(problems)}")
    return result


def developer_instructions(result):
    """The effective developer instructions a shape-checked config/read `result`, asked with
    includeLayers, states: text, '' for none. Held to the layers (D-20261102-efc529, measured on
    codex-cli 0.163.0: the key is always sent, null when no layer sets it, and the highest layer
    that sets it wins, so a higher layer's "" over a lower layer's text is the user's choice): null
    only when no layer sets a string, a string only when some layer sets that string. Anything else,
    or no layers, refuses by name: an effective value that drops text a layer holds would replace
    the user's developer instructions with nothing. So does a layer that reports no `config` (the
    schema requires one): an unreported configuration is not an empty one, and only a reported
    config without the field says that layer sets none. A layer's `config` is open in the generated
    schema (`true`), so its field is held by SHAPES and this check, not by USED."""
    value = result["config"]["developer_instructions"]
    layers = result.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ProtocolError("app-server config/read: no layers to hold config.developer_instructions to, "
                            "though agent-bios asked for them (includeLayers)")
    unreported = [f"{layer['name']['type']} (layer {index})" for index, layer in enumerate(layers)
                  if not isinstance(layer.get("config"), dict)]
    if unreported:
        raise ProtocolError(f"app-server config/read: the {', '.join(unreported)} layer reported no config, so "
                            f"whether it sets developer_instructions is unknown")
    stated = {}
    for layer in layers:
        held = layer["config"].get("developer_instructions")
        if isinstance(held, str):
            stated.setdefault(held, []).append(layer["name"]["type"])
    if value is None and stated:
        raise ProtocolError(f"app-server config/read: config.developer_instructions is null while the "
                            f"{', '.join(t for types in stated.values() for t in types)} layer(s) set it")
    if isinstance(value, str) and value not in stated:
        raise ProtocolError(f"app-server config/read: config.developer_instructions is a value no layer sets "
                            f"({len(value)} characters; layers setting it: "
                            f"{', '.join(t for types in stated.values() for t in types) or 'none'})")
    return value or ""


def schema_missing(bundle):
    """The USED names the generated schema `bundle` (codex_app_server_protocol.schemas.json, parsed)
    does not carry. A step into an open part of the schema (`true`, or additionalProperties) is not
    a missing name: the schema allows it and names nothing to check."""
    def resolve(ref):
        node = bundle
        for part in ref.lstrip("#/").split("/"):
            node = node[part]
        return node

    def alternatives(node, seen=()):
        if node is True or node == {}:
            return [True]
        if not isinstance(node, dict):
            return []
        if "$ref" in node:
            return [] if node["$ref"] in seen else alternatives(resolve(node["$ref"]), seen + (node["$ref"],))
        found = [node]
        for key in ("anyOf", "oneOf", "allOf"):
            for sub in node.get(key, []):
                found += alternatives(sub, seen)
        return found

    def step(nodes, name):
        nexts = []
        for node in nodes:
            for alt in alternatives(node):
                if alt is True:
                    nexts.append(True)
                elif name == "[]":
                    if "items" in alt:
                        nexts += alternatives(alt["items"])
                elif name in alt.get("properties", {}):
                    nexts += alternatives(alt["properties"][name])
                elif alt.get("additionalProperties") not in (None, False):
                    nexts.append(True)
        return nexts

    requests = {}
    for alt in bundle.get("definitions", {}).get("ClientRequest", {}).get("oneOf", []):
        props = alt.get("properties", {})
        methods = props.get("method", {}).get("enum") or []
        ref = (props.get("params") or {}).get("$ref")
        if methods and ref:
            requests[methods[0]] = ref
    missing = []
    for method, side, path in USED:
        if method not in requests:
            missing.append(f"{method} (method)")
            continue
        ref = requests[method] if side == "params" else re.sub(r"Params$", "Response", requests[method])
        try:
            nodes = [resolve(ref)]
        except (KeyError, TypeError):
            missing.append(f"{method} {side}")
            continue
        steps, value = _steps(path), None
        if "=" in steps[-1]:
            steps[-1], value = steps[-1].split("=", 1)
        for name in steps:
            nodes = step(nodes, name)
        if not nodes:
            missing.append(f"{method} {side} {path}")
        elif value is not None and True not in nodes and not any(
                value in (alt.get("enum") or []) or alt.get("const") == value
                for node in nodes for alt in alternatives(node) if isinstance(alt, dict)):
            missing.append(f"{method} {side} {path}")
    return missing


def fixture_bundle(drop=()):
    """A schema bundle naming exactly USED (less the `drop` entries), in the generated schema's layout:
    what a fake Codex writes for `app-server generate-json-schema`, so a fake can answer the check
    without a vendor schema. The installed Codex's own schema is what decides in use."""
    definitions, requests = {}, []
    for method in dict.fromkeys(m for m, _, _ in USED):
        base = "".join(part[:1].upper() + part[1:] for part in re.split(r"[/_]", method))
        requests.append({"properties": {"method": {"enum": [method]}, "params": {"$ref": f"#/definitions/{base}Params"}}})
        definitions[f"{base}Params"], definitions[f"{base}Response"] = {"type": "object"}, {"type": "object"}
    for method, side, path in USED:
        if (method, side, path) in drop:
            continue
        base = "".join(part[:1].upper() + part[1:] for part in re.split(r"[/_]", method))
        node = definitions[f"{base}{'Params' if side == 'params' else 'Response'}"]
        steps, value = _steps(path), None
        if "=" in steps[-1]:
            steps[-1], value = steps[-1].split("=", 1)
        for step in steps:
            if step == "[]":
                node = node.setdefault("items", {"type": "object"})
            else:
                node = node.setdefault("properties", {}).setdefault(step, {"type": "object"})
        if value is not None:
            node.setdefault("enum", []).append(value)
    definitions["ClientRequest"] = {"oneOf": requests}
    return {"definitions": definitions}


_VERDICTS = {}


def codex_version(codex, env=None, timeout=30):
    """The version `codex --version` names, asked with a scratch CODEX_HOME: even this command
    creates <CODEX_HOME>/tmp, and the check writes nothing into the caller's homes."""
    try:
        with tempfile.TemporaryDirectory(prefix="codex-protocol-") as scratch:
            done = subprocess.run([codex, "--version"], env={**(os.environ if env is None else env), "CODEX_HOME": scratch},
                                  capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProtocolError(f"`{codex} --version` did not run: {exc}") from exc
    version = done.stdout.strip().splitlines()[-1].strip() if done.returncode == 0 and done.stdout.strip() else ""
    if not version:
        raise ProtocolError(f"`{codex} --version` named no version (exit {done.returncode}); agent-bios checks the "
                            f"app-server protocol per Codex version and refuses an unnamed one")
    return version


def ensure_schema(codex, env=None, cache_dir=None, timeout=30):
    """Refuse unless the installed Codex's generated protocol schema carries every USED name. The
    verdict is kept per binary (path, size, modification time), version and USED: in this process,
    and in `cache_dir` when one is given and is a real directory (created inside its parent only)."""
    env = dict(os.environ if env is None else env)
    located = codex if os.sep in str(codex) else shutil.which(codex, path=env.get("PATH"))
    if not located:
        raise ProtocolError(f"no Codex executable named {codex!r} on PATH")
    real = pathlib.Path(located).resolve()
    status = real.stat()
    binary = {"path": str(real), "size": status.st_size, "mtime_ns": status.st_mtime_ns}
    memo = (json.dumps(binary, sort_keys=True), USED_DIGEST)
    if memo in _VERDICTS:
        return _raise_for(_VERDICTS[memo])
    version = codex_version(str(real), env, timeout)
    record_path = None
    if cache_dir is not None:
        cache = pathlib.Path(cache_dir)
        if cache.parent.is_dir() and not cache.parent.is_symlink() and not cache.is_symlink():
            cache.mkdir(mode=0o700, exist_ok=True)
            record_path = cache / (re.sub(r"[^0-9A-Za-z._-]", "_", version) + ".json")
    if record_path is not None and record_path.is_file() and not record_path.is_symlink():
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            record = None
        if (isinstance(record, dict) and record.get("binary") == binary and record.get("used") == USED_DIGEST
                and record.get("version") == version and isinstance(record.get("missing"), list)):
            _VERDICTS[memo] = record
            return _raise_for(record)
    missing, generated = generated_missing(str(real), env, timeout)
    record = {"version": version, "binary": binary, "used": USED_DIGEST, "missing": missing,
              "names": len(USED), "checked_at": time.time()}
    # A schema that could not be generated is not a verdict about the version: it is kept neither in
    # this process nor on disk, so the next check generates again.
    if generated:
        _VERDICTS[memo] = record
    if record_path is not None and generated:
        handle, staged = tempfile.mkstemp(dir=record_path.parent, prefix=".codex-protocol-")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                json.dump(record, out, sort_keys=True)
            os.replace(staged, record_path)
        finally:
            if os.path.exists(staged):
                os.unlink(staged)
    return _raise_for(record)


def generated_missing(codex, env, timeout=30):
    """Generate the version's schema offline into a scratch directory, with a scratch CODEX_HOME (the
    command writes a tmp/ there): (the USED names it lacks, whether a schema was generated at all)."""
    with tempfile.TemporaryDirectory(prefix="codex-protocol-") as scratch:
        out = pathlib.Path(scratch) / "schema"
        home = pathlib.Path(scratch) / "codex-home"
        home.mkdir()
        bundle_path = out / "codex_app_server_protocol.schemas.json"
        try:
            done = subprocess.run([codex, "app-server", "generate-json-schema", "--experimental", "--out", str(out)],
                                  env={**env, "CODEX_HOME": str(home)}, capture_output=True, text=True,
                                  timeout=timeout, stdin=subprocess.DEVNULL)
            code = done.returncode
        except (OSError, subprocess.SubprocessError) as exc:
            code = f"no exit ({exc})"
        if code != 0 or not bundle_path.is_file():
            return [f"the schema itself (`app-server generate-json-schema` exited {code} without "
                    f"{bundle_path.name})"], False
        try:
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        except ValueError:
            return [f"the schema itself ({bundle_path.name} is not JSON)"], False
        return schema_missing(bundle), True


def _raise_for(record):
    if record["missing"]:
        raise ProtocolError(f"Codex {record['version']}'s app-server protocol schema lacks what agent-bios uses: "
                            f"{', '.join(record['missing'])}; this Codex version is not one agent-bios was checked "
                            f"against")
    return record


TICK_S = 0.05      # how often a wait on a child's pipes or on its end looks again
CLOSE_S = 5        # how long a server whose input closed is given to end, and to end after SIGTERM
DRAIN_S = 2        # how long its output is given to close once its group has been ended
_UNREAPED = set()  # every Owned whose child has not been reaped yet
_TERMINATED = []   # the termination signal raise_on_termination turned into Terminated, if any
_INSTALLED = []    # whether raise_on_termination has installed its handler in this process
_CLEANING = [0]    # how many cleanups (Owned.end, Client.close, a collection's end) are running
_NOTED = []        # a termination signal that arrived during a cleanup, raised when the outermost ends


class Terminated(SystemExit):
    """SIGTERM or SIGHUP, raised while this process owns an unreaped child (raise_on_termination), so
    the owner's cleanup ends the child's group on the way out; the process then ends by the signal."""

    def __init__(self, signum):
        super().__init__(128 + signum)
        self.signum = signum


def raise_on_termination():
    """For an entry point that owns children through Owned, called from its main thread: from now on
    SIGTERM and SIGHUP raise Terminated while any Owned child is unreaped, and at exit the process ends
    by the same signal; while none is, they end the process at once, as their default does, so code
    that owns no child (a host session this process waits on, a UI) sees them unchanged. The library
    never installs this itself."""
    if threading.current_thread() is not threading.main_thread() or _INSTALLED:
        return
    _INSTALLED.append(True)

    def handler(signum, _frame):
        if _TERMINATED:
            return  # the first one ends the process once its cleanup is done
        if _CLEANING[0]:
            _NOTED[:] = _NOTED or [signum]  # raised when the cleanup it would have cut short is done
            return
        if not _UNREAPED:
            end_by(signum)
        _TERMINATED.append(signum)
        raise Terminated(signum)
    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, handler)
    atexit.register(lambda: _TERMINATED and end_by(_TERMINATED[0]))


def unreaped():
    """The numbers of the children this process owns through Owned and has not reaped."""
    return sorted(owned.proc.pid for owned in _UNREAPED)


def end_by(signum):
    """End this process by `signum`'s default action, so whoever waits on it sees that signal. What
    Python still buffers is written first, since the default action ends the process at once; a
    terminal that has gone (SIGHUP) refuses the write, which is then given up."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(OSError, ValueError, AttributeError):
            stream.flush()
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


class _Cleanup:
    """A cleanup a termination signal must not cut short: raise_on_termination's handler only notes a
    signal that arrives inside one, and the outermost one raises it when it is done. When another
    exception is already leaving the cleanup, that one goes on, and the process still ends by the noted
    signal at exit."""

    def __enter__(self):
        _CLEANING[0] += 1

    def __exit__(self, exc_type, _exc, _tb):
        _CLEANING[0] -= 1
        if _CLEANING[0] or not _NOTED or _TERMINATED:
            return False
        signum = _NOTED.pop()
        _TERMINATED.append(signum)
        if exc_type is None:
            raise Terminated(signum)
        return False


class Owned:
    """A child started in a session of its own (start_new_session=True), ended with its process group.

    The child's end is watched without reaping it — kqueue's process filter where the platform has
    one, since the Pythons macOS ships lack os.waitid, and waitid(WNOWAIT) elsewhere — and its group
    is signalled before the child is reaped, on every path: until then the child's number, which is
    the group's, belongs to no other process. A child that ended by itself has its group sent SIGKILL,
    which reaches what it left behind in the group; one still running is sent SIGTERM, given its
    grace, then SIGKILL. A process that made a session of its own has left the group and is beyond
    this reach: a pipe it still holds is closed on this side after a bounded drain, never waited for,
    and the caller is told. On Windows there is no group: the child is terminated, then killed, and
    its handle keeps its number until it is waited for."""

    def __init__(self, proc):
        self.proc, self._ended, self._watch = proc, False, None
        self.clock = time.monotonic  # collect's clock; a control gives one that moves between two reads
        _UNREAPED.add(self)
        if os.name != "nt" and hasattr(select, "kqueue"):
            self._watch = select.kqueue()
            try:
                self._watch.control([select.kevent(proc.pid, select.KQ_FILTER_PROC,
                                                   select.KQ_EV_ADD | select.KQ_EV_ONESHOT, select.KQ_NOTE_EXIT)], 0, 0)
            except ProcessLookupError:  # it ended before the watch began: an unreaped child cannot be watched
                self._ended = True

    def ended(self, wait_s=0.0):
        """Whether the child has ended, waiting at most `wait_s`. It is never reaped here."""
        if self._ended or self.proc.returncode is not None:
            return True
        if os.name == "nt":
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.proc.wait(timeout=wait_s)
            return self.proc.returncode is not None
        if self._watch is not None:
            self._ended = bool(self._watch.control(None, 1, max(wait_s, 0)))
            return self._ended
        deadline = time.monotonic() + wait_s
        while os.waitid(os.P_PID, self.proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
            if time.monotonic() >= deadline:
                return False
            time.sleep(TICK_S)
        self._ended = True
        return True

    def end(self, grace_s):
        """End the child's group, then reap the child. Nothing is signalled once the child is reaped,
        SIGKILL is sent even when the wait for SIGTERM is interrupted, and a termination signal waits
        until the child is reaped (_Cleanup)."""
        with _Cleanup():
            self._end(grace_s)

    def _end(self, grace_s):
        if self.proc.returncode is not None:
            _UNREAPED.discard(self)
            return
        if os.name == "nt":
            if not self.ended():
                self.proc.terminate()
                if not self.ended(grace_s):
                    self.proc.kill()
            self.proc.wait()
            _UNREAPED.discard(self)
            return
        try:
            if not self.ended():
                # ESRCH, or EPERM on macOS when the unreaped child is all the group holds: nothing to signal
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(self.proc.pid, signal.SIGTERM)
                    self.ended(grace_s)
        finally:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait()
            _UNREAPED.discard(self)
            if self._watch is not None:
                self._watch.close()

    def collect(self, limit_s, grace_s, drain_s):
        """(stdout, stderr, timed_out, held): the child's piped output, read until every pipe has closed
        and the child has ended, for at most `limit_s`; then its group is ended (end) and the pipes are
        read for at most `drain_s` more. The pipes are closed however the collection ends, an
        interrupted one included. `held` is true when one was still open after the drain, held by a
        process outside the group. POSIX only: Windows pipes cannot be selected."""
        streams = [stream for stream in (self.proc.stdout, self.proc.stderr) if stream is not None]
        fds = [None if stream is None else stream.fileno() for stream in (self.proc.stdout, self.proc.stderr)]
        open_fds = {stream.fileno() for stream in streams}
        read = {fd: [] for fd in open_fds}

        def take(wait_s):
            # a wait computed from a deadline that passed meanwhile is a poll, never a refusal
            for fd in select.select(sorted(open_fds), [], [], max(wait_s, 0))[0]:
                chunk = os.read(fd, 65536)
                if chunk:
                    read[fd].append(chunk)
                else:
                    open_fds.discard(fd)
        deadline, timed_out = self.clock() + limit_s, False
        try:
            try:
                while open_fds or not self.ended():
                    left = deadline - self.clock()
                    if left <= 0:
                        timed_out = True
                        break
                    if open_fds:
                        take(min(left, TICK_S))
                    else:
                        self.ended(min(left, TICK_S))
            finally:
                self.end(grace_s)
            deadline = self.clock() + drain_s
            while open_fds and self.clock() < deadline:
                take(min(deadline - self.clock(), TICK_S))
        finally:
            for stream in streams:
                stream.close()
        held = bool(open_fds)
        out, err = (b"" if fd is None else b"".join(read[fd]) for fd in fds)
        return out, err, timed_out, held


class Client:
    """One app-server over stdio, read on a thread into a queue, in a process group of its own (Owned).

    On POSIX a request is written to the server's input descriptor, made non-blocking, only while the
    call's deadline lasts: a server that stops reading cannot hold a call past its timeout. A request
    not sent whole by then leaves part of a frame in the server's input, so the client refuses every
    later call, naming that request. Nothing is written through the buffered input stream, so closing
    it flushes nothing. On Windows, where pipes cannot be selected, a request is written as before."""

    def __init__(self, argv, cwd=None, env=None):
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     cwd=cwd, env=env, start_new_session=True)
        self.owned = Owned(self.proc)
        self.broken = None
        if os.name != "nt":
            os.set_blocking(self.proc.stdin.fileno(), False)
        self.sequence = 0
        self.events = queue.Queue()
        self.stopping, self.drained = threading.Event(), threading.Event()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self._lines():
                try:
                    self.events.put(json.loads(line))
                except ValueError:
                    self.events.put({"transport_error": "invalid app-server JSON"})
        finally:
            self.events.put({"transport_error": "app-server closed before its response"})

    def _lines(self):
        """The server's output, line by line, until it closes or close() stops the reading. On POSIX
        the descriptor is read directly, so a stop takes effect within TICK_S and no thread is left
        reading a stream that a process outside the group holds open; Windows pipes cannot be
        selected, so there the stream is read until it closes."""
        if os.name == "nt":
            yield from self.proc.stdout
            self.drained.set()
            return
        fd, partial = self.proc.stdout.fileno(), b""
        while not self.stopping.is_set():
            if not select.select([fd], [], [], TICK_S)[0]:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                self.drained.set()
                if partial:
                    yield partial
                return
            *lines, partial = (partial + chunk).split(b"\n")
            yield from lines

    def _send(self, method, message, deadline):
        if self.broken:
            raise ProtocolError(self.broken)
        data = (json.dumps(message) + "\n").encode("utf-8")
        if os.name == "nt":
            self.proc.stdin.write(data)
            self.proc.stdin.flush()
            return
        fd, whole = self.proc.stdin.fileno(), len(data)
        while data:
            left = deadline - time.monotonic()
            if left <= 0 and len(data) == whole:
                raise ProtocolError(f"app-server timed out: {method} (the server read none of the request)")
            if left <= 0:
                self.broken = (f"app-server {method}: the request was not sent whole within its timeout, so the "
                               f"server's input holds part of it and this client sends nothing more")
                raise ProtocolError(self.broken)
            if not select.select([], [fd], [], min(left, TICK_S))[1]:
                continue
            try:
                data = data[os.write(fd, data):]
            except BlockingIOError:
                continue
            except OSError as exc:  # a server that ended has broken the pipe
                self.broken = f"app-server {method}: the server's input closed ({exc.__class__.__name__})"
                raise ProtocolError(self.broken) from exc

    def notify(self, method, timeout=45):
        self._send(method, {"method": method}, time.monotonic() + timeout)

    def call(self, method, params, timeout=45):
        self.sequence += 1
        request_id = self.sequence
        deadline = time.monotonic() + timeout
        self._send(method, {"id": request_id, "method": method, "params": params}, deadline)
        while time.monotonic() < deadline:
            try:
                message = self.events.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty as exc:
                raise ProtocolError(f"app-server timed out: {method}") from exc
            if "transport_error" in message:
                raise ProtocolError(message["transport_error"])
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"]
                raise ProtocolError(f"app-server {method}: "
                                    f"{error.get('message', 'refused') if isinstance(error, dict) else error}")
            return message.get("result")
        raise ProtocolError(f"app-server timed out: {method}")

    def close(self):
        """The server's input is closed and it is given CLOSE_S to end, then its group is ended before
        it is reaped (Owned.end). Its output then has DRAIN_S to close: a process outside the group
        that still holds it is not waited for, and one line on stderr says so. The reader is stopped,
        within TICK_S on POSIX, and the output is closed only once no thread reads it. Each step runs
        however the one before it ended, an interrupted wait included, and a termination signal waits
        until the last is done (_Cleanup)."""
        with _Cleanup():
            self._close()

    def _close(self):
        try:
            try:
                with contextlib.suppress(OSError):
                    self.proc.stdin.close()  # nothing was written through its buffer, so this flushes nothing
                self.owned.ended(CLOSE_S)
            finally:
                self.owned.end(CLOSE_S)
            if not self.drained.wait(DRAIN_S):
                with contextlib.suppress(OSError):  # a terminal that has gone (SIGHUP) refuses the line
                    sys.stderr.write("agent-bios: a process the Codex app-server left outside its process group "
                                     "still holds its output; agent-bios stopped reading it without waiting for it "
                                     "to close\n")
        finally:
            self.stopping.set()
            self.reader.join(timeout=DRAIN_S)
            if not self.reader.is_alive():
                self.proc.stdout.close()
