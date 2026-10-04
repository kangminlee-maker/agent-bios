---
created_at: 2026-10-04T21:04:29+09:00
head: 1fd0843
kind: review
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V2
supersedes: null
decisions: D-20261004-b0636e, D-20261004-0bb8e6, D-20261004-64847d, D-20261004-24368a
---

# What a cross-provider review of V2's first slice found, and how each finding was repaired

This records the review of `1fd0843`, the commit that made SRC-10 and SRC-11 run and pass, and the
repairs that followed. Three reviewers from another provider each answered one set of questions:
the driver, the product, and the scenarios. Every finding was reproduced here before it was
repaired. It accepts nothing.

`2026-10-04T1904--e47c640--v2-several-checkouts-record.md` describes `1fd0843`. Four of its
statements no longer hold, and are corrected under "What the earlier record got wrong".

## The review

- **Scenarios.** No defect. The reviewer found the four scenario corrections justified and the
  case and binding accounting reproducible. It also noted two wording points, below.
- **Product.** Nine findings, P1 to P9.
- **Driver.** Six findings, D1 to D6.

All fifteen were reproduced in a clean copy of `1fd0843` with the reviewers' own probes, except
P3, which was confirmed by reading the code and then by a new test, and D6, which the reviewer
demonstrated by building the case.

## The product findings

- **P1 — identical bindings moved a home's checkout.** A binding's bytes do not name its checkout.
  Two checkouts on the same remote, branch, HEAD and working bytes therefore make the same
  binding. The second replaced the first in `binding_checkouts`, so a home on the first checkout
  read and wrote the second.
  - Repair (`workenv/sources/checkouts.py`). A binding is kept as made in the first checkout that
    made it. `checkout_for` reads that checkout while it still holds the binding. Where it has
    since been bound again to something else, it reads another checkout that holds the binding
    now, the one bound first.
- **P2 — an admission ignored the source's home.** `source.revision.admit` read the checkout the
  repository was bound from last, even for a source whose home names another checkout.
  - Repair (`revisions.py`). For a source already held, an admission reads the checkout its
    home's binding was made from, as a commit does.
- **P3 — the entry named the wrong branch.** The entry's location label read the branch of the
  checkout bound most recently, not the one the entry was opened in.
  - Repair (`workenv/tui.py`, `commands.py`). The label reads the checkout the entry is opened in,
    where that checkout is bound to the repository, else the one bound most recently.
- **P4 — a member path the contract cannot state.** A tracked file named `결정.md`,
  `with space.md` or `a:b.md` under a document root was published as a manifest member that C01's
  own manifest schema rejects.
  - Repair (`workenv/memory.py`), by the owner's choice. The publication is refused with
    `manifest_member_unlisted` at that path, and nothing is written. The contract is not widened
    now.
- **P5 — a revision read through a symbolic link.** A revision commit read a tracked link as the
  file it leads to. A manifest stating bytes outside the checkout was committed.
  - Repair (`revisions.py`). A revision reads a file as git keeps it: a link is the path it holds.
- **P6 — a dangling link read as drift.** A published link whose target does not exist read as
  changed at once, because the drift check asked whether a file was there.
  - Repair (`workenv/roles.py`). Drift reads the member as it was published.
- **P7 — committed records were overwritten.** Where a repository already had a committed
  `records.jsonl` and this installation held no revision naming it, the first publication wrote
  a new file over it.
  - Repair (`memory.py`). The first publication extends the member as git has it committed.
- **P8 — a fork wrote its original's sources.** Only `reference.resolve` refused a fork. A
  request owned by a fork bound only to derive its own authority could publish records, register
  a home, commit or admit a revision, and resolve state on the original's sources.
  - Repair (`workenv/sources/homes.py` and the operations). A request whose owner is a repository
    bound as a fork of the source's repository writes none of that source, under either fork
    relation. It reads the source only where it is bound to read the original through the fork
    (`fork_original_read`). `source.home.register`, `source.revision.commit`,
    `source.revision.admit`, `memory.record.publish` and `memory.lifecycle.apply` refuse it;
    `reference.resolve` and `memory.state.resolve` refuse it unless bound to read. Each answers
    `repository_binding_required`.
- **P9 — a read below a linked directory.** A tracked file below a directory replaced by a link
  to somewhere outside the checkout was read and published.
  - Repair (`checkouts.py`). A path below a directory that is a link holds nothing, as git reads
    it. Observation, publication, revision and drift all read through one function,
    `held_bytes`.

## The driver findings

- **D1 — steps ran in the wrong checkout.** A home and a manifest were not attributed to a
  checkout, so the steps returning them fell back to the first. SRC-11 registered and published
  S's source from R's checkout. SRC-10's two fork refusals ran in the clone.
  - Repair (`features/checkout.py`). A repository-authored home speaks of the checkout its binding
    was made in, and a manifest of the checkout its source's first home rests on. A step whose
    records speak of no checkout works in the one checkout of the repository that owns its
    request, or that a record it carries works in (`work_scope`). That last covers DC-KEEP's link
    and use in its second repository, which the person's own requests carry.
- **D2 — a removed checkout read as blocked.** If the code under test removed a checkout, the
  next step's directory could not be entered, and the host reported `blocked`, as if the driver
  lacked a feature.
  - Repair (`conformance/host.py`). The driver built every such directory, so the step fails by
    name.
- **D3 — the branch switch left the old index.** Editing `.git/HEAD` changed the branch but left
  the index tracking the removed ADR. An implementation reading the index could pass here and fail
  after a real switch.
  - Repair (`features/checkout.py`). Once the edits before a step have rewritten `.git/HEAD`, the
    index is reset to the new HEAD's tree, as `git switch` leaves it.
- **D4 — any minted size read as a file the code writes.** An observation-only scenario with a
  minted read size lost that file from its first state, and the test double created it during a
  read.
  - Repair (`features/checkout.py`). A manifest member whose size is minted names a file the code
    writes, and so does another record's read of a file by that same minted size. Nothing else.
- **D5 — the test double did not check what it was sent.** It accepted a request carrying a
  value the scenario joins to something else, so a driver that dropped a join passed.
  - Repair (`scripted_owner.py`). The double holds each request and carried record to the values
    it minted, and to the digest of each record whose values it holds, wherever the scenario joins
    one. Another value fails the step by name.
- **D6 — the fork's commit correction was not needed.** `1fd0843` gave SRC-10's fork a commit of
  its own, on the grounds that the fork's files differ from the clone's. They differ only in
  modified and untracked files; the fork can share the clone's HEAD, as the scenario first said.
  - Repair. SRC-10's spec states the clone's commit for the fork again. The driver builds a
    checkout sharing a commit with one built before it as a clone of that checkout (a worktree is
    added at HEAD). Its committed files are the commit's and must match what its records state,
    and only its modified and untracked files are its own. What disagrees is blocked by name.

## The scenarios reviewer's two notes

- C01 makes a binding's branch and commit optional, and a detached HEAD has no branch. The
  earlier record said "a real checkout has both"; it has a commit, and a branch unless detached.
- SRC-11's two repositories hold equal trees, so a real build can give them one commit. Each
  binding states a stand-in of its own, the driver replaces each with its own checkout's HEAD,
  and nothing in the case depends on the two differing.

## What the earlier record got wrong

`2026-10-04T1904--e47c640--v2-several-checkouts-record.md` is not edited. These statements in it
are superseded here:

- "SRC-10, the fork's commit … its HEAD cannot be that commit." It can (D6), and the spec states
  the clone's commit again.
- "one commit stated for two" is no longer blocked. Two commits stated for one checkout before a
  switch are, and so is a sharing checkout whose committed files disagree with the commit.
- "A file a record states whose size the owner mints is one the code writes, whatever record
  states it." Narrowed by D4.
- "Limit. Only `reference.resolve` checks this." Every write and both resolves now check it (P8).

## Decisions

- `D-20261004-b0636e` — P4: a member path the contract cannot state refuses the publication at
  that path. Closed: widening C01's member path pattern now. Revisit when a team needs such names
  under a document root.
- `D-20261004-0bb8e6` — P8: a fork writes none of its original's sources under either relation,
  and reads them only under `fork_original_read`. Closed: refusing only `reference.resolve`;
  letting a read binding write.
- `D-20261004-64847d` — D6: SRC-10's fork shares the clone's commit, and the driver builds a
  checkout sharing a commit. Closed: a commit stand-in of the fork's own.
- `D-20261004-24368a` — P1: identical bindings stay with the first checkout that made them.
  Closed: the last maker taking over; putting the checkout into the binding's bytes.

## What was checked

- **Negative controls.** Each repair was reverted alone, the named tests were run, and the file
  was restored; the working tree's diff was the same before and after. Each failed by name:

  | Reverted | Failed |
  | --- | --- |
  | P1: the first maker always kept; the last maker taking over | one `Places` test each |
  | P2: an admission reading the newest checkout | the `Places` admission test |
  | P3: the label ignoring where the entry opens; the command passing no directory | the `Places` entry test; the `test_commands` entry test (`feature-backups`, not `main`) |
  | P4: no check of member paths | its three sub-tests |
  | P5, P6, P7, P9 | one `AsGitHoldsThem` test each |
  | P8: each `as_fork` call alone; a read binding opening writes; no read ever refused | the fork write test (each write, the lifecycle event included), the state test, the resolve test; SRC-10 at `refuse_the_fork_read_as_its_original` for the resolve |
  | D1: homes and manifests; request owners; carried records' `work_scope` | SRC-11's attribution test; the three-checkouts test; the DC-KEEP test |
  | D2: the host replying `blocked` | the host test |
  | D3: no index reset | the branch-switch test |
  | D4: any minted size a written file | the minted-read test |
  | D5: the double trusting what it is sent | the dropped-join test, at `register_s/payload_digest` |
  | D6: the fork not shared; size, pinned content, git state, two commits, a worktree sharing another checkout's commit, each unchecked | the three-checkouts test; one blocked-by-name sub-test each |

  Six controls first passed: the command's directory, the attribution of homes and manifests,
  the minted read, pinned content, two commits, and the worktree's base. Each got a test, and
  each test was shown to fail on its reverted repair. Without the worktree's guard, the later
  commit check still blocks that world, under a less precise message.
- **Where each step works**, across all 162 scenarios, against `1fd0843`. The steps that moved to
  another checkout are the ones D1 named: SRC-10's two fork refusals (to the fork), SRC-11's
  registration and publication on S (to S's checkout), and DC-KEEP's four steps in its second
  repository. Every other step works in the checkout it did.
- **The cases.** Under profile V2, all 47 cases: the same outcome, step and reason as at
  `1fd0843`, 29 passed, 8 failed, 10 blocked. Under profile V1, its 21 cases passed.
- **The other runs.**
  - `scenarios.py --check`: 162 specs, no problem.
  - `units/v1` passed 594 tests and `units/v2` 107.
  - `test_executor` (its run of all 162 scenarios against the scripted owner included),
    `test_driver`, `test_cases` and `test_scenarios` passed 243.
  - `check-workenv.py`: OK, once four line-length findings in this repair were fixed.
- **The bindings**, against `1fd0843` (`cases.py --bindings`). `adapter_fingerprint` moved for
  PK, R0 and V1 … V9, because the driver's bytes changed. `fixture_fingerprint` moved for V2 …
  V9, because SRC-10's spec and scenario changed. P00 and P01 did not move.

## Limits that remain

- **Readers that compose.** The fork rule is checked by the operations that write a source and
  by `reference.resolve` and `memory.state.resolve`. Composition and preparation, which V2's later
  slices build, do not check it yet.
- **A name the contract cannot state** stops every publication to its source until the person
  renames the file (`D-20261004-b0636e`).
- **The test double** now holds what it is sent to every value it can compute, but it still
  answers as the scenario states. How the driver builds a checkout is held by the checkout tests
  in `test_executor` and by the real code's runs, not by the double.
- **DC-KEEP** is in neither V1's nor V2's profile, so its steps in the second checkout run only
  against the double until a later profile runs it.
