---
created_at: 2026-08-18T18:58:00+09:00
head: bfcc567
kind: review
---

# Writable-scratch round — corpus-state and the registration wizard (raw findings)

The round every earlier reviewer could not run: `codex exec -s workspace-write` on a
disposable standalone clone at `bfcc567` (v0.12.0), so the self-tests, trial loads, real
flocks and partial writes were actually exercised. Reviewer: gpt-5.6-sol at ultra; 192,845
tokens. Seven findings (2 High, 5 Medium), all on shipped machinery: corpus-state rollback
and status writes, the registration wizard's trial/publication paths, and one gate that
stays green when its second real reader is deleted. Verbatim below.

## Findings

### 1. High — rollback reports an older corpus while the active instruction surfaces remain current

File/function: [compose/corpus-state.py:cmd_rollback](/Users/kangmin/Documents/agent-bios-scratch-review/compose/corpus-state.py:186), [deployable](/Users/kangmin/Documents/agent-bios-scratch-review/compose/corpus-state.py:152), [compose/assemble.py:main](/Users/kangmin/Documents/agent-bios-scratch-review/compose/assemble.py:524)

- Says: rollback moves corpus “globals, guides, hooks”; `deployable()` requires `assemble.py` and `domains.json` because otherwise “the bundle, which is what the agent reads, would stay.”
- Does: `CORPUS` contains only Claude guides/hooks and Codex guides. `cmd_rollback` never assembles `central/bundle.md` or updates the Codex `AGENTS.md` central region.

Two-commit fixture, with v2 live and v1 requested:

```text
ROLLBACK_V1_RC=0
...3 files written, 1 removed...
V1_COMMON=OLD GUIDE          # control: write loop reached
V1_FRESH_EXISTS=False        # control: a HEAD-only guide was removed
V1_BUNDLE=NEW LIVE BUNDLE    # failure
V1_CODEX_GLOBAL=NEW LIVE CODEX GLOBAL
V1_STATUS=v1
```

The launcher will display v1 while both active global instruction surfaces remain v2.

Proposed fix: materialize the historical corpus source, then run the current assembly mechanics against that source and current selection, including the Claude bundle and owned Codex marker region. Include all resulting writes in rollback’s undo transaction; preserve personal entry regions.

Missed check: `compose/corpus-state.py --self-test`, invoked by `gates/check-parity.sh`, seeds only six guides and asserts one guide’s content. It has no bundle, global, Codex-region, or real assembly assertion. `compose/check-domains.py` only checks static corpus classification.

### 2. High — concurrent rollbacks both succeed but leave a split corpus

File/function: [compose/corpus-state.py:cmd_rollback](/Users/kangmin/Documents/agent-bios-scratch-review/compose/corpus-state.py:186), [_status_lock](/Users/kangmin/Documents/agent-bios-scratch-review/compose/corpus-state.py:303)

- Says: “A corpus is a SET of files that agree about which version they are.”
- Does: `_status_lock` serializes status writes only. Corpus writes, removals, and backup creation have no transaction-wide lock.

Timing mutation: 120 managed guides; rollback `one` was slowed after each real write, then rollback `two` started 0.10 seconds later.

```text
RC one=0 two=0
corpus rolled back to one ...
corpus rolled back to two ...
ONE files=116
TWO files=4
status current=one rolled_back_to=one
```

Serial control with the same fixture:

```text
CONTROL_RC one=0 two=0
ONE files=0
TWO files=120
status current=two rolled_back_to=None
```

Both concurrent operations also selected the same second-granularity backup directory, allowing their backup files to overwrite one another.

Proposed fix: add a separate deployment lock held from target/backup calculation through file mutation and final status update. Use collision-proof per-transaction backup directories.

Missed check: `corpus-state.py --self-test` runs only sequential rollbacks. `check_parity.py --list` exposes status-reader checks, but no rollback mutual-exclusion check.

### 3. Medium — rolling forward leaves files that exist only in the prior deployed version

File/function: [compose/corpus-state.py:cmd_rollback](/Users/kangmin/Documents/agent-bios-scratch-review/compose/corpus-state.py:202)

- Says: rollback leaves one exact corpus file set.
- Does: removal candidates are derived from `corpus_files(repo, "HEAD")`, not from the currently deployed version. A file restored from v1 but deleted by v2/HEAD is absent from both operands when rolling forward, so it persists.

Mutation sequence and control:

```text
# v2 -> v1
V1_FRESH_EXISTS=False       # correct control: v2-only file removed
V1_LEGACY_EXISTS=True

# v1 -> v2
ROLLBACK_V2_RC=0
V2_COMMON=NEW GUIDE
V2_FRESH_EXISTS=True
V2_LEGACY_EXISTS=True       # wrong: v1-only file survives
V2_STATUS=v2
```

The self-test’s removal control is vacuous. Replacing the removal loop with `for rel in ()` still produced:

```text
exit=0
...6 files written, 0 removed...
corpus-state --self-test: OK
```

Proposed fix: persist the exact deployed managed-file manifest and diff that against the target transactionally. At minimum, derive the previous set from the recorded current-version commit and refuse safely when it cannot be established.

Missed check: `corpus-state.py --self-test` has one commit, making `managed_now == target_files`; it never asserts a removal.

### 4. Medium — locked status writes can still leave truncated state that a later projection erases

File/function: [cmd_project](/Users/kangmin/Documents/agent-bios-scratch-review/compose/corpus-state.py:117), [cmd_record_apply](/Users/kangmin/Documents/agent-bios-scratch-review/compose/corpus-state.py:318)

- Says: the lock protects whole-file read/modify/write and `record-apply` changes only `last_apply`.
- Does: both paths call `STATUS.write_text()` in place. The lock excludes cooperating writers but does not make the write atomic.

Control:

```text
last_apply recorded: applied
```

Result: valid 183-byte JSON retaining the existing fields.

Interrupted-write mutation:

```text
interrupted write result: OSError: simulated interruption after truncate
bytes after interrupted write: b'{"current_version":'
corpus status unreadable: Expecting value: line 1 column 20 (char 19)
next_run_rc=1
```

A subsequent real `project` returned zero and silently replaced the damaged state with:

```text
current=2026-07-18, latest=2026-07-18
"rolled_back_to": null
"last_apply": null
```

Proposed fix: one shared same-directory temporary-write-and-`os.replace` helper under the lock. An unreadable prior status should be reported or quarantined rather than silently discarding rollback/apply state.

Missed checks: the corpus self-test stubs `cmd_project` and never tests `record-apply`; `corpus_status_shapes_degrade_rather_than_lie` tests rendering malformed input, not writer interruption.

### 5. Medium — the registration gate remains green when the second real reader is deleted

File/function: [gates/check_parity.py:launcher_registration_wizard](/Users/kangmin/Documents/agent-bios-scratch-review/gates/check_parity.py:2008), [launch/agent-launch.py:_trial_registration](/Users/kangmin/Documents/agent-bios-scratch-review/launch/agent-launch.py:5298)

The trial’s comment correctly says `load_review_methods()` is required because `load_config()` alone accepts instruction slots the runtime reader rejects. The gate’s duplicate-ID negative control is rejected earlier by TOML parsing, however.

Deleting only `load_review_methods(trial_config)` still passed:

```text
python3 gates/check_parity.py --only launcher_registration_wizard
NOTE: partial run (1/62 checks) ...
LAUNCH/BINDINGS OK: ...
```

Discriminating descriptor:

```text
# Restored implementation
mutation VERDICT 'review_methods.trial-bad.instructions: unknown slot {not_a_slot}...'
control VERDICT None

# Second-reader call deleted
mutation VERDICT None
control VERDICT None
```

Proposed fix: add a wizard-driven candidate that parses through `load_config` but fails only in `load_review_methods`, such as `instructions = "review {not_a_slot}"`. Assert the reader-specific refusal and byte-identical user file.

Missed check: `launcher_registration_wizard` itself; its claimed trial-oracle control passed after the guarded call was removed.

### 6. Medium — publication failure escapes raw and leaves its completed temporary file

File/function: [launch/agent-launch.py:register_reviewer_wizard](/Users/kangmin/Documents/agent-bios-scratch-review/launch/agent-launch.py:5334)

- Says: append atomically, retain answers on refusal, and restore on post-write failure.
- Does: the initial temporary write/chmod/replace sequence has neither an `OSError` boundary nor `finally` cleanup.

Mutation: make `review-methods.local.toml` a directory, then drive the real wizard through confirmation.

```text
fail RAISED IsADirectoryError: [Errno 21] Is a directory:
'/.../.review-methods.local.toml.72234.tmp' ->
'/.../review-methods.local.toml' LEFT 1
fail METHOD_TARGET_KIND dir
fail PUBLISH_TEMPS ['.review-methods.local.toml.72234.tmp']
```

Nearest control, identical answers with the target absent:

```text
ok RETURN True LEFT 0
ok METHOD_TARGET_KIND file
ok PUBLISH_TEMPS []
```

Proposed fix: catch publication `OSError`, unlink only the wizard-owned temporary in `finally`, render a normal refusal, and return to the retained-answer loop.

Missed check: `launcher_registration_wizard` tests successful publication and pre-write duplicate refusal only.

### 7. Medium — every registration trial leaks its temporary directory

File/function: [launch/agent-launch.py:_trial_registration](/Users/kangmin/Documents/agent-bios-scratch-review/launch/agent-launch.py:5298)

`tempfile.mkdtemp()` has no cleanup path. Both semantic controls behaved correctly but left residue:

```text
accept verdict: None
original user file exists: False

refusal verdict: ...capabilities name(s) already shipped: codex-exec...
original user file exists: False
```

After exactly these calls, two `agent-launch-register-*` directories remained, each containing `profiles.toml` and `review-methods.local.toml`. Running the narrow wizard gate created two more trial directories.

Proposed fix: use `TemporaryDirectory` or unconditional `shutil.rmtree` in `finally`, covering copy, candidate-write, and reader exceptions. The narrow gate should compare the trial-directory set before and after.

Missed check: `launcher_registration_wizard` asserts the user file’s lifecycle but not its trial workspace’s lifecycle.

## Void readings

- The real corpus self-test passed its clean and injected-write-failure paths:

  ```text
  corpus-state --self-test: OK (a failed rollback restores; a clean one applies)
  ```

  Suppressing restoration made it fail, so that specific restoration control is genuine.

- `project → record-apply(applied) → project` preserved `last_apply`.
- The inherited-`GIT_DIR` insulation control passed; `core.worktree` remained unset and the subject tree stayed clean.
- Two synchronized registrations behaved intentionally: one landed and the later writer refused changed bytes. No lost update was found.
- A stale, unlocked `.lock` file did not block registration.
- A read race over 25 real registrations completed 4,000 `load_config` plus `load_review_methods` reads with zero torn-TOML errors:

  ```text
  WRITES 25
  READS 4000 ERRORS 0
  METHODS=25
  PUBLISH_TEMPS=0
  ```

- No supported-input/refused-input mismatch was established in the reader itself.
- The current release’s sole registered corpus version is correctly marked unavailable, so no live registered rollback was attempted; the rollback findings used commits satisfying `deployable()`.

## Denominator

Executed:

- `check_parity.py --list`.
- Real corpus self-tests, status projection/recording, sequential version transitions, partial-write injection, concurrent rollbacks, and two self-test mutations.
- `compose/check-domains.py`: passed with `77 bullets`.
- Real valid/refused registration trials, successful and failed publication, two-process registration race, stale-lock retry, 25-write/4,000-read race, and second-reader deletion mutation.
- Narrow `launcher_registration_wizard` and `launcher_review_editor` checks: passed as a partial `2/62` run.
- Read all 565 lines of `corpus-state.py`, its installer/launcher consumers, the registration reader/writer functions, and all 26 `launcher_review_editor` controls.

Only read: the actual assembler’s owned-surface logic, installer call wiring, registration catalogs, and unrelated context needed to bound consumers.

## Not examined

The full parity umbrella, installer E2E, actual Textual rendering, host backend dispatch, host CLIs, and hard-kill/power-loss durability.

The clone is restored clean at `bfcc567`; no scratch or tracked changes remain.

Scope note: one final repeat of the two narrow launcher checks was inadvertently invoked without the clone-local `TMPDIR` override. Given finding 7, it may have left temporary gate artifacts in the ambient temp area; I did not inspect or modify anything outside the clone afterward.
diff --git a/.review-root-scratch/probe_corpus_transitions.py b/.review-root-scratch/probe_corpus_transitions.py
new file mode 100644
index 0000000000000000000000000000000000000000..e93d865f14cba581601dbce08c3fe5bf461455f5
--- /dev/null
+++ b/.review-root-scratch/probe_corpus_transitions.py
@@ -0,0 +1,142 @@
+#!/usr/bin/env python3
+import json
+import os
+import pathlib
+import shutil
+import subprocess
+
+
+SUBJECT = pathlib.Path(__file__).resolve().parents[1]
+ROOT = pathlib.Path(__file__).resolve().parent / "corpus-transition"
+REPO = ROOT / "fixture-repo"
+HOME = ROOT / "home"
+CLAUDE = ROOT / "live-claude"
+CODEX = ROOT / "live-codex"
+STATE = HOME / ".local" / "share" / "agent-bios"
+STATUS = STATE / "corpus-status.json"
+GIT = shutil.which("git")
+
+REPO_ENV = {
+    "GIT_DIR", "GIT_WORK_TREE", "GIT_IMPLICIT_WORK_TREE", "GIT_INDEX_FILE",
+    "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
+    "GIT_PREFIX", "GIT_GRAFT_FILE", "GIT_SHALLOW_FILE", "GIT_NO_REPLACE_OBJECTS",
+    "GIT_REPLACE_REF_BASE", "GIT_CONFIG",
+}
+
+
+def clean_env() -> dict[str, str]:
+    env = {key: value for key, value in os.environ.items() if key not in REPO_ENV}
+    env.update({
+        "HOME": str(HOME),
+        "TMPDIR": str(ROOT / "tmp"),
+        "CLAUDE_CONFIG_DIR": str(CLAUDE),
+        "CODEX_HOME": str(CODEX),
+        "AGENT_BIOS_CORPUS_STATUS": str(STATUS),
+    })
+    return env
+
+
+def git(*args: str) -> str:
+    result = subprocess.run(
+        [GIT, "-C", str(REPO), *args],
+        check=True,
+        capture_output=True,
+        text=True,
+        env=clean_env(),
+    )
+    return result.stdout.strip()
+
+
+def write(rel: str, text: str) -> None:
+    path = REPO / rel
+    path.parent.mkdir(parents=True, exist_ok=True)
+    path.write_text(text, encoding="utf-8")
+
+
+def commit(message: str) -> str:
+    git("add", "-A")
+    git("-c", "user.email=probe@example.invalid", "-c", "user.name=probe",
+        "commit", "-qm", message)
+    return git("rev-parse", "HEAD")
+
+
+def run_subject(*args: str) -> subprocess.CompletedProcess[str]:
+    return subprocess.run(
+        ["python3", str(SUBJECT / "compose" / "corpus-state.py"), *args],
+        capture_output=True,
+        text=True,
+        env=clean_env(),
+        cwd=SUBJECT,
+    )
+
+
+def show(label: str, result: subprocess.CompletedProcess[str]) -> None:
+    print(f"{label}_RC={result.returncode}")
+    for line in (result.stdout + result.stderr).strip().splitlines():
+        print(f"{label}_OUT={line}")
+
+
+def main() -> None:
+    if ROOT.exists():
+        shutil.rmtree(ROOT)
+    for directory in (REPO, HOME, CLAUDE, CODEX, ROOT / "tmp", STATE):
+        directory.mkdir(parents=True, exist_ok=True)
+
+    git("init", "-q")
+    write("compose/assemble.py", "# target assembler exists\n")
+    write("compose/domains.json", json.dumps({"domains": []}) + "\n")
+    write("claude/CLAUDE.md", "OLD GLOBAL\n")
+    write("claude/guides/common.md", "OLD GUIDE\n")
+    write("claude/guides/legacy.md", "OLD LEGACY\n")
+    write("codex/guides/common.md", "OLD CODEX GUIDE\n")
+    old = commit("old corpus")
+
+    write("claude/CLAUDE.md", "NEW GLOBAL\n")
+    write("claude/guides/common.md", "NEW GUIDE\n")
+    (REPO / "claude/guides/legacy.md").unlink()
+    write("claude/guides/fresh.md", "NEW FRESH\n")
+    write("codex/guides/common.md", "NEW CODEX GUIDE\n")
+    new = commit("new corpus")
+
+    write("design/session-distill/versions.json", json.dumps({
+        "versions": [
+            {"version": "v1", "commit": old, "closed": "2026-01-01", "summary": "old"},
+            {"version": "v2", "commit": new, "closed": "2026-01-02", "summary": "new"},
+        ]
+    }) + "\n")
+    write("design/session-distill/ledger.json", json.dumps({"entries": []}) + "\n")
+    commit("version registry")
+
+    (STATE / "selection.json").write_text(
+        json.dumps({"version": 1, "domains": []}) + "\n", encoding="utf-8"
+    )
+    (CLAUDE / "central/guides").mkdir(parents=True)
+    (CLAUDE / "central/guides/common.md").write_text("NEW GUIDE\n")
+    (CLAUDE / "central/guides/fresh.md").write_text("NEW FRESH\n")
+    (CLAUDE / "central/bundle.md").write_text("NEW LIVE BUNDLE\n")
+    (CODEX / "guides").mkdir(parents=True)
+    (CODEX / "guides/common.md").write_text("NEW CODEX GUIDE\n")
+    (CODEX / "AGENTS.md").write_text("NEW LIVE CODEX GLOBAL\n")
+
+    project = run_subject("project", "--repo", str(REPO))
+    show("PROJECT", project)
+
+    rollback_old = run_subject("rollback", "--repo", str(REPO), "--version", "v1")
+    show("ROLLBACK_V1", rollback_old)
+    print("V1_COMMON=" + (CLAUDE / "central/guides/common.md").read_text().strip())
+    print("V1_FRESH_EXISTS=" + str((CLAUDE / "central/guides/fresh.md").exists()))
+    print("V1_LEGACY_EXISTS=" + str((CLAUDE / "central/guides/legacy.md").exists()))
+    print("V1_BUNDLE=" + (CLAUDE / "central/bundle.md").read_text().strip())
+    print("V1_CODEX_GLOBAL=" + (CODEX / "AGENTS.md").read_text().strip())
+    print("V1_STATUS=" + json.loads(STATUS.read_text())["current_version"])
+
+    rollback_new = run_subject("rollback", "--repo", str(REPO), "--version", "v2")
+    show("ROLLBACK_V2", rollback_new)
+    print("V2_COMMON=" + (CLAUDE / "central/guides/common.md").read_text().strip())
+    print("V2_FRESH_EXISTS=" + str((CLAUDE / "central/guides/fresh.md").exists()))
+    print("V2_LEGACY_EXISTS=" + str((CLAUDE / "central/guides/legacy.md").exists()))
+    print("V2_STATUS=" + json.loads(STATUS.read_text())["current_version"])
+
+
+if __name__ == "__main__":
+    main()

