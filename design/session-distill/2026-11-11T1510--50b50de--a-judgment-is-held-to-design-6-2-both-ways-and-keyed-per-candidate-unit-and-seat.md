---
created_at: 2026-11-11T15:10:00+09:00
head: 50b50de
kind: design
supersedes: 2026-11-11T1445--9e1082e--one-judgment-packet-outweighs-the-s6-budget-and-the-inventory-publishes-the-edges-it-reads.md
---

# WP-11 J1a: the contract a judgment is held to, before any packet shape

Plan WP-11, lead decisions D11, D12 and D14 (2026-11-11). This commit holds what no packet shape changes; the packet
itself (which context, how many units, one candidate or several per call) waits for the budget decision J0's
numbers raised.

## What is held

- `schemas/judge.schema.json` against design §6.2's judged fields both ways (done-when 8, the schema's half):
  `stage_judge.contract_problems` maps every §6.2 phrase to the schema paths that hold it, refuses a phrase with no
  field and a field no phrase names unless `EXTRA_FIELDS` declares it with its reason (the packet's labels, the
  ledger relation's reason, §6.4's no-longer-arises evidence). CONTRACT_DRIFT names each.
- The reuse key (D12, D-20261111-f174ea): one key per (candidate, unit, seat), the hash of exactly §6.2's thirteen
  components by the design's own names (`key_components`), refused when handed any other set (done-when 8, the key's
  half). Each component changed gives another key; the seat among them, so A's judgment never answers B.
- One payload for both judges (done-when 1, N#1): PACKET_DIVERGENCE when two seats' payloads differ, or their
  receipts carry different payload hashes; RECEIPT_STALE when two receipts carry one packet hash. The envelope is the
  only per-seat part, so the packet hashes differ while the payload hash is shared, asserted over `packet.build`.
- An answer against its packet: every unit judged once (UNIT_UNJUDGED, UNIT_JUDGED_TWICE), a quote exactly where a
  match is yes and a span of that unit (D14, D-20261111-1aa1b3: QUOTE_MISSING, QUOTE_UNEXPECTED,
  QUOTE_NOT_IN_UNIT), every matching unit's following and contribution (MATCHING_UNIT_MISSING, _UNEXPECTED,
  _TWICE), every ledger entry related once (ENTRY_UNJUDGED, ENTRY_JUDGED_TWICE), labels the packet shows
  (UNKNOWN_LABEL), and a later reference point's call judging its units only (FIELD_UNEXPECTED).
- The consequence classes (D11, D-20261111-f3d39c): the schema's enum is their one owner, spelled as §7.5 lists them.
  `tables/unit_outcome.json`'s promotion row now reads `security`; derive's copy of §6.4 keeps the design's
  `security-relevant` and reads it through a declared rename; CLASS_UNDECLARED fails a promotion row naming a class
  outside the enum.

## Evidence

`stage_judge --self-test` 43 controls, `derive --self-test` 54; the revert trial of the 30 mechanisms above, each
failing by name under its own revert, the base passing.

## Not yet

The packet builder, the template, the stage and its dry run (`distill.py judge`) follow once the packet shape is
decided. Until then `stage_judge.TEMPLATE` names a template that does not exist and nothing calls the stage.
