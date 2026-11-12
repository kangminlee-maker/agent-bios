#!/usr/bin/env bash
# Payload gate: every repo file the installer or assembler EXECUTES or READS at
# runtime must be in package.json `files[]`, or the npm install is broken in a
# way no clone-side test can see.
#
# This is derived, not a hardcoded list: it greps the real "$REPO/..." and
# REPO / "..." references out of install.sh and assemble.py, so a path added
# later is covered without touching this gate.
#
# Author-side only (it reads package.json, not the registry). Exit 0 clean, 1 on
# any unshipped runtime path.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# --self-test: plant each violation this gate claims to catch into a throwaway
# copy of the tree and require the gate to fail BY NAME on it. Until now the flag
# was rejected rather than implemented, which was honest but left every leg
# unproven — and four of these violations were verified to pass green before the
# fixes below, so "the gate would have caught it" was not a safe assumption.
#
# The copy is the tracked working tree, so a case mutates a real subject rather
# than a fixture, and each case starts from a pristine copy so mutations cannot
# mask one another.
if [ "${1:-}" = "--self-test" ]; then
  [ $# -eq 1 ] || { echo "check-package: --self-test takes no arguments" >&2; exit 2; }
  T=$(mktemp -d "${TMPDIR:-/tmp}/pkg-selftest-XXXXXX") || exit 1
  trap 'rm -rf "$T"' EXIT
  # Copied in python rather than through `git ls-files | rsync`: a pipeline hides
  # the exit status of every stage but the last, so a git that listed nothing
  # would have produced an empty copy and blamed the positive control. This also
  # keeps the gate's dependencies to git and python, which the repo already has.
  python3 - "$REPO" "$T/pristine" <<'PY' || exit 1
import pathlib, shutil, subprocess, sys
src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
listed = subprocess.run(["git", "-C", str(src), "ls-files", "-z"],
                        capture_output=True, check=True).stdout.decode()
rels = [r for r in listed.split("\0") if r]
if not rels:
    sys.exit("check-package --self-test: git listed no tracked files, so the copy "
             "below would be empty and every case would fail over nothing")
for rel in rels:
    out = dst / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / rel, out)
gate = dst / "gates" / "check-package.sh"
if not gate.is_file():
    sys.exit(f"check-package --self-test: {gate} is missing from the copy")
print(f"check-package --self-test: {len(rels)} tracked files copied per case")
PY
  bad=0 ran=0 W="$T/w"

  fresh() { rm -rf "$W"; cp -R "$T/pristine" "$W"; }
  # Edit a file in the copy by literal substring, failing loudly when the target
  # text is gone: a mutation that silently applies to nothing plants no violation
  # and the case then "passes" over an unmutated tree.
  sub() { python3 - "$W/$1" "$2" "$3" <<'PY'
import pathlib, sys
p, old, new = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
t = p.read_text(encoding="utf-8")
if old not in t:
    sys.exit(f"self-test mutation is stale: {old!r} not in {p}")
p.write_text(t.replace(old, new, 1), encoding="utf-8")
PY
  }
  # Drop every line naming a substring — used to retire a reference entirely,
  # which a substitution cannot do while the invocation line survives.
  dropline() { python3 - "$W/$1" "$2" <<'PY'
import pathlib, sys
p, needle = pathlib.Path(sys.argv[1]), sys.argv[2]
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
kept = [l for l in lines if needle not in l]
if len(kept) == len(lines):
    sys.exit(f"self-test mutation is stale: no line in {p} names {needle!r}")
p.write_text("".join(kept), encoding="utf-8")
PY
  }
  pkg() { python3 - "$W/package.json" "$@" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text(encoding="utf-8"))
op, arg = sys.argv[2], sys.argv[3]
if op == "add":
    d["files"].append(arg)
elif op == "collapse":                    # replace every entry under arg with arg
    keep = [e for e in d["files"] if not e.startswith(arg)]
    if len(keep) == len(d["files"]):
        sys.exit(f"self-test mutation is stale: no files[] entry under {arg!r}")
    d["files"] = keep + [arg]
p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
PY
  }

  case_ok() {   # name: the planted text is no violation, so the gate still passes
    local name="$1" out rc
    ran=$((ran + 1))
    set +e; out=$("$W/gates/check-package.sh" 2>&1); rc=$?; set -e
    if [ "$rc" -ne 0 ]; then
      echo "check-package --self-test: FAIL: $name — the gate failed on text that is no violation" >&2
      printf '%s\n' "$out" | sed 's/^/    got: /' >&2
      bad=1
    fi
  }
  case_is() {   # name, expected substring in the failure output
    local name="$1" want="$2" out rc
    ran=$((ran + 1))
    set +e; out=$("$W/gates/check-package.sh" 2>&1); rc=$?; set -e
    if [ "$rc" -eq 0 ]; then
      echo "check-package --self-test: FAIL: $name — the planted violation passed" >&2
      bad=1
    # a here-string, not a pipe: under pipefail a match that stops grep early SIGPIPEs the
    # printf of a long failure report, and the planted case would read as "not by name"
    elif ! grep -qF -- "$want" <<<"$out"; then
      echo "check-package --self-test: FAIL: $name — failed, but not by name" >&2
      echo "    wanted: $want" >&2
      printf '%s\n' "$out" | sed 's/^/    got: /' >&2
      bad=1
    fi
  }

  # Positive control first. Every case below reads "the gate went from clean to
  # failing BECAUSE of this mutation" — which is only true if the copy was clean.
  fresh
  set +e; out=$("$W/gates/check-package.sh" 2>&1); rc=$?; set -e
  ran=$((ran + 1))
  if [ "$rc" -ne 0 ]; then
    echo "check-package --self-test: FAIL: the unmutated copy does not pass, so no" >&2
    echo "    case below can attribute its failure to the planted violation" >&2
    printf '%s\n' "$out" | sed 's/^/    /' >&2
    bad=1
  fi

  fresh; pkg add 'claude/**'
  case_is "a glob in files[] is refused rather than guessed at" "contains glob pattern"

  fresh; pkg add 'gates/'
  case_is "an author-side entry in files[] leaks a gate" "author-side path in files[]"

  # npm resolves `./gates/` to the same subtree as `gates/`; comparing the raw
  # entry let it satisfy neither shipped() nor author_side(), so the tarball got
  # the gates while this check reported clean.
  fresh; pkg add './gates/'
  case_is "a files[] entry spelled with a leading ./ is still that subtree" \
          "author-side path in files[]"

  fresh; printf '\npython3 "$REPO/compose/NO-SUCH-PROBE.py"\n' >> "$W/install.sh"
  case_is "a runtime reference to a path that does not exist" "no such path in this repo"

  fresh; pkg collapse 'learn/'
  case_is "a directory entry that swallows an author-side file" \
          "packed by a directory entry"

  fresh
  echo 'print("probe")' > "$W/compose/probe-selftest.py"
  printf '\ncat "$REPO/compose/probe-selftest.py" >/dev/null\n' >> "$W/install.sh"
  case_is "a runtime path missing from files[]" "not in package.json files"

  # a quiet grep fed by a pipe, in a shipped and in an author-side script that sets pipefail
  # (the planted text is assembled, so this file does not carry the shape it plants)
  fresh; printf '\nprintf x | grep -%s x\n' q >> "$W/wrappers/codex-run.sh"
  case_is "a piped grep -q in a shipped pipefail script" "wrappers/codex-run.sh:"
  fresh; printf '\nprintf x | grep -%s x\n' q >> "$W/gates/check-package.sh"
  case_is "a piped grep -q in an author-side pipefail script" "gates/check-package.sh:"
  # ...the same match through a here-string is no violation
  fresh; printf '\ngrep -q x <<<"x"\n' >> "$W/wrappers/codex-run.sh"
  case_ok "a grep -q reading a here-string in a pipefail script"

  # a mktemp -t in a shipped shell script, alone and with another flag first; a comment naming it is no call
  fresh; printf '\nlog="$(mktemp -%s probe)"\n' t >> "$W/install.sh"
  case_is "a mktemp -t in a shipped shell script" "mktemp -t call(s) in a shipped shell script"
  fresh; printf '\nlog="$(mktemp -q -%s probe)"\n' t >> "$W/wrappers/codex-helm.sh"
  case_is "a mktemp -q -t in a shipped shell script" "wrappers/codex-helm.sh:"
  fresh; printf '\n# never mktemp -%s here\n' t >> "$W/install.sh"
  case_ok "a comment naming mktemp -t in a shipped shell script"
  # ...a -t on a continuation line is the same call, as the shell joins it
  fresh; printf '\nlog="$(mktemp \\\n  -%s probe)"\n' t >> "$W/install.sh"
  case_is "a mktemp -t continued onto the next line" "mktemp -t call(s) in a shipped shell script"

  # a lock writer that waits without bound, shipped and author-side; a control's holder and a string are not
  fresh; printf '\n\ndef planted_writer(fh):\n    fcntl.flock(fh, fcntl.LOCK_%s)\n' EX >> "$W/compose/instructions_store.py"
  case_is "an unbounded lock writer in a shipped module" "compose/instructions_store.py:"
  fresh; printf '\n\ndef planted_writer(fh):\n    fcntl.flock(fh.fileno(), fcntl.LOCK_%s)\n' EX >> "$W/decisions/record-decision.py"
  case_is "an unbounded lock writer in the decision recorder" "lock writer(s) waiting on flock(LOCK_EX) without a bound"
  fresh; printf '\n\ndef self_test():\n    fcntl.flock(fh, fcntl.LOCK_%s)\n' EX >> "$W/compose/instructions_store.py"
  case_ok "a control's lock holder inside a self_test"
  fresh; printf '\n\nSHOWN = "fcntl.flock(fh, fcntl.LOCK_%s)"\n' EX >> "$W/compose/instructions_store.py"
  case_ok "a string showing an unbounded flock call"
  # ...and LOCK_NB behind a conditional is not set on the writer's branch: d30268e's transaction lock
  fresh; printf '\n\ndef planted_writer(descriptor, readonly):\n    fcntl.flock(descriptor, fcntl.LOCK_%s | (fcntl.LOCK_NB if readonly else 0))\n' EX >> "$W/compose/instructions_store.py"
  case_is "a lock writer whose LOCK_NB is conditional" "compose/instructions_store.py:"

  # a shipped module loaded by path, which no import statement names
  fresh; dropline package.json '"wrappers/jsonl_lines.py"'
  case_is "a module loaded by path that files[] does not ship" "wrappers/jsonl_lines.py"
  # Each by-path discovery finds its load alone: the installer's reference and every other
  # loader of the module are taken away, so only that one mechanism can name it.
  fresh; dropline package.json '"wrappers/jsonl_lines.py"'
  dropline install.sh 'wrappers/jsonl_lines.py'
  sub wrappers/claude_hermetic_evidence.py '.parent / "jsonl_lines.py"' '.parent / "jsonl_lines_gone.py"'
  sub learn/migrate-learnings.py '"wrappers" / "jsonl_lines.py"' '"wrappers" / "jsonl_lines_gone.py"'
  case_is "a module loaded by a path chain that files[] does not ship" \
          "wrappers/jsonl_lines.py   (referenced by compose/host_platform.py)"
  fresh; dropline package.json '"wrappers/jsonl_lines.py"'
  dropline install.sh 'wrappers/jsonl_lines.py'
  sub compose/host_platform.py '"wrappers" / "jsonl_lines.py"' '"wrappers" / "jsonl_lines_gone.py"'
  sub learn/migrate-learnings.py '"wrappers" / "jsonl_lines.py"' '"wrappers" / "jsonl_lines_gone.py"'
  case_is "a module loaded from beside its loader that files[] does not ship" \
          "wrappers/jsonl_lines.py   (referenced by wrappers/claude_hermetic_evidence.py)"
  # one constant root-relative path, `release / "compose/app_desktop/server.py"`, is a load too;
  # nothing else references the Desktop server, so only that recognition can name it
  fresh; dropline package.json '"compose/app_desktop/"'
  case_is "a module loaded by one root-relative path string that files[] does not ship" \
          "compose/app_desktop/server.py   (referenced by compose/instructions_app.py)"
  # ...and a comment or a docstring that shows a path is not a load
  fresh
  cat >> "$W/compose/host_platform.py" <<'EOF_PROBE'


# documentation example: scratch / "gates" / "check-lexicon.py"
def _documented_example():
    """An example only: scratch / "gates" / "check-lexicon.py" names a path in prose."""
EOF_PROBE
  case_ok "a path shown in a comment or a docstring is no runtime reference"

  fresh; printf '\ncat "$REPO/decisions/record-decision.py" >/dev/null\n' >> "$W/install.sh"
  case_is "an unguarded runtime reference to an author-side path" "no proven guard"

  fresh; sub install.sh '[ -x "$REPO/gates/check-package.sh" ]' \
                        '[ -f "$REPO/gates/check-package.sh" ]'
  case_is "a declared guard that was removed" "declared guard"

  fresh; dropline install.sh 'gates/check-parity.sh'
  case_is "a RUNTIME_GUARDED entry nothing references any more" \
          "nothing references at runtime"

  fresh; sub package.json '"provenance.json"' '"zz-provenance-unshipped-probe"'
  case_is "provenance dropped from files[] ships an unbound tarball" \
          "without its commit binding"

  fresh; sub package.json 'check-publish.sh --stamp' 'true'
  case_is "a prepack that no longer writes provenance" \
          "nothing writes provenance.json at pack time"

  fresh; sub package.json 'check-publish.sh --guard' 'true'
  case_is "a prepublishOnly that no longer guards" \
          "prepublishOnly must be exactly"

  fresh; sub package.json 'bash gates/check-publish.sh --stamp' \
                          'bash gates/check-publish.sh --stamp || true'
  case_is "an appended || true is not the canonical command" \
          "prepack must be exactly"

  fresh; sub package.json 'rm -f provenance.json' 'true'
  case_is "a postpack that leaves the stamp behind" \
          "binds the tarball to the WRONG commit"

  fresh; printf '\nSee `gates/check-lexicon.py` for details.\n' \
      >> "$W/claude/guides/tooling-gotchas.md"
  case_is "shipped prose naming an unshipped repo path" "gates/check-lexicon.py"

  fresh; printf '\nSee `decisions/decisions.jsonl` for details.\n' \
      >> "$W/claude/guides/tooling-gotchas.md"
  case_is "a five-letter suffix is not invisible to the prose scan" \
          "decisions/decisions.jsonl"

  fresh; printf '\nSee `design/session-distill/NO-SUCH-FILE.md` for details.\n' \
      >> "$W/claude/guides/tooling-gotchas.md"
  case_is "shipped prose naming a path that does not exist" "no such path in this repo"

  fresh; printf '\nSee `design/session-distill/NO-SUCH-FILE.md` for details.\n' \
      >> "$W/claude/guides/session-distill-workflow.md"
  case_is "an author-only guide may name the checkout, not the nonexistent" \
          "no such path in this repo"

  fresh; sub claude/guides/session-distill-workflow.md \
             'Requires an agent-bios checkout' 'Just run it'
  case_is "audience: author without the prerequisite it obliges" "without stating"

  # Single-sourcing, proven rather than asserted: break the ASSEMBLER's reader and
  # this gate's exemption must vanish with it. If the gate kept its own parser the
  # mutation would change nothing here, and the two could drift into exempting a
  # file the assembler still installs.
  fresh
  python3 - "$W" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]) / "compose" / "assemble.py"
t = p.read_text(encoding="utf-8")
old = '    try:\n        text = path.read_text(encoding="utf-8")'
if old not in t:
    sys.exit("self-test mutation is stale: author_only's body has moved")
p.write_text(t.replace(old, "    return False\n" + old, 1), encoding="utf-8")
PY
  case_is "the exemption comes from the assembler's reader, not a second copy" \
          "session-distill-workflow.md ->"

  # A files[] negation may name BYTECODE and nothing else. npm force-includes README, LICENSE,
  # the bin and main targets whatever files[] says, so `!README.md` took README out of the content
  # and endpoint scans while the tarball still carried it, and the packlist comparison agreed
  # (review Y r2 #2). Planted as the reviewer planted it.
  fresh
  python3 - "$W" <<'NEG'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]) / "package.json"
d = json.loads(p.read_text(encoding="utf-8"))
if not any(isinstance(e, str) and e.startswith("!") for e in d["files"]):
    sys.exit("self-test mutation is stale: files[] carries no negation to sit beside")
d["files"].append("!README.md")
p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
NEG
  case_is "a files[] negation naming anything but bytecode" \
          "FILES_NEGATION_UNSUPPORTED !README.md"

  # Fourth direction, both halves: product code and a self_test body. The second is what
  # proves the scan's scope — a scan that skipped self-tests would exempt a whole class of
  # sites without naming one of them.
  fresh; printf '\nPLANTED_AUTHOR_MODULE = "gates/check-lexicon.py"\n' >> "$W/compose/pkgid.py"
  case_is "shipped code naming an author-side module" \
          "names the author-side module gates/check-lexicon.py"

  fresh; printf '\n\ndef self_test():\n    planted = "gates/check-lexicon.py"\n    return planted\n' \
      >> "$W/compose/pkgid.py"
  case_is "a self_test body is in the scan's scope, not outside it" \
          "names the author-side module gates/check-lexicon.py"

  # The third direction for shipped JSON DATA. A table is neither prose nor code, and
  # session-distill/tables/destinations.json legitimately names an author-side writer in a
  # row that declares writer_scope: author -- a declaration whose reader is the runtime rule
  # in destinations.py. Three plants: an undeclared path fails, a declared path that exists
  # nowhere fails anyway, and removing the runtime reader makes the declaration stop
  # excusing anything.
  fresh
  python3 - "$W" <<'JPLANT'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]) / "session-distill/tables/redundancy.json"
d = json.loads(p.read_text(encoding="utf-8"))
d["$planted"] = {"note": "gates/check-lexicon.py"}
p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
JPLANT
  case_is "shipped json data naming an author-side path with no declaration" \
          "names the author-side path gates/check-lexicon.py in a row that does not declare"

  fresh
  python3 - "$W" <<'JPLANT2'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]) / "session-distill/tables/redundancy.json"
d = json.loads(p.read_text(encoding="utf-8"))
d["$planted"] = {"note": "gates/no-such-gate-here.py", "writer_scope": "author"}
p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
JPLANT2
  case_is "a declared path that exists nowhere fails anyway" \
          "exists nowhere in this repo"

  # The declaration's reader is what makes it safe: remove the runtime rule and the
  # declaration must stop excusing the reference -- the same single-sourcing the
  # audience: author rule has, where the gate imports the assembler's own reader.
  fresh
  python3 - "$W" <<'JPLANT3'
import pathlib, sys
p = pathlib.Path(sys.argv[1]) / "session-distill/runlib/destinations.py"
t = p.read_text(encoding="utf-8")
if "author_rows_absent" not in t:
    sys.exit("self-test mutation is stale: destinations.py no longer carries author_rows_absent")
p.write_text(t.replace("author_rows_absent", "author_rows_gone"), encoding="utf-8")
JPLANT3
  case_is "a writer_scope declaration whose runtime reader is gone excuses nothing" \
          "no longer DEFINES author_rows_absent"

  # The mutation above removes EVERY occurrence of the name, so it never tested what the old rule
  # actually asked — whether the name appears in the text. These two keep the name and take away
  # the thing that reads the declaration. The first leaves the DEFINITION and the comments and
  # removes only the invocations; the second removes the definition and leaves the comment that
  # mentions it. Each plant asserts the name still occurs afterwards, so the control also proves
  # the old text rule would have passed the mutated file.
  fresh
  python3 - "$W" <<'JPLANT4'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1]) / "session-distill/runlib/destinations.py"
t = p.read_text(encoding="utf-8")
# EVERY call site, whatever it is handed. Removing one form while another survived left the rule
# invoked and the plant passed: the gate said so, in the commit hook, after a second call site was
# added by an unrelated fix. The mutation therefore asserts its own result.
held = t.replace("def author_rows_absent(", "def KEEP_THE_DEFINITION(")
held = re.sub(r"\bauthor_rows_absent\s*\(", "author_rows_never_called(", held)
held = held.replace("def KEEP_THE_DEFINITION(", "def author_rows_absent(")
if held == t:
    sys.exit("self-test mutation is stale: destinations.py no longer calls author_rows_absent")
if "def author_rows_absent" not in held:
    sys.exit("self-test mutation is stale: the definition did not survive the plant")
if re.search(r"\bauthor_rows_absent\s*\(", held.replace("def author_rows_absent(", "", 1)):
    sys.exit("self-test mutation is stale: a call to author_rows_absent survived the plant, so the "
             "rule is still invoked and this case would test nothing")
p.write_text(held, encoding="utf-8")
JPLANT4
  case_is "a runtime rule that is defined and never invoked reads no declaration" \
          "never calls it outside its own suite"

  fresh
  python3 - "$W" <<'JPLANT5'
import pathlib, sys
p = pathlib.Path(sys.argv[1]) / "session-distill/runlib/destinations.py"
t = p.read_text(encoding="utf-8")
held = t.replace("def author_rows_absent(", "def author_rows_renamed(")
if held == t:
    sys.exit("self-test mutation is stale: destinations.py no longer defines author_rows_absent")
if "author_rows_absent" not in held:
    sys.exit("self-test mutation is stale: no mention of the name survived, so this plant would "
             "also have failed the old text rule and proves nothing about the comment")
p.write_text(held, encoding="utf-8")
JPLANT5
  case_is "and a comment naming the rule does not stand in for the rule" \
          "no longer DEFINES author_rows_absent"

  # A call from the SUITE is not a runtime reader, whatever the suite's function is called. The
  # exclusion was the single name `self_test`, and the day that suite gained a dying-control wrapper
  # its body moved to `_self_test_body` — so the call this gate counted came from the suite again
  # (the round-3 review). The plant moves the only runtime call into the suite's body and leaves it
  # called there, so the name, the definition and a call all survive.
  fresh
  python3 - "$W" <<'JPLANT5B'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1]) / "session-distill/runlib/destinations.py"
t = p.read_text(encoding="utf-8")
held = t.replace("def author_rows_absent(", "def KEEP_THE_DEFINITION(")
held = re.sub(r"\bauthor_rows_absent\s*\(", "author_rows_never_called(", held)
held = held.replace("def KEEP_THE_DEFINITION(", "def author_rows_absent(")
if held == t:
    sys.exit("self-test mutation is stale: destinations.py no longer calls author_rows_absent")
# ...and now call it from the SUITE's own body, which is where the hole was.
mark = "def _self_test_body(failures, ran):\n"
if mark not in held:
    sys.exit("self-test mutation is stale: destinations.py has no _self_test_body to call from")
held = held.replace(mark, mark + "    author_rows_absent(None)\n", 1)
if not re.search(r"\bauthor_rows_absent\s*\(", held.replace("def author_rows_absent(", "", 1)):
    sys.exit("self-test mutation is stale: the planted call did not survive, so the case would "
             "pass for the wrong reason")
p.write_text(held, encoding="utf-8")
JPLANT5B
  case_is "a rule the SUITE alone calls is not a runtime reader, whatever the suite is named" \
          "never calls it outside its own suite"

  # The same hole one hop further out: the call sits in a HELPER, and the helper's only caller is
  # the suite. One hop of exclusion counted that as a runtime reader (the round-4 review), so the
  # closure is computed to a fixpoint and this case is what proves it.
  fresh
  python3 - "$W" <<'JPLANT5C'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1]) / "session-distill/runlib/destinations.py"
t = p.read_text(encoding="utf-8")
held = t.replace("def author_rows_absent(", "def KEEP_THE_DEFINITION(")
held = re.sub(r"\bauthor_rows_absent\s*\(", "author_rows_never_called(", held)
held = held.replace("def KEEP_THE_DEFINITION(", "def author_rows_absent(")
if held == t:
    sys.exit("self-test mutation is stale: destinations.py no longer calls author_rows_absent")
# A top-level helper that calls it, called only from the suite's own body.
mark = "def _self_test_body(failures, ran):\n"
if mark not in held:
    sys.exit("self-test mutation is stale: destinations.py has no _self_test_body to call from")
held = held.replace(mark,
                    "def fixture_reader():\n    return author_rows_absent(None)\n\n\n" + mark
                    + "    fixture_reader()\n", 1)
if "def fixture_reader():" not in held or "    fixture_reader()\n" not in held:
    sys.exit("self-test mutation is stale: the planted helper or its call did not survive")
p.write_text(held, encoding="utf-8")
JPLANT5C
  case_is "a rule reached only through a helper the suite alone calls is not a runtime reader "\
"either, which one hop of exclusion could not see" \
          "never calls it outside its own suite"

  # Two shapes the fixpoint could not see (the round-5 review): a suite-only helper that calls
  # ITSELF has a caller outside the suite — its own name — and a METHOD was not in the graph.
  fresh
  python3 - "$W" <<'JPLANT5D'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1]) / "session-distill/runlib/destinations.py"
t = p.read_text(encoding="utf-8")
held = t.replace("def author_rows_absent(", "def KEEP_THE_DEFINITION(")
held = re.sub(r"\bauthor_rows_absent\s*\(", "author_rows_never_called(", held)
held = held.replace("def KEEP_THE_DEFINITION(", "def author_rows_absent(")
if held == t:
    sys.exit("self-test mutation is stale: destinations.py no longer calls author_rows_absent")
mark = "def _self_test_body(failures, ran):\n"
if mark not in held:
    sys.exit("self-test mutation is stale: destinations.py has no _self_test_body to call from")
held = held.replace(mark,
                    "def fixture_reader(depth=1):\n    if depth:\n        return fixture_reader(depth - 1)\n"
                    "    return author_rows_absent(None)\n\n\n" + mark + "    fixture_reader()\n", 1)
if "return fixture_reader(depth - 1)" not in held or "    fixture_reader()\n" not in held:
    sys.exit("self-test mutation is stale: the planted recursive helper did not survive")
p.write_text(held, encoding="utf-8")
JPLANT5D
  case_is "a suite-only helper that calls ITSELF is still the suite: its own name is not a "\
"production caller" \
          "never calls it outside its own suite"

  fresh
  python3 - "$W" <<'JPLANT5E'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1]) / "session-distill/runlib/destinations.py"
t = p.read_text(encoding="utf-8")
held = t.replace("def author_rows_absent(", "def KEEP_THE_DEFINITION(")
held = re.sub(r"\bauthor_rows_absent\s*\(", "author_rows_never_called(", held)
held = held.replace("def KEEP_THE_DEFINITION(", "def author_rows_absent(")
if held == t:
    sys.exit("self-test mutation is stale: destinations.py no longer calls author_rows_absent")
mark = "def _self_test_body(failures, ran):\n"
if mark not in held:
    sys.exit("self-test mutation is stale: destinations.py has no _self_test_body to call from")
held = held.replace(mark,
                    "class PlantedFixture:\n    def planted_run(self):\n"
                    "        return author_rows_absent(None)\n\n\n" + mark
                    + "    PlantedFixture().planted_run()\n", 1)
if "def planted_run(self):" not in held or "PlantedFixture().planted_run()" not in held:
    sys.exit("self-test mutation is stale: the planted method or its call did not survive")
p.write_text(held, encoding="utf-8")
JPLANT5E
  case_is "a rule reached only through a METHOD the suite alone calls is not a runtime reader" \
          "never calls it outside its own suite"

  # Round 6: a constructor is reached by calling its class, and a call under the flag is the suite's.
  fresh
  python3 - "$W" <<'JPLANT5F'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1]) / "session-distill/runlib/destinations.py"
t = p.read_text(encoding="utf-8")
held = t.replace("def author_rows_absent(", "def KEEP_THE_DEFINITION(")
held = re.sub(r"\bauthor_rows_absent\s*\(", "author_rows_never_called(", held)
held = held.replace("def KEEP_THE_DEFINITION(", "def author_rows_absent(")
if held == t:
    sys.exit("self-test mutation is stale: destinations.py no longer calls author_rows_absent")
mark = "def _self_test_body(failures, ran):\n"
if mark not in held:
    sys.exit("self-test mutation is stale: destinations.py has no _self_test_body to call from")
held = held.replace(mark,
                    "class PlantedBuilt:\n    def __init__(self):\n"
                    "        self.held = author_rows_absent(None)\n\n\n" + mark
                    + "    PlantedBuilt()\n", 1)
if "class PlantedBuilt:" not in held or "    PlantedBuilt()\n" not in held:
    sys.exit("self-test mutation is stale: the planted constructor or its call did not survive")
p.write_text(held, encoding="utf-8")
JPLANT5F
  case_is "a rule reached only through a CONSTRUCTOR the suite alone calls is not a runtime reader" \
          "never calls it outside its own suite"

  fresh
  python3 - "$W" <<'JPLANT5G'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1]) / "session-distill/runlib/destinations.py"
t = p.read_text(encoding="utf-8")
held = t.replace("def author_rows_absent(", "def KEEP_THE_DEFINITION(")
held = re.sub(r"\bauthor_rows_absent\s*\(", "author_rows_never_called(", held)
held = held.replace("def KEEP_THE_DEFINITION(", "def author_rows_absent(")
if held == t:
    sys.exit("self-test mutation is stale: destinations.py no longer calls author_rows_absent")
mark = "def main(argv):\n"
if held.count(mark) != 1:
    sys.exit("self-test mutation is stale: destinations.py has no single main(argv) to plant in")
held = held.replace(mark,
                    "def planted_flag_helper():\n    return author_rows_absent(None)\n\n\n" + mark
                    + "    if '--self-test' in argv:\n        planted_flag_helper()\n", 1)
if "def planted_flag_helper():" not in held or "        planted_flag_helper()\n" not in held:
    sys.exit("self-test mutation is stale: the planted helper or its guarded call did not survive")
p.write_text(held, encoding="utf-8")
JPLANT5G
  case_is "a rule reached only under the self-test flag in a production function is not a runtime "\
"reader" \
          "never calls it outside its own suite"

  # Round 7: the same guard at the module's TOP LEVEL, in both spellings.
  fresh
  python3 - "$W" <<'JPLANT5H'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1]) / "session-distill/runlib/destinations.py"
t = p.read_text(encoding="utf-8")
held = t.replace("def author_rows_absent(", "def KEEP_THE_DEFINITION(")
held = re.sub(r"\bauthor_rows_absent\s*\(", "author_rows_never_called(", held)
held = held.replace("def KEEP_THE_DEFINITION(", "def author_rows_absent(")
if held == t:
    sys.exit("self-test mutation is stale: destinations.py no longer calls author_rows_absent")
held += "\n\nif '--self-test' in sys.argv:\n    author_rows_absent(None)\n"
p.write_text(held, encoding="utf-8")
JPLANT5H
  case_is "a rule called only under a TOP-LEVEL self-test guard is not a runtime reader" \
          "never calls it outside its own suite"

  fresh
  python3 - "$W" <<'JPLANT5I'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1]) / "session-distill/runlib/destinations.py"
t = p.read_text(encoding="utf-8")
held = t.replace("def author_rows_absent(", "def KEEP_THE_DEFINITION(")
held = re.sub(r"\bauthor_rows_absent\s*\(", "author_rows_never_called(", held)
held = held.replace("def KEEP_THE_DEFINITION(", "def author_rows_absent(")
if held == t:
    sys.exit("self-test mutation is stale: destinations.py no longer calls author_rows_absent")
held += "\n\nif '--self-test' not in sys.argv:\n    pass\nelse:\n    author_rows_absent(None)\n"
p.write_text(held, encoding="utf-8")
JPLANT5I
  case_is "nor is one called only in the else of a top-level `not in` guard" \
          "never calls it outside its own suite"

  # The exemption is keyed to the ROW. The same path written in a second row is a reference nothing
  # has excused, and keyed by (file, path) alone it was excused anyway.
  fresh
  python3 - "$W" <<'JPLANT6'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]) / "session-distill/tables/drift_layers.json"
d = json.loads(p.read_text(encoding="utf-8"))
held = [l for l in d["layers"] if "design/session-distill/ledger.json" in (l.get("prefixes") or [])]
if not held:
    sys.exit("self-test mutation is stale: no layer carries the exempted ledger prefix")
d["layers"].append({"layer": "$planted", "prefixes": ["design/session-distill/ledger.json"]})
p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
JPLANT6
  case_is "an exemption excuses its own row, not the same path written in another" \
          "names the author-side path design/session-distill/ledger.json in a row that does not"

  # An exemption is only safe while it names a real site: a stale one exempts by a path
  # nobody has, which is the shape this repo keeps finding (a declared author-side file
  # that moved, a concept home matching nothing).
  # Mutated through python rather than `sub`: any literal handed to `sub` also appears in
  # the line that hands it over, and `sub` replaces the first occurrence — it would have
  # mutated the mutation. This one is anchored to the exemption table itself.
  fresh
  python3 - "$W" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]) / "gates" / "check-package.sh"
t = p.read_text(encoding="utf-8")
# The LAST occurrence, and it must lie inside the table: a forward search anchored on the
# table's name finds this very line first, and the mutation rewrote itself.
at, table = t.rfind("benchmarks" + "/absence.py"), t.rfind("AUTHOR_IMPORT" + "_EXEMPT = {")
if at < 0 or at < table:
    sys.exit("self-test mutation is stale: the gate.py exemption is not in the table")
p.write_text(t[:at] + "benchmarks/NO-SUCH.py" + t[at + len("benchmarks/absence.py"):], encoding="utf-8")
PY
  case_is "an author-side import exemption naming a file nobody has" \
          "exemption(s) naming a file that does not exist"

  # review Y #5: existence is not use. Both files stay; the REFERENCE the exemption excuses is
  # removed, which used to leave the entry in place, the gate green, and the next thing written in
  # that file excused by a line nobody had read.
  fresh; python3 - "$W" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]) / "session-distill" / "runlib" / "dispatch.py"
t = p.read_text(encoding="utf-8")
needle = "session-distill" + "/migrate-ledger.py"
if t.count(needle) < 1:
    sys.exit("self-test mutation is stale: dispatch.py no longer names the migrator")
p.write_text(t.replace(needle, "session-distill" + "/runlib/ledger.py"), encoding="utf-8")
PY
  case_is "an author-side import exemption the scan never met" \
          "exemption(s) the scan never met"

  # review Y #1: npm is the authority on what the tarball carries, and it honours a negated
  # files[] entry and nothing else once files[] exists.
  fresh; python3 - "$W" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]) / "package.json"
d = json.loads(p.read_text(encoding="utf-8"))
d["files"] = [e for e in d["files"] if not e.startswith("!")]
p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
PY
  case_is "a payload with no rule npm honours against bytecode" \
          "carries no negated entry"

  fresh; printf '\n[presets.selftest-probe]\nlabel = "probe"\nmission = "first read gates/check-lexicon.py"\n' \
      >> "$W/launch/agent-launch.toml"
  case_is "shipped config prose naming an unshipped repo path" "gates/check-lexicon.py"

  # The config scan carries its own copy of the suffix class, and its failure was
  # worse than the prose one: the 2-4 letter bound matched the PREFIX
  # `decisions/decisions.json`, a path that exists nowhere, so the existence test
  # then dropped the reference as though it had never been a path.
  fresh; printf '\n[presets.selftest-probe]\nlabel = "probe"\nmission = "first read decisions/decisions.jsonl"\n' \
      >> "$W/launch/agent-launch.toml"
  case_is "shipped config prose naming a five-letter suffix" "decisions/decisions.jsonl"

  fresh; printf '\n[presets.selftest-probe]\nlabel = "probe"\nmission = "first read design/session-distill/NO-SUCH-FILE.md"\n' \
      >> "$W/launch/agent-launch.toml"
  case_is "shipped config prose naming a path that does not exist" \
          "no such path in this repo"

  fresh; rm -f "$W"/decisions/*
  case_is "an author-side directory with no files left to exempt" "no files under"

  fresh; rm -f "$W/learn/build-promotions.py"
  case_is "an author-side file declared by name that no longer exists" \
          "declared author-side file(s) do not exist"

  # The vacuity guards. A leg pointed at nothing satisfies every claim, so the
  # gate's own refusals to report clean over an empty subject are controls too.
  fresh
  python3 - "$W" <<'PY'
import pathlib, sys
root = pathlib.Path(sys.argv[1])
sh = root / "install.sh"
sh.write_text(sh.read_text(encoding="utf-8").replace("$REPO/", "$GONE/"), encoding="utf-8")
py = root / "compose" / "assemble.py"
py.write_text(py.read_text(encoding="utf-8").replace("REPO /", "GONE /"), encoding="utf-8")
PY
  case_is "patterns that no longer match their sources" "extracted zero runtime paths"

  if [ "$bad" -ne 0 ]; then
    echo "check-package --self-test: FAILED" >&2
    exit 1
  fi
  echo "check-package --self-test: OK ($ran controls, each a planted violation this gate must name)"
  exit 0
fi

python3 - "$@" <<'PY'
import ast, importlib.util, json, os, pathlib, posixpath, re, shutil, subprocess, sys, tempfile, tomllib

# Reject anything not implemented, loudly. A gate that accepts --self-test by
# ignoring it and then prints OK tells the caller a control ran when none did.
ARGS = sys.argv[1:]
if ARGS and not (ARGS[0] == "--explain" and len(ARGS) == 2):
    sys.exit("check-package: usage: check-package.sh [--explain <path> | --self-test]\n"
             f"  refusing {' '.join(ARGS)!r} — this gate implements no other flag, "
             "and silently ignoring one would report a check that never ran")

REPO = pathlib.Path(".").resolve()
files = json.loads((REPO / "package.json").read_text(encoding="utf-8"))["files"]
NEGATED = [entry[1:] for entry in files if isinstance(entry, str) and entry.startswith("!")]
POSITIVE = [entry for entry in files if not (isinstance(entry, str) and entry.startswith("!"))]


# Author-side by directory: these exist only in a checkout, and their absence
# from the payload degrades instead of crashing. Stating it as a directory rule
# rather than one exemption per file also covers files added later, and lets the
# rule be enforced in both directions (see the files[] assertion below). Each
# entry carries its reason, and each must hold at least one file — a declared
# directory with nothing in it would pass its half of the rule over nothing.
AUTHOR_SIDE_DIRS = {
    "gates/": "author-side verification; install.sh guards each call with [ -x ] or [ -d ko ]",
    "decisions/": "this repo's own decision record — it is about developing agent-bios, "
                  "not something its users install",
    "design/": "dated design records and per-initiative SSOTs; history, not runtime",
    "benchmarks/": "the instruction-behavior benchmark; run from a checkout only",
    "session-distill/fixtures/": "retained capture and replay fixtures of the driver's own suites; "
                                "their PROVENANCE files carry the author's probe paths",
    ".githooks/": "the pre-commit gate; enabled per clone with core.hooksPath",
}

# Author-side FILES inside shipped directories. Promote — certifying an instruction
# package as globally distributable — is an administrator/developer action, so its
# machinery stays in the checkout even though it lives beside the shipped capture
# flow in learn/. A directory rule cannot express this: learn/ ships.
AUTHOR_SIDE_FILES = {
    "compose/test_instructions_compatibility.py": "author-side legacy alias, lock, root and immutable-snapshot regression tests",
    "compose/test_instructions_end_to_end.py": "author-side npm-layout and public CLI integration tests",
    "compose/test_instructions_catalog.py": "author-side catalog and private compiler tests",
    "compose/test_instructions_store.py": "author-side storage transaction tests",
    "compose/test_instructions_ui.py": "author-side Instructions Studio and CLI tests",
    "compose/test_instructions_install.py": "author-side private installation and migration tests",
    "compose/test_instructions_session.py": "author-side session activation and pin tests",
    "compose/test_instructions_native.py": "author-side native opt-in and immutable plugin integration tests",
    "compose/test_instructions_shell.py": "author-side optional shell lifecycle and recovery tests",
    "compose/test_instructions_understand.py": "author-side learning bundle and discovery provenance tests",
    "compose/test_instructions_understand_ui.py": "author-side learning session launcher and trophy UI tests",
    "learn/build-promotions.py":
        "derives the promotion manifest from the curator ledger; promote is an "
        "administrator/developer action, never a user one",
    "learn/ingest-learnings-export.py":
        "curator intake of a dashboard export; the user side of the loop is "
        "collect-learning.py, which does ship",
    "session-distill/census.py":
        "v1 curator window stage; it mines this repo's own sessions to author instructions "
        "content and reads the ledger under design/",
    "session-distill/merge-ledger.py":
        "v1 curator window stage; it mines this repo's own sessions to author instructions "
        "content and reads the ledger under design/",
    "session-distill/plain-asks.py":
        "v1 curator window stage; it mines this repo's own sessions to author instructions "
        "content and reads the ledger under design/",
    "session-distill/update-state.py":
        "v1 curator window stage; it mines this repo's own sessions to author instructions "
        "content and reads the ledger under design/",
    "session-distill/migrate-ledger.py":
        "the author-side ledger migration and its reader inventory; the checkout's ledger lives "
        "under design/, which never ships",
    "session-distill/REPIN.md":
        "how to re-pin the driver's fixtures, which only a checkout has",
    "session-distill/tables/ledger_readers.json":
        "the reader registry of the CHECKOUT's ledger: every row names an author-side path, and "
        "its one consumer is migrate-ledger.py, which does not ship (review Y #8)",

}

# Individual paths deliberately NOT shipped. Each needs a reason, and each must be
# guarded in the caller so its absence degrades instead of crashing.
EXEMPT = {
    "provenance.json":
        "written at pack time by gates/check-publish.sh --stamp and gitignored, so "
        "a clone legitimately lacks it; install.sh reads it behind isfile/[ -f ] "
        "guards. Existence is all this exempts — files[] membership and the "
        "generator wiring are asserted separately below, because shipping the "
        "binding is the point",
    "ko":
        "Korean mirror is author-side parity material; install.sh guards with [ -d ]",
    ".git":
        "probed for ABSENCE to tell a clone from an npm install; shipping it would invert the test",
}

# npm packs these regardless of files[]: the manifest, the readme, the licence.
# Verified against `npm pack --dry-run` on this tree — LICENSE and package.json
# are in the 65-file tarball while neither appears in files[]. Reporting them as
# unshipped, or as author-side, was wrong in both directions.
ALWAYS_PACKED = re.compile(r"^(package\.json|readme(\.[a-z]+)?|licen[sc]e(\.[a-z]+)?)$", re.I)

def always_packed(rel):
    return "/" not in rel and ALWAYS_PACKED.match(rel) is not None

# This gate matches literal paths and directory prefixes. A glob in a POSITIVE entry would be
# mis-classified rather than understood, so it fails instead of guessing.
#
# A NEGATED entry is different in kind and is modelled: `excluded_by_npm` translates it, because
# with `files[]` present npm-packlist nulls the root `.npmignore` and a negation is then the only
# rule npm honours — the one place bytecode can be kept out of the tarball (review Y #1). Its
# patterns are still refused anywhere but at the front of a negation.
GLOB = re.compile(r"[*?\[\]{}!]")
_globs = sorted(e for e in POSITIVE if GLOB.search(e))
if _globs:
    sys.exit(f"check-package: FAILED — files[] contains glob pattern(s) {_globs}; this "
             "gate models literal paths and directory prefixes only, and would answer "
             "both directions wrongly rather than fail")
_bad_negations = sorted(e for e in NEGATED if GLOB.search(e.replace("*", "").replace("?", "")))
if _bad_negations:
    sys.exit(f"check-package: FAILED — negated files[] entr(ies) {_bad_negations} carry a "
             "character this gate's translation does not model; keep a negation to `*`, `**` and "
             "`?` or teach `excluded_by_npm` the rest")
# A negation may name BYTECODE and nothing else. npm force-includes README, LICENSE, the bin and
# main targets whatever files[] says, so a negation naming one of those removed it from the content
# and endpoint scans while the tarball still carried it — `!README.md` hid a forbidden identifier
# and a live endpoint, and the packlist comparison agreed because npm shipped the file too
# (review Y r2 #2). The supported spellings are the installer's (`SUPPORTED_NEGATIONS`), imported
# rather than restated, so the gate cannot tolerate a negation the payload does not implement.
sys.path.insert(0, str(REPO / "compose"))
try:
    from instructions_install import negation_supported
except ImportError as exc:
    sys.exit(f"check-package: cannot read the supported negations — {exc}. "
             f"compose/instructions_install.py owns them, and this gate keeps no second copy")
_unsupported = sorted(e for e in files
                      if isinstance(e, str) and e.startswith("!") and not negation_supported(e))
if _unsupported:
    sys.exit("check-package: FAILED — " + "; ".join(
        f"FILES_NEGATION_UNSUPPORTED {e}: a files[] negation may name only compiled Python "
        f"(__pycache__, *.pyc, *.pyo); anything else hides a packed file from the content and "
        f"endpoint scans, because npm force-includes README, LICENSE, bin and main whatever "
        f"files[] says" for e in _unsupported))
if not NEGATED:
    sys.exit("check-package: FAILED — files[] carries no negated entry, so nothing keeps npm from "
             "packing a local __pycache__: npm nulls the root .npmignore when files[] exists")

SOURCES = ["install.sh", "compose/assemble.py"]
# "$REPO/compose/x.py" / "$REPO/claude/settings.json"  and  REPO / "claude" / "settings.json"
SH = re.compile(r'\$\{?REPO\}?/([A-Za-z0-9_./-]+)')
PY_ = re.compile(r'REPO\s*/\s*((?:"[A-Za-z0-9_.-]+"\s*/\s*)*"[A-Za-z0-9_.-]+")')

# Each check registers what it actually operated on. Reporting "N findings" says
# nothing about coverage; reporting "which legs, over how many subjects" is what
# reveals a leg pointed at an empty set. An aggregate across legs cannot.
LEGS = {}

def leg(name, subjects):
    items = list(subjects)
    LEGS[name] = LEGS.get(name, 0) + len(items)
    return items


def rel_key(raw):
    # Normalize before matching: the author-side rule below is a path-prefix test,
    # so an un-normalized "gates/../x" would claim an exemption it has no
    # right to. normpath collapses that to the path actually referenced.
    return posixpath.normpath(raw.rstrip("/"))


found = {}
for src in SOURCES:
    text = (REPO / src).read_text(encoding="utf-8")
    for m in SH.finditer(text):
        found.setdefault(rel_key(m.group(1)), set()).add(src)
    for m in PY_.finditer(text):
        parts = re.findall(r'"([^"]+)"', m.group(1))
        found.setdefault(rel_key("/".join(parts)), set()).add(src)

if not found:
    sys.exit("check-package: FAILED — extracted zero runtime paths; the patterns "
             "no longer match the sources, so a green result here would be vacuous")

# A helper module is pulled in by `import`, not by a path literal, so the path scan
# above cannot see it — and since the importer manipulates sys.path at runtime, the
# module need not sit beside its importer (learn/ imports pkgid out of compose/).
# Resolve each import name against every subsystem directory that actually holds
# python, derived from the tree rather than hardcoded, and walk it transitively:
# an unshipped helper fails the import at runtime just as hard as an unshipped script.
MODULE_DIRS = sorted({
    str(p.parent.relative_to(REPO)) for p in REPO.glob("*/*.py")
    if not str(p.relative_to(REPO)).startswith(tuple(AUTHOR_SIDE_DIRS) + ("research/", "design/"))
})
if not MODULE_DIRS:
    sys.exit("check-package: FAILED — found no subsystem directory holding python, so the "
             "import walk below has nothing to resolve against and would pass vacuously")

IMPORT = re.compile(r'^\s*(?:import\s+([a-z_][a-z0-9_]*)|from\s+([a-z_][a-z0-9_]*)\s+import)', re.M)
# A module loaded by path (importlib's spec_from_file_location) is named by an executable
# `/` expression whose right-hand operands are string segments, and neither the `$REPO/`
# scan nor the import walk sees it. Two shapes, each a runtime path walked like an import:
# CHAIN, two or more segments, or one segment holding `/`-separated components, naming a
# python file from the repo root — `REPO / "learn" / "redact.py"`,
# `Path(__file__).resolve().parents[1] / "wrappers" / "jsonl_lines.py"`,
# `release / "compose/app_desktop/server.py"`; SIBLING, one segment after `.parent`, resolved in the loader's own
# directory — `pathlib.Path(__file__).resolve().parent / "jsonl_lines.py"`. They are read
# from the parsed module, so a comment or a docstring that shows such a path is not one.
def path_loads(text):
    """(chains, siblings): the segment paths of every outermost `/` expression ending in a
    string naming a .py file; siblings are those of one segment whose base is `.parent`."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [], []
    inner = {id(n.left) for n in ast.walk(tree) if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)}
    chains, siblings = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Div) or id(node) in inner:
            continue
        segments, base = [], node
        while (isinstance(base, ast.BinOp) and isinstance(base.op, ast.Div)
               and isinstance(base.right, ast.Constant) and isinstance(base.right.value, str)):
            segments.insert(0, base.right.value)
            base = base.left
        if not segments or not segments[-1].endswith(".py"):
            continue
        if len(segments) > 1 or "/" in segments[0]:  # also one constant root-relative path: release / "a/b.py"
            chains.append("/".join(segments))
        elif isinstance(base, ast.Attribute) and base.attr == "parent":
            siblings.append(segments[0])
    return chains, siblings


TOP = {p.name for p in REPO.iterdir() if p.is_dir()}
queue = [s for s in SOURCES if s.endswith(".py")] + [r for r in found if r.endswith(".py")]
seen = set()
while queue:
    rel = queue.pop()
    if rel in seen or not (REPO / rel).exists():
        continue
    seen.add(rel)
    chains, siblings = path_loads((REPO / rel).read_text(encoding="utf-8")) if rel.endswith(".py") else ([], [])
    named = [rel_key(c) for c in chains if c.split("/", 1)[0] in TOP] + \
            [rel_key(posixpath.join(posixpath.dirname(rel), s)) for s in siblings]
    for path in named:
        if (REPO / path).is_file():
            found.setdefault(path, set()).add(rel)
            queue.append(path)
    for m in IMPORT.finditer((REPO / rel).read_text(encoding="utf-8")):
        mod = m.group(1) or m.group(2)
        for d in MODULE_DIRS:
            sib = f"{d}/{mod}.py"
            if (REPO / sib).exists():
                found.setdefault(sib, set()).add(rel)
                queue.append(sib)

def excluded_by_npm(rel):
    """npm honours a negated `files[]` entry; nothing else excludes once `files[]` exists."""
    for pattern in NEGATED:
        pat = pattern.strip("/")
        anchored = "/" in pat
        out, i = [], 0
        while i < len(pat):
            if pat.startswith("**/", i):
                out.append("(?:.*/)?"); i += 3
            elif pat.startswith("**", i):
                out.append(".*"); i += 2
            elif pat[i] == "*":
                out.append("[^/]*"); i += 1
            elif pat[i] == "?":
                out.append("[^/]"); i += 1
            else:
                out.append(re.escape(pat[i])); i += 1
        prefix = "^" if anchored else "^(?:.*/)?"
        if re.match(prefix + "".join(out) + "$", rel):
            return True
    return False


def shipped(rel):
    # npm treats a directory entry as its whole subtree whether or not the entry
    # carries a trailing slash, and resolves `./gates/` to the same subtree as
    # `gates/`. Both spellings are normalized here, through the same rel_key the
    # runtime scan uses: comparing raw entries let `./gates/` satisfy neither this
    # test nor author_side(), so npm packed the tree while the gate reported OK.
    if excluded_by_npm(rel):
        return False
    if always_packed(rel):
        return True
    for entry in POSITIVE:
        e = rel_key(entry)
        if rel == e or rel.startswith(e + "/"):
            return True
    return False

def author_side(rel):
    return (rel in AUTHOR_SIDE_FILES
            or any(rel == d.rstrip("/") or rel.startswith(d) for d in AUTHOR_SIDE_DIRS))


# Whether a reference points INTO this repository is decided by its first segment,
# not by whether the target happens to exist. Deciding it by existence meant a
# mistyped target — `design/session-distill/NO-SUCH-FRAMEWORK.md` — read as "not a
# repo path, nothing promised" and shipped as an instruction to open nothing.
# Derived from the tree, so a directory added later is covered without an edit.
REPO_ROOTS = sorted(p.name for p in REPO.iterdir()
                    if p.is_dir() and not p.name.startswith("."))
if not REPO_ROOTS:
    sys.exit("check-package: FAILED — no top-level directories found, so every prose "
             "reference below would be judged as pointing outside the repo")


def repo_path(target):
    # Bound: a typo in the FIRST segment (`desgin/...`) reads as someone else's
    # tree and is skipped. Judging it would mean guessing which unknown prefixes
    # were meant to be ours, and shipped prose does legitimately name paths in a
    # user's own project. A typo in any later segment is caught, which is where
    # the long tail of real references lives.
    return target.split("/", 1)[0] in REPO_ROOTS


# Query mode: the boundary is decidable, so nobody should have to infer it by
# reading files[] semantics. Prints the verdict and why, for one path.
if ARGS and ARGS[0] == "--explain":
    raw = ARGS[1]
    if posixpath.isabs(raw):
        try:
            raw = str(pathlib.Path(raw).resolve().relative_to(REPO))
        except ValueError:
            sys.exit(f"check-package: {raw} is outside this repo; the payload "
                     f"boundary is only defined for paths inside it")
    rel = rel_key(raw)
    if always_packed(rel):
        print(f"{rel}: SHIPS — npm always packs it, regardless of files[]")
    elif rel in AUTHOR_SIDE_FILES:
        print(f"{rel}: AUTHOR-SIDE — declared by name\n  {AUTHOR_SIDE_FILES[rel]}")
    elif author_side(rel):
        d = next(d for d in AUTHOR_SIDE_DIRS if rel == d.rstrip("/") or rel.startswith(d))
        print(f"{rel}: AUTHOR-SIDE — never shipped\n  declared by {d} in check-package.sh: "
              f"{AUTHOR_SIDE_DIRS[d]}")
    elif rel in EXEMPT:
        print(f"{rel}: AUTHOR-SIDE — exempt by name\n  {EXEMPT[rel]}")
    elif shipped(rel):
        print(f"{rel}: SHIPS — matched by package.json files[]")
    elif not (REPO / rel).exists():
        print(f"{rel}: UNKNOWN — no such path in the repo")
        sys.exit(2)
    else:
        print(f"{rel}: not shipped, and not declared author-side\n  "
              f"add it to files[] if the installer or a shipped guide needs it, "
              f"else declare its directory in AUTHOR_SIDE_DIRS")
    sys.exit(0)

# An author-side path the installer really does reach at runtime, each with the
# literal guard that makes its absence degrade instead of crash. The runtime leg
# used to skip EVERY author-side path on the strength of a directory's stated
# reason, so adding an unguarded `cat "$REPO/decisions/record-decision.py"` to
# install.sh left the gate green while the packaged install would die there —
# reproduced. Blanket exemption is now enumeration: a new reference must be
# declared here, and the guard text must still be present in the referring file,
# so deleting the guard fails even though the reference is unchanged.
#
# Known bound, stated rather than papered over: the guard is looked for in the
# referring FILE, not around each reference, so adding a SECOND unguarded call to
# an already-guarded path keeps the text present and passes. Proving that every
# reference sits inside its guard is not decidable from a substring, and this repo
# blocks only on decidable violations — so what is enforced is "a new author-side
# path cannot be reached without a declaration", which is the case that recurs.
RUNTIME_GUARDED = {
    "gates/check-package.sh": '[ -x "$REPO/gates/check-package.sh" ]',
    "gates/check-parity.sh": '[ -x "$REPO/gates/check-parity.sh" ]',
}

missing, unguarded = [], []
leg("runtime paths", found)
leg("guarded author-side refs", RUNTIME_GUARDED)
for rel in sorted(found):
    if rel in EXEMPT:
        continue
    if author_side(rel):
        guard = RUNTIME_GUARDED.get(rel)
        if guard is None:
            unguarded.append((rel, sorted(found[rel]),
                              "not declared in RUNTIME_GUARDED"))
        else:
            lost = [s for s in sorted(found[rel])
                    if guard not in (REPO / s).read_text(encoding="utf-8")]
            if lost:
                unguarded.append((rel, lost, f"declared guard {guard!r} is gone"))
        continue
    # A `$REPO/...` reference names a repo file by construction, so one that does
    # not exist is a typo, not "a path built at runtime". Skipping it excused
    # `$REPO/compose/NO-SUCH.py` in install.sh — the same hole the prose scan had,
    # left open on the leg that actually runs the installer. No current reference
    # is affected: all 31 exist. A genuinely runtime-built path needs an EXEMPT
    # entry with its reason, like every other exception here.
    if not (REPO / rel).exists():
        unguarded.append((rel, sorted(found[rel]), "no such path in this repo"))
        continue
    if not shipped(rel):
        missing.append((rel, sorted(found[rel])))

stale_guards = sorted(set(RUNTIME_GUARDED) - set(found))
if stale_guards:
    sys.exit(f"check-package: FAILED — RUNTIME_GUARDED declares path(s) nothing "
             f"references at runtime: {', '.join(stale_guards)}; a stale declaration "
             f"silently exempts nothing and hides the next real one")

# Third direction: SHIPPED PROSE that sends the reader to an unshipped path. The
# instructions are loaded into an agent's context on a user's machine, so a guide naming
# a repo file the user does not have is a broken instruction that no clone-side
# test can see — the same failure class as an unshipped runtime path, with the
# guide as the referrer instead of the installer.
#
# A step only the instructions author can perform is legitimate; documenting it as
# everyone's is not. So a file may reference author-side paths when its
# frontmatter declares `audience: author`, and that declaration is the whole
# exception: unlabelled, it fails.
#
# Scope is the instructions trees, not README/DEPENDENCIES — those describe the repo to
# contributors, and pointing at gates/ is exactly their job.
# The suffix is not length-limited. A 2-4 letter class silently excluded `.jsonl`
# — this repo's own ledger extension — so the one reference the leg most needed to
# judge was the one it could not see. Extensions are matched as "letters and
# digits after the last dot", which is what a filename suffix is.
PROSE_PATH = re.compile(r'`([A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+\.[a-z][a-z0-9]*)`')
# Bare filenames are NOT checked. The list held IMPLEMENTATION_MAP.html until it
# produced fourteen false positives — the instructions tells an agent to maintain that
# file in its own repo — and then LEXICON.md until this branch removed the single
# shipped reference that gave it a subject. A leg with no possible subject is not
# a check, so the whole idea is retired: only directory-qualified paths are judged.

# A file may name author-side paths only if it also tells its reader, in the text,
# that it needs a checkout. Otherwise the label is read by nothing but the gate that
# the label exempts — a consumer of itself — and a packaged reader still follows
# instructions they cannot execute.
PREREQ = "Requires an agent-bios checkout"


# The declaration has ONE reader, and it is the shipped one. `compose/assemble.py`
# withholds an `audience: author` file from delivery; this gate only tolerates the
# references that withholding makes safe. Parsing the frontmatter a second time
# here would let the two drift into exempting a file the assembler still installs
# — the exact defect the pair was written to close. Author-side may import shipped
# code; never the reverse, since the payload must not depend on gates/.
sys.path.insert(0, str(REPO / "compose"))
try:
    from assemble import author_only
except ImportError as exc:
    sys.exit(f"check-package: cannot read the audience declaration — {exc}. "
             f"compose/assemble.py owns it, and this gate keeps no second copy")


def author_doc(rel):
    return author_only(REPO / rel)

instructions_prose = sorted(
    str(f.relative_to(REPO)) for tree in ("claude", "codex")
    for f in (REPO / tree).rglob("*.md")
    if shipped(str(f.relative_to(REPO))))
if not instructions_prose:
    sys.exit("check-package: FAILED — no shipped instructions prose found, so the "
             "reference scan below would pass over nothing")

prose_bad, prose_scanned = [], 0
declared = [r for r in instructions_prose if author_doc(r)]
for rel in leg("audience-declared docs", declared):
    if PREREQ not in (REPO / rel).read_text(encoding="utf-8"):
        prose_bad.append((rel, f"declares audience: author without stating {PREREQ!r}"))
for rel in instructions_prose:
    # An author-declared guide is still SCANNED, not skipped. The declaration
    # excuses naming a path the reader will not have; it does not excuse naming a
    # path nobody has. Skipping the file outright made the one document allowed to
    # reference the checkout the one document whose references were never read.
    declared_author = author_doc(rel)
    body = (REPO / rel).read_text(encoding="utf-8")
    for m in PROSE_PATH.finditer(body):
        target = rel_key(m.group(1))
        if not repo_path(target):
            continue                      # someone else's tree; nothing promised
        prose_scanned += 1
        leg("markdown prose refs", [target])
        if not (REPO / target).exists():
            prose_bad.append((rel, f"{target} (no such path in this repo)"))
        elif not declared_author and not shipped(target):
            prose_bad.append((rel, target))


# Shipped config carries agent-facing prose as well: a launch preset's mission is
# an instruction the agent follows, so it can send a packaged user to a path they
# do not have. Backticks are a markdown habit, so config paths are matched bare
# and filtered by existence in the repo. The escape mirrors the guide one: a table
# declaring audience = "author" covers its whole subtree.
# Backticks are stripped before matching rather than excluded by a lookbehind: the
# earlier lookbehind rejected `path` outright, and every path in this repo's prose
# is backticked, so the leg saw only the spelling that happens not to occur.
# Same unbounded suffix as PROSE_PATH, and for a worse reason here: the 2-4 class
# did not merely skip `decisions/decisions.jsonl`, it matched the PREFIX
# `decisions/decisions.json`, which exists nowhere, so the reference was dropped
# by the existence test as though it were not a path at all.
CONFIG_PATH = re.compile(r'(?<![/\w])([a-z0-9_.-]+/[A-Za-z0-9_./-]+\.[a-z][a-z0-9]*)')

def toml_hits(rel):
    data = tomllib.loads((REPO / rel).read_text(encoding="utf-8"))
    out, seen = [], 0

    def states_prereq(node):
        if isinstance(node, dict):
            return any(states_prereq(v) for v in node.values())
        if isinstance(node, list):
            return any(states_prereq(v) for v in node)
        return isinstance(node, str) and PREREQ in node

    def walk(node, declared):
        nonlocal seen
        if isinstance(node, dict):
            if node.get("audience") == "author":
                declared = True
                if not states_prereq(node):
                    out.append((rel, f"a table declares audience = \"author\" without "
                                     f"stating {PREREQ!r} in its own text"))
            for v in node.values():
                walk(v, declared)
        elif isinstance(node, list):
            for v in node:
                walk(v, declared)
        elif isinstance(node, str):
            for m in CONFIG_PATH.finditer(node.replace("`", " ")):
                target = rel_key(m.group(1))
                if not repo_path(target):
                    continue
                seen += 1
                if not (REPO / target).exists():
                    out.append((rel, f"{target} (no such path in this repo)"))
                elif not declared and not shipped(target):
                    out.append((rel, target))
    walk(data, False)
    return out, seen

for rel in sorted(str(f.relative_to(REPO)) for f in REPO.rglob("*.toml")
                  if shipped(str(f.relative_to(REPO)))):
    hits, seen = toml_hits(rel)
    prose_scanned += seen
    leg("config prose refs", range(seen))
    prose_bad.extend(hits)

# The other direction: an author-side gate that sneaks into files[] ships a check
# the packaged install can never run, and silently re-opens the boundary above.
#
# Asked of the FILES, not of the entries. npm expands a directory entry to its
# whole subtree, so replacing the individual `learn/*` entries with `learn/` ships
# both author-side scripts while no entry is itself author-side — reproduced, and
# the gate exited 0. What must hold is that no author-side path is packed, and
# `shipped()` already models npm's expansion, so it is the thing to ask.
leaked = sorted(e for e in files if author_side(rel_key(e)))
author_paths = sorted(set(AUTHOR_SIDE_FILES) | {
    str(p.relative_to(REPO)) for d in AUTHOR_SIDE_DIRS
    for p in (REPO / d).rglob("*") if p.is_file()})
leaked += [f"{rel} (packed by a directory entry in files[])"
           for rel in author_paths if shipped(rel)]
# Non-empty subject, per declared directory: a dir with no files is a stale
# declaration, and its half of the rule would pass over nothing.
author_files = {d: sorted(p.name for p in (REPO / d).glob("*") if p.is_file())
                for d in AUTHOR_SIDE_DIRS}
ghosts = [f for f in AUTHOR_SIDE_FILES if not (REPO / f).is_file()]
if ghosts:
    sys.exit(f"check-package: FAILED — declared author-side file(s) do not exist: "
             f"{', '.join(ghosts)}; a stale declaration silently exempts nothing")
empty = [d for d, names in author_files.items() if not names]
if empty:
    sys.exit(f"check-package: FAILED — no files under {', '.join(empty)}; that "
             "author-side rule has no subject, so a green result would be vacuous")
gates = [n for names in author_files.values() for n in names]
leg("author-side files", gates)
leg("shipped instructions docs", instructions_prose)

# Fourth direction: SHIPPED CODE may not reach for an author-side module. The third
# direction asks this of prose, which covers a guide telling a reader to open a path
# they will not have; it does not cover code, and code is where it is fatal rather
# than confusing — a shipped module that loads `gates/x.py` works in every clone and
# raises on the first packaged user, exactly the failure the first direction exists
# to prevent. The driver reached for `gates/check-global-file.py` this way.
#
# Asked of string CONSTANTS, parsed, so a comment naming a gate is not a violation
# while a path assembled for a loader is. Asked of every shipped `.py`, self-test
# bodies included: a scan that skipped them would exempt a whole class of sites
# without naming one, and this repo's rule is that an exemption names its site and
# carries its reason. The two references that are self-test-only are named below.
AUTHOR_IMPORT_EXEMPT = {
    ("session-distill/runlib/dispatch.py", "benchmarks/tier/live.py"):
        "named in OUT_OF_SCOPE as a path the driver's closure may NOT import, and in a self_test "
        "assertion about that rule; the tier experiments are not loaded, they are forbidden",
    ("session-distill/runlib/gate.py", "benchmarks/absence.py"):
        "read as SOURCE in its self-test (ast, one function lifted out) rather than imported, "
        "because importing it would pull in a host dispatcher; that leg is one of the module "
        "suites a packaged user cannot run, and the driver's own `--self-test` does not run it",
    ("session-distill/runlib/dispatch.py", "session-distill/census.py"):
        "a self_test plant's subject: a SCRIPT_RUNS row naming a real file the site does not run, "
        "which is how the stale-declaration refusal is stated. The v1 window census is not loaded "
        "by anything shipped; after the WP-22 cutover it is not even declared",
    ("session-distill/runlib/dispatch.py", "session-distill/migrate-ledger.py"):
        "a PROGRAMS declaration row: the author-side migrator runs git. It is declared because the "
        "closure inventory judges declared scripts, not because shipped code loads it",
}
shipped_python = sorted(
    rel for rel in (str(p.relative_to(REPO)) for p in REPO.rglob("*.py"))
    if shipped(rel) and not author_side(rel) and (REPO / rel).is_file())
if not shipped_python:
    sys.exit("check-package: FAILED — no shipped .py files found, so the author-side import scan "
             "would pass over nothing")
author_imports = []
# Which exemptions the scan actually MET. Existence is not use: with both files present, deleting
# the reference an exemption excuses left the exemption in place and the gate green, so the next
# real reference from that file would have been excused by a line nobody had read in months
# (review Y #5).
exercised_exempt = set()
for rel in leg("shipped python author-side loads", shipped_python):
    try:
        parsed = ast.parse((REPO / rel).read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as problem:
        author_imports.append(f"{rel}: could not be parsed ({type(problem).__name__}), so the scan cannot judge it")
        continue
    for node in ast.walk(parsed):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        named = rel_key(node.value)
        if not named.endswith(".py") or not author_side(named):
            continue
        if (rel, named) in AUTHOR_IMPORT_EXEMPT:
            exercised_exempt.add((rel, named))
            continue
        author_imports.append(f"{rel}:{node.lineno}: names the author-side module {named}, which a "
                              f"packaged user does not have")
stale_exempt = [f"{rel} -> {named}" for rel, named in AUTHOR_IMPORT_EXEMPT
                if not (REPO / rel).is_file() or not (REPO / named).is_file()]
if stale_exempt:
    sys.exit("check-package: FAILED — author-side import exemption(s) naming a file that does not "
             f"exist: {', '.join(stale_exempt)}; a stale exemption exempts nothing by name")
unused_exempt = [f"{rel} -> {named}" for rel, named in AUTHOR_IMPORT_EXEMPT
                 if (rel, named) not in exercised_exempt]
if unused_exempt:
    sys.exit("check-package: FAILED — author-side import exemption(s) the scan never met: "
             f"{', '.join(unused_exempt)}; the reference each excuses is gone, so the entry now "
             "excuses whatever is written next in that file. Delete the entry with the reference.")

# ---- the third direction for shipped JSON DATA -------------------------------------------------
#
# The prose and code legs above read markdown and .py. A shipped TABLE is neither, and
# `session-distill/tables/destinations.json` names `session-distill/update-state.py` — an
# author-side writer — in a row a shipped module reads at runtime. A packaged user does not have
# that file, which is the same failure the code leg exists for, arriving as data. It is admissible
# only in a row that declares `writer_scope: author`, because that declaration has a READER: the
# runtime rule in `session-distill/runlib/destinations.py` records such a row as not installed and
# does not certify its destination. A label whose only reader is this gate changes nothing a user
# receives, so the gate requires that rule to still be there.
AUTHOR_SCOPE_RULE = ("session-distill/runlib/destinations.py", "author_rows_absent")


def rule_reader(rel, name):
    """Whether the runtime rule `name` is still DEFINED in `rel`, and still CALLED there.

    The first version asked only whether the NAME occurred in the file's text, which a comment
    mentioning it satisfies — and a comment reads nothing, so the declaration would again have had
    no reader but this gate. Both halves come off the syntax tree now, and a call reached only from
    `self_test` does not count: a rule the suite alone invokes changes nothing a user receives.
    """
    path = REPO / rel
    if not path.is_file():
        return False, False
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return False, False
    defined = any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
                  for node in ast.walk(tree))
    # The SUITE, whatever it is called. Excluding the one name `self_test` stopped working the day
    # the suite gained a dying-control wrapper and its body moved to `_self_test_body`: the call
    # the gate was counting then came from the suite again (the round-3 review). Any top-level
    # function whose name begins `self_test` or `_self_test` is the suite, and so is a function the
    # suite alone calls — but one hop is what this gate needs, because the rule it asks about is
    # invoked from the manifest's own entry point or from nowhere.
    # By REACHABILITY from production code, over functions AND methods. The closure this replaced
    # grew a suite set until nothing moved, which a helper that calls ITSELF defeats — it always has
    # a caller outside the suite, its own name — and methods were not in its graph at all, so a
    # `Fixture.run` the suite alone called counted as a runtime reader (the round-5 review).
    #
    # Units are top-level functions, methods (keyed by bare name, since `x.run()` names no class:
    # the over-approximation only ever makes a method MORE reachable), and the module's own top
    # level with every class body. The suite is entered by name and never walked into from
    # production: `main` calling `self_test()` under the flag does not make the suite's calls
    # runtime calls. A production root is the top level, or a unit nothing but itself calls.
    # Two more shapes (the round-6 review). A CONSTRUCTOR is reached by calling the class, which
    # names no `__init__`: left without that edge it had no caller and so read as a production
    # root, and a rule called only from a fixture's `__init__` counted as read. And a call under
    # `if '--self-test' in argv:` inside a production function is the suite's dispatch, not a
    # production call. So `Class(...)` is an edge to that class's `__init__`, and a branch the exact
    # flag guards on the argument vector is not walked from production code — the same two
    # predicates, and no others, that the effect audit takes.
    units, top, constructors = {}, [], {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            units.setdefault(node.name, []).append(node)
        elif isinstance(node, ast.ClassDef):
            for held in node.body:
                if isinstance(held, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    key = f"{node.name}.__init__" if held.name == "__init__" else held.name
                    units.setdefault(key, []).append(held)
                    if held.name == "__init__":
                        constructors[node.name] = key
                else:
                    top.append(held)
        else:
            top.append(node)

    def is_suite(unit):
        return unit == "self_test" or unit.startswith("_self_test") or unit.startswith("self_test")

    def suite_half(node):
        """`"body"` or `"orelse"`: the half of an `if` that runs only under the flag, else None."""
        test = node.test
        if isinstance(test, ast.Compare) and len(test.ops) == 1 \
                and isinstance(test.left, ast.Constant) and test.left.value == "--self-test" \
                and ast.unparse(test.comparators[0]) in ("sys.argv", "argv", "sys.argv[1:]", "argv[1:]"):
            if isinstance(test.ops[0], ast.In):
                return "body"
            if isinstance(test.ops[0], ast.NotIn):
                return "orelse"
        return None

    def calls_of(nodes):
        held = set()

        def walk(node):
            # The guard is asked of the node ITSELF, not of a child: an `if` handed in directly —
            # every statement of the module's top level is — was walked whole, so a rule called
            # only under a top-level `if '--self-test' in sys.argv:` counted as read (the round-7
            # review).
            if isinstance(node, ast.If):
                half = suite_half(node)
                if half:
                    walk(node.test)
                    for part in (node.orelse if half == "body" else node.body):
                        walk(part)
                    return
            if isinstance(node, ast.Call):
                called_name = ast.unparse(node.func).split(".")[-1]
                held.add(constructors.get(called_name, called_name))
            for child in ast.iter_child_nodes(node):
                walk(child)

        for node in nodes:
            walk(node)
        return held

    calls = {unit: calls_of(nodes) for unit, nodes in units.items()}
    callers = {unit: set() for unit in units}
    for unit, held_calls in calls.items():
        for reached in held_calls & set(units):
            if reached != unit:
                callers[reached].add(unit)
    top_calls = calls_of(top)
    for reached in top_calls & set(units):
        callers[reached].add("<module>")
    # A unit some SUITE-only branch calls is not thereby uncalled: its callers are counted over the
    # whole body, so a helper reached only under the flag has a caller and is no root.
    def all_calls(nodes):
        return {constructors.get(n, n) for n in
                (ast.unparse(node.func).split(".")[-1] for held in nodes for node in ast.walk(held)
                 if isinstance(node, ast.Call))}
    any_caller = {unit: set() for unit in units}
    for unit, nodes in units.items():
        for reached in all_calls(nodes) & set(units):
            if reached != unit:
                any_caller[reached].add(unit)
    for reached in all_calls(top) & set(units):
        any_caller[reached].add("<module>")
    frontier = {unit for unit in units if not is_suite(unit)
                and (not any_caller[unit] or "<module>" in callers[unit])}
    production = set()
    while frontier:
        unit = frontier.pop()
        if unit in production or is_suite(unit):
            continue
        production.add(unit)
        frontier |= calls[unit] & set(units)
    called = name in top_calls or any(name in calls[unit] for unit in production)
    return defined, called


# Each exemption is keyed to the ROW that carries it, by JSON pointer, and not to the file. Keyed
# by (file, path) alone, one annotated occurrence excused the same path written anywhere else in
# that file — including in a live data row a shipped module reads, which is the failure the leg
# exists for. The pointer is what the scan meets, so a reference that moves to another row fails as
# an unmet exemption rather than being quietly carried.
# Two references this leg found on the day it was added, each named with its own reason and the
# condition that retires it. They are TRANSITIONAL, not licensed: the shape exists because work is
# in flight, and the answer is finishing it. An entry whose reference is gone fails below, so
# neither can quietly outlive its finding.
JSON_AUTHOR_REF_EXEMPT = {
    ("session-distill/tables/drift_layers.json", "/layers/6/prefixes/0",
     "design/session-distill/ledger.json"):
        "the ledger drift layer's prefix, written against THIS repo's checkout while the layer "
        "vocabulary is undecided (the table's own open_question says so). A packaged user has no "
        "design/ tree, so the prefix is wrong for them — an open finding, to be fixed with the "
        "layer vocabulary rather than by deleting the layer. Retires when config_manifest_B's keys "
        "are decided.",
    ("session-distill/tables/drift_layers.json", "/layers/6/prefixes/2",
     "design/session-distill/versions.json"):
        "the same prefix list, same reason.",
}
shipped_json = sorted(
    rel for rel in (str(p.relative_to(REPO)) for p in REPO.rglob("*.json"))
    if shipped(rel) and not author_side(rel) and (REPO / rel).is_file())
if not shipped_json:
    sys.exit("check-package: FAILED — no shipped .json files found, so the data scan would pass "
             "over nothing")


def declared_author_scope(data):
    """Every author-side path a JSON document declares with `writer_scope: author`.

    Walked rather than read at one key, because the declaration must travel with the row it
    excuses: a top-level flag would excuse every path in the file.
    """
    held = set()
    if isinstance(data, dict):
        if data.get("writer_scope") == "author":
            for value in data.values():
                if isinstance(value, str):
                    held.add(rel_key(value))
        for value in data.values():
            held |= declared_author_scope(value)
    elif isinstance(data, list):
        for value in data:
            held |= declared_author_scope(value)
    return held


def json_strings(data, pointer=""):
    """Every string in a JSON document, with the JSON pointer it sits at.

    The pointer is what ties an exemption to one row rather than to the whole file.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            yield from json_strings(value, f"{pointer}/{key}")
    elif isinstance(data, list):
        for index, value in enumerate(data):
            yield from json_strings(value, f"{pointer}/{index}")
    elif isinstance(data, str):
        yield pointer, data


json_refs = []
exercised_json_exempt = set()
rule_file, rule_name = AUTHOR_SCOPE_RULE
rule_defined, rule_called = rule_reader(rule_file, rule_name)
for rel in leg("shipped json data refs", shipped_json):
    try:
        data = json.loads((REPO / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError) as problem:
        json_refs.append(f"{rel}: could not be parsed ({type(problem).__name__}), so the scan "
                         f"cannot judge it")
        continue
    excused = declared_author_scope(data)
    for pointer, text in json_strings(data):
        named = rel_key(text)
        if "/" not in named or named.endswith("/"):
            continue
        if not author_side(named):
            continue
        # Exemptions are consulted BEFORE existence, because a prose field's key is the whole
        # sentence and no such path exists: the existence branch would report the sentence instead
        # of the reference the exemption is about. The POINTER must match: the same path written in
        # another row of the same file is a different reference, and nothing has excused it.
        held_exempt = next(((held_rel, held_at, held_named)
                            for held_rel, held_at, held_named in JSON_AUTHOR_REF_EXEMPT
                            if rel == held_rel and pointer == held_at
                            and named.startswith(held_named)), None)
        if held_exempt:
            exercised_json_exempt.add(held_exempt)
        elif not (REPO / named).exists():
            json_refs.append(f"{rel}: names {named}, which exists nowhere in this repo — a "
                             f"declaration can excuse a path the reader will not have, never one "
                             f"nobody has")
        elif named not in excused:
            json_refs.append(f"{rel}: names the author-side path {named} in a row that does not "
                             f"declare writer_scope: author, so a packaged user receives a table "
                             f"pointing at a file they do not have")
        elif not rule_defined:
            json_refs.append(f"{rel}: declares writer_scope: author for {named} while "
                             f"{rule_file} no longer DEFINES {rule_name}() — the declaration's only "
                             f"reader would be this gate, which changes nothing a user receives")
        elif not rule_called:
            json_refs.append(f"{rel}: declares writer_scope: author for {named} while "
                             f"{rule_file} defines {rule_name}() and never calls it outside its own "
                             f"suite — a rule nothing invokes reads no declaration, so the label "
                             f"again changes nothing a user receives")
stale_json_exempt = [f"{rel} -> {named} (at {pointer})"
                     for rel, pointer, named in JSON_AUTHOR_REF_EXEMPT
                     if (rel, pointer, named) not in exercised_json_exempt]
if stale_json_exempt:
    sys.exit("check-package: FAILED — shipped-JSON exemption(s) the scan never met: "
             f"{', '.join(stale_json_exempt)}; the reference each excuses is gone, so the entry now "
             "excuses whatever is written next in that file. Delete the entry with the reference.")
if json_refs:
    sys.exit("check-package: FAILED — " + str(len(json_refs)) + " shipped JSON reference(s) to an "
             "author-side path:\n      " + "\n      ".join(json_refs)
             + "\n      fix: declare the row `writer_scope: author` (and keep the runtime rule that "
               "reads it), or stop naming the path")

# provenance.json is EXEMPT above because a clone legitimately lacks a
# pack-generated file — but the exemption also skips shipped(), and an unshipped
# provenance regresses to the unbound-tarball shape silently, behind install.sh's
# own runtime guard. The pair that makes the exemption safe is asserted directly:
# the tarball must carry the file, and package.json must still wire the generator
# that writes it.
pkg_scripts = json.loads((REPO / "package.json").read_text(encoding="utf-8")).get("scripts", {})
prov_bad = []
if "provenance.json" not in files:
    prov_bad.append("provenance.json missing from package.json files[] — the "
                    "tarball would ship without its commit binding")
# EXACT equality, never membership: the script value is this repo's own, so the
# canonical command is demandable in full — a substring test accepted
# `... || true`, which swallows the gate's refusal while keeping its name.
for hk, want_cmd, consequence in (
    ("prepack", "bash gates/check-publish.sh --stamp",
     "nothing writes provenance.json at pack time"),
    # A two-command chain, demanded in full. `&&` cannot swallow either exit code, while
    # `;` and `|| true` can — and only exact equality tells those apart, which is why the
    # chain is spelled out rather than allowed by pattern. The currency guard runs FIRST
    # because it needs no network and refuses in milliseconds.
    ("prepublishOnly",
     "python3 gates/check-model-currency.py --publish-guard "
     "&& bash gates/check-publish.sh --guard",
     "directory-form publishes lose the clean-tree and live-origin checks, or ship tier "
     "bindings the host catalogues have already moved past"),
    ("postpack", "rm -f provenance.json",
     "a stale stamp left by a normal pack rides a later --ignore-scripts pack "
     "and binds the tarball to the WRONG commit"),
):
    got = pkg_scripts.get(hk, "")
    if got != want_cmd:
        prov_bad.append(f"package.json {hk} must be exactly {want_cmd!r} (got {got!r}) "
                        f"— anything else, a wrapper or an appended || true included, "
                        f"can swallow the gate: {consequence}")
leg("publication provenance",
    ["files[] carries it", "prepack writes it", "prepublishOnly guards it",
     "postpack cleans it"])

# A tracked shell script that sets pipefail may not pipe into `grep -q`. grep exits at its
# first match, the writer takes SIGPIPE on the rest of its output, and pipefail reports that
# exit as the pipeline's: a match reads as a miss, more often the later the match sits. The
# compatibility verify's `claude-run --help | grep -q` failed that way on every run once the
# help outgrew the pipe's first read, and this gate's own self-test lost cases the same way.
# Capture the output, then match a here-string or `case`. Author-side scripts are judged too:
# they break the same way, they only break somewhere else.
SHELL_SUFFIXES = (".sh", ".zsh", ".bash")
PIPEFAIL = re.compile(r"\bset\b[^#\n]*\bpipefail\b")
PIPED_QUIET_GREP = re.compile(r"\|\s*grep\s+(?:-[A-Za-z]*q[A-Za-z]*|--quiet|--silent)\b")
def tracked_files():
    # a checkout lists what git tracks; a copy of the tracked tree (this gate's self-test, the
    # commit hook's materialised index) holds nothing else, so it is walked whole
    if (REPO / ".git").exists():
        listed = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"], capture_output=True, check=True)
        return [REPO / r for r in listed.stdout.decode().split("\0") if r]
    return [p for p in sorted(REPO.rglob("*")) if ".git" not in p.relative_to(REPO).parts]
def shell_scripts():
    for p in tracked_files():
        if not p.is_file():
            continue
        if p.suffix in SHELL_SUFFIXES:
            yield p
            continue
        try:
            first = p.open("rb").readline()
        except OSError:
            continue
        if first.startswith(b"#!") and re.search(rb"\b(ba|z|da)?sh\b", first):
            yield p
pipefail_scripts, piped_grep = [], []
for p in shell_scripts():
    code = [(n, line) for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
            if not line.lstrip().startswith("#")]
    if not any(PIPEFAIL.search(line) for _, line in code):
        continue
    rel = p.relative_to(REPO).as_posix()
    pipefail_scripts.append(rel)
    piped_grep += [(rel, n, line.strip()) for n, line in code if PIPED_QUIET_GREP.search(line)]
leg("pipefail scripts without a piped quiet grep", pipefail_scripts)

# A shipped shell script may not call `mktemp -t`. macOS builds a template from -t's prefix; GNU
# mktemp requires three X's in the last component and marks -t deprecated, so under `set -e` the
# line aborts on Linux, which package.json declares. The portable form names its own template:
# `mktemp "${TMPDIR:-/tmp}/name.XXXXXX"`. Comment lines are not calls. A command is read as the shell
# reads it, its backslash-newline continuations joined, so `mktemp \` with `-t` on the next line is one.
MKTEMP_T = re.compile(r"\bmktemp\s+(?:-[A-Za-z]+\s+)*-[A-Za-z]*t")


def logical_lines(text):
    """(first line number, line) for each shell line, continuation lines joined. A comment line ends
    at its newline, backslash or not."""
    joined, start = "", None
    for n, line in enumerate(text.splitlines(), 1):
        if start is None and line.lstrip().startswith("#"):
            yield n, line
            continue
        start = n if start is None else start
        if (len(line) - len(line.rstrip("\\"))) % 2:
            joined += line[:-1]
            continue
        yield start, joined + line
        joined, start = "", None
    if start is not None:
        yield start, joined


shipped_shell, mktemp_t = [], []
for p in shell_scripts():
    rel = p.relative_to(REPO).as_posix()
    if not shipped(rel):
        continue
    shipped_shell.append(rel)
    mktemp_t += [(rel, n, line.strip())
                 for n, line in logical_lines(p.read_text(encoding="utf-8", errors="replace"))
                 if not line.lstrip().startswith("#") and MKTEMP_T.search(line)]
leg("shipped shell scripts without mktemp -t", shipped_shell)

# Every exclusive lock a writer takes waits at most 30 s and then refuses naming the lock
# (D-20261102-49b466), through host_platform.lock_within; a flock(LOCK_EX) without LOCK_NB waits
# without bound. LOCK_NB counts only when every evaluation sets it: an operand of a `|` chain. Behind
# a conditional (`LOCK_EX | (LOCK_NB if readonly else 0)`, whose writer branch blocks), a variable or
# a call, it cannot be established, and the call is a writer that waits without bound. Read from the
# parsed module, so a string or a comment showing the call is not one. A
# control's own holder takes a lock on purpose: a call inside a function named self_test, _self_test or
# test_*, in a test_*.py module, or under gates/ (whose every check is a control) is not a writer.
# No tracked writer is exempt: the author-side benchmark budget waits on the same bound.


def always_nonblocking(flags):
    """Whether the flag expression sets LOCK_NB on every evaluation: a `|` chain with it as an operand."""
    if isinstance(flags, ast.BinOp) and isinstance(flags.op, ast.BitOr):
        return always_nonblocking(flags.left) or always_nonblocking(flags.right)
    return (flags.attr if isinstance(flags, ast.Attribute) else getattr(flags, "id", None)) == "LOCK_NB"


def unbounded_locks(text):
    """Line numbers of flock calls asking LOCK_EX without an unconditional LOCK_NB outside a control."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines = []

    def visit(node, control):
        for child in ast.iter_child_nodes(node):
            inside = control or (isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                                 and (child.name in ("self_test", "_self_test") or child.name.startswith("test_")))
            if not inside and isinstance(child, ast.Call) and len(child.args) >= 2:
                called = child.func.attr if isinstance(child.func, ast.Attribute) else getattr(child.func, "id", None)
                flags = {n.attr if isinstance(n, ast.Attribute) else getattr(n, "id", None)
                         for n in ast.walk(child.args[1])}
                if called == "flock" and "LOCK_EX" in flags and not always_nonblocking(child.args[1]):
                    lines.append(child.lineno)
            visit(child, inside)
    visit(tree, False)
    return lines


lock_writers, unbounded = [], []
for p in tracked_files():
    rel = p.relative_to(REPO).as_posix()
    if p.suffix != ".py" or not p.is_file() or rel.startswith("gates/") or p.name.startswith("test_"):
        continue
    text = p.read_text(encoding="utf-8", errors="replace")
    if "flock" not in text:
        continue
    lock_writers.append(rel)
    unbounded += [(rel, n) for n in unbounded_locks(text)]
leg("python lock writers without an unbounded wait", lock_writers)

checked = sum(1 for r in found if r not in EXEMPT and not author_side(r) and (REPO / r).exists())
if missing or leaked or prose_bad or unguarded or prov_bad or piped_grep or mktemp_t or unbounded \
        or author_imports:
    if missing:
        print(f"check-package: FAILED — {len(missing)} runtime path(s) not in package.json files[]:")
        for rel, srcs in missing:
            print(f"  {rel}   (referenced by {', '.join(srcs)})")
    if unguarded:
        print(f"check-package: FAILED — {len(unguarded)} runtime reference(s) to an "
              f"author-side path with no proven guard; npm omits these, so the "
              f"packaged install dies where a clone succeeds:")
        for rel, srcs, why in unguarded:
            print(f"  {rel}   (referenced by {', '.join(srcs)}) — {why}")
    for entry in leaked:
        print(f"check-package: FAILED — author-side path in files[]: {entry}")
    for msg in prov_bad:
        print(f"check-package: FAILED — {msg}")
    if piped_grep:
        print(f"check-package: FAILED — {len(piped_grep)} piped quiet grep(s) in a tracked script that sets "
              f"pipefail; grep's early exit SIGPIPEs the writer and pipefail turns a match into a miss "
              f"(capture the output, then match a here-string or case):")
        for rel, n, line in piped_grep:
            print(f"  {rel}:{n}: {line}")
    if mktemp_t:
        print(f"check-package: FAILED — {len(mktemp_t)} mktemp -t call(s) in a shipped shell script; GNU mktemp "
              f"refuses -t's prefix as a template (use mktemp \"${{TMPDIR:-/tmp}}/name.XXXXXX\"):")
        for rel, n, line in mktemp_t:
            print(f"  {rel}:{n}: {line}")
    if unbounded:
        print(f"check-package: FAILED — {len(unbounded)} lock writer(s) waiting on flock(LOCK_EX) without a "
              f"bound; take the lock through host_platform.lock_within (D-20261102-49b466):")
        for rel, n in unbounded:
            print(f"  {rel}:{n}")
    if author_imports:
        print(f"check-package: FAILED — {len(author_imports)} shipped python reference(s) to an "
              f"author-side module; the code works in every clone and raises on the first packaged "
              f"user:")
        for msg in author_imports:
            print(f"  {msg}")
        print("  fix: move the code into a shipped module and import it from both sides "
              "(author-side imports shipped, never the reverse), or name the site and its "
              "reason in AUTHOR_IMPORT_EXEMPT")
    if prose_bad:
        print(f"check-package: FAILED — {len(prose_bad)} shipped-prose reference(s) "
              f"to a path the user will not have:")
        for rel, target in prose_bad:
            print(f"  {rel} -> {target}")
        print("  fix: ship the path, drop the reference, or declare it author-only "
              "— `audience: author` in a guide's frontmatter, `audience = \"author\"` "
              "in the config table that holds the text")
    sys.exit(1)

hollow = sorted(n for n, c in LEGS.items() if c == 0)
if hollow:
    sys.exit(f"check-package: FAILED — leg(s) that judged nothing: {', '.join(hollow)}. "
             f"An empty subject satisfies every claim, so reporting it clean is the "
             f"most common way a gate lies. Point it at real subjects or delete it.")

# ---- the fourth direction's instrument: npm's own expansion, not a model of it ----------------
# Everything above reasons about what npm packs. npm is the authority, and it disagreed: with
# `files[]` present, npm-packlist nulls the root `.npmignore`, so a local `__pycache__` under a
# listed directory was eligible for the tarball while the installer and the endpoint gate excluded
# it — "the rules agree" was a claim nobody had asked npm about (review Y #1). This leg asks it, on
# a copy with a cache planted both ways, and fails on any difference the force-include set does not
# explain.
npm_bin = shutil.which("npm")
if npm_bin is None:
    print("check-package: SKIPPED the npm expansion leg: npm is not on PATH, so the tarball's own "
          "file list cannot be derived here", file=sys.stderr)
else:
    # The INDEX where there is one — under the hook that is the snapshot the commit carries — and
    # the tree itself otherwise, because this gate's own self-test judges copies that are not git
    # repositories at all, and a crash there reads as "the gate failed on text that is no
    # violation".
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True)
    if tracked.returncode == 0 and tracked.stdout:
        names = [n for n in tracked.stdout.decode().split("\0") if n]
    else:
        names = [str(q.relative_to(REPO)) for q in REPO.rglob("*")
                 if q.is_file() and ".git/" not in str(q.relative_to(REPO))
                 and not str(q.relative_to(REPO)).startswith(".git")]
    with tempfile.TemporaryDirectory() as raw_tmp:
        copy = pathlib.Path(raw_tmp) / "tree"
        for rel in names:
            src = REPO / rel
            if not src.is_file():
                continue
            dst = copy / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        planted = [
            "session-distill/runlib/__pycache__/records.cpython-312.pyc",   # expanded from a dir entry
            "session-distill/runlib/legacy.pyc",                            # a bare .pyc beside its source
            "compose/__pycache__/instructions_install.cpython-312.pyc",     # a second listed tree
            "session-distill/runlib/legacy.pyo",                            # the other bytecode suffix
        ]
        for rel in planted:
            (copy / rel).parent.mkdir(parents=True, exist_ok=True)
            (copy / rel).write_bytes(b"\x00planted")
        # npm writes a compile cache into TMPDIR, and the umbrella's leg runner requires a leg
        # to leave TMPDIR as it found it: npm gets a TMPDIR inside the copy, which goes with it.
        npm_tmp = copy.parent / "npm-tmp"
        npm_tmp.mkdir()
        done = subprocess.run([npm_bin, "pack", "--dry-run", "--json", "--ignore-scripts"],
                              cwd=copy, capture_output=True, text=True,
                              env={**os.environ, "TMPDIR": str(npm_tmp),
                                   "npm_config_cache": str(npm_tmp / "cache")})
        if done.returncode != 0:
            sys.exit(f"check-package: FAILED — npm pack --dry-run could not derive the tarball's "
                     f"file list: {done.stderr.strip()[:300]}")

        def entry_list(payload):
            if isinstance(payload, dict):
                if "files" in payload and "entryCount" in payload:
                    return payload
                for value in payload.values():
                    found = entry_list(value)
                    if found:
                        return found
            if isinstance(payload, list):
                for value in payload:
                    found = entry_list(value)
                    if found:
                        return found
            return None
        report = entry_list(json.loads(done.stdout))
        if report is None:
            sys.exit("check-package: FAILED — npm pack --dry-run --json returned no file list; its "
                     "output shape changed and this leg cannot judge it")
        npm_files = {row["path"] for row in report["files"]}
        installer = importlib.util.spec_from_file_location(
            "instructions_install_under_test", copy / "compose" / "instructions_install.py")
        module = importlib.util.module_from_spec(installer)
        sys.modules[installer.name] = module
        installer.loader.exec_module(module)
        own = set(module.InstructionsInstaller(copy, {"HOME": str(copy / "home")})._package_files())
        # npm force-includes a few names whatever files[] says (probed, 2026-08-20): the manifest,
        # the readme and the licence. They are npm's, not the installer's, so they are named here
        # rather than counted as a disagreement.
        forced = {name for name in npm_files if always_packed(name)}
        leg("npm expansion rows", npm_files)
        def is_cache(name):
            # Both suffixes, because files[] now negates both and the installer's predicate knows
            # both: a comparison that reads only `.pyc` would pass over the pair it is here to hold.
            return name.endswith((".pyc", ".pyo")) or "__pycache__" in name.split("/")

        npm_bytecode = sorted(n for n in npm_files if is_cache(n))
        own_bytecode = sorted(n for n in own if is_cache(n))
        if npm_bytecode or own_bytecode:
            sys.exit("check-package: FAILED — compiled bytecode is still payload: npm packs "
                     f"{npm_bytecode}, the installer stores {own_bytecode}. A negated files[] entry "
                     "is the only rule npm honours once files[] exists.")
        only_npm = sorted(npm_files - own - forced)
        only_own = sorted(own - npm_files - {"package.json"})
        if only_npm or only_own:
            sys.exit("check-package: FAILED — the tarball and the private release are different "
                     f"payloads: npm only {only_npm[:8]}, installer only {only_own[:8]}. One of the "
                     "two reads files[] in a way the other does not.")
        if not planted:
            sys.exit("check-package: FAILED — the npm expansion leg planted nothing, so its "
                     "agreement is a claim over an unplanted tree")

print("check-package: OK — " + ", ".join(f"{n} {c}" for n, c in sorted(LEGS.items()))
      + f" ({len(EXEMPT)} exempt by name)")
PY
