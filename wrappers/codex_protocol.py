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
  response unread until the timeout.

Loaded by path: beside codex_frame_filter.py, deployed together, and by compose from the package's
wrappers/ directory (host_platform.codex_protocol_for).
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import queue
import re
import shutil
import subprocess
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
    the user's developer instructions with nothing. A layer's `config` is open in the generated
    schema (`true`), so its field is held by SHAPES and this check, not by USED."""
    value = result["config"]["developer_instructions"]
    layers = result.get("layers")
    if not isinstance(layers, list):
        raise ProtocolError("app-server config/read: no layers to hold config.developer_instructions to, "
                            "though agent-bios asked for them (includeLayers)")
    stated = {}
    for layer in layers:
        held = (layer.get("config") or {}).get("developer_instructions")
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


class Client:
    """One app-server over stdio, read on a thread into a queue."""

    def __init__(self, argv, cwd=None, env=None):
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     cwd=cwd, env=env, text=True, encoding="utf-8")
        self.sequence = 0
        self.events = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.proc.stdout:
                try:
                    self.events.put(json.loads(line))
                except ValueError:
                    self.events.put({"transport_error": "invalid app-server JSON"})
        finally:
            self.events.put({"transport_error": "app-server closed before its response"})

    def notify(self, method):
        self.proc.stdin.write(json.dumps({"method": method}) + "\n")
        self.proc.stdin.flush()

    def call(self, method, params, timeout=45):
        self.sequence += 1
        request_id = self.sequence
        self.proc.stdin.write(json.dumps({"id": request_id, "method": method, "params": params}) + "\n")
        self.proc.stdin.flush()
        deadline = time.monotonic() + timeout
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
        if self.proc.stdin:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        if self.proc.stdout:
            self.proc.stdout.close()
        self.reader.join(timeout=2)
