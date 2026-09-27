"""Probing delivery to a recipient on the host installed here (C12 `capability.probe`).

A delivery capability (`new_delivery`, `current_delivery`, `child_delivery`,
`rehydrated_delivery`) is probed by a real run of the installed host: the host is started with
its adapter's hook on the route to that recipient, the hook hands the recipient a random code
with the instruction to give it when asked, and the recipient is asked for it. The route worked
only if the reply carries that code, which nothing but the hook's context could have told it.
The recipient is asked to act on what it was handed, not to repeat it: Codex adds a hook's
context as a developer message, and its model declines to disclose one.

What the run found is recorded as C12 states it, kept apart from what was declared:

  - `unsupported`, not offered: no adapter names the host, the adapter declares no route to
    that recipient, or it cannot drive its host;
  - `unreachable`, not offered: the host is not installed on this machine's path, or the
    installed version is not the one the probe names, since a probe qualifies one version;
  - `worked`: the reply carried the code;
  - `refused`: the host answered without it, as when it did not run a hook it was given;
  - `no_response`: the host gave no reply, failed or ran out of time.

A probe is recorded as a real run, since it runs the installed host, with the configuration it
ran under: the hook it gave the host, and whether the host would run it. The run happens before
the request's unit of work, so the store is not held while the host runs.

Probing any other capability is not served yet.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pathlib
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile

from workenv import hosts, journal
from workenv.contracts import c03, c12

CODE = "agent-bios probe code"
JOB = "AGENT_BIOS_HOOK_JOB"
HOOK = pathlib.Path(__file__).with_name("hook.py")
WIRE = {"protocol": "command_hook", "version": "1"}
ASK = f"What is the {CODE}? Reply with the code alone, or NONE if you were not given one."
ASK_CHILD = (f"Start one subagent with your subagent tool and ask it: \"{ASK}\" Then reply with "
             "exactly what the subagent replied and nothing else.")
TIMEOUT = 300
# The longest `observed` a probe keeps (C12).
OBSERVED = 4000
RECIPIENT = {capability: recipient for recipient, capability in hosts.CAPABILITY.items()}


@dataclasses.dataclass
class Run:
    """What one run of a host showed: the recipient's reply (None where the host gave none),
    the hooks it ran under, and what the host reported."""
    reply: str | None
    hooks: list[dict]
    note: str = ""


def handed(code: str) -> str:
    """What the hook hands the recipient."""
    return f"If you are asked for the {CODE}, reply with {code}."


def command(host_name: str) -> str:
    """The hook a host runs, the same bytes on every run: this installation's interpreter
    running `hook.py` for the host."""
    return " ".join(shlex.quote(part) for part in (sys.executable, str(HOOK), host_name))


def hook(event: str, handler: str, enabled: bool) -> dict:
    """One hook of a host configuration: its event, the digest of its handler, and whether the
    host would run it."""
    return {"event": event, "handler_digest": hashlib.sha256(handler.encode("utf-8")).hexdigest(),
            "enabled": enabled}


def ran(argv: list[str], cwd: pathlib.Path, environ: dict,
        timeout: int = TIMEOUT) -> subprocess.CompletedProcess | None:
    """One run of a host, or None where it could not be started or ran out of time."""
    try:
        return subprocess.run(argv, cwd=cwd, env=environ, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def installed(adapter: hosts.Adapter, environ: dict,
              workdir: pathlib.Path) -> tuple[str, str] | None:
    """The installed host's executable and the version it reports, or None."""
    path = shutil.which(adapter.binary, path=environ.get("PATH")) if adapter.binary else None
    done = ran([path, "--version"], workdir, environ, timeout=60) if path else None
    version = re.search(r"\d+\.\d+\.\d+\S*", done.stdout) if done else None
    return (path, version.group()) if version else None


def probed(asked: dict, environ: dict, workdir: pathlib.Path) -> tuple[dict, list[dict]]:
    """What a probe of one delivery capability observed, and the hooks it ran under."""
    client, recipient = asked["client"], RECIPIENT[asked["capability"]]
    adapter = hosts.adapter_for(client["name"])

    def found(offered: bool, outcome: str, observed: str, ran_under=(), note: str = "") -> tuple:
        observed = " ".join(part for part in (observed, note) if part)
        return ({"offered": offered, "outcome": outcome, "observed": observed[:OBSERVED]},
                list(ran_under))
    if adapter is None:
        return found(False, "unsupported", f"No adapter here names {client['name']}.")
    if recipient not in adapter.routes:
        return found(False, "unsupported",
                     f"The {client['name']} adapter declares no route to a {recipient} session.")
    if adapter.drive is None:
        return found(False, "unsupported", f"The {client['name']} adapter cannot drive its host.")
    host = installed(adapter, environ, workdir)
    if host is None:
        return found(False, "unreachable",
                     f"No {client['name']} is installed on this machine's path.")
    if host[1] != client["version"]:
        return found(False, "unreachable",
                     f"The installed {client['name']} is {host[1]}, not {client['version']}.")
    code = secrets.token_hex(8)
    job = workdir / "job.json"
    job.write_text(json.dumps({"recipient": recipient, "text": handed(code)}), encoding="utf-8")
    quiet = {name: value for name, value in environ.items() if name not in adapter.nested}
    run = adapter.drive(recipient, host[0], command(client["name"]), workdir,
                        {**quiet, JOB: str(job)})
    route = adapter.routes[recipient]
    where = f"{route.event}" + (f" ({route.source})" if route.source else "")
    if run.reply is None:
        return found(True, "no_response", f"The host gave no reply to the {where} probe.",
                     run.hooks, run.note)
    if code in run.reply:
        return found(True, "worked", f"The {recipient} session gave the code the adapter handed "
                     f"it on {where}.", run.hooks, run.note)
    return found(True, "refused", f"The {recipient} session did not give the code the adapter "
                 f"handed it on {where}.", run.hooks, run.note)


def refused(call, code: str, pointer: str) -> dict:
    return journal.answered(call, "refused", gaps=[{"code": code, "pointer": pointer}],
                            recovery=["new_governed_request"])


def prepare(call) -> dict:
    """Refuse what can be refused, then run the host, before the unit of work."""
    asked = journal.payload(call)
    if asked["capability"] not in RECIPIENT:
        raise journal.JournalError(f"probing {asked['capability']} is not served yet")
    if call.request["target"]["resource_id"] != call.request["actor"]["profile_id"]:
        return {"answer": refused(call, c03.REQUEST_MISMATCH, "/target/resource_id")}
    if asked["wire"] != WIRE:
        return {"answer": refused(call, c12.WIRE_VERSION_UNSUPPORTED, "/wire")}
    with tempfile.TemporaryDirectory(prefix="agent-bios-probe-") as workdir:
        fields, ran_under = probed(asked, dict(os.environ), pathlib.Path(workdir).resolve())
    return {"fields": fields, "hooks": ran_under}


def capability_probe(call) -> dict:
    prepared = getattr(call, "prepared", None) or prepare(call)
    if "answer" in prepared:
        return prepared["answer"]
    asked, at = journal.payload(call), journal.now(call)
    probe = {**asked, "probe_id": journal.mint("prb"), **prepared["fields"],
             "mode": {"runs": "real"}, "at": at}
    configuration = {"kind": "host_configuration", "schema": 1, "client": asked["client"],
                     "hooks": prepared["hooks"], "mode": {"runs": "real"}, "measured_at": at}
    return journal.committed(call, [probe, configuration])
