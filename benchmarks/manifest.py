#!/usr/bin/env python3
"""The scenario manifest: every response the run owes, declared before it runs.

The manifest is written and hashed BEFORE any dispatch, and it is the run's
denominator. Counting responses after the fact answers "how many did we get",
which is the question that cannot detect a cell that never ran — so the expected
count is asserted from here, never printed from the run.

A cell is one response: (item, obligation, role, arm, host, repetition). `item`
is a ledger id or scenario id; `obligation` is the single behavior being probed
(a bundled ledger entry is atomized into obligations first, and each obligation
carries its original id so an original is dispositioned only when all of them
are); `role` is the scenario's job — trigger, transfer, adversarial, control.

Each cell also carries `expected_request_sha256`, the digest of the exact bytes that
cell must be dispatched with, computed here and covered by `manifest_sha256`. Without
it a scenario's opener can be rewritten while every cell key stays identical, so two
materially different runs share one declared identity — and the receipts' own request
digests have nothing to be checked against.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

SCHEMA = "BenchManifest/v1"
ROLES = ("trigger", "transfer", "adversarial", "control")
GUARDS = ("irreversible", "authority", "security", "none")


class ManifestError(RuntimeError):
    """A manifest that cannot be trusted as a denominator."""


def cell_key(item: str, obligation: str, role: str, arm: str, host: str, rep: int) -> str:
    return f"{item}|{obligation}|{role}|{arm}|{host}|{rep}"



def _seat_for(item: str, host: str, seats: dict, overrides: dict) -> dict:
    """The seat this cell is dispatched at and judged against.

    The override replaces only the fields it declares, so a run's `--effort` still
    reaches an item whose model is pinned for a reason unrelated to effort."""
    spec = (overrides.get(item) or {}).get(host)
    if not spec:
        return seats[host]
    return {**seats[host], **{k: v for k, v in spec.items()
                              if k in ("model", "effort") and v}}


def build(items: list[dict], arms: list[str], hosts: list[str], reps: int,
          seats: dict, notes: str = "", guards_approved: str | None = None,
          seat_overrides: dict | None = None, ablation: str | None = None) -> dict:
    """`items` carry id, obligation, role, guards. `seats` is host -> {model, effort}.

    `seat_overrides` is item -> host -> {model, effort, reason}: a scenario whose
    declared seat differs from the host default, because the default model does not
    serve that request. `sec-admin-auth` is the case it exists for — Opus 5 runs a
    cybersecurity classifier and re-runs a flagged request on Opus 4.8, so a cell
    declaring Opus 5 records whichever model happened to answer.

    Each entry names its own site and carries its own reason: a binding that excused
    every scenario, or excused one without saying why, would turn the seat check from
    a check into a waiver. An entry naming an item this manifest does not cover is a
    stale declaration and refused, so deleting a scenario cannot leave its override
    behind."""
    if not items:
        raise ManifestError("no items — a manifest over nothing is satisfied by nothing")
    if not arms or not hosts or reps < 1:
        raise ManifestError(f"empty design: arms={arms} hosts={hosts} reps={reps}")
    missing_seat = [h for h in hosts if h not in seats or not seats[h].get("model")]
    if missing_seat:
        raise ManifestError(
            f"no accepted seat declared for {', '.join(missing_seat)} — a response cannot "
            f"be judged in or out of an undeclared set")

    overrides = seat_overrides or {}
    known_items = {it.get("id") for it in items}
    for item, by_host in sorted(overrides.items()):
        if item not in known_items:
            raise ManifestError(
                f"seat override for {item!r} names no item in this manifest — a binding that "
                f"matches nothing is a stale declaration, not a narrowing")
        if not by_host:
            raise ManifestError(f"{item}: seat override names no host, so it binds nothing")
        for host, spec in sorted(by_host.items()):
            if not (spec or {}).get("model"):
                raise ManifestError(
                    f"{item}/{host}: seat override declares no model — the thing it exists "
                    f"to pin is the one field it must carry")
            if spec.get("model") == (seats.get(host) or {}).get("model"):
                raise ManifestError(
                    f"{item}/{host}: seat override declares {spec['model']!r}, which is "
                    f"already this host's seat — a binding that changes nothing is printed "
                    f"as a declared per-cell seat and hides that the override did not apply")
            if not str((spec or {}).get("reason", "")).strip():
                raise ManifestError(
                    f"{item}/{host}: seat override carries no reason — an unexplained seat "
                    f"is indistinguishable from a seat that drifted")

    cells = []
    for it in items:
        if it.get("role") not in ROLES:
            raise ManifestError(f"{it.get('id')}: role {it.get('role')!r} not in {ROLES}")
        if it.get("guards") not in GUARDS:
            raise ManifestError(f"{it.get('id')}: guards {it.get('guards')!r} not in {GUARDS}")
        if not it.get("request_sha256"):
            raise ManifestError(
                f"{it.get('id')}: no request digest — a cell that does not bind the bytes it "
                f"will be dispatched with cannot tell two different runs apart")
        for arm in arms:
            for host in hosts:
                for rep in range(1, reps + 1):
                    cells.append({
                        "key": cell_key(it["id"], it["obligation"], it["role"], arm, host, rep),
                        "item": it["id"], "obligation": it["obligation"],
                        "role": it["role"], "guards": it["guards"],
                        "arm": arm, "host": host, "rep": rep,
                        "seat": _seat_for(it["id"], host, seats, overrides),
                        "expected_request_sha256": it["request_sha256"],
                    })
    dupes = {c["key"] for c in cells if sum(1 for x in cells if x["key"] == c["key"]) > 1}
    if dupes:
        raise ManifestError(f"duplicate cell keys: {sorted(dupes)[:3]}")

    body = {"schema": SCHEMA, "arms": arms, "hosts": hosts, "reps": reps,
            "seats": seats, "notes": notes, "guards_approved": guards_approved,
            # Arm identity as a field, not a substring of prose. It was read out of
            # `notes` by first textual match, so a --corpus path containing the text
            # `ablation=...` relabelled an unablated arm as an ablated one and the
            # verdict followed the label.
            "ablation": ablation or "none",
            "seat_overrides": overrides, "cells": cells}
    body["manifest_sha256"] = hashlib.sha256(
        json.dumps({k: v for k, v in body.items() if k != "manifest_sha256"},
                   sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return body


def write_once(path: pathlib.Path, manifest: dict) -> None:
    """A manifest is written before the run and never rewritten after it.

    Overwriting one would let the denominator be edited to match the responses
    that happened to arrive, which is the failure the manifest exists to prevent."""
    if path.exists():
        raise ManifestError(f"{path}: already exists — a manifest is written once")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def check_bijection(manifest: dict, receipts: list[dict]) -> list[str]:
    """C4: manifest cells and dispatch receipts in bijection, by identity.

    Returns the problems; an empty list means every declared cell has exactly one
    receipt and every receipt names a declared cell."""
    declared = {c["key"] for c in manifest["cells"]}
    if not declared:
        return ["manifest declares no cells — bijection over nothing is vacuous"]
    seen = {}
    problems = []
    for r in receipts:
        key = r.get("cell_key")
        if key is None:
            problems.append(f"receipt {r.get('receipt_id', '?')} names no cell")
            continue
        if key not in declared:
            problems.append(f"receipt names undeclared cell {key}")
        seen.setdefault(key, []).append(r)
    for key, rs in seen.items():
        if len(rs) > 1:
            problems.append(f"cell {key} has {len(rs)} receipts")
    for key in sorted(declared - set(seen)):
        problems.append(f"cell {key} has no receipt")
    return problems
