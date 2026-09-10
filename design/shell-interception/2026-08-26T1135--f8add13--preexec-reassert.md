# Shell interception: reassert the entrypoints at preexec — implementation handoff

Dated record (written once, per AGENTS.md §2). Authored 2026-08-26 by a Claude session
working from `~/Documents/operator_platform` after diagnosing a live failure on this
machine; handed to the agent-bios session (`agent-bios-4c`, cwd `~/Documents/agent-bios`).

**요약 (KO):** cmux 터미널 안에서 bare `claude`가 agent-launch preflight를 거치지 않는다.
cmux의 zsh 통합이 `claude` 셸 함수를 첫 precmd에서 다시 덮어쓰기 때문이다(`codex`는 안 건드림).
대응은 cmux 전용 처리가 아니라 **끼어드는 방식 자체를 바꾸는 것**: 명령 실행 직전(preexec)에
우리 함수인지 확인하고 아니면 다시 정의한다. 후보 코드는 검증 완료(부정 대조군 포함), 아래 Appendix A.

## 0. Current state, one line

Design decided and the replacement `launch/agent-launch.zsh` is written and tested outside
the repo (Appendix A, sha256 prefix `dbab4a15ece27cb7`, file beside this record); nothing in
the repo is changed yet.

## 1. Pinned state

- Worktree `~/Documents/agent-bios`, branch `main`, HEAD `f8add13` (the record's own commit is
  never named; resume from the commit containing this file). The tree was dirty with unrelated
  `benchmarks/*` and `design/session-distill/*` work when this was written — not part of this item.
- Deployed copy on this machine comes from the **npm package** (`agent-bios status`: npm 0.13.0,
  source `/opt/homebrew/lib/node_modules/agent-bios`), not from this checkout. Re-derive:
  `agent-bios status | head -4`.
- Author tier for the implementation: WORKHORSE is enough (bounded zsh + bash + one gate);
  review cross-family per the repo's normal loop.

## 2. CONFIRMED (each claim carries the command that re-establishes it)

C1. Inside cmux, `claude` resolves to cmux's function, `codex` to ours.
```
printf 'whence -v claude\nwhence -v codex\n' | ZDOTDIR=/Applications/cmux.app/Contents/Resources/shell-integration \
  CMUX_SHELL_INTEGRATION_DIR=/Applications/cmux.app/Contents/Resources/shell-integration zsh -il 2>/dev/null | grep -a 'shell function'
# claude is a shell function            <- no "from": eval'd by cmux
# codex is a shell function from ~/.config/agent-launch/shell.zsh
```
C2. The override is deliberate and happens AFTER all rc files: symbol `_cmux_fix_path` in
`cmux-zsh-integration.zsh` ("reinstall cmux-owned wrapper functions in case user startup
replaced them"), registered on `precmd`, calls `_cmux_install_cli_wrapper claude …`, then
removes itself. Re-derive: `grep -n -a '_cmux_fix_path\|_cmux_install_cli_wrapper claude' /Applications/cmux.app/Contents/Resources/shell-integration/cmux-zsh-integration.zsh`.
C3. Re-sourcing `shell.zsh` from `~/.zshrc` does NOT fix it (rc runs before that precmd).
A `precmd` guard registered from `~/.zshenv` runs BEFORE cmux's (registration order) and loses
the first command; only from the second command on does it win. A `preexec` guard wins from
the first command. (Harness in Appendix B, cases T2/T3.)
C4. Downstream is unaffected: after reassert, `builtin command claude` resolves to cmux's
per-surface shim (first in PATH), whose wrapper injects `--session-id`/`--settings {hooks}` and
execs the real binary. agent-launch projects `--model/--effort/--append-system-prompt/
--permission-mode|--dangerously-skip-permissions`, never `--settings` → no collision.
Re-derive: `grep -n -o -E '"--(settings|append-system-prompt|permission-mode)[^"]*"' launch/agent-launch.py | sort -u`.
C5. With forwarded args agent-launch bypasses the TUI by design (symbol: `bypass = args.no_tui or bool(args.forward) …` in `launch/agent-launch.py`), which is why a PATH-level shim
cannot be our interception point (cmux's wrapper would hand it injected args).
C6. `zsh -ilc '…'` does not run precmd — it produced a false PASS during diagnosis. Only an
interactive shell fed on stdin (`printf … | zsh -il`) exercises the hook chain.
C7. A child `zsh -il` started from inside a cmux shell does NOT reproduce cmux's bootstrap
(cmux's `.zshenv` unsets the injected ZDOTDIR), so a child-shell canary reports PASS while
the live shell is shadowed. (Codex frontier cross-check, 2026-08-26, agreed; see §6.)
C8. Pre-existing and unrelated: `agent-bios status` says "zsh hook absent" on this machine —
`~/.zshrc` carries only the orphan comment `# Agent launch preflight…`; `~/.zshenv` (2026-07-27)
sources `shell.zsh` instead. Already so on 2026-08-06 (`grep -F agent-launch ~/.zshrc.bak-20260806-174644` → empty). The fix below does not depend on that line.

## 3. Design (decided)

**Mechanism.** `launch/agent-launch.zsh` keeps everything it has and adds:
1. `_agent_launch_define` — the single place that (re)defines `claude()`/`codex()` (the existing
   `unalias` + two function definitions move into it; the initial source calls it once).
2. `_agent_launch_reassert` — a `preexec` hook: for each host, if `$functions[host]` does not
   contain `_agent_launch_dispatch <host> `, note the shadow and call `_agent_launch_define`.
   O(1) string compare per command. Registered with remove-then-add so double sourcing keeps
   one registration.
3. `_agent_launch_note_shadow` — evidence, not repair: appends one line per host per shell
   (`ISO-UTC \t host \t $TERM_PROGRAM \t first line of the foreign body`) to
   `$HOME/.local/share/agent-bios/shell-shadow.log`. Never creates the state dir (no install →
   no log). This is the live-path evidence `status`/`verify` read (§5), replacing any child-shell
   canary (C7).

**Downstream stays `builtin command <host>`.** No chaining of foreign functions (no safe
"next handler" contract; recursion-prone; and the TUI path crosses `execve` anyway, so
function-only integrations cannot be preserved by any wrapper). A tool that owns a PATH shim
(cmux) keeps its behaviour; a tool that exists only as a function is reported (§5), not fought.

**Rejected.** PATH-level shim (C5; cmux re-prepends its shim at first prompt; loop guard
collisions). cmux-specific configuration (`CMUX_SHELL_INTEGRATION=0`, `CMUX_CUSTOM_CLAUDE_PATH`,
GUI binary path): not portable, repeats for the next tool, and the custom-path route still
injects args. Default-off switch: overkill — agent-bios already claims ownership of these two
names; this makes the existing contract durable, and rollback is `agent-bios install` of the
prior version or `uninstall`.

**Escalation rule.** A tool that re-defines the names in a preexec registered after ours still
wins. Do not escalate into hook warfare: the shadow log + `status` line make it visible; a
tool-specific adapter is considered only then, with evidence.

**Concept accounting (concept-economy).** Increasing, minimally: three private shell symbols
(`_agent_launch_define`, `_agent_launch_reassert`, `_agent_launch_note_shadow`) and one state
artifact (`shell-shadow.log`, in the state dir agent-bios already owns and already removes on
uninstall). No config key, no env var, no new failure kind, no public term. The existing
vocabulary "shell interception" (SURFACES.md) names the mechanism — reuse it; do not coin
"shadow guard" or similar in live docs.

## 4. Implementation plan (ordered; each step names its check)

S1. `launch/agent-launch.zsh` ← Appendix A verbatim (copy from the file beside this record;
    confirm `shasum -a 256 design/shell-interception/agent-launch.zsh.candidate | cut -c1-16` =
    `dbab4a15ece27cb7` before copying). Check: `zsh -n launch/agent-launch.zsh`, then the
    existing `launcher_syntax` in `gates/check_parity.py`.
S2. New launcher check in `gates/check_parity.py` (decorate with `@launcher_check`), name
    `launcher_shell_reassert`, implementing Appendix B with a temp HOME+ZDOTDIR (never the
    author's rc files; with HOME=tmp the state dir is absent, which also asserts the log is not
    created outside an install):
    - fixture `.zshenv`: `source <repo>/launch/agent-launch.zsh` + a synthetic shadower that
      redefines `claude` on precmd (T3a shape — mirrors cmux without needing cmux);
    - fixture `.zshrc`: override `_agent_launch_direct() { print "AGENT_LAUNCH_DIRECT host=$1 args=${*:2}" }`;
    - run `printf 'claude probe\n' | zsh -il` with `ZDOTDIR=<fixture> HOME=<tmp>`; assert
      stdout contains `AGENT_LAUNCH_DIRECT host=claude args=probe`;
    - NEGATIVE CONTROL in the same check: append `add-zsh-hook -d preexec _agent_launch_reassert`
      to the fixture `.zshrc` and assert the output now contains `SHADOW-RAN probe`. If the
      control does not fail, `mark_fail` ("reassert gate cannot distinguish") — a gate whose
      opposite input also passes proves nothing (C6 is the precedent).
    - also assert `<tmp>/.local/share/agent-bios/shell-shadow.log` does not exist afterwards.
    Check: `bash gates/check-parity.sh` green, and green only with S1 applied (run it once on
    the pre-S1 tree to see the new check fail).
S3. `install.sh`:
    - `cmd_status`: after the "zsh hook present/absent" line, if `$STATE_DIR/shell-shadow.log`
      exists print `info "shell interception: reasserted N time(s), last <ts> — <host> was shadowed by: <first line>"`,
      else `info "shell interception: no shadowing observed"`.
    - `cmd_verify`: print the same evidence line (never affects `fail` — a shadow that was
      repaired is the mechanism working), plus one live-check line:
      `info "live check (run in the terminal you use): whence -v claude   → expect …/agent-launch/shell.zsh"`.
      Do NOT add a child-shell canary that can say PASS (C7). If a future canary cannot
      reproduce the terminal's bootstrap it must say "inconclusive".
    - `cmd_uninstall`: nothing new if the state dir is already removed (it is — confirm by
      reading the uninstall path once; if the dir survives for any mode, remove the log there).
    Check: `bash install.sh status` and `bash install.sh verify` from the checkout print the
    lines; `bash gates/check-package.sh` (boundary), `python3 gates/check-lexicon.py`.
S4. Docs that the gates hold against code: `SURFACES.md` — the sentence naming "the shell
    interception in `launch/agent-launch.zsh`" (grep it) gains the reassert-at-preexec fact
    and the shadow-log evidence; `README.md` if it describes the zsh hook's contract; run
    `python3 gates/check-surfaces.py`. `LEXICON.md` is generated — add nothing unless a gate
    demands a term. Record the decision with `decisions/record-decision.py` (read its usage
    first). Update `IMPLEMENTATION_MAP.html` per the global rule.
S5. Live E2E on this machine (the only real-path proof; C7 says gates cannot substitute):
    1. deploy from the checkout: `bash ~/Documents/agent-bios/install.sh install --dry-run`
       to confirm REPO resolves to the checkout, then without `--dry-run`;
    2. open a NEW cmux surface (existing shells keep the old functions);
    3. `whence -v claude` → `…/agent-launch/shell.zsh`; `whence -v codex` same;
    4. bare `claude` → the preflight TUI appears; pick any preset and confirm the launched
       session still carries cmux's hooks (`ps -o args= -p $(pgrep -n -f '.local/bin/claude') | grep -c -- --session-id` → 1);
    5. `agent-bios status` → the shell-interception line names
       `_cmux_claude_wrapper_command "$@"` as the shadower;
    6. control: `AGENT_LAUNCH_TUI=0 claude --version` still goes straight through (no TUI).

## 5. Done-when (machine-checkable where possible)

- [ ] `bash gates/check-parity.sh` green, including `launcher_shell_reassert`, and the same
      check fails on a tree with S1 reverted (`git stash` the zsh change and run once).
- [ ] `bash gates/check-package.sh`, `python3 gates/check-lexicon.py`,
      `python3 gates/check-surfaces.py` green.
- [ ] S5 steps 3–6 observed in a fresh cmux surface; `shell-shadow.log` has one line for that
      shell naming `_cmux_claude_wrapper_command`.
- [ ] No behaviour change outside a shadowed shell: T5 (clean shell → no log file, same
      dispatch) holds; `git diff launch/agent-launch.zsh` shows only additions plus the moved
      `unalias`/definitions.

## 6. PROPOSED / OPEN

- Codex frontier cross-check (2026-08-26, `codex exec -s read-only -m gpt-5.6-sol`, blind
  packet) agreed on reassert + evidence, rejected PATH shim / chaining / default-off switch,
  and supplied C7. It proposed precmd-with-re-add (relying on the `.zshrc` re-source line);
  preexec supersedes that because it wins regardless of registration order and does not depend
  on C8's missing line. Its remaining suggestion — a receipt-emitting sentinel that proves
  wrapper → agent-launch → downstream exactly once — is a larger canary than this item needs;
  OPEN, not scheduled.
- Whether `agent-bios install` should re-add the `.zshrc` hook line on this machine (C8) is a
  separate, pre-existing item; the reassert works without it.
- Other terminals/tools that wrap `claude` (Superset hooks, mobius, "claude-3" aliases seen in
  history) were not tested; the gate's synthetic shadower covers the class "redefine on precmd",
  and the shadow log will name any other instance when it happens.

## Appendix A — `launch/agent-launch.zsh` (tested candidate; identical to the file beside this record)

```zsh
# Interactive zero-argument entrypoints use agent-launch. Every argument-bearing
# or non-TTY call skips profile projection; Claude retains its direct-path
# permission-bypass default.
_agent_launch_direct() {
  local host="$1"
  shift
  # `builtin command`, not bare `command`. The point of this line is to reach the real
  # binary without re-entering a shell function, and zsh lets a user define `command()`
  # — at which point the bare form calls THAT, and the direct path this wrapper exists to
  # provide is handed to whatever the user's function does. `builtin` cannot be shadowed,
  # so the resolution is the one the comment above already promised.
  if [[ "$host" == "claude" ]]; then
    builtin command claude --dangerously-skip-permissions "$@"
  else
    builtin command codex "$@"
  fi
}

_agent_launch_dispatch() {
  local host="$1"
  shift
  local launcher="${AGENT_LAUNCH_BIN:-$HOME/.local/bin/agent-launch}"

  if [[ $# -gt 0 && "$1" == "--no-tui" ]]; then
    shift
    _agent_launch_direct "$host" "$@"
  elif [[ $# -eq 0 && -t 0 && -t 1 && "${AGENT_LAUNCH_TUI:-1}" != "0" ]]; then
    "$launcher" "$host"
  else
    _agent_launch_direct "$host" "$@"
  fi
}

# The entrypoints are (re)defined from one place so the reassert below installs the
# same thing the initial source did.
_agent_launch_define() {
  unalias codex 2>/dev/null
  unalias claude 2>/dev/null
  codex() { _agent_launch_dispatch codex "$@"; }
  claude() { _agent_launch_dispatch claude "$@"; }
}
_agent_launch_define

# Reassert the entrypoints right before each command runs. "Last definer wins" is
# the shell's rule, and a terminal or tool that defines `claude` after the rc files
# (cmux does, on its first precmd — deliberately, "in case user startup replaced
# them") would otherwise win in silence: bare `claude` skips the preflight while
# `codex` keeps working. preexec runs after every precmd, whatever the registration
# order, so the check is the last word at the only moment that matters. Cost: one
# string compare per command. The downstream stays `builtin command <host>`, so a
# tool that also owns a PATH shim (cmux) keeps its own injection.
zmodload -i zsh/parameter 2>/dev/null
typeset -gA _agent_launch_shadow_noted
_agent_launch_note_shadow() {
  setopt localoptions extendedglob
  local host="$1" foreign="$2" state="$HOME/.local/share/agent-bios" first
  local -a lines
  # One line per host per shell, into the state dir agent-bios already owns — the
  # evidence `agent-bios status`/`verify` read. Never create the dir: no install, no log.
  [[ -n "${_agent_launch_shadow_noted[$host]-}" || ! -d "$state" ]] && return
  _agent_launch_shadow_noted[$host]=1
  lines=("${(@f)foreign}")
  first="${lines[1]##[[:space:]]#}"
  printf '%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$host" \
    "${TERM_PROGRAM:-unknown}" "${first:-<undefined>}" >> "$state/shell-shadow.log" 2>/dev/null
}
_agent_launch_reassert() {
  local host
  for host in claude codex; do
    if [[ "${functions[$host]-}" != *"_agent_launch_dispatch $host "* ]]; then
      _agent_launch_note_shadow "$host" "${functions[$host]-}"
      _agent_launch_define
      return
    fi
  done
}
autoload -Uz add-zsh-hook
add-zsh-hook -d preexec _agent_launch_reassert 2>/dev/null
add-zsh-hook preexec _agent_launch_reassert
```

## Appendix B — harness that produced the evidence (turn into `launcher_shell_reassert`)

Run from any directory; `C` is the candidate file, `INT` cmux's integration dir (only for T2).
All six cases passed on 2026-08-26 with the file above.

```bash
C=<candidate>; INT=/Applications/cmux.app/Contents/Resources/shell-integration; S=<tmp>
mk() { d="$S/$1"; mkdir -p "$d"
  printf 'source "%s"\n%s\n' "$C" "$2" > "$d/.zshenv"
  printf '_agent_launch_direct() { print "AGENT_LAUNCH_DIRECT host=$1 args=${*:2}"; }\n%s\n' "$3" > "$d/.zshrc"; }
run_plain() { printf '%s\n' "$2" | HOME="$S/home" ZDOTDIR="$S/$1" zsh -il 2>/dev/null | grep -a -o 'AGENT_LAUNCH_DIRECT.*\|SHADOW.*'; }
run_cmux()  { printf '%s\n' "$2" | ZDOTDIR="$INT" CMUX_ZSH_ZDOTDIR="$S/$1" CMUX_SHELL_INTEGRATION_DIR="$INT" zsh -il 2>/dev/null | grep -a -o 'AGENT_LAUNCH_DIRECT.*\|SHADOW.*'; }
SHADOW='autoload -Uz add-zsh-hook; _shadow_once() { eval "claude() { print SHADOW-RAN \$*; }"; add-zsh-hook -d precmd _shadow_once; }; add-zsh-hook precmd _shadow_once'
SHADOW_EACH='autoload -Uz add-zsh-hook; _shadow_each() { eval "claude() { print SHADOW-RAN \$*; }"; }; add-zsh-hook precmd _shadow_each'

# T1 syntax                     zsh -n "$C"
# T2 cmux bootstrap, 1st cmd    mk t2 "" "";            run_cmux  t2 $'claude foo\ncodex bar'   # both AGENT_LAUNCH_DIRECT
# T3a generic shadower          mk t3a "$SHADOW" "";    run_plain t3a 'claude foo'             # AGENT_LAUNCH_DIRECT host=claude args=foo
# T3b NEGATIVE CONTROL          mk t3b "$SHADOW" 'add-zsh-hook -d preexec _agent_launch_reassert'; run_plain t3b 'claude foo'   # SHADOW-RAN foo
# T4 log line (needs state dir) one line: <utc>\tclaude\t<TERM_PROGRAM>\t_cmux_claude_wrapper_command "$@"
# T5 clean shell                mk t5 "" "";            run_plain t5 'claude x'; no shell-shadow.log created
# T6 every-prompt shadower      mk t6 "$SHADOW_EACH" ""; run_plain t6 $'claude a\nclaude b'    # both ours; log has 1 line
```

The gate needs T3a + T3b (+ the no-log assertion of T5); T2 requires cmux and belongs to S5,
not to the gate.
