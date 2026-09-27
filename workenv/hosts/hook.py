#!/usr/bin/env python3
"""The command a host runs on its events, as its adapter's hook: `python3 hook.py <host name>`.

The command is the same bytes on every run, so a host that asks the person to trust a hook once
(Codex lists a session's hooks as untrusted until the person reviews them) keeps trusting it.
What a run does is named by the job file `AGENT_BIOS_HOOK_JOB` points at, which whoever
configured the hook wrote: the recipient it serves and the text it hands that recipient. The
host passes the event on standard input; where the host's adapter says the event reaches that
recipient, the command prints the adapter's output carrying the text, and otherwise nothing.

It writes nothing, and it never fails its host: an event it cannot read, a host no adapter
names or a job it cannot read leaves the session as it was, with the reason on standard error.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from workenv import hosts  # noqa: E402

JOB = "AGENT_BIOS_HOOK_JOB"


def answer(host_name: str, event: dict, job: dict) -> str | None:
    """What the command prints for one event: the adapter's output where the event reaches the
    job's recipient, or None."""
    adapter = hosts.adapter_for(host_name)
    if adapter is None or adapter.recipient_of(event) != job["recipient"]:
        return None
    return adapter.output(event, job["text"])


def main(argv: list[str], stdin, environ) -> int:
    try:
        event = json.load(stdin)
        job = json.loads(pathlib.Path(environ[JOB]).read_text(encoding="utf-8"))
        printed = answer(argv[0], event, job)
    except (IndexError, KeyError, OSError, ValueError) as error:
        print(f"agent-bios hook: nothing handed over ({type(error).__name__})", file=sys.stderr)
        return 0
    if printed is not None:
        print(printed)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], sys.stdin, os.environ))
