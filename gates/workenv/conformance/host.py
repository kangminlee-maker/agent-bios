"""The host: one world process of a case, running the code under test.

The executor starts one host per world process, `python3 -B -P host.py <root> <state>`. It
imports the code under test from `<root>` and nothing from `gates/`: `-P` keeps this directory
off its path, and the host's environment carries no PYTHON* variable, so neither the caller's
PYTHONPATH nor its PYTHONOPTIMIZE reaches it: the code under test runs its own assertions and
cannot import the judge. Nor does any XDG_* variable, and HOME is a directory of the run's own, so
nothing the code under test writes outside its state root lands in the person's home.

The host reads one message per line on stdin and answers one per line on stdout. A message names
what answers the step, outermost first: the layers in scope, each called `layer(call, inner)`;
then either the entry `entry(call)`, an addressed operation that only a layer may answer, or the
driver's given answer, which the host returns after handing it to each place entry
`place(call)` as `call.given`. Its answer is one of:

  {"answer": <the entry's answer>, "admitted": <times admitted() was called>, "points": [...]}
  {"blocked": "<why>"}   the entry, a layer or a place is not written yet
  {"error": "<why>"}     the code under test raised; the line is the exception's own

A process that dies answers nothing, and the driver's side reports it as dead. The call is
duck-typed, as the adapter design fixes it: `request`, `carried`, `members` (bytes by sha256),
`now`, `state` (this process's state root, the same one after a restart), `exchange` (a directory
every process of the case shares), `point(name)` (the fault hook) and `admitted()` (the
admission hook). Bytes cross the pipe as {"bytes": base64}: no record holds such an object, since
a record's keys are ASCII snake_case.

Only the protocol uses the pipes. At start the host moves them to descriptors of its own and
points stdin at /dev/null and stdout at stderr, so code that prints or reads cannot corrupt a
message; stderr is kept in `host.log` beside the state root.
"""
from __future__ import annotations

import base64
import importlib
import json
import os
import pathlib
import select
import subprocess
import sys
import traceback

# How long a host has to answer one step.
TIMEOUT = 120
# The exit status of a host killed at an armed fault point.
KILLED = 70
BYTES = "bytes"


def encode(value):
    """A value with bytes, as JSON can carry it."""
    if isinstance(value, bytes):
        return {BYTES: base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {key: encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(item) for item in value]
    return value


def decode(value):
    if isinstance(value, dict):
        if set(value) == {BYTES} and isinstance(value[BYTES], str):
            return base64.b64decode(value[BYTES])
        return {key: decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode(item) for item in value]
    return value


class Host:
    """The driver's side of one host process."""

    def __init__(self, root: pathlib.Path, base: pathlib.Path, timeout: int = TIMEOUT,
                 env: dict[str, str] | None = None):
        self.base, self.timeout = base, timeout
        state = base / "state"
        state.mkdir(parents=True, exist_ok=True)
        (base / "home").mkdir(exist_ok=True)
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("PYTHON", "XDG_"))}
        environment.update(env or {})
        environment["HOME"] = str(base / "home")
        self.log = open(base / "host.log", "ab")
        self.process = subprocess.Popen(
            [sys.executable, "-B", "-P", __file__, str(root), str(state)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, env=environment,
            cwd=base)

    def call(self, message: dict) -> dict:
        """The host's reply, or {"dead": why} when it died or did not answer in time."""
        try:
            self.process.stdin.write(json.dumps(encode(message)).encode("utf-8") + b"\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError):
            return {"dead": self.death()}
        ready, _, _ = select.select([self.process.stdout], [], [], self.timeout)
        if not ready:
            self.process.kill()
            self.process.wait()
            return {"dead": f"gave no answer within {self.timeout}s and was killed"}
        line = self.process.stdout.readline()
        if not line:
            return {"dead": self.death()}
        try:
            return decode(json.loads(line))
        except ValueError:
            return {"error": f"the host wrote a line that is no message: {line[:120]!r}"}

    def death(self) -> str:
        status = self.process.wait()
        tail = self.tail()
        return (f"died with status {status}" if status != KILLED
                else "was killed at its armed fault point") + (f": {tail}" if tail else "")

    def tail(self) -> str:
        self.log.flush()
        lines = (self.base / "host.log").read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-1].strip() if lines else ""

    def close(self) -> None:
        for pipe in (self.process.stdin, self.process.stdout):
            try:
                pipe.close()
            except OSError:
                pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.log.close()


# The host process's own side.

class NotWritten(Exception):
    """An entry, layer or place the code under test has not written yet."""


class Call:
    """What the code under test is called with."""

    def __init__(self, message: dict, state: pathlib.Path):
        self.request = message["request"]
        self.carried = message["carried"]
        self.members = message.get("members", {})
        self.now = message.get("now")
        self.state = state
        self.exchange = pathlib.Path(message["exchange"])
        self.given = message.get("given")
        self._armed = message.get("arm")
        self.points: list[str] = []
        self.admissions = 0

    def point(self, name: str) -> None:
        self.points.append(name)
        if name == self._armed:
            os._exit(KILLED)

    def admitted(self) -> None:
        self.admissions += 1


def resolve(entry: str, loaded: dict):
    """The callable an entry names, `module:function`; NotWritten when either is missing."""
    if entry in loaded:
        return loaded[entry]
    module, _, name = entry.partition(":")
    try:
        found = importlib.import_module(module)
    except ModuleNotFoundError as error:
        if error.name and (module == error.name or module.startswith(f"{error.name}.")):
            raise NotWritten(f"{entry}: module {module} is not written yet") from error
        raise
    if not hasattr(found, name):
        raise NotWritten(f"{entry}: {module} defines no {name} yet")
    loaded[entry] = getattr(found, name)
    return loaded[entry]


class Addressed(Exception):
    """An addressed operation no layer answered."""


def answer(message: dict, state: pathlib.Path, loaded: dict) -> dict:
    call = Call(message, state)
    try:
        layers = [resolve(entry, loaded) for entry in message.get("layers", [])]
        if "given" in message:
            places = [resolve(entry, loaded) for entry in message.get("places", [])]

            def inner(call):
                for place in places:
                    place(call)
                return call.given
        elif message.get("addressed"):
            def inner(call):
                raise Addressed("an addressed operation reached past every layer, and only the "
                                "journal layer answers one")
        else:
            inner = resolve(message["entry"], loaded)
    except NotWritten as why:
        return {"blocked": str(why)}
    for layer in reversed(layers):
        inner = (lambda layer, inner: lambda call: layer(call, inner))(layer, inner)
    try:
        found = inner(call)
    except NotWritten as why:
        return {"blocked": str(why)}
    except Exception as error:  # the code under test's defect, reported as its own line
        traceback.print_exc()
        return {"error": f"{type(error).__name__}: {error}"}
    return {"answer": found, "admitted": call.admissions, "points": call.points}


def serve(root: str, state: str) -> None:
    replies = os.fdopen(os.dup(1), "wb")
    requests = os.fdopen(os.dup(0), "rb")
    null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null, 0)
    os.dup2(2, 1)
    sys.path.insert(0, root)
    loaded: dict = {}
    for line in requests:
        reply = answer(decode(json.loads(line)), pathlib.Path(state), loaded)
        try:
            data = json.dumps(encode(reply)).encode("utf-8")
        except (TypeError, ValueError) as error:
            data = json.dumps({"error": f"the answer is not JSON: {error}"}).encode("utf-8")
        replies.write(data + b"\n")
        replies.flush()


if __name__ == "__main__":
    serve(sys.argv[1], sys.argv[2])
