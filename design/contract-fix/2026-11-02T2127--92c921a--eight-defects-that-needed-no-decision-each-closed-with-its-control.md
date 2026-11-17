---
created_at: 2026-11-02T21:27:00+09:00
head: 92c921a
kind: design
---

# Contract fix, commit 2: eight defects that needed no decision, each closed with the control that would have caught it

This record lands with the second commit of the contract-fix package. It closes the items whose fix the lead
recorded on 2026-11-02 without an owner decision: F-23 (D-20261102-16af2f), F-25 (-fcbcd5), F-27 (-0048bd),
F-28 (-967506), and the dependency record's C-2, C-6, B-10 and A-12. F-23, F-25, F-27 and F-28 leave
`FINDINGS.md` with it. `head` is the base the figures were measured on, with this commit's changes laid on it.
Commit 1's record (`2026-11-02T2030--d30268e--...`) stands; this one adds a new item set and supersedes nothing.

## What a user sees differently, per shipped file

- `install.sh` (the compatibility path only, `AGENT_BIOS_LEGACY_INSTALL=1`; the default install never reaches
  these lines): the logs of the status projection, the verify parity run and the onboarding apply-record are made
  with `mktemp "${TMPDIR:-/tmp}/<name>.XXXXXX"`. On Linux, whose GNU `mktemp` refuses `-t <word>`, the
  compatibility install, verify and onboard no longer abort there (and the abort no longer restores the previous
  manifest over a finished deployment). On macOS, a log kept after a failure is now in TMPDIR, where the printed
  "full output:" path points, instead of the per-user temp directory `mktemp -t` always chose.
- `session-cost.py` (`agent-bios cost`): two warnings after the totals. "WARN N response(s) carry a usage object
  with none of the keys this report reads (...), written by Claude Code <version>: the transcript format has
  moved, and the totals above count them as zero"; and "WARN N line(s) are not a JSON record and were skipped".
  A usage object with an added key raises nothing. A JSON line that is not an object is counted there instead of
  ending the report with a traceback. Totals are unchanged.
- `launch/agent-launch.zsh`: the permission default (`--dangerously-skip-permissions`) is no longer put in front
  of any subcommand the installed `claude --help` lists under `Commands:`, every spelling (2.1.316: 21). Before,
  only six verbs measured on 2.1.280 went without it, so a newer verb typed bare started a permission-skipping
  session with the verb as its prompt. `claude mcp ...`, `claude doctor`, `claude plugin ...`, `claude update`
  and the like now run without the flag; a prompt, an option-first call (`claude -p ...`) and a bare `claude`
  keep it. The first verb-like call for an installed binary runs `claude --help` once; the list is kept in the
  shell and in `~/.local/share/agent-bios/claude-subcommands` when that directory exists (never created here),
  keyed by the binary's resolved path, modification time and size, so an update is read again. If the help
  cannot be read (it fails, lists nothing, or zsh has no `zstat`), a verb-like first argument runs without the
  flag, and nothing is cached.
- `wrappers/codex-helm.sh`: stdin is read only when no prompt argument is given (and stdin is not a terminal),
  or where a prompt argument is `-`; with other arguments beside `-`, stdin is appended in a `<stdin>` block as
  before. `--dry-run` never reads stdin: with no prompt argument it refuses ("--dry-run reads no stdin; pass the
  prompt as arguments"), and a `-` shows as `<stdin: not read under --dry-run>`. A prompt argument without `-`
  now leaves piped stdin unread, which is the documented change; a bare `-` was "unknown argument" before. An
  open stdin nobody writes to no longer hangs a call that has its prompt.
- `compose/canary.sh` (reached from the compatibility onboarding): the not-loading diagnosis no longer tells the
  user to re-approve imports. It names the entry file and its `@central/bundle.md` line. The entry file is
  user-scope, and the vendor's memory page, as quoted in `design/dependency-contracts/` (2026-10-26), says
  Claude Code loads a user-scope file's imports without the approval dialog. The page was not re-read for this
  commit: the package's rules allow no network.
- `claude/guides/tooling-gotchas.md` and its Korean text (and the generated `codex/` copies): one sentence says
  codex-helm reads stdin only with no prompt argument or with a `-` argument.

## Controls

- F-23: `gates/check-package.sh` gains the leg "shipped shell scripts without mktemp -t" (8 subjects), which
  fails naming `file:line` for a non-comment `mktemp [-flags] -t`. Self-test cases (38): a planted `mktemp -t`
  in `install.sh`, a planted `mktemp -q -t` in `codex-helm.sh`, and a comment naming it, which passes.
- F-25: `session-cost.py --self-test` plants a transcript whose usage keys are renamed (two responses, a planted
  version), one with an added key, and one with a line that is not JSON. The self-test had no leg: the umbrella
  now runs it (`leg -q`), and its failure lines go to stderr so a quiet leg shows them.
- F-27: `gates/check_parity.py` `shell_wrapper` runs the wrapper with a HOME of its own (it ran with the
  caller's) and a fake `claude` whose `--help` lists six verbs, `mcp` and a planted verb. Every listed spelling
  passes with no flag, the planted one included; a prompt, `-p` and a bare `claude` get it. Every call runs in a
  shell of its own and the help is probed once (the file cache); after the binary changes, a newly listed verb
  passes and the help is probed a second time; a help that fails or lists nothing leaves the flag off and
  writes no cache. `launcher_shell_reassert`'s fake `claude` now answers `--help`, so its prompt case still
  gets the flag.
- F-28: `codex_run` drives codex-helm through the fake `codex`, which now records the prompt it read. Each call
  holds a stdin pipe whose write end the check keeps open: with a prompt argument the call ends and the prompt
  is the argument; `--dry-run` with no prompt refuses at once; `--dry-run probe -` shows the placeholder; no
  argument takes the piped prompt; `probe -` appends a `<stdin>` block; a prompt argument without `-` leaves
  piped data unread. A call that times out (60 s) has its stdin closed and its session killed before the drain.
- C-2: `stop.py`'s `ps_table` runs `ps` with `LC_ALL=C` and `TZ=UTC`, as `compose/instructions_setup_cli.py`
  does. Control: under `LC_ALL=ko_KR.UTF-8` the listing reads this process with no unreadable line, with a
  presence term that `ps` prints a seven-word `lstart` under that locale.
- C-6: `stop_tree` runs its freeze deadline on `time.monotonic`, keeps a monotonic instant beside each wall
  stamp (`record["monotonic"]`), and when the wall clock moved more than 1 s against the monotonic one between
  the decision and the kill, sets `freeze_at` to None with `STOP_FREEZE_UNVERIFIED the wall clock moved ...`,
  which the boundary reads as `STOP_BOUNDARY_UNVERIFIED`. No new code: design §13.2's two stop codes stay the
  contract. Control: a clock that steps back an hour after the decision (stop controls 36 -> 38 with C-2). The
  deadline's move to the monotonic clock has no control.
- B-10: `check-model-currency.py` tells a catalogue that is absent from one present in a shape it does not read
  (`{"unreadable": ...}`, naming `~/.claude/cache/model-catalog/<file>` or `~/.codex/models_cache.json` and the
  first missing key); such a host's bindings are NOT JUDGED with that note, the report says "present, in a
  shape this does not read", and `--publish-guard` refuses it. Control: both caches with a renamed key (34).
- A-12: `canary_separates_not_loading_from_not_probed` requires the not-loading output to name
  `'@central/bundle.md'` and no approval.

## Found on the way

- macOS `mktemp -t` ignores TMPDIR and writes to the per-user temp directory. The install scenarios' I17 case
  plants a projection failure, so each umbrella run left an `instructions-projection.*` log there, outside every
  TMPDIR: on 2026-11-02 that directory held 52 of them and 52 `verify-parity.*`/`instructions-record-apply.*`.
  With the portable form the log followed TMPDIR into the leg's own directory, where commit 1's leftover check
  failed the leg by name; I7 and I17 now run their installs with `TMPDIR=$T/tmp`. The files already there are the
  owner's to remove.

## Verification

- Development runs (fake HOME, a fresh short TMPDIR each, no `-B`): every changed suite passed with its TMPDIR
  empty. The first development umbrella failed two legs, both fixed above: the install scenarios' leftover
  (found by commit 1's control) and `launcher_shell_reassert`'s fake `claude`; after the fixes both passed.
- Pretrial (`work/impl/cfix/c2-revert.py`, disposable copies committed into fresh repositories, six at a time,
  fake HOME): 18 revert rows, each failing with its expected text, and 9 unmutated suites (check-package and its
  self-test, session-cost, stop, model-currency, `check_parity.py` whole, dispatch, monitor, the install
  scenarios), each passing with its TMPDIR empty. In the first run the three F-28 rows that hang a call stopped
  the whole check at the harness's 1200 s limit: the helper killed bash and left the reader of the idle stdin
  holding the output pipes. With the helper closing the stdin and killing the call's session, the four F-28 rows
  and `check_parity.py` were run again and passed (the rows failing by name in 7-127 s).
- Real conditions (2026-11-02 21:23-21:26, a clean clone of the worktree at `92c921a` with these changes, the
  real HOME and venv, a fresh TMPDIR): rc=0 in 191 s, 91 legs declared and run (one new: session-cost's
  self-test), 0 failed, the TMPDIR empty after, `git status` of the clone the same before and after, and the
  per-user temp directory's count of legacy install logs 104 before and after. Under the same conditions commit
  1 measured 192 s; its hook ran 195 s.
