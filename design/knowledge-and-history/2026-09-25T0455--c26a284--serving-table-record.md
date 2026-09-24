---
created_at: 2026-09-25T04:55:31+09:00
head: c26a284
kind: design
plan: 2026-09-24T0740--a0e289e--development-plan.json
amends: 2026-09-24T2124--0fe13da--conformance-adapter-design.md
decisions: D-20260925-3768a8, D-20260925-3f21bb, D-20260924-f80d5c, D-20260924-3bb074
---

# Serving table landed: layers, a split carrier row, and nothing left answered by the driver without a reason

Stages 1 and 2 of the 21:24 adapter design are in the tree: the serving table, its checks, the
per-row and per-feature closure in `cases.py`, and the review of every step the driver would
answer at every profile binding its case. Doing the review changed the design twice, and the
21:24 record is amended here rather than edited.

## What the review of given steps found

The first run of the table printed 100 steps in 27 cases that the driver would answer at every
profile binding their case. Most are plainly setup — a key bound so that P03's backup has a
principal to belong to. The cases were not judged one by one for which kind each step is: the
rule applied is mechanical (below). But three of them, read in full, showed a shape the design
had no way to say: the refusal the case asserts is not the serving node's, it is a check every
operation passes through.

- `N03-SECRET-NEG`: "While locked, the signed commit ... is not admitted, with access_locked."
  The commit is P03's operation; the refusal is P02's.
- `N03-ENTRANCES-NEG`: old handles are refused at "the owner's admission" on history reads,
  which P03 serves.
- `N01-STORE-NEG`: records are "refused at admission" with their schema codes, on operations
  P02 and P09 serve.

One serving node per operation cannot say that. The owner chose layers (`D-20260925-3768a8`):
every request passes through the access-admission layer (P02) and then the request journal
layer (P03), each only when its node is in scope, and the layers run on a given step too. With
the journal in scope it answers queries, since it holds every result (`D-20260925-3f21bb`,
refining `D-20260924-7e9a10`).

`carrier.bind` moved from P12 to P03. C09 says "a carrier is bound before it is used ... nothing
reaches the network for a carrier that was only selected"; the binding is a local record, P03's
done_when names "exact repository bindings", and P03 is the earliest profile that binds a case
using it. Provisioning and disconnecting, which reach the network, stay with P12.

## What the registry now holds

| | |
| --- | --- |
| serving rows | 91 operations, 2 of them addressed; 2 layers; 16 places; 2 events the runtime receives |
| cases bound at a later profile | 23, each at the earliest profile holding its family where every step is answered by code (`D-20260924-f80d5c`), computed rather than chosen |
| accepted `given` rows | 4 cases, 11 steps, each with the reason no profile holding its family can run them |
| steps the driver answers everywhere without a row | 0 |

The four accepted rows are `N01-STORE-NEG`, `N01-STORE-POS`, `N02-C01-NEG` and `N08-PENDING-NEG`.
N01 is held by P01 and P03 alone; N02 by P02 and M1, neither with P07; N08 by profiles none of
whose scope holds P10. A row that stops matching — a step some profile now answers by code, a
step or case that no longer exists — fails `cases.py check`, so an exemption cannot outlive its
reason.

## Where this departs from the 21:24 record

- **No `addressed` table.** A query goes to the journal layer when in scope, and otherwise to the
  module that served the request it addresses; the entry is derived, not listed, so there is no
  second place to state it.
- **Layers are rows** in the serving table, each with the contract its node must implement.
- **`given` is a registry field**, not a note: accepted steps are data naming their site.

## How the checks were shown to work

Every new check has a test that plants the violation it refuses and requires the refusal by
name, and a positive control that the real table and registry pass clean. Then each guarantee
was reverted in a copy of the tree, one at a time, and the tests were required to fail. The
unmutated copy passed; each of the 20 reverts failed, and each failed on the test written for it:
the missing row, the undeclared row, the contract, the owned path, the implementation kind, the
addressed target, the journal layer, a layer stated twice, an unroutable query, a case on which
no code runs, a stale, missing, unknown or doubled `given` row, an exemption that hides a live
disclosure, transitive scope, a feature module's absence as a value, a serving row, the core, and
the routing of a query to its request's owner.

The first run of that audit reported every revert caught, all in `setUpClass`. Uniform results
were the instrument failing: the copy was not a git repository, so the tests' `git ls-files`
failed before any assertion ran. The audit was rebuilt with a git copy and a positive control
that must pass before any mutation counts.
