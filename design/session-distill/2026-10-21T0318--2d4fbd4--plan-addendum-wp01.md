---
created_at: 2026-10-21T03:18:00+09:00
head: 2d4fbd4
kind: design
supersedes: null
---

# Session distill implementation plan: addendum for WP-01

This record adds two readings to `2026-10-20T2119--cc0498f--implementation-plan.md` (below: the
plan), work package WP-01, settled while that work package was reviewed. The plan and the design
stand otherwise.

## `run.json` carries the failure posture

The design's §4 names a run's **failure posture**: development, rehearsal, and gate failures stop
by name; in a production run a failing item is quarantined with its dependants and independent
items continue. WP-01's goal requires that posture, but its list of `run.json` fields does not say
where a run declares which posture it is under. This record adds the field:

- `posture ∈ {production, rehearsal, development}`, required, declared at S0 and changed only
  through `--amend` like every other declared value.
- Consumer: the item-failure primitive of `session-distill/runlib/records.py` (quarantine with
  dependants and continue under `production`; stop by name otherwise).

The posture is part of the declaration, not a command-line option, so that every stage of one run
fails the same way and the stage records pin which way that was.

The declaration's own structure is validated through the shared schema path like every other
record, so WP-01's author-side file list gains `session-distill/schemas/run.schema.json`.

## The jsonschema pin is enforced by version, not by interpreter path

The plan's conventions ask for `jsonschema` 4.26.0 "exactly as `learn/check-learning.py` loads it,
through the managed interpreter `launch/provision-venv.sh` provisions (`JSONSCHEMA_PIN`)". In this
checkout the umbrella runs `learn/check-learning.py` under the system `python3`, and the managed
launcher venv does not carry `jsonschema`. The reading this record takes: the session-distill
modules run under the same interpreter as `learn/check-learning.py`, and `runlib/validate.py`
refuses by name any `jsonschema` whose version differs from the pin, reading the pin from
`launch/provision-venv.sh` `JSONSCHEMA_PIN` so the version has one owner. Provisioning stays out of
the offline gate.
