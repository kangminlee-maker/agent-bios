---
created_at: 2026-11-13T01:30:00+09:00
head: 0ab9fca
kind: design
supersedes: 2026-11-12T2030--c1a861a--release-1-s11-writes-the-checkout-and-commits-and-six-findings-are-deferred-with-it.md
---

# Release 1's S11 writes files; the owner commits

The owner decided this on 2026-11-13, after the fourth review round on the containment unit
(`D-20261113-f22b7d`). It NARROWS `D-20261112-2cf1c4` and does not reopen it.

**What release 1's S11 does.** It writes the approved changes into files of the declared checkout,
and nothing else. It executes no git. It ends by naming two commands for the owner to run — the
commit and the install — and runs neither.

**What follows from that.** The owner commits as usual, so the repository's hooks run in the
owner's own environment, with the owner's own PATH, TMPDIR and HOME. Nothing about that environment
is this run's to certify, because this run does not produce it. The before-state S11 needs is the
file hashes the approvals already carry, checked through `runlib/targets`; git holds nothing S11
needs in order to write a file.

**Why, and this is the part worth keeping.** Four rounds on this one surface each produced NEW
blocking defects. Round 4's five were all in the git certification. The fifth is not a defect in
this code at all, which is what settled it:

> reachable: the repository's certified hook itself writes outside the declared checkout and can
> invoke a release-1-excluded writer. — The produced environment contains no TMPDIR, so lines 63
> and 69 create the index snapshot and staged tree under /tmp; lines 86–87 execute gates from that
> tree. gates/check-parity.sh:1909–1914 selects the launcher venv under HOME, executes its Python,
> and invokes launch/provision-venv.sh when unavailable. (`.githooks/pre-commit:63`)

A commit that runs the repository's own hooks inherits everything the hooks do. Certifying the
commit means certifying the hook's workload, and the hook's workload includes writing outside the
declared checkout and provisioning under HOME through a writer this release does not invoke. That
is not a bug to fix in one place; it is the shape of the thing.

## Round 4's five blocking findings, deferred with the commit

Each is quoted from `work/lead/wp21a-x-r4-review.json` as the reviewer wrote its claim. They are
DEFERRED, not answered. The code they are about is removed from the tree (see below), so none of
them is reachable in release 1 — which is the point of recording them here rather than fixing them.

1. `.githooks/pre-commit:63` — "the repository's certified hook itself writes outside the declared
   checkout and can invoke a release-1-excluded writer."
2. `destinations.py:1131` — "the config parser certifies different settings and paths from those git
   actually uses." `git_problems` returned `[]` for `[core] hooksPath=/outside` and for `[include]
   path=/outside/config`, both of which `git config` reads; a continued value, a quoted `#`, a
   quoted subsection and invalid key syntax also passed.
3. `destinations.py:1190` — "unchecked repository metadata can redirect git outside the repository
   that was certified": `extensions.worktreeConfig` with an unexamined `config.worktree`, a
   `commondir` file, a symlinked config, `objects/info/alternates` as a file, symlinked object and
   ref directories.
4. `destinations.py:1253` — "a certified hooks directory can contain a hook that executes code
   outside the checkout": hook FILES are not inspected, and the default `.git/hooks` is not walked
   at all.
5. `destinations.py:1084` — "ordinary commit signing executes an arbitrary program that the command
   policy accepts": `commit.gpgSign` with `gpg.program`, `gpg.format=ssh` with `gpg.ssh.program`,
   `gpg.ssh.defaultKeyCommand`, and (the policy accepted these too) `trailer.*.cmd` and
   `gc.recentObjectsHook`.

**Revisit condition for all five, and for the commit itself: release 2 decides S11 commits.** Until
then no part of this is a live obligation, because no code in the tree speaks to it.

## Two facts for release 2 to start from

Measured on the installed git, 2.50.1 (Apple Git-155), from its own documentation rather than from
memory:

- **One variable closes both global files.** `git(1)`: "if GIT_CONFIG_GLOBAL is set, neither
  $HOME/.gitconfig nor $XDG_CONFIG_HOME/git/config will be read. Can be set to /dev/null to skip
  reading configuration files of the respective level." `git-config(1)`'s FILES section names both
  as the "global" files and says `$HOME/.config/` stands in when `XDG_CONFIG_HOME` is unset. The
  same section also documents `$GIT_DIR/config.worktree` as searched "only when
  extensions.worktreeConfig is present", which is finding 3's surface.
- **Which git binary runs is decided outside any configuration policy.** The produced environment
  carried no PATH, so CPython's lookup falls to `os.defpath` (`/bin:/usr/bin` here) and resolves
  `/usr/bin/git`. That binary RELOCATES: launched with that environment, `git --exec-path` reported
  `/Applications/Xcode.app/Contents/Developer/usr/libexec/git-core`. `xcode-select(1)` documents
  `DEVELOPER_DIR` as overriding the active developer directory. So a release that executes git must
  certify the BINARY, not only the configuration — an absolute certified path, and `DEVELOPER_DIR`
  in the isolation.

## What the code says now

The git certification is REMOVED from the tree rather than kept behind a label. The reason is this
repository's own rule about what active files mean: a module carrying a `git_certificate` would read
as a working certification to the next person and to the next model, and round 4 established that it
is not one. Keeping five known-defective rules in the tree, labelled, buys nothing — the code is in
git history at `0ab9fca2`, with this record and the review beside it, which is where release 2
starts.

What stays is the narrowing mechanism itself, which the same decision uses: every git row and
destination is `not_invoked_in_release_1` with no path, the release-1 scope produces no git
environment, and a control holds that no row outside the checkout set comes back certified — with
its non-empty counterpart, so the control cannot pass over an empty set.

## S12's release-1 form, and the wording the earlier stages owe

S11's report ends by naming the two commands. S12, S9 and S10b must say the same thing in the
owner's own words, and the sentence is:

> 승인하면 선언된 체크아웃의 파일이 바뀝니다. 커밋과 설치는 소유자가 직접 합니다 — 적용이 끝나면
> 실행할 명령 두 줄을 그대로 보여 드립니다.

(English, for the record's own language: approving edits files in the declared checkout; the owner
then commits and installs, and the stage prints the two commands to run.)
