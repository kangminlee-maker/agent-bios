---
created_at: 2026-11-02T23:18:55+09:00
head: 609e7df
kind: design
---

# Contract fix, commit 3: every wait is bounded, every host protocol is checked against its own schema, and a hermetic receipt says how hermetic it was

This record lands with the third commit of the contract-fix package. It closes the owner's decisions of
2026-11-02 that commit 2 did not carry (F-24, F-26, F-29, F-30, F-31), the F-28 amendment and the F-27 control the
lead set after reviewing 609e7df, and adds `hermeticity` to the call receipt's evidence. It adds to
`2026-11-02T2127--92c921a--eight-defects-that-needed-no-decision-each-closed-with-its-control.md` without
restating it. `head` is the commit these changes are laid on. F-24, F-26, F-29, F-30 and F-31 leave `FINDINGS.md`.

## F-29: every exclusive lock waits at most 30 s and says what it waits for (D-20261102-49b466)

`compose/host_platform.py` owns the wait: `lock_within(file, name, holder=None)` takes the lock without blocking,
retries every 0.05 s, prints after 2 s `agent-bios: waiting for <what> (<path>)[, held by …]; giving up after
30 s`, and at 30 s raises `LockWaitExpired` with `<what> (<path>) is still held after 30 s[, held by …]`. The
Windows emulation of `flock` (`emulated_flock`) retried a blocking request forever; it now stops at the same
bound. Holds measured for the bound: an install 0.38 s, a verify 0.034 s, a launcher preset save under 1 ms; only
a setup apply holds the transaction lock for minutes, and that is the one holder a waiter names.

What a user sees, by writer:

| Writer | Lock | Past the bound |
| --- | --- | --- |
| `compose/instructions_transaction.py` (setup apply, launches) | the instructions transaction lock | `TransactionError` naming the lock and, while a setup apply runs, `setup apply <review_id>, pid N, started <time>` from its running receipt; a receipt whose recorded process identity no longer matches names nobody |
| `compose/instructions-state.py` | the instructions status lock, the deploy lock | exits naming the lock |
| `learn/collect-learning.py` | the learning upload lock | the drain is not run (`upload -> NOT RUN: …`); the record is captured and drains next time |
| `decisions/record-decision.py` | the decision ledger lock | exits naming the ledger; nothing is recorded |
| `launch/agent-launch.py` | the launcher methods lock, the presets lock | the wizard shows the refusal on its screen and writes nothing; a preset save refuses |
| `benchmarks/tier/budget.py` | the benchmark budget lock | `BudgetError` naming it |

`process_identity` moved from `instructions_setup_cli` into `host_platform`, which the CLI now imports.

The launcher loads the helper by path only when the wizard or a preset save takes a lock, from the package it
runs in or, for the compatibility install's standalone copy in `~/.local/bin`, from the copy `install.sh` now
deploys beside its config (`$LAUNCH_DIR/host_platform.py`, held by `verify_match`). It starts, reads its config
and plans a launch without the helper; with neither copy, only those two actions refuse, naming both paths
("the launcher's lock helper is missing … reinstall agent-bios"). The lead set this condition.

`gates/check-package.sh` has a leg, "python lock writers without an unbounded wait": every tracked Python file
calling `flock` with `LOCK_EX` and without `LOCK_NB` outside a control fails it, read from the parsed module so a
string or a comment is not a call. A control's holder is not a writer: calls inside `self_test`, `_self_test` or
`test_*`, in a `test_*.py` module or under `gates/` are skipped. No file is exempt: the benchmark budget, which
the first draft exempted, waits on the same bound at the lead's ruling.

Controls: `compose/test_instructions_platform.py` (a child holding the transaction lock, the holder named and a
receipt with a stale identity not named, the notice, the Windows emulation bounded); the self-tests of
`instructions-state.py`, `collect-learning.py` (check 18), `record-decision.py` and `budget.py`;
`gates/check_parity.py` `launcher_registration_wizard` (bounded refusal on the screen; refusal naming the missing
helper with the file unchanged) and `preset_save_round_trips` (bounded refusal; a standalone launcher copy with no
helper starts, plans and refuses only the save); four `check-package.sh --self-test` cases. Every holder is a
child process that lets go after 8 s (the Windows control's primitive gives up after 100 tries), so a reverted
writer fails its control late instead of hanging the suite.

## F-30 and F-24: the app-server protocol is checked against the installed Codex's own schema (D-20261102-d8310f)

`wrappers/codex_protocol.py` (new, shipped beside the frame filter and deployed with it) owns what agent-bios
reads from `codex app-server`:

- `USED`: the 37 method, parameter and result names the code uses, and `SHAPES`: the shape of every field it
  reads from `initialize`, `config/read`, `hooks/list`, `thread/start` (twice: the session's and the frame
  filter's `instructionSources`), `thread/read` and `thread/inject_items`. `check_result` refuses an answer in another
  shape naming the field (`instructionSources: str, not list`), and refuses a reading it declares no shape for.
- `ensure_schema`: per installed Codex binary (path, size, modification time), version and `USED`, it runs
  `codex app-server generate-json-schema --experimental --out <scratch>` once, offline, with a scratch
  `CODEX_HOME` (the command writes a `tmp/` there; `codex --version` too), and checks every `USED` name. A
  missing name refuses: `Codex <version>'s app-server protocol schema lacks what agent-bios uses: <names>`. The
  verdict is kept in the process and in `<state dir>/codex-protocol/<version>.json` when the state directory
  exists; a schema that could not be generated is not kept.
- `Client`: a reader thread and a queue over the app-server's stdout. F-24's defect was the frame filter's
  `select` on a buffered stream: a response written in one write with a notification sat in the buffer until the
  60 s timeout. `instructions_session.CodexServer` and the frame filter's `app_server_sources` both use it.

Measured on codex-cli 0.163.0: the generated schema carries all 37 names; generation took 0.045–0.051 s and
wrote 452 files, 5.7 MB, into the scratch directory. What a user sees on a new Codex version: the first
activation or capture with it runs that check once (well under a second) and keeps the verdict; if the new
version dropped or renamed a name agent-bios reads, the activation or capture refuses naming the name and the
version, before the app-server is asked anything.

With the schema check in place, `config.developer_instructions` may be `null`, which the vendor documents as "use
the built-in instructions" (`cfix-doc-facts.md`): it is read as the user's none, not refused. Any other non-text
value refuses naming the field. The vendor page still calls the app-server experimental; of the six names the
dependency record found undocumented, `includeLayers` is now documented.

Controls: `compose/test_instructions_codex_protocol.py` (new: every used name is one the check asks for and each
dropped one is named; the installed Codex's own schema carries all of them and the check leaves HOME untouched;
the verdict kept per binary, a changed binary checked again, a missing name refused by name and version; a failed
generation refused and not kept; no state directory created; null is none and a wrong shape refuses; an undeclared
reading refuses; a response coalesced with a notification is read at once; a session refuses a Codex whose schema
lacks a used name); `gates/check_parity.py` `codex_run` (the verdict kept in the state directory, a dropped name
refused before any dispatch, a wrong shape refused naming the field, a coalesced response read within 30 s).

## F-26: the transcript's record kinds are checked, for drift rather than for a version (D-20261102-29ca35)

`wrappers/claude_hermetic_evidence.py` keeps `RECORD_KINDS`, the record types and attachment types measured per
Claude version (2.1.304: 19 types and 21 attachment types, counted over the 404 transcripts of the 2026-10-20 probe
captures). A transcript passes when every record type and every attachment type is in the union of the measured
sets, whichever version wrote it (`hook*` attachments are read by prefix). One outside it is refused,
`RECORD_KIND_UNKNOWN '<type>' (Claude <version>; the known kinds were measured on 2.1.304) in <file>` or
`ATTACHMENT_TYPE_UNKNOWN …`; a transcript in which no record names a version is refused as
`RECORD_VERSION_UNKNOWN`, since the drift could not be named (a transcript's `api-request-blob` records carry no
version, so the versions are collected from every record that does). The lead relaxed the first draft, which
refused every version without a measured set, on review. The three codes join `dispatch.py`'s `ADAPTER_CODES`,
so a refused call's outcome names them.

## F-31: managed and server-delivered settings (D-20261102-6b6676, D-20261102-252c92)

File half: before a hermetic call, `claude_hermetic_evidence.py prepare` checks the documented managed-settings
locations for existence only, never reading one (macOS `/Library/Application Support/ClaudeCode/`
{`managed-settings.json`, `managed-settings.d`, `managed-mcp.json`}, `/Library/Managed Preferences/` and its
per-user copy of `com.anthropic.claudecode.plist`; Linux `/etc/claude-code/` (the same three); Windows
`C:\Program Files\ClaudeCode\` (the same three) and the `Settings` value under `HKLM` and `HKCU`
`SOFTWARE\Policies\ClaudeCode`, asked for its size only). Present, the call runs, stderr says the call is not
fully hermetic, and the capture names them.

Server half: an organisation's policy reaches a Team or Enterprise credential from the server at startup, which
no file check sees. Once per distill run, before its first hermetic Claude call, the dispatcher asks the adapter:
`claude-run.sh --profile hermetic --server-policy-probe` makes no call; in a cell of its own, with exactly the
call's seven environment names and the token (which never passes through the dispatcher), it runs `claude
doctor` with stdin closed and a 60 s bound, and prints the status of its one documented line, `Managed settings
(remote): <status>`, as JSON. Nothing else of doctor's output is kept; the rest names the account. The verdict:
`clean` only when the status is exactly `none configured for this organization`; any other status is copied (at
most 200 characters) as `not confirmed`; no line, two lines, an exit other than 0 or no answer in time is
`unknown`, never clean. The dispatcher keeps the record as `supervisor/server-policy.json` (the first writer
wins; it asks outside the supervisor lock, so no call waits on it) and hands it to every hermetic Claude call
with `--server-policy FILE`. A runner that is not the pinned one (a golden host) asks nothing, and its calls
record the server policy as unknown; direct `claude-run` use without the flag records it the same way. Nothing
skips the fetch: a provider or base-URL variable that would avoid it would also evade the organisation's policy.
The files doctor and the call's own startup write into the cell's configuration home (`remote-settings.json`,
`.synced-at`, `policy-limits.json` and its signature and stamp files) are not a signal and raise no problem.

The capture's `hermeticity` block, for the hermetic profile: `assessed: true`, `managed_sources`,
`server_policy` (`status`, `verdict`, `reason`), `fully_hermetic` (no managed source and a clean server
verdict), and `setting_sources_note`, which states why `--setting-sources ""` is moot here (its empty value is
undocumented; the call runs with a fresh HOME and configuration directory in an empty working directory, and the
evidence check reads every source the host recorded as loaded). The inherit profile states `assessed: false` with
its reason.

## The receipt states hermeticity (contract addition)

The call receipt's evidence (design §3.2 step 1's list, with plan WP-02's `payload_sha256`) gains `hermeticity`,
canonical JSON like `usage_totals`. No receipt is written without it: `session-distill/runlib/receipts.py`
`EVIDENCE_KEYS` holds it, so a receipt lacking it is `RECEIPT_KEY_MISSING evidence.hermeticity`.

- A hermetic Claude call: the capture's assessed block.
- A Codex call: `{"assessed": false, "reason": "hermeticity is assessed for hermetic Claude calls
  (D-20261102-252c92); a Codex call's context evidence is its prompt-input rendering and instructionSources"}`,
  written by the frame filter into the capture.
- A capture carrying no assessment: `{"assessed": false, "reason": "the capture carries no hermeticity
  assessment"}`.

`claude_hermetic_evidence.receipt_hermeticity` is the one derivation; `gate.py` recomputes the value from the
call directory and refuses a receipt whose value differs (`RECORD_INTEGRITY receipt evidence.hermeticity`), and
the adapters' own receipts carry it. The frame filter's `EVIDENCE_KEYS`, its "evidence-keys-are-the-gates"
control and `check_parity.py`'s `CAPTURE_EVIDENCE_KEYS` hold the same set.

## F-28 amended (D-20261102-7f5309)

609e7df left a piped stdin beside a prompt argument unread without a word. `tooling-gotchas` steers agents to pass
values through stdin, so `git diff | codex-helm.sh "review"` is the likely call, and it spent a Codex call on the
prompt alone; the dependency record names a silent failure as the one outcome not allowed.

What a user of `wrappers/codex-helm.sh` sees differently, beside a prompt argument without `-`:

- A redirected regular file (`< review.diff`) is read and appended in a `<stdin>` block, as with `-`. A file
  cannot hang the call.
- A pipe or a socket is left unread, and stderr says `codex-helm: stdin is a pipe and was not read, because a
  prompt argument was given without -; add - to the arguments to append stdin in a <stdin> block` ("a socket"
  for a socket), under `--dry-run` too. On a pipe an idle writer and a slow one look the same, so reading it would
  bring back the hang 609e7df closed.
- A terminal, or a device such as `/dev/null`, is left unread with no note, as in 609e7df.

Unchanged: with no prompt argument stdin is read; `-` reads it; `--dry-run` never reads it. The usage text says
the same. The kind is told by `[ -f /dev/stdin ]`, `-p` and `-S`; macOS bash 3.2 answers f, p, c and S for a
redirected file, a pipe, `/dev/null` and a socket pair (probed 2026-11-02).

`claude/guides/tooling-gotchas.md`, its Korean text and the generated `codex/` copies: beside a prompt argument
codex-helm reads a pipe only with `-`, as in `git diff | codex-helm.sh "review" -`, and appends a redirected
file either way.

Controls (`gates/check_parity.py` `codex_run`, whose helper gives the call a pipe, a socket pair or a redirected
file and reports what it saw as presence flags, never the text): an idle open pipe beside a prompt ends at once
and the note names the pipe, with and without `--dry-run`; an idle open socket does the same and the note names
the socket; piped data beside a prompt is absent from the prompt Codex received and the note is printed; a
redirected file beside a prompt is appended in a `<stdin>` block with no note; `probe -` appends the piped data
with no note. The earlier cases stay.

## F-27: the probe leaves `stat` as it found it

The lead approved the F-27 design on one condition: the probe loads `zstat` alone, because `zmodload zsh/stat`
puts a `stat` builtin in front of `/usr/bin/stat` in the user's interactive shell, where the wrapper runs.
609e7df already loads `zmodload -F zsh/stat b:zstat`; the control the condition asked for was missing.
`shell_wrapper` now takes `whence -w stat` in a shell that had not loaded `zsh/stat` and in one that had,
sources the wrapper, makes a call that runs the probe (`claude planted-verb probe-id`), and requires `stat` to
resolve as before (`command` and `builtin` respectively) and the call to reach the binary without the flag.

## A-1: the re-pin runbook

`session-distill/REPIN.md` (author-side) moves distill's pinned Claude to the installed version and measures that
version's record kinds with one hermetic call. It is written and not run: it makes a model call, which waits for
the owner.

## Gates that had to learn the new files

- `gates/check-surfaces.py` `NOT_A_SURFACE`: `compose/host_platform.py`, now deployed beside the launcher's
  config, is code the launcher runs; no text in it reaches a model.
- `gates/check-seam-coverage.py`: `drain_under_lock` is classified outside the transport seam (the lock around
  the drain; it decides no endpoint), and the scratch copy carries `compose/host_platform.py`, which the drain
  imports.
- `gates/check-endpoints.py`: its three planted ambient-configuration bypasses anchor on the drain call that
  replaced the inline lock.
- `ontology/instances/graph.json`: the derived counts re-measured by `ontology/extract.py`, 15 deploy targets
  (the protocol module and the launcher's helper) and 86 payload paths; the map re-emitted.
- `compose/test_instructions_app.py`: its `skills/list` question is the test's own, not a reading agent-bios
  makes, so it asks the client directly rather than through the checked call.

## What 2127 should have said

- The subcommand change is the safer side, not only a different one: `claude mcp`, `claude doctor`, `claude
  plugin` and every other subcommand the installed help lists now run exactly as they do without the wrapper;
  only a prompt, an option-first call and a bare `claude` take the permission default.
- The session-cost leg made controls run that never had: `session-cost.py --self-test` existed, and no leg of
  the umbrella called it.
- F-23 closes a leak as well as the GNU abort: macOS `mktemp -t` prefers `_CS_DARWIN_USER_TEMP_DIR` to TMPDIR
  (`man mktemp`), so every umbrella run left I17's planted-failure logs in the per-user temp directory. Counted
  on 2026-11-02 after commit 2: 52 `instructions-projection.*` and 52 `instructions-record-apply.*`, none older
  than three days, the newest from 20:32, and no `verify-parity.*` (2127's "52
  `verify-parity.*`/`instructions-record-apply.*`" named a kind that was not there). The lead's ruling replaces
  2127's "the owner's to remove": they stay, since macOS clears that directory's old files and the install
  scenarios add none since commit 2.
- The first F-28 pretrial's stop at the harness's 1200 s limit was explained in 2127 and measured after it
  (`work/impl/cfix/probes/f28-helper-hang.py` against 92c921a's codex-helm on an idle open pipe): after a 3 s
  timeout the old helper's kill ended bash (-9) and left one `cat` re-parented to pid 1; the drain still waited
  after 5 s, and returned in 0.0 s once the stdin's write end was closed. The `cp-*` entries in those rows'
  TMPDIRs were `check_parity.py`'s own temporary root, left because the harness killed it at 1200 s.

## Verification

Measured on 2026-11-02 on the author's machine; the run logs are in the implementer's work directory.

- Development umbrella (the worktree, a fake HOME, the real venv): the first run failed 8 legs, every one a gate
  that had not yet learned the new files (the surfaces catalog, the endpoint self-test's anchors, the seam
  classification and its copy set, the ontology's derived counts, a test asking `skills/list` through the checked
  call, and dispatch's adapter-code inventory); the second, after the fixes above, passed: 91 legs declared and
  run, none failed, 202 s, its TMPDIR left empty.
- Revert trials: 60 rows, each planting one fault in a disposable copy and requiring the suite that guards it to
  fail by the expected text, with all 16 suites passing unmutated, six at a time, 383 s. 56 rows passed at once.
  Two found a control gap, closed above: no test renamed a value inside a field's enum (dropping the name removed
  the field), and the installed-Codex test's HOME sat inside the TMPDIR given to Codex, where Codex 0.163.0 writes
  no `<home>/.codex/tmp` (measured), so a version check without a scratch home went unseen. One row's expected
  text was wrong (the receipt-inventory control says `receipt fields … are not the contract's`, not its name). In
  one row the gate self-test stops with an uncaught refusal and leaves its scratch directory, as any crash of that
  suite does; that row admits the one leftover. The re-run of those rows and every row of the protocol suite
  passed.
- Real conditions, as the hook runs: a clean clone at 609e7df with the 38 changed files laid on it and added to
  its index, the real HOME and venv: 91 legs declared and run, none failed, 197 s, TMPDIR left empty, the clone's
  `git status` the same before and after, the per-user temp directory's legacy install logs 104 before and after,
  and the owner's agent-bios state root unchanged by name, with no `codex-protocol/` in it. An earlier run on a
  clone that left the new files untracked failed one leg (the package self-test copies tracked files, so the copy
  had no `wrappers/codex_protocol.py`); the tree was not at fault.
