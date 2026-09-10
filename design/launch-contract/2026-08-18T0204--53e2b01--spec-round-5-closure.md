---
created_at: 2026-08-18T02:04:00+09:00
head: 53e2b01
kind: review
supersedes: 2026-08-18T0131--53e2b01--spec-round-5-findings.md
---

# Spec round 5 — closure

One code violation and two specification defects, from
`…T0131--53e2b01--spec-round-5-findings.md` against the third revision of the spec
instrument (`…T2310--11ed16b--review-evidence-invariants.md`).

The code finding is closed at the authority with a named control. The two spec defects
are **proposals only** — the spec is a dated record and is not edited here.

## L7 (High) — an MCP registration's NAME changed argv and no line of the contract

**The finding.** A selected MCP capability's name becomes the backend's
`mcp_servers.<name>` namespace in argv, and neither the human contract nor the
`ReviewPlan/v1` record stated it. Renaming only the capability therefore produced
different argv under a byte-identical contract, while the contract's own tail promises
that what is described there is what runs.

**Reproduced before the fix**, with the reviewer's own probe (the resolved path differs
from the record's only because this machine's `claude` resolves through a different PATH
entry; the shape is identical):

```
mutation (capability renamed):  contracts_equal=True  argv_differ=True
                                a=[mcp_servers.ultracode.*]  b=[mcp_servers.alias.*]
control  (same identity, command changed): contracts_equal=False argv_differ=True
```

**Fixed at** `launch/agent-launch.py`:

- `review_mcp_servers` now returns the whole registration — `(name, command, args)` —
  instead of a pair with the args read from a module constant at the argv site. A third
  of the registration was outside the value anything could be generated from.
- `run_contract` renders that value into the contract prose (`Review MCP registrations,
  in the order the backend receives them (server name = command args): …`), and both argv
  builders (`project_args`, codex `-c mcp_servers.*` and claude `--mcp-config`) consume
  the same function's output. The names are not reconstructed a second time — the
  host-disambiguation rule that can generate a name no author wrote lives in one place,
  and the contract states whatever that rule produced.

After the fix the reviewer's mutation reads `contracts_equal=False argv_differ=True`, and
the control is unchanged at `contracts_equal=False`. Deleting the new clause from both
contracts of the mutation pair restores byte-identity, so the clause is the only
difference and it carries the rename.

**Control** added to the check the finding names, `launcher_review_contract` in
`gates/check_parity.py` — the capability-rename twins the existing mutations were missing
(they vary method removal, effort and resolved command, and hold the capability identity
fixed). On **both** hosts, because the two argv shapes are built separately:

| Assertion | What it catches |
| --- | --- |
| vacuity: both twins register at least one server | an empty subject set satisfying everything |
| nearest control: the same config projected twice renders one contract | grading nondeterminism as "the rename moved it" |
| the rename must move the registered names in argv | an inert mutation |
| argv names moved ⇒ the contract must differ | **L7 itself** |
| every registered `(name, command)` is stated in the contract | a contract that moved for an unrelated reason |
| `rename_cases == 2` | the case going quiet on one host |

`contract_cases` floor raised 5 → 7 to match.

**Revert-proven.** With the fix faithfully reverted (the clause no longer reaching
`prose`, everything else intact) the control fails by name, six times:

```
FAIL: … renaming the capability moved the registered server names on claude
      (['gate-mcpkit'] -> ['gate-renamedkit']) and left the contract byte-identical …
FAIL: … the baseline projection on claude registers 'gate-mcpkit' at '…/vendor-mcp',
      and the contract does not state its name
… and the same three on codex.
```

**What the revert taught.** The first draft of the reconciliation assertion said "which
the contract does not state" for a missing name *or* a missing command. The revert showed
it firing on the baseline too — and the reason mattered: the command already reaches the
contract through the method's instruction template, so the half that was actually missing
was the *name*, and the message could not say which. A control whose message covers two
different failures is graded by whichever fires first. The assertion now names the missing
half, and the revert output above is what proves the distinction is real rather than
asserted.

**Decision recorded.** `D-20260818-7ad546` (design) — the registration is stated as
contract prose generated from the one projection, closing (a) adding it to the
`ReviewPlan/v1` record and (b) reconstructing the names inside `run_contract`. The names
depend on plan-level data the `ReviewReport` does not carry, so a record field would need
the closed grammar widened, a new inverse, and a value receipt adjudication would compare
against something no reviewer certifies — the registration is a fact about argv, not about
a reviewer's seat.

## Spec amendments proposed

The spec file is a dated record and was not edited. Both defects are in the specification,
not the runtime; the runtime is internally consistent on each.

### D4 — the self-contradiction on packet binding

The current text says the anchor "must be bound to real bytes" and that verification "must
receive" the packet, then permits no packet with disclosure in the same sentence; the
checklist separately calls "a digest bound to no bytes" a violation, which makes the
permitted path a violation.

**The recommended reading is the permissive one**, and this is a wording repair rather than
a design change: the disclosure path was decided deliberately in spec round 1
(`D-20260817-c3a9f0`) and the runtime implements exactly it — `exit=0`,
`achievement=complete`, `packet_binding=none — … bound to no bytes`. Exact replacement for
the D4 bullet:

> - **D4 — Packet consumption.** The receipt's `packet_sha256` is canonical hex and equals
>   the bundle's anchor; absence is refused before equality. Whether that anchor is bound to
>   real BYTES is a disclosed property rather than a condition of achievement: fold hashes
>   the packet *file*, so a bundle is written bound. Verification is offered the packet
>   independently (`--verify-receipts --packet`), and when it is supplied it must recompute
>   the digest and check the embedded plan is the plan being adjudicated. When it is not,
>   the packet-less path is the norm and not a violation — achievement and exit status are
>   unaffected — and the verdict must render `packet_binding=none`, naming the digest as
>   bound to no bytes (spec round 1, `D-20260817-c3a9f0`). "Must receive the packet" binds
>   only a verification that CLAIMS byte binding. Packet retention is Q3.

Exact replacement for the checklist entry (§5, Dispatch):

> · D4 packet check passing on absence or non-hex equality; a supplied packet whose digest
> or embedded plan is not re-derived; a packet-less verify that claims
> `packet_binding=bytes`, or renders no binding line at all

**The alternative, stated neutrally.** If "must receive" is meant literally, then a
verification without `--packet` may not reach ACHIEVED: the spec would instead say a
missing `--packet` forces PROPOSED and a nonzero exit. That is a **design change**, not a
wording repair — it makes byte binding a precondition of achievement rather than a
disclosed property, it overturns `D-20260817-c3a9f0`, and it changes the exit status of a
path that exists today. It is **not implemented here.** Whichever reading is adopted,
`launcher_receipts` needs a case pinning the *exit and achievement* of the packet-less
path: it checks the disclosure line only, so it cannot currently tell the two readings
apart, and today's behavior would satisfy the permissive spec and violate the strict one
without any check noticing.

### S4 — universal saveability contradicts S6

S4 says every profile the launcher accepts must remain saveable; S6 requires mission/trigger
and routed plans to be refused at save. The runtime is consistent — `save_preset` and
`preset_save_round_trips` deliberately enforce S6 — so the defect is the S4 sentence.
Adopting the reviewer's minimal fix; exact replacement for the clause inside the S4 bullet:

> the complement holds — except for S6's routed-content refusals, every non-routed profile
> the launcher accepts remains saveable; any other refusal names the genuinely unwritable
> entry (D-20260817-105da4, -53c588, -25a972, -89fc58) —

Exact replacement for the checklist entry (§5, Save):

> S4 a drop or default without a named refusal; a non-routed launchable profile refused

## Round-4 closure replay

Reported by the reviewer as held, all three: the L2/L3/V2 evidence grammar, F2 marker
presence, and the V2/V7 controls registry, each reached through both parsers and both
adjudication sides. Nothing in this round touched them.

## Verification

| Check | Result |
| --- | --- |
| `check_parity.py` (62 checks, full) | exit 0 — `LAUNCH/BINDINGS OK` |
| `launcher_review_contract` with the fix | pass |
| …faithfully reverted | FAIL by name ×6 (both hosts, both assertions) |
| …restored | pass |
| `capture-review-goldens.py --check` | 121 cells, 0 control failures |
| `capture-review-goldens.py --self-test` | 10 controls each proven to fire |
| `check-surfaces.py` | 13 surfaces, 35 authority paths live |

**Golden movement, proven by inverse transformation.** Two fields changed, both the
`contract` of the one scenario carrying an `mcp-stdio-v1` adapter:
`composable/local-registry/claude` and `composable/local-registry/codex`. Stripping the new
clause from every string of the re-captured golden reproduces the pre-change file exactly
(`inverted == pre-change golden: True`), and the inverse transformation is not vacuous —
it removed 2 occurrences, and a planted cell still survives it, so it can see a difference
that is not the clause.
