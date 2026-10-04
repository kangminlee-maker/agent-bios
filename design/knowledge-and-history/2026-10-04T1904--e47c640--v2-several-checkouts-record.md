---
created_at: 2026-10-04T19:04:27+09:00
head: e47c640
kind: design
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V2
supersedes: null
decisions: D-20261004-11f83a
---

# A person's clone, worktree and fork are three checkouts, each step runs in its own, and a fork bound for its own authority does not read its original

This records the end of V2's first slice. SRC-10 and SRC-11 were the two cases of V2's profile
that the conformance driver could not build. They now run, against V2's code, and pass. It
accepts nothing.

## What could not run

- **SRC-10.** One person has a clone of repository W, a worktree of it on a feature branch, and a
  fork with its own repository id. Its selections name three checkouts. The driver built one
  and blocked by name.
- **SRC-11.** Two repositories, R and S, each bound by its remote, with no selection. Its bindings
  observe two remotes. The driver built one checkout and blocked by name.
- **The host.** The driver starts each world process once, in one directory. `repository.bind`
  binds the checkout the process runs in, so binding a second checkout needed a step to run
  somewhere else.

## What changed in the driver

- **Several checkouts** (`features/checkout.py`).
  - Each path a selection names is one checkout, and a repository no selection reads is a
    checkout of its own.
  - An observation reads its selection's checkout. A binding was made in the checkout whose
    observation its working bytes name, else in the one checkout the selections read its
    repository in. A repository-authored source's members are files of the checkout its first
    stated home's binding was made in.
  - Each checkout has its own files, branch, remote and commit. A checkout a binding calls a
    `worktree` is added as a real git worktree of the first checkout of its repository, so its
    `.git` is a file, as a person's is.
  - Stand-ins are replaced per checkout: its path, its file digests, each binding's commit by its
    own checkout's HEAD.
  - What cannot be built is still blocked by name: a selection naming two checkouts, a binding
    whose checkout no observation says, two remotes for one checkout, two branches for one before
    an edit switches it, and one commit stated for two.
- **A step runs in its checkout.** A step works in the checkout a record it returns speaks of,
  else one it carries. The driver sends that directory as the message's `cwd`, and the host
  answers the message there (`host.py`). Any other step runs in the first checkout.
- **A branch switch is a real commit.** SRC-10 switches the clone's branch by editing `.git/HEAD`
  and writing a stated 40-hex commit into `.git/refs/heads/chore/prune-old-adrs`. The driver
  makes that commit, HEAD's tree without the files removed before the same step, and the edit
  and the rebinding state it in the stand-in's place (`features/event_file_edit.py`).
- **Files the code writes.** A file a record states whose size the owner mints is one the code
  writes, whatever record states it. Before, only a manifest member was. SRC-10's later
  observation reads the `records.jsonl` the publication wrote, so that file is no longer put in
  the first state.
- **The scripted owner** (`scripted_owner.py`) reads each checkout where it first answers a step
  in it, and reads a binding's commit as HEAD when the step that returns it runs.

## What changed in the product

- **A repository is held once per checkout** (`workenv/storage.py` layout 8,
  `workenv/sources/checkouts.py`, `homes.py`).
  - Before, binding a repository again from another checkout replaced the first binding, so a
    home resting on the clone's binding became `binding_unverified` once the worktree was bound.
  - `repositories` is now keyed by repository and checkout, and `binding_checkouts` keeps the
    checkout each binding was made from.
  - A repository-authored source is read from the checkout its home's binding was made from:
    publishing, committing its revision, and the drift a start checks. That holds after the
    same checkout is bound again, and after another checkout is bound later.
  - A home naming a binding no checkout holds now is `binding_unverified`.
  - A store laid out before layout 8 keeps its rows. A home resting on a binding replaced before
    then reads the checkout bound most recently, as every home did.
- **A document root's members are the files git tracks** (`workenv/memory.py`,
  `D-20261004-11f83a`). They are committed or modified files, read as the working tree holds
  them. A file git does not track is not yet the repository's, and is no member until it is
  added.
- **A fork does not read its original** (`workenv/sources/reading.py`).
  - The SSOT (S04, Repository ADR and Team ADR) says a fork gains no second writer under the copied source id, and needs an
    explicit binding to read the original or one establishing derived authority.
  - `reference.resolve` now refuses a request whose owner is a repository bound here as a fork of
    the source's repository only to derive its own authority: `repository_binding_required`,
    recovered by a new request.
  - A fork bound to read its original (`fork_original_read`) resolves, and so does a repository
    bound as no fork of it.
  - **Limit.** Only `reference.resolve` checks this. It is the operation SRC-10 uses. Other reads
    a fork's request could make are not refused yet.

## What changed in the scenarios

Each correction makes a scenario agree with the facts it states itself or with what git does.

- **SRC-10, the fork's commit.** The fork's binding stated the clone's commit. The fork commits
  other bytes than the clone (its own `fork_adr*_bytes`), so its HEAD cannot be that commit. It
  now states a stand-in of its own.
- **SRC-10, the published revision.** It now lists `docs/adr/0002-backups.md` (2211 bytes, as the
  clone's observation reads it), between 0001 and `records.jsonl`. Under `D-20261004-11f83a` a
  file git tracks under the document root is a member as the working tree holds it, and 0002 is
  tracked and modified. 0003 is untracked and stays out.
- **SRC-10, the observation after the switch.** It now reads `docs/adr/records.jsonl` as
  untracked, with the digest and size the publication minted. The publication wrote that file
  and did not add it, and git leaves an untracked file in place when the branch changes. It
  still lists no 0001.
- **SRC-11, the bindings.** Each now states branch `main` and a commit stand-in of its own. A
  binding states the branch and HEAD the checkout has, and a real checkout has both.

## What was checked

- **The cases.** Under profile V2, all 47 cases were run before and after.
  - SRC-10 and SRC-11 moved from blocked to passed. No other case changed outcome, step or reason.
  - Before: 27 passed, 8 failed, 12 blocked. After: 29 passed, 8 failed, 10 blocked.
  - The failures and blocks are on operations and driver features V2's later slices build.
- **The new tests.**
  - `test_executor`: three checkouts for SRC-10, two for SRC-11, the branch switch, the host's
    `cwd`, and five new blocked-by-name situations.
  - `units/v2/test_checkouts.py`: five tests of a clone and a worktree of one repository, and
    three of forks.
  - `test_storage_layout.py`: a repository bound before layout 8 keeps its checkout and binding.
  - `test_memory.py`: a file added under the root is a member once git tracks it, and an ADR
    being edited is one as the working tree holds it.
- **Negative controls.** Each was planted, the named tests were run, and the file was restored.
  Each failed by name:

  | Planted | Failed |
  | --- | --- |
  | A home's checkout ignores its binding | two of the five two-checkout tests |
  | The fork rule off | the fork unit test; SRC-10 at `refuse_the_fork_read_as_its_original` |
  | No `cwd` in the message | SRC-10 at `bind_worktree` (branch `main`); SRC-11 at `bind_repository_s` (R's remote) |
  | The host ignores `cwd` | the host test; the same two driver failures |
  | The edit keeps the stated commit | the branch-switch test; SRC-10 at `observe_after_the_branch_switch` |
  | The switch keeps the removed file | the branch-switch test |
  | Only manifests are files the code writes | the three-checkouts test; SRC-10 at `observe_clone` |
  | The worktree built as a separate repository | the three-checkouts test |

- **The other runs.**
  - Under profile V1, its 21 cases passed.
  - `scenarios.py --check`: 162 specs, no problem.
  - `units/v1` passed 593 tests and `units/v2` 87.
  - `test_executor` (its run of all 162 scenarios against the scripted owner included),
    `test_driver`, `test_cases` and `test_scenarios` passed 240.
  - `check-workenv.py`: OK, once four style findings in this change were fixed. Its ruff walks
    `workenv/` and `gates/workenv/` on disk, so the new test file was among the 98 it read.
- **The bindings**, against `e47c640` (`cases.py --bindings` on both trees).
  - `adapter_fingerprint` moved for PK, R0 and V1 … V9, because the driver's bytes changed.
  - `fixture_fingerprint` moved for V2 … V9, because SRC-10 and SRC-11 changed.
  - P00 and P01 did not move.
  - Against `run-21`, where V1 was accepted, V1's fixture fingerprint had already moved with
    this slice's earlier work. V1 is re-established when V2 is accepted.
