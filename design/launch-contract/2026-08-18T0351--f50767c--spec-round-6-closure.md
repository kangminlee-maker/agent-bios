---
created_at: 2026-08-18T03:51:00+09:00
head: f50767c
kind: review
supersedes: 2026-08-18T0306--f50767c--spec-round-6-findings.md
---

# Spec round 6 — closure

Two code violations, from `…T0306--f50767c--spec-round-6-findings.md` against the fourth
revision of the spec instrument (`…T0235--3328cb8--review-evidence-invariants.md`). No
specification defects were reported and none is proposed here.

Both are twins of shapes closed in earlier rounds — L7's is the round-5 MCP registration
one projection later, F3's is round 4's multi-pass faithfulness applied to the group size
round 4 did not vary. Each is closed at the authority with a named control.

## L7 (High) — the child agent-template projection changed argv and no line of the contract

**The finding.** A Codex tier's agent template decides the `description` the backend is
handed AND, through the digest that names the child config directory, the `config_file`
path it reads that child's binding from. The contract recorded only the child's
model/effort, so repointing one tier at another tier's template produced different argv
under a byte-identical contract.

**Reproduced before the fix**, with the reviewer's own probe and control:

```
mutation (sweep repointed at frontier.toml):  contracts_equal=True  argv_differ=True
    a=agents.sweep.description="Cheap read-heavy scans, …"  …/7220d4cb9eec4821012a/sweep.toml
    b=agents.sweep.description="Bounded hardest decisions, …" …/f0145feda407671dd3ba/sweep.toml
control  (repointed at its own path, respelled): contracts_equal=True argv_differ=False
```

**Fixed at** `launch/agent-launch.py`:

- `child_agent_registrations(plan)` is the projection — pure, writing nothing — returning
  `(tier, description, config path, config content)` per spawnable tier in the order the
  backend receives them. It is everything `codex_agent_configs` used to decide privately,
  lifted to a value.
- `codex_agent_configs` is now only the materialiser: it takes the projection, takes the
  cache root from the first path, and adds the bytes and the failure modes writing them
  has. Nothing about *what* is registered is decided there any more.
- `run_contract` renders that same value (`Codex child agent registrations, in the order
  the backend receives them (tier = description at config file): …`), and `project_args`
  reaches it through `codex_agent_configs`. One producer, three consumers — the round-5
  shape.
- The projection refuses an empty registration set. `SPAWNABLE_TIERS` is a constant, so it
  fires only if someone empties it — which is exactly when one empty list would silently
  satisfy the contract clause (states nothing), the reconciliation (nothing to find), and
  leave the materialiser with no path to take a cache root from.

After the fix the mutation reads `contracts_equal=False argv_differ=True` and the control
is unchanged at `contracts_equal=True argv_differ=False`.

**The clause is the only difference, proven by inverse transformation on the pair.**
Stripping the new clause from both contracts of the mutation pair restores byte-identity
(`stripped contracts identical=True`), and the strip is not vacuous (`strip(ca) != ca`).

**Why the full path and not the description alone.** A template edit that changes content
without changing the description — the digest's whole subject — moves every `config_file`
in argv and nothing else. Measured directly: with a same-description restatement,
`descriptions_equal=True argv_differ=True contracts_differ=True`. Recorded as
`D-20260818-18a8be`, closing "state the descriptions only, or a bare content digest".

**Why codex only.** `claude_agents` derives every field from the tier, model and effort the
contract's `tiers:` clause already states, so no authored value reaches claude's `--agents`
except through that clause. Measured on the same mutation: `CLAUDE SCOPE:
contracts_equal=True argv_equal=True`. Recorded as `D-20260818-7fa9ed`, closing "render a
child clause on claude too". The scope is asserted by the gate rather than assumed.

**Control** added to the check the finding names, `launcher_review_contract` in
`gates/check_parity.py` — the child-template twins the existing mutations were missing
(they vary method removal, effort, resolved command and capability name, and hold the child
templates fixed). Two cases, on synthetic templates in a directory of the check's own:

| Assertion | What it catches |
| --- | --- |
| the fixture rewrite really repointed `[hosts.codex.agent_templates]` | the whole block running against the machine's own templates, inert, wearing green |
| vacuity: every registered child carries BOTH a description and a config file | a half-empty set satisfying the reconciliation |
| nearest control: the same config projected twice renders one contract | grading nondeterminism as "the mutation moved it" |
| the mutation must move what the backend registers | an inert mutation |
| registrations moved ⇒ the contract must differ | **L7 itself** |
| every registered `(tier, description, config file)` is stated in the contract | a contract that moved for an unrelated reason |
| `child_cases == 2` | either half going quiet |
| the same repoint moves neither claude's argv nor its contract | the codex-only scope silently becoming a hole |

`contract_cases` floor raised 7 → 9 to match.

**Revert-proven, twice.** With the fix faithfully reverted — `child_clause` no longer
reaching `prose`, everything else intact — the control fails by name **14 times**: both
cases' "moved what the backend registers … and left the contract byte-identical", and every
row of both reconciliation loops.

The second revert is the one that taught something. Rendering **descriptions only** and
dropping the paths — the alternative `D-20260818-18a8be` closes — leaves case 1 (a
description-moving repoint) passing L7's own inequality assertion, because the description
alone moved the contract; only the reconciliation fires, naming the missing half ("and the
contract does not state its **config file**"). Case 2, the same-description restatement,
fails on `left the contract byte-identical` — **one** occurrence across the whole check,
and it is the content-digest case. So the two cases are not redundant: a plausible partial
fix passes the first and is caught only by the second, and that is proven by the revert
rather than argued from the code.

## F3 (Medium) — a singleton fold omitted its pass set

**The finding.** `_merge_method_passes` returned a valid lone receipt unchanged, so the one
record the method is judged on carried no `passes` — the fold's own output, the place where
"one process ran" becomes "one pass is evidenced", absent for the commonest group size.
Round 4 made the multi-pass record faithful; this is its twin, and F1 already says the
per-pass bar is asked of each receipt "singleton included".

**Reproduced before the fix**, with the reviewer's probe (`has_passes=False; passes=None`)
and control (two valid passes, `has_passes=True` with both digests).

**Fixed at** `launch/agent-launch.py` `_merge_method_passes`: the `if len(group) == 1:
return group[0]` early return is removed. The agreement loops below it are vacuously true
over one receipt and cost nothing; the common merge path assigns `passes` after the raw-pass
validation, and for a lone receipt it is naturally the one-element set.

Measured on the finished tree: `passes == [result_sha256]`, the folded record keeps the
receipt's identity and payload, every other key is byte-identical to the input, the input
dict is not mutated, and a lone failed pass still propagates its exit status with `passes`
as the only key added.

**Downstream readers checked (Q4).** `passes` has exactly one adjudication reader,
`_receipt_reason`, behind `if required_passes > 1`. Probed directly:

| Input | Verdict |
| --- | --- |
| folded singleton, `trials=1` | `''` — accepted; the new key is inert, as Q4 predicted |
| folded singleton, `trials=2` | `evidences fewer than the 2 requested passes` — refused |
| raw receipt (unfolded, no `passes`), `trials=2` | `carries no pass list, …` — refused |

The refusal of a one-receipt group under `trials=2` therefore **survives with a different
message**: it used to say "carries no pass list", and now says "evidences fewer than the 2
requested passes", because the record now has a pass list with one entry in it. The new
message is the accurate one, the old branch is still live for a raw receipt arriving at the
adjudicator without a fold, and no live gate asserts the old needle — it appears only in two
dated findings records, which are history and not edited.

`_raw_receipt_reason` still refuses the folded record as a raw one, so the phase separation
the round-1 fix installed is untouched.

**D7 does not interact.** D7 binds `passes` "for `trials > 1`" and that scope is unchanged —
the singleton now satisfies **F3**, which asks for the set of per-pass result digests with
nothing filtered, and says nothing about a trial count. The spec is a dated record and was
not edited; no amendment is proposed.

**Control** strengthened at the exact place the finding names, `launcher_receipt_fold` in
`gates/check_parity.py`. Its singleton positive control asked only for the dispatch id and
the primary digest — both of which an *untouched* receipt has by construction, so it could
not tell a folded record from an unfolded one, which is why it accepted the defect. It now
additionally requires `passes == [result_sha256]`, by value: presence alone is satisfied by
any list, and the one thing a one-pass fold means is that the set is exactly the receipt's
own result.

**Revert-proven.** With the early return restored, the control fails by name:

```
FAIL: agent-launch fold of a lone pass omits its pass set: passes=None, want
      ['7692c3ad…'] — the folded record is what the adjudicator reads passes off, and a
      singleton that skips the merge evidences no pass at all
```

## Spec amendments proposed

None. Neither fix forced one, and the D7 reading above needed no widening.

## Verification

| Check | Result |
| --- | --- |
| `check_parity.py` (62 checks, full) | exit 0 — `LAUNCH/BINDINGS OK` |
| `launcher_review_contract` with the fix | pass |
| …with `child_clause` removed from `prose` | FAIL by name ×14 (both cases, both loops) |
| …with descriptions rendered and paths dropped | FAIL by name; `left the contract byte-identical` ×1, on the content-digest case |
| …restored | pass |
| `launcher_receipt_fold` with the fix | pass |
| …with the singleton early return restored | FAIL by name |
| …restored | pass |
| `capture-review-goldens.py --check` | 121 cells, 0 control failures |
| `capture-review-goldens.py --self-test` | 10 controls each proven to fire |
| `check-surfaces.py` | 13 surfaces, 35 authority paths live |
| `check-ontology.py` | 38 entities, 49 edges, 9 kinds |
| `check-lexicon.py` | 337 files scanned, 14 tokens enforced, 9 concept homes held |
| `record-decision.py --check` | 103 records, ids content-bound |
| dry-run `--config launch/agent-launch.toml` on codex / claude | exit 0 / exit 0; the clause renders on codex and is absent on claude |

**Golden movement, proven by inverse transformation.** 121 cells before and after, the same
keys. Stripping the new clause from every string of the re-captured golden reproduces the
pre-change file exactly (`inverted == pre-change golden: True`), removing **28**
occurrences, and the inverse transformation is not vacuous — a planted change in a cell
survives it, so it can still see a difference that is not the clause.

The 28 are every codex cell that delegates and nothing else: 16 legacy `codex/**/deleg-on`
cells plus the 12 composable and shipped `*/codex` cells. No claude cell moved, which is the
codex-only scope read off the artifact rather than off the code.
