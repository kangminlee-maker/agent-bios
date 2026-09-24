---
created_at: 2026-09-24T21:24:42+09:00
head: 0fe13da
kind: design
plan: 2026-09-24T0740--a0e289e--development-plan.json
decisions: D-20260924-f63e31, D-20260924-38ef51, D-20260924-f80d5c, D-20260924-3bb074, D-20260924-7e9a10, D-20260924-f8da36
---

# The conformance adapter: how the driver reaches an implementation, and what P01 freezes of it

`D-20260924-f63e31` moved a family case's verdict into the conformance driver. The driver executes
the case's frozen scenario and judges what the implementation answers. This record designs what
that decision left open: the boundary between the driver and the code under test, and the order
in which the driver learns to execute what scenarios state. It was reviewed adversarially before
it was written here (same-provider; the cross-provider seat was out of credit). That review found
two blockers and three high findings, and each is resolved below or named as open.

## What binds the design

| Source | What it requires |
| --- | --- |
| spec, *Work packets* | P01 freezes "adapter-**contract** fingerprints". It "does not assert that future product adapters ... already exist", and the actual implementation identities "are measured in the appropriate tested subject ... when those nodes run" |
| catalog `profile_rule` | "P01 freezes executable implementations/adapter selectors" |
| C03 | "A result always answers a request its owner holds; an id the owner never received is answered by `request_not_held`" |
| `D-20260922-e5fdae` | the driver reads the world section: processes, clock, partitions, faults |
| `D-20260922-e48992` | a step whose operation belongs to a node the profile neither tests nor depends on is given its stated answer, and its returned records are placed as given state |
| `D-20260922-61e94c` | public keys and `sshsig` in a scenario stand for what the driver's own key makes at run time |
| `D-20260923-1966f3` | a joined case runs against an accepted predecessor's real files |
| `cases.py` | a fingerprint "moves with what it names and nothing else" |

The frozen side is the driver, the scenario bytes, the contracts and the contract of the boundary.
The implementation side is measured in the node's subject when the node runs.

## 1. One serving table, keyed by operation

The contracts declare 91 operations. Every one is driven by some scenario step, and 75 are driven
by steps in more than one family: `identity.binding.add` by 33, `team.found` by 27. A connection
per family module would restate most operations many times. So the connection is one table
(`D-20260924-38ef51`):

    gates/workenv/conformance/serving.json
    operations   operation -> {node, entry}                   one row per declared operation
    addressed    node -> {operation.query | operation.cancel -> entry}
    places       node -> entry                                 given records land here
    events       event kind -> {node, entry}                   where the runtime receives one

The catalog's family `path` modules leave the verdict path. They remain those families' ordinary
test files, run by `check-workenv.py`. The `CASES` machinery in `driver.py` is deleted, not left
beside the new route as a second route.

**Addressed operations** (`D-20260924-7e9a10`). `operation.query` and `operation.cancel` target a
request. They go to the node that serves the operation of the scenario step whose request carries
that id, wherever that step sits, through that node's `addressed` entry.

**Scope and given steps** (`D-20260924-3bb074`). A profile's scope is its node and every node that
node transitively depends on. A step whose serving node is outside the scope is given: the driver
answers it with the stated answer and hands its returned records to the `places` entry of each
in-scope node, on the step's own process. A verification profile's scope is its whole predecessor
closure. `scenarios.py`'s docstring is aligned to this reading in the same change.

**Before the first step** the driver brings a new profile to the access generation the first
request states, through restrictions and re-entries of its own (`scenarios.py`). Those are
given as well.

`cases.py check` fails by name on:

- a declared operation with no row, or a row for none;
- a row whose node is not an implementation node, or whose node's plan `contracts` lack the
  operation's contract;
- an entry whose module path is not under that node's `owned_paths`;
- an addressed step whose target id no step of its scenario carries;
- a node serving an operation some addressed step targets, with no `addressed` entry for it;
- **a case with no submitted step at a profile that binds it** (`D-20260924-f80d5c`).

It also **discloses**, without failing, every step that is given at every profile binding its
case. Which of those are setup and which are the point of their case is a judgment. It is made
once over the whole list, and each row is resolved in the registry, by binding the case at a later
profile where the step is submitted. `N03-SECRET-NEG` is the first such row. Its signing steps are
`source.revision.commit`, served by P03, so at P02, its only binding, the driver answers them itself.

## 2. The entry: one call per step, over the contracts' own records

An entry is a Python callable `entry(call) -> answer`. It is imported inside a host process that
the driver starts for each world process. A scenario without `world.processes` has one implicit
process. The call carries:

| attribute | meaning |
| --- | --- |
| `request` | the `operation_request`, every minted value and digest filled in |
| `carried` | the step's carried records, in order |
| `members` | source member bytes by sha256 |
| `now` | the step's instant under a world clock, else `None` |
| `state` | the process's state root; everything the implementation keeps durably is under it, and a restarted process is given the same one |
| `exchange` | a directory the driver moves bytes through between processes by digest (a backup taken on one process and restored on another, a package staged on one and accepted on another) |
| `point(name)` | the fault hook, called on passing each B03 `FAULT_POINTS` name |
| `admitted()` | the admission hook, called once after the request is admitted and before any effect |

The answer takes one of two shapes:

- **Answered:** `{"result": operation_result, "returned": [...], "receipt": record | None}`.
- **Refused:** `{"refused": [{"record", "code", "pointer"}, ...]}`, the same triples a refused
  step states. A refused call must not have called `admitted()`.

The implementation never imports from `gates/`; the call object is duck-typed. In production
the same entries are called with hooks that do nothing. Whether the hook obligations should also
be declared in `workenv/contracts/`, so that both halves of the boundary sit in the frozen
contracts, is open: that edit moves the `contracts` subject.

**Why hooks rather than environment variables.** The host implements `point` and `admitted`, so
the implementation cannot implement them wrongly; it can only fail to call them, and that is
decidable. A fault armed on a step whose process answers anyway is `failed`, and the report names
both the fault and the step. The same holds for `admitted` under `during`.

**Faults.** When the armed point is reached the host process dies, and the driver records a dead
call, distinct from an answer. Without `observed_by`, the driver restarts the process on the same
state root and resubmits the same request; that answer is the step's. With `observed_by`, it does
not resubmit. The step's minted values are learned at the observing step, which returns
`<step>_result`, not at the step `minted[].step` names.

## 3. Features are modules, and a fingerprint holds only what its profile uses

Beyond a plain answered step, scenarios use 19 features:

- five world features: processes, clock, faults, partitions, during;
- nine event kinds;
- replays, `receipt_of`, runner situations, routes and signing.

Each is one module under `gates/workenv/conformance/features/`. `cases.py` derives each case's
features from its scenario, the way it already derives operations and contracts. A profile's
adapter fingerprint covers:

- the core: `driver.py`, `executor.py`, `host.py`, `rules.py` (it applies the rule oracles) and
  `subjects.py` (it verifies joined predecessors), which every family case runs;
- the feature modules its cases use;
- the serving rows its cases' operations, addressed targets, places and events use, each hashed
  on its own;
- the contracts, the reader and the filled commands, as today.

A feature with no module yet is `blocked` by name. A negative control plants a feature into a
scenario and requires its module to appear in that profile's fingerprint, because a derivation
miss would narrow a closure silently.

**What this protects, and what it does not.** Adding a feature module later moves only the
profiles that use the feature, and those were blocked on it, so none of them was accepted. An
**edit** is not protected in the same way. An edit to the core, the generator (`scenarios.py`
and its schema are in every case's fixtures), the reader, `rules.py`, or a serving row moves every
profile that uses it; a row for `identity.binding.add` reaches 33 families. `D-20260924-f8da36`
accepts that cost for the re-freeze ahead. It is not eliminated.

## 4. What the core does with one step

1. Build the request and carried records. Each minted stand-in is replaced by the value the owner
   actually returned, where `joins` places it, and every digest and size `joins` derives is
   recomputed.
2. Decide from the serving table whether the step is given, submitted, or addressed.
3. If the step is submitted, call its process and receive an answer, a refusal, or a dead call.
4. Learn each minted value at its first place in the answer, and refuse any later place that
   disagrees with it.
5. Compare the answer with the stated one. Minted places are filled from what was learned, and
   digests are recomputed over the actual bytes. The first difference is `failed`, and the report
   names the step, the record and the JSON pointer.
6. A refused step must be refused with exactly the stated triples, and without `admitted()`.

A replay resubmits the earlier step's request bytes and expects its result and receipt. A
`receipt_of` answer expects the earlier step's receipt and no new one.

## 5. Signing and key material

The driver generates one ed25519 key for each distinct stand-in public key in a scenario, and
replaces that stand-in everywhere before the first step. It signs each `signature_envelope`'s
`signed_digest` under its `namespace` with the key of the binding `signer_binding_id` names
(`ssh-keygen -Y sign`). It does this when the envelope is first submitted, and also when it places
an envelope as given state, so a placed envelope is never left with a stand-in signature. For a
`key_layout` event the driver materialises the files and agents the layout names from those same
keys, because under `owned_agent` it is the runtime that signs. Receipts carry no signature, so
verifying one needs no driver key.

## 6. Joined cases

For a joined case, only imports under the joined predecessor's accepted-subject paths are held
against the verified member map before they run. A file there that is missing from the map, or
that has a different sha256, stops the case as `failed`, naming the path. Everything else, such as
the contracts and the running node's own modules, resolves from the tree. The running node's own
subject measurement covers those files. `--subject-root` stays refused.

## 7. How the executor is shown to work before any product exists

A scripted owner in the driver's tests answers every request-bearing step with the scenario's
stated answer, minting fresh values of each stand-in's shape.

- **Positive control:** every scenario's request-bearing steps, all submitted to the scripted
  owner, come out `passed`. Runner and route steps are exercised with their own features.
- **Negative controls:** there is one per core rule and one per feature. Each plants a single
  difference and requires `failed` naming it, for example:
  - a principal id that moves after rotation;
  - a refusal code swapped;
  - a fault that never fires;
  - a digest computed over the wrong bytes.
- **Revert check:** each control is then shown to fail against a faithful revert of the rule it
  protects.

## 8. Order, and the one re-freeze

1. The serving table, its checks and disclosure, the per-row and per-feature closure in `cases.py`,
   and the `scenarios.py` docstring.
2. The disclosure reviewed, and the registry rows it resolves.
3. The core, the host, given steps and placement, addressed routing, signing, replays and
   `receipt_of`.
4. Clock, faults, during, processes, partitions and the exchange directory.
5. The nine event kinds.
6. Runner situations and routes.

After that, P01 is re-frozen once (`D-20260924-f8da36`). The spec successor that restores
"implementation acceptance" to its reading of the S11 header is published in the same step.

## Open

- **Hook obligations in the contracts.** Whether to declare them in `workenv/contracts/` (§2).
- **Provider and carrier doubles.** Their seams (`provider_refresh`, `reply_lost`,
  `carrier_reports`) are designed with stage 5.
- **Routes.** They submit through a shipped entrance rather than an entry, and are designed with
  stage 6.
- **Whether `members` by digest is enough** for an implementation that reads a checkout by path.
  This depends on product APIs that do not exist yet.
