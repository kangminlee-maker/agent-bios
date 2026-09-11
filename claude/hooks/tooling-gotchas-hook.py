#!/usr/bin/env python3
"""PreToolUse(Bash) hook: inject tooling-gotchas reminders on matching commands.

Read-only context injection only — never blocks, rewrites, or judges (hook
charter, design/session-distill/PLACEMENT-FRAMEWORK.md). Message text derives
from claude/guides/tooling-gotchas.md; edit the guide first, then sync here.
The verification suite greps each message's anchor phrase against the guide.
"""
import json
import re
import sys

GUIDE = "guides/tooling-gotchas.md"

# (name, compiled trigger, one-line reminder, guide anchor). Priority order; max 2 injected.
#
# Each anchor names the canonical guide section compressed by this shared hook.
# Both hosts receive the same command payload and additionalContext response.
# The guide remains available when native hooks are disabled, untrusted, or do
# not cover a tool path. --self-test checks every anchor against both guide trees.
RULES = [
    ("reserved-shell-names",
     re.compile(r"\b(UID|EUID|GID|PPID)="),
     "Assigning reserved shell names (UID/EUID/GID/PPID) can invoke the bound "
     f"system behavior instead of storing a value — use unreserved names ({GUIDE}).",
     "Reserved parameter names"),
    ("git-diff-two-dot",
     re.compile(r"git\s+diff\s+[^|;&]*(?<!\.)\.\.(?!\.)"),
     "git diff A..B is a direct snapshot comparison, not a range exclusion — "
     f"for PR/review diffs use three-dot origin/base...HEAD ({GUIDE}).",
     "Two-dot diff semantics"),
    ("git-pull-dirty",
     re.compile(r"\bgit\s+pull\b"),
     "Before pulling into a worktree with local changes: fetch first, compare "
     f"incoming paths against dirty paths, prefer --ff-only ({GUIDE}).",
     "Dirty-worktree pulls"),
    ("metachar-inline-arg",
     re.compile(r"(codex-run|codex-helm|codex\s+exec|claude\s+-p)\b[^|;&]*[\"'][^\"']*(\$\(|`)"),
     "Values with shell metacharacters must reach the target via stdin or a "
     f"file, not inline arguments — the shell expands them first ({GUIDE}).",
     "Metacharacter-bearing values"),
    ("pipe-exit-masking",
     re.compile(r"\$\?"),
     "A pipeline's $? reflects only the last stage — capture the tested "
     f"stage's own status (unpiped run, PIPESTATUS, per-command pipefail) ({GUIDE}).",
     "Pipe exit masking"),
    # Path-shaped argument only: `git checkout main` is a branch switch and needs no
    # warning, while `git checkout src/x.py` silently discards every uncommitted edit in
    # that file — including ones the caller did not put there.
    ("git-checkout-path",
     re.compile(r"\bgit\s+(checkout|restore)\b[^|;&]*(--\s|[\w.-]*[./][\w./-]*)"),
     "Reverting a path discards ALL uncommitted edits in that file, not just the one "
     f"you planted — check `git diff <path>` first, or restore from a copy ({GUIDE}).",
     "Reverting a path is not undoing your edit"),
    # A sweeping write treats every delta in the tree as the caller's own. Named paths
    # (`git add src/x.py`) are exempt: naming is the attribution the rule asks for.
    ("shared-tree-sweep",
     # The commit flag must be its own token: a path like /x/-agent/msg.txt after -F carries
     # "-a" too, and the first version of this rule fired on exactly that.
     re.compile(r"\bgit\s+(add\s+(-A|--all|\.)(\s|$)|commit\s+(?:[^|;&]*\s)?(?:-[a-zA-Z]*a[a-zA-Z]*|--all)(?=\s|$)|stash\b(?!\s+(pop|apply|list|show))|clean\b|reset\s+--hard)"),
     "A shared tree may hold another operator's work — attribute every delta you did not "
     f"make (git status, reflog, live sessions) before sweeping it; add by name ({GUIDE}).",
     "A shared tree holds other operators' work"),
    ("job-logs-by-execution",
     re.compile(r"\bgcloud\s+(?:alpha\s+|beta\s+)?(?:logging\s+read|run\s+jobs)\b"),
     "Job-level logs retain earlier executions (even a job deleted and recreated under the "
     f"same name) — scope the read to the execution id you launched ({GUIDE}).",
     "Job logs outlive the execution"),
    ("name-substring-liveness",
     re.compile(r"\bpgrep\s+(?:-\w+\s+)*-\w*f|\bps\b[^|\n]*\|[^|\n]*\bgrep\b"),
     "A name-substring process lookup matches the querying shell's own argv and unrelated "
     f"same-named processes — confirm liveness by PID, handle, or output growth ({GUIDE}).",
     "Name-substring lookup is not a liveness check"),
    # Not a search for the word: a grep/rg over sources mentions revoke without revoking.
    ("revoke-grant-blast-radius",
     re.compile(r"^(?!.*\b(?:rg|grep|ag|git\s+log)\b).*\brevoke\b"),
     "A revoke is grant-wide: everything issued under a shared client id, including the "
     f"user's live sessions, goes with it — confirm the scope before revoking ({GUIDE}).",
     "A revoke is grant-wide, not token-wide"),
    ("grep-binary-heuristic",
     # Applied per extracted STAGE by matches(), not to the raw line. The stage's
     # COMMAND WORD must be grep — after optional reserved words (`if ! grep -q`
     # is the assert-absence idiom) and per-command assignments (`LC_ALL=C grep`
     # — locale pinning is what our own guides recommend); bare, path-prefixed,
     # or the DIRECT git subcommand (git grep shares the binary heuristic). A
     # stage that merely passes the word along (`echo grep needle`) runs no grep
     # and gets no reminder. Greps reached through any other prefix — sudo,
     # xargs, git global options between git and the subcommand (`git -C repo
     # grep`), env, timeout, and their successors — are accepted residual by
     # decision: each is one rung of an endless prefix ladder, and a missed
     # reminder is the failure mode this advisory-only hook tolerates.
     re.compile(r"\s*(?:(?:!|if|elif|else|then|do|while|until|time)\s+)*"
                r"(?:\w+=\S*\s+)*(?:\S+/)?(?:git\s+)?grep\s"),
     "grep can misread text with heavy non-ASCII/NUL as binary and return a "
     f"false no-match — prefer the Grep tool (ripgrep) or grep -a ({GUIDE}).",
     "grep binary heuristic"),
]
MAX_INJECT = 2


def matches(command: str, limit: int | None = MAX_INJECT):
    """Rules this command trips. `limit` is a DELIVERY policy — at most two reminders are
    worth injecting at once — not a judgement about which rules matched, so the self-test
    asks for the untruncated list rather than re-deriving the matching itself."""
    hits = []
    for name, rx, msg, _ in RULES:
        if name == "pipe-exit-masking" and "|" not in command:
            continue
        if name == "grep-binary-heuristic":
            # Per STAGE, not per command: -a on an upstream grep does nothing for a
            # downstream one (`git grep -a foo | grep bar` leaves bar's stage on the
            # binary heuristic), so the exemption holds only when EVERY grep stage
            # carries its own text-mode flag.
            # Every separator starts a new stage: a single & (background) and a newline
            # join commands as surely as ; and | — `grep -a foo a & grep bar b` left the
            # -a covering a stage it never touches.
            # A command substitution executes regardless of the quotes around it:
            # `echo "$(grep needle payload)"` runs that grep, and quote-blanking was
            # hiding it from the stage list so an outer -a covered it. Substitution
            # bodies are lifted out (innermost-first, to a fixpoint) and judged as
            # stages of their own.
            scan = command
            seen_subs = set()
            while True:
                subs = [s2 for s2 in re.findall(r"\$\(([^()]*)\)", scan)
                        + re.findall(r"`([^`]*)`", scan)
                        if s2 not in seen_subs]
                if not subs:
                    break
                seen_subs.update(subs)
                scan = scan + "\n" + "\n".join(subs)
            # Quotes are blanked BEFORE splitting: a separator inside a quoted pattern
            # (`grep 'grep -a;foo'`) manufactured a pseudo-stage carrying a text-mode
            # flag that exists only as pattern content. Blanked to a placeholder TOKEN,
            # not to nothing: `grep -e "needle" -a file` blanked to whitespace left -e
            # to consume the -a as its argument, and the real text-mode flag vanished
            # with the operand's token boundary.
            blanked = re.sub(r"'[^']*'|\"(?:\\\\.|[^\"\\\\])*\"", "0", scan)
            # Comments go after the quotes: with quoted text blanked, any remaining # is
            # a real comment, and `grep needle payload # use -a next time` was exempting
            # itself with advice bash never passes to grep.
            blanked = re.sub(r"#[^\n]*", "", blanked)
            # Parens split as the old line-shaped trigger's [;&(|] class did: a
            # subshell or group opener starts a command (`(grep needle)` runs grep),
            # and dropping ( from the boundaries regressed exactly that form.
            stages = [st for st in re.split(r"\|\||&&|[|;&\n()]", blanked)
                      if rx.match(st)]
            # The STAGES are the trigger: a grep whose only appearance is inside a
            # lifted substitution (`echo "\`grep needle payload\`"`) never matched a
            # line-shaped regex, and a quoted assignment value (`FILTER='two words'
            # grep ...`) hid the command word from it. The rule's regex judges each
            # stage in COMMAND-WORD position — `echo grep needle` passes the word as
            # an argument, runs no grep, and stays quiet.
            if not stages:
                continue
            # Options end at `--`: after it, `-a` is the PATTERN operand (grep's usage is
            # [OPTION]... PATTERNS [FILE]...), so `grep -- -a payload` is still on the
            # binary heuristic and must keep its reminder.
            # And `-e <pattern>` consumes its argument: in `grep -e -a payload` the -a
            # is the PATTERN (grep --help: -e, --regexp=PATTERNS), so it must not read
            # as text mode. The pattern-taking options are blanked before the flag scan.
            # -f/--file consumes its argument the same way (-f, --file=FILE): every
            # pattern-taking option is blanked, or its argument reads as a flag.
            # Quoted text is pattern content, never options: `grep 'foo -a bar'` has no
            # text-mode flag, and the unquoted scan read the -a inside the pattern.
            # Quotes are blanked first, then the -- operand split, then pattern-taking
            # option arguments.
            opts = [re.sub(r"(^|\s)(?:-e|--regexp|-f|--file)(?:=\S+|\s+\S+)", " ",
                           st.split(" -- ", 1)[0])
                    for st in stages]

            # Bundled short options count too: `grep -qa` enables text mode (grep
            # --help: -a, --text), and requiring a whitespace-delimited -a warned
            # about binary data on a grep that reads it as text. A letter that takes
            # an argument (-e -f -m -A -B -C -d -D) consumes the REST of the bundle,
            # so in `-ea` the a is the PATTERN, not a flag — an `a` reads as text
            # mode only when every letter before it is argument-free.
            def text_mode(o):
                if re.search(r"(^|\s)(-a\b|--text\b|--binary-files(?:=|\s+)text\b)", o):
                    return True
                return any(len(halves) == 2 and not set(halves[0]) & set("efmABCdD")
                           for tok in re.findall(r"(?:^|\s)-([A-Za-z0-9]+)", o)
                           for halves in [tok.split("a", 1)])

            if all(text_mode(o) for o in opts):
                continue
            hits.append((name, msg))
            continue
        if rx.search(command):
            hits.append((name, msg))
    return hits if limit is None else hits[:limit]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # never block on malformed input
    # Malformed is a SHAPE, not just a parse failure. The guard above only covered bytes
    # that are not JSON; a well-formed payload of the wrong shape — a top-level array, a
    # list-valued tool_input, a non-string command — walked straight into `.get` or into
    # `re.search` and left this hook exiting 1 with a traceback. That is the one thing
    # the charter says it never does, and it would do it before EVERY Bash call in every
    # deployed session, on a payload shape decided by a host this repo does not own.
    # Advisory means silent on anything it cannot read, so each check returns 0.
    if (not isinstance(payload, dict) or payload.get("tool_name") != "Bash"
            or payload.get("hook_event_name", "PreToolUse") != "PreToolUse"):
        return 0
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not command:
        return 0
    hits = matches(command)
    if not hits:
        return 0
    context = " ".join(msg for _, msg in hits)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": context,
        }
    }))
    return 0


def self_test() -> int:
    """Check shared stdin/output behavior and the guide fallback on both hosts."""
    import pathlib, subprocess

    here = pathlib.Path(__file__).resolve()
    repo = here.parent.parent.parent
    problems = []
    assert RULES, "no rules: this self-test would pass over nothing"

    # -- half 1: the hook runs, matches, and emits. A file that is copied and registered but
    # crashes on every invocation satisfies every other check in this repository.
    fires = "UID=0 echo hi"
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": fires}})
    r = subprocess.run([sys.executable, str(here)], input=payload,
                       capture_output=True, text=True)
    if r.returncode != 0:
        problems.append(f"hook exited {r.returncode} on a matching command: {r.stderr.strip()[:120]}")
    elif "additionalContext" not in r.stdout:
        problems.append(f"hook emitted no context for {fires!r}; got {r.stdout.strip()[:80]!r}")

    # A non-matching command must stay silent, or "it fired" proves nothing.
    quiet = json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo hello"}})
    r2 = subprocess.run([sys.executable, str(here)], input=quiet, capture_output=True, text=True)
    if r2.stdout.strip():
        problems.append(f"hook injected on a command that matches nothing: {r2.stdout.strip()[:80]!r}")

    # Never-blocks is a claim about EVERY payload, so the shapes that are valid JSON and
    # not the expected object are the ones worth naming. Each of these exited 1 with a
    # traceback before the shape guard existed, and each stands for a different way the
    # host's payload could move: a different top-level type, a different tool_input type,
    # a command that is not a string. The two controls above are the other half — a guard
    # that returns 0 on everything would satisfy this block and nothing else.
    for label, raw in (
        ("top-level array", "[1, 2, 3]"),
        ("top-level null", "null"),
        ("top-level string", '"hello"'),
        ("tool_input as a list", '{"tool_name": "Bash", "tool_input": [1, 2]}'),
        ("tool_input as null", '{"tool_name": "Bash", "tool_input": null}'),
        ("command as a number", '{"tool_name": "Bash", "tool_input": {"command": 123}}'),
        ("command as a list", '{"tool_name": "Bash", "tool_input": {"command": ["git", "pull"]}}'),
        ("command absent", '{"tool_name": "Bash", "tool_input": {}}'),
        ("empty stdin", ""),
        ("wrong event", '{"hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"git pull"}}'),
    ):
        r3 = subprocess.run([sys.executable, str(here)], input=raw, capture_output=True, text=True)
        if r3.returncode != 0:
            problems.append(
                f"hook exited {r3.returncode} on {label} instead of staying silent: "
                f"{r3.stderr.strip()[-120:]}")
        elif r3.stdout.strip():
            problems.append(f"hook injected context for {label}: {r3.stdout.strip()[:80]!r}")

    # Every rule needs a command that must reach it. A nonempty pattern is not evidence: a
    # trigger of `(?!)` can never match, and a rule suppressed by the special-case logic in
    # matches() never reaches the caller either — both leave the rule inert while this file
    # goes on reporting that all of them fire.
    FIXTURES = {
        "reserved-shell-names":  "UID=0 echo hi",
        "git-diff-two-dot":      "git diff main..HEAD",
        "git-pull-dirty":        "git pull origin main",
        "metachar-inline-arg":   'codex exec "$(cat packet.md)"',
        "pipe-exit-masking":     "make build | tail -1; echo $?",
        "git-checkout-path":     "git checkout src/thing.py",
        "shared-tree-sweep":     "git add -A && git commit -m x",
        "job-logs-by-execution": "gcloud logging read 'resource.labels.job_name=probe' --limit 50",
        "name-substring-liveness": "pgrep -f codex",
        "revoke-grant-blast-radius": "gcloud auth revoke probe@example.com",
        "grep-binary-heuristic": "grep needle haystack.md",
    }
    # Naming the path IS the attribution the sweep rule asks for, so a named add, a
    # plain commit, and stash pop must not draw the reminder — or it fires on every commit.
    for quiet_cmd in ("git add src/thing.py", "git commit -m 'fix'", "git stash pop", "git add -p",
                      "git commit -F /tmp/claude-501/-Users-someone-Documents-agent-bios/scratch/msg.txt"):
        if "shared-tree-sweep" in [h for h, _ in matches(quiet_cmd, limit=None)]:
            problems.append(f"shared-tree-sweep: fired on a non-sweeping command ({quiet_cmd!r})")
    for sweep_cmd in ("git add .", "git commit -am 'wip'", "git commit --all -m x", "git stash", "git reset --hard HEAD"):
        if "shared-tree-sweep" not in [h for h, _ in matches(sweep_cmd, limit=None)]:
            problems.append(f"shared-tree-sweep: did not fire on a sweeping command ({sweep_cmd!r})")
    for quiet_cmd in ("gcloud run services list", "docker logs probe", "kill -0 12345",
                      "grep -rn pgrep claude/guides/", "ls | grep foo", "rg revoke src/",
                      "git log --grep revoke"):
        hit = [h for h, _ in matches(quiet_cmd, limit=None)]
        for rule in ("job-logs-by-execution", "name-substring-liveness", "revoke-grant-blast-radius"):
            if rule in hit:
                problems.append(f"{rule}: fired on a non-matching command ({quiet_cmd!r})")
    for rule, cmd in (("job-logs-by-execution", "gcloud beta run jobs executions list --job probe"),
                      ("name-substring-liveness", "ps aux | grep codex"),
                      ("revoke-grant-blast-radius", "vault token revoke s.f3b9c2")):
        if rule not in [h for h, _ in matches(cmd, limit=None)]:
            problems.append(f"{rule}: did not fire on ({cmd!r})")
    # A pipeline-stage grep must reach the rule too — the fixture alone exercises only
    # command-start grep, and the reminder is most needed mid-pipeline.
    if "grep-binary-heuristic" not in [h for h, _ in matches("cat payload | grep needle", limit=None)]:
        problems.append("grep-binary-heuristic: does not fire on a pipeline stage "
                        "('cat payload | grep needle')")
    if "grep-binary-heuristic" not in [h for h, _ in matches("git grep -a foo | grep bar", limit=None)]:
        problems.append("grep-binary-heuristic: an upstream -a cancelled the reminder for "
                        "a downstream grep that has no text-mode flag")
    if "grep-binary-heuristic" in [h for h, _ in matches("git grep -a foo | grep -a bar", limit=None)]:
        problems.append("grep-binary-heuristic: fired although every grep stage carries "
                        "its own text-mode flag")
    if "grep-binary-heuristic" not in [h for h, _ in matches("grep -- -a payload", limit=None)]:
        problems.append("grep-binary-heuristic: '-a' AFTER the -- marker is the pattern "
                        "operand, not a flag, and the reminder was suppressed")
    if "grep-binary-heuristic" in [h for h, _ in matches("grep -a -- pattern file.md", limit=None)]:
        problems.append("grep-binary-heuristic: fired although -a precedes the -- marker")
    if "grep-binary-heuristic" not in [h for h, _ in matches("grep -e -a payload", limit=None)]:
        problems.append("grep-binary-heuristic: '-a' as the ARGUMENT of -e is the pattern, "
                        "not text mode, and the reminder was suppressed")
    if "grep-binary-heuristic" in [h for h, _ in matches("grep -a -e pattern file.md", limit=None)]:
        problems.append("grep-binary-heuristic: fired although -a stands alone before -e")
    if "grep-binary-heuristic" not in [h for h, _ in matches("grep -f -a payload", limit=None)]:
        problems.append("grep-binary-heuristic: '-a' as the ARGUMENT of -f is a pattern "
                        "file, not text mode, and the reminder was suppressed")
    if "grep-binary-heuristic" not in [h for h, _ in matches("grep 'foo -a bar' payload", limit=None)]:
        problems.append("grep-binary-heuristic: a text-mode spelling INSIDE a quoted "
                        "pattern is pattern content, and the reminder was suppressed")
    if "grep-binary-heuristic" in [h for h, _ in matches("grep -a 'foo bar' payload", limit=None)]:
        problems.append("grep-binary-heuristic: fired although -a stands outside the "
                        "quoted pattern")
    if "grep-binary-heuristic" not in [h for h, _ in matches("grep 'grep -a;foo' payload", limit=None)]:
        problems.append("grep-binary-heuristic: a separator inside a quoted pattern "
                        "manufactured a pseudo-stage whose -a suppressed the reminder")
    if "grep-binary-heuristic" in [h for h, _ in matches("grep -a 'x;y' payload", limit=None)]:
        problems.append("grep-binary-heuristic: fired although the real stage carries -a "
                        "and the separator is only pattern content")
    if "grep-binary-heuristic" not in [h for h, _ in
                                       matches('echo "`grep needle payload`" | grep -a foo', limit=None)]:
        problems.append("grep-binary-heuristic: a LEGACY backtick substitution's grep lost "
                        "its reminder to the outer stage's -a")
    if "grep-binary-heuristic" not in [h for h, _ in
                                       matches('echo "`grep needle payload`"', limit=None)]:
        problems.append("grep-binary-heuristic: a grep whose ONLY appearance is a lifted "
                        "substitution never triggered")
    if "grep-binary-heuristic" in [h for h, _ in
                                   matches("grep -a needle payload # note", limit=None)]:
        problems.append("grep-binary-heuristic: fired although the real invocation "
                        "carries -a and only the comment follows")
    if "grep-binary-heuristic" not in [h for h, _ in
                                       matches("grep needle payload # use -a next time", limit=None)]:
        problems.append("grep-binary-heuristic: advice in a trailing comment exempted a "
                        "grep bash never passes it to")
    if "grep-binary-heuristic" not in [h for h, _ in
                                       matches("FILTER='two words' grep needle payload", limit=None)]:
        problems.append("grep-binary-heuristic: a quoted assignment value hid the command "
                        "word from the trigger")
    for argcmd in ("echo grep needle", "command -v grep"):
        if "grep-binary-heuristic" in [h for h, _ in matches(argcmd, limit=None)]:
            problems.append(f"grep-binary-heuristic: fired although grep is an ARGUMENT, "
                            f"not the stage's command word ({argcmd!r})")
    if "grep-binary-heuristic" not in [h for h, _ in
                                       matches("if ! grep -q needle payload; then echo none; fi",
                                               limit=None)]:
        problems.append("grep-binary-heuristic: reserved words and negation before the "
                        "command word suppressed the reminder")
    if "grep-binary-heuristic" not in [h for h, _ in
                                       matches("/usr/bin/grep needle payload", limit=None)]:
        problems.append("grep-binary-heuristic: a path-prefixed grep is still grep, and "
                        "the reminder was suppressed")
    for bundled in ("grep -qa needle payload", "grep -aH needle payload",
                    "cat payload | grep -qa needle"):
        if "grep-binary-heuristic" in [h for h, _ in matches(bundled, limit=None)]:
            problems.append(f"grep-binary-heuristic: fired although a bundled short "
                            f"option enables text mode ({bundled!r})")
    for consumed in ("grep -ea payload", "grep -fa payload"):
        if "grep-binary-heuristic" not in [h for h, _ in matches(consumed, limit=None)]:
            problems.append(f"grep-binary-heuristic: an 'a' consumed as an option "
                            f"ARGUMENT read as text mode ({consumed!r})")
    for grouped in ("(grep needle payload)", "if (grep needle payload); then echo found; fi"):
        if "grep-binary-heuristic" not in [h for h, _ in matches(grouped, limit=None)]:
            problems.append(f"grep-binary-heuristic: a subshell-grouped grep lost its "
                            f"reminder to the opening paren ({grouped!r})")
    for qop in ('grep -e "needle" -a file', 'grep -f "patterns.txt" -a file'):
        if "grep-binary-heuristic" in [h for h, _ in matches(qop, limit=None)]:
            problems.append(f"grep-binary-heuristic: fired although -a stands after a "
                            f"QUOTED pattern operand — blanking ate the token boundary "
                            f"({qop!r})")
    if "grep-binary-heuristic" not in [h for h, _ in
                                       matches('grep -e "needle" file', limit=None)]:
        problems.append("grep-binary-heuristic: a quoted pattern operand with no "
                        "text-mode flag was read as exempt")
    for bf in ("grep --binary-files=text needle payload",
               "grep --binary-files text needle payload"):
        if "grep-binary-heuristic" in [h for h, _ in matches(bf, limit=None)]:
            problems.append(f"grep-binary-heuristic: fired although --binary-files "
                            f"selects text handling ({bf!r})")
    if "grep-binary-heuristic" not in [h for h, _ in
                                       matches("grep --binary-files without-match needle payload",
                                               limit=None)]:
        problems.append("grep-binary-heuristic: a non-text --binary-files TYPE was "
                        "read as text mode")
    if "grep-binary-heuristic" in [h for h, _ in matches("(grep -a needle payload)", limit=None)]:
        problems.append("grep-binary-heuristic: fired although the subshell-grouped "
                        "grep carries its own text-mode flag")
    for envcmd in ("LC_ALL=C grep needle payload", "cat payload | LC_ALL=C grep needle"):
        if "grep-binary-heuristic" not in [h for h, _ in matches(envcmd, limit=None)]:
            problems.append(f"grep-binary-heuristic: an env-assignment prefix hid the "
                            f"command word ({envcmd!r})")
    if "grep-binary-heuristic" not in [h for h, _ in
                                       matches('echo "$(grep needle payload)" | grep -a foo', limit=None)]:
        problems.append("grep-binary-heuristic: a grep inside a command substitution lost "
                        "its reminder to the outer stage's -a")
    if "grep-binary-heuristic" in [h for h, _ in
                                   matches('echo "$(grep -a needle payload)" | grep -a foo', limit=None)]:
        problems.append("grep-binary-heuristic: fired although every invocation, nested "
                        "included, carries its own text-mode flag")
    if "grep-binary-heuristic" not in [h for h, _ in matches("grep -a foo a & grep bar b", limit=None)]:
        problems.append("grep-binary-heuristic: a background-joined second grep with no "
                        "text-mode flag lost its reminder to the first stage's -a")
    if "grep-binary-heuristic" not in [h for h, _ in matches("grep -a foo a\ngrep bar b", limit=None)]:
        problems.append("grep-binary-heuristic: a newline-joined second grep with no "
                        "text-mode flag lost its reminder to the first stage's -a")
    if "grep-binary-heuristic" not in [h for h, _ in
                                       matches('grep "foo \\" -a bar" payload', limit=None)]:
        problems.append("grep-binary-heuristic: an escaped quote inside the pattern closed "
                        "the blanking early and the embedded -a read as a flag")
    uncovered = [n for n, _rx, _m, _a in RULES if n not in FIXTURES]
    if uncovered:
        problems.append(f"rules with no fixture, so nothing proves they fire: {uncovered}")
    for name, _rx, _msg, _anchor in RULES:
        cmd = FIXTURES.get(name)
        if cmd is None:
            continue
        if name not in [hit for hit, _ in matches(cmd, limit=None)]:
            problems.append(f"{name}: its own fixture {cmd!r} does not reach it — the rule is inert")

    # -- half 2: both hosts retain a guide fallback when native hooks do not run.
    for tree in ("claude", "codex"):
        g = repo / tree / "guides" / "tooling-gotchas.md"
        if not g.is_file():
            problems.append(f"{tree}/guides/tooling-gotchas.md missing — no fallback to check")
            continue
        body = g.read_text(encoding="utf-8")
        for name, _rx, _msg, anchor in RULES:
            if anchor not in body:
                problems.append(f"{name}: anchor {anchor!r} absent from {tree}/guides/tooling-gotchas.md")

    for p in problems:
        print(f"self-test [FAIL] {p}")
    if problems:
        print(f"HOOK SELF-TEST FAIL: {len(problems)} problem(s)")
        return 1
    print(f"HOOK SELF-TEST OK: {len(RULES)} rules each fire on their own fixture, stay quiet "
          f"when they should, and each has its guide counterpart on both hosts")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        sys.exit(self_test())
    sys.exit(main())
