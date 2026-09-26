"""Revision bytes: what a person holds when they commit a revision the scenario states by digest.

A scenario states a managed revision its person commits or admits by its manifest: each member's
path, size and digest. Where it gives the member's text, the text travels with every request, as
for any member. Where it states the digest alone (`cases.stated_revision_members`), the digest
stands for bytes the person holds, as a file digest stands for the file the checkout feature
writes: before the first step this makes bytes of the stated size for each such digest, the same
bytes for the same digest, and puts their sha256 in its place wherever the scenario states it.
The request that commits or admits the revision carries those bytes, as a person's own revision
carries its members; no other request does, so a place the scenario says the bytes never reached
does not receive them from here.
"""
from __future__ import annotations

import hashlib

import cases
import executor


def install(run) -> None:
    run.prepare_hooks.append(build)
    run.message_hooks.append(attach)


def made(digest: str, size: int) -> bytes:
    """Bytes of the stated size standing for one stated digest."""
    seed = f"stated {digest}\n".encode()
    return (seed * (size // len(seed) + 1))[:size]


def build(run) -> None:
    replaced: dict[str, str] = {}
    held: dict[str, bytes] = {}
    for name, pointer in cases.stated_revision_members(run.built):
        member = executor.at(run.templates[name], pointer)[1]
        data = made(member["digest"], member["size"])
        replaced[member["digest"]] = hashlib.sha256(data).hexdigest()
        held[replaced[member["digest"]]] = data
    for name, record in run.templates.items():
        run.templates[name] = swapped(record, replaced)
    run.revision_bytes = held
    run.authoring = {step["name"] for step in run.built["steps"]
                     if run.templates.get(step.get("request"), {}).get("operation")
                     in cases.AUTHORING}
    run.forget()


def attach(run, step: dict, message: dict) -> None:
    """The request that commits or admits a revision carries the bytes its members state."""
    if step["name"] not in run.authoring:
        return
    carried = [member.get("digest") for record in message.get("carried", [])
               if isinstance(record, dict) and record.get("kind") == "source_manifest"
               for member in record.get("members", [])]
    message["members"].update({digest: run.revision_bytes[digest] for digest in carried
                               if digest in run.revision_bytes})


def swapped(value, replaced: dict[str, str]):
    """The value with each stated digest replaced wherever it stands: a member's digest, a body a
    unit or a delivery names, a digest listed in any field."""
    if isinstance(value, dict):
        return {key: swapped(item, replaced) for key, item in value.items()}
    if isinstance(value, list):
        return [swapped(item, replaced) for item in value]
    return replaced.get(value, value) if isinstance(value, str) else value
