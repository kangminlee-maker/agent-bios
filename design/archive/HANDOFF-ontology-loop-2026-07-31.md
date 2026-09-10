# Handoff — 2026-07-31

Written to survive a context clear. Read `DESIGN.md` for the loop itself and `FINDINGS.md` for
the implementation queue; this file says only where things stand and what to do next.

## Where you are

- Repo `~/Documents/agent-bios`, branch **`ontology-seed`**, HEAD **`75ba371`**, 22 commits ahead
  of `main`, working tree clean.
- Four untracked directories (`.claude/`, `research/`, `design/review-process-learnings/`,
  `design/reviewer-registry/reviews/`) are **intentionally untracked**. Never `git add -A` here —
  doing that once produced a 1.3-million-line commit that had to be reset.
- **Nothing is deployed.** The machine still runs the previously installed corpus; `install.sh`
  on this branch changes install behaviour and has only been exercised against throwaway HOMEs.

Verify the whole thing before trusting any of the above:

```bash
cd ~/Documents/agent-bios
python3 ontology/check-ontology.py && python3 ontology/check-ontology.py --self-test
./gates/check-parity.sh          # runs the domain, learn, prune and migrate self-tests too
python3 ontology/check-ontology.py --coverage   # standing purpose/obligation report
```

## What landed

Stages A, B and the first C batch of the ontology loop, plus the product changes those decisions
required. `DESIGN.md`'s `Round log` has the per-stage account with what each one actually found;
it is not repeated here.

The product changes worth knowing before you touch the installer:

- **One install shape.** "Full" mode is gone; an install with no `--domains` selects every domain
  and goes down the same assembly path. The entry `CLAUDE.md` is the user's — we write to
  `central/` and only seed an import line.
- **Uninstall is a security operation.** It removes everything of ours (deployed files, state,
  backups, cache, venv, and the loose `.bak-*` copies in the user's config dirs) and emits ONE
  archive at `$HOME/agent-bios-uninstall-<ts>.tar.gz`. Archive first, verify, then purge — a
  failed archive leaves the machine untouched.
- **Backup retention**: a copy is deleted only when it is both older than 30 days AND outside the
  newest 10. Both groups (state-dir directories, sibling `.bak-*`) are pruned independently.
- **The prune of personal learnings now needs the canary's proof.** `compose/canary.sh` records
  the bundle rev it proved loading; `migrate-learnings` reads that. A plain `install` runs no
  canary and therefore prunes nothing; `onboard` prunes after the canary passes.

## What is open

**Decide, then do:**

1. **`F-10` — `rollback` is not on the CLI surface.** `compose/corpus-state.py rollback` exists
   and is reachable from the launcher; `agent-bios` advertises only install / verify / status /
   update / uninstall / help. Options: add a subcommand, mention it in `help`/`status`, or leave
   it. Recommendation on the table: mention only — it is a discoverability gap, not a missing
   capability.

**Probably closable, needs one pass:**

2. **`PT-1`'s two remaining foreclosure questions** (in `purpose.target`, graph.json). Both were
   written before the modes converged and the convergence answers most of them: adding or
   dropping a package is now "change the selection and re-assemble", which also makes the
   `selection.json` snapshot shape a non-issue. Re-read them against the current installer and
   close what no longer bites.

3. **`F-9` residual.** Retention landed, but the backups still have no automated restore
   consumer, and `README.md` states their location rather than a restore contract. Decide whether
   a restore path is wanted or whether the uninstall archive already covers the need.

## Traps this session paid for

Each of these cost real time; they are not hypotheticals.

- **A negative control that indexes a live list stops testing when that list empties.** Happened
  three times as debts closed and verdicts resolved — twice as a *silent pass*, once as an
  IndexError. When you resolve an item, re-run `--self-test` and read for controls that went
  quiet. New controls should build their own rows.
- **An inherited claim is a hypothesis.** Roughly eight this round did not survive being
  measured, including four from the previous session's own write-ups and three of my own from
  earlier the same day. Re-derive before building on anything.
- **Split on a line, not a substring.** Two separate bugs came from partitioning text on a token
  that also appears in prose (`[agents.*]` inside a comment; `def self_test(` inside a string
  literal). The second one deleted 337 lines before `git checkout` restored it.
- **A green check that could not have failed is not evidence.** Two controls in this repo were
  passing while testing nothing. Plant the violation and watch it fail.
- **The ontology catches installer changes before the tests do.** After editing `install.sh`,
  expect `check-ontology.py` to fail on drifted evidence literals and derived counts, and fix
  those by re-measuring rather than by editing the number to match.

## If you deploy

Not done yet, and it changes this machine's install shape. From a clone the deploy is
`bash install.sh install` — **not** `agent-bios install`, which deploys the globally installed
npm package instead of this tree. Dry-run first:

```bash
bash install.sh install --dry-run
```

After deploying, confirm what actually landed with `agent-bios status` (version marker, no DRIFT)
rather than trusting the command's exit code.
