#!/usr/bin/env python3
"""Canonical package identity for the domain-package ecosystem (contract v2).

A package is `@scope/name` — **unversioned**, and independent of the domains it
declares. A domain's canonical identity is the pair `(package_id, domain)`, so a
bare domain string is only meaningful relative to a package.

`CORE` is the built-in engine manifest. A manifest or record that carries no
package id means `CORE`, permanently: that reservation is what keeps every
artifact written before v2 — selections, promotions, ledger placements — valid
with no migration.

Spec: design/adapter-split/ECOSYSTEM-ARCHITECTURE.md, "Foundational contract v2".
"""
import re

CORE = "@agent-bios/core"

_SEG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
PATTERN = re.compile(rf"^@{_SEG}/{_SEG}$")


def is_valid(pid):
    """True for a well-formed package id. Callers validate before deriving paths."""
    return isinstance(pid, str) and PATTERN.match(pid) is not None


def resolve(obj, key="package_id"):
    """The package id an object declares, or CORE when it declares none.

    Absent means CORE — never guess from context, and never treat a present but
    malformed id as absent: that would silently promote a typo to core's
    authority. Validate with is_valid() where the value is first accepted.
    """
    if not isinstance(obj, dict):
        return CORE
    pid = obj.get(key)
    return CORE if pid is None else pid


def segments(pid):
    """('scope', 'name') for deriving deploy paths. Only call on a valid id.

    No caller yet, and that is recorded rather than left to be rediscovered: deploy-path
    derivation belongs to the multi-package composer, which
    design/adapter-split/ECOSYSTEM-ARCHITECTURE.md defers "to the first real second package".
    Kept because the id grammar it splits is settled and rewriting it later would re-derive the
    same two lines; delete it if that deferral is ever abandoned rather than landed.
    """
    if not is_valid(pid):
        raise ValueError(f"not a package id: {pid!r}")
    return tuple(pid[1:].split("/", 1))
