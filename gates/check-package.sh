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
elif op == "bin":                         # name a file as an executable npm installs
    d.setdefault("bin", {})["self-test-probe"] = arg
elif op == "collapse":                    # replace every entry under arg with arg
    keep = [e for e in d["files"] if not e.startswith(arg)]
    if len(keep) == len(d["files"]):
        sys.exit(f"self-test mutation is stale: no files[] entry under {arg!r}")
    d["files"] = keep + [arg]
p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
PY
  }

  case_is() {   # name, expected substring in the failure output
    local name="$1" want="$2" out rc
    ran=$((ran + 1))
    set +e; out=$("$W/gates/check-package.sh" 2>&1); rc=$?; set -e
    if [ "$rc" -eq 0 ]; then
      echo "check-package --self-test: FAIL: $name — the planted violation passed" >&2
      bad=1
    # A here-string, not a pipe: `grep -q` stops at its first match, and under pipefail the
    # writer's broken pipe on a long output turned a match into "not by name".
    elif ! grep -qF -- "$want" <<< "$out"; then
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

  fresh; pkg add '/workenv/contracts/examples/'
  case_is "a files[] entry spelled with a leading / is still that subtree" \
          "author-side path in files[]"

  fresh; pkg bin 'workenv/contracts/examples.py'
  case_is "a bin entry packs an author-side file whatever files[] says" \
          "packed as a package.json bin or main"

  fresh; printf 'c01_source_ref.schema.json\n' > "$W/workenv/contracts/schemas/.npmignore"
  case_is "an ignore file inside a shipped directory drops a file npm would otherwise pack" \
          "ignore file inside a shipped directory"

  fresh; printf '\npython3 "$REPO/compose/NO-SUCH-PROBE.py"\n' >> "$W/install.sh"
  case_is "a runtime reference to a path that does not exist" "no such path in this repo"

  fresh; pkg collapse 'learn/'
  case_is "a directory entry that swallows an author-side file" \
          "packed by a directory entry"

  fresh
  echo 'print("probe")' > "$W/compose/probe-selftest.py"
  printf '\ncat "$REPO/compose/probe-selftest.py" >/dev/null\n' >> "$W/install.sh"
  case_is "a runtime path missing from files[]" "not in package.json files"

  fresh; printf '\ncat "$REPO/decisions/record-decision.py" >/dev/null\n' >> "$W/install.sh"
  case_is "an unguarded runtime reference to an author-side path" "no proven guard"

  fresh; sub package.json '"workenv/contracts/records.py",' ''
  case_is "a work-environment runtime module nobody added to files[]" \
          "neither in package.json files[] nor declared author-side"

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
import json, pathlib, posixpath, re, sys, tomllib

# Reject anything not implemented, loudly. A gate that accepts --self-test by
# ignoring it and then prints OK tells the caller a control ran when none did.
ARGS = sys.argv[1:]
if ARGS and not (ARGS[0] == "--explain" and len(ARGS) == 2):
    sys.exit("check-package: usage: check-package.sh [--explain <path> | --self-test]\n"
             f"  refusing {' '.join(ARGS)!r} — this gate implements no other flag, "
             "and silently ignoring one would report a check that never ran")

REPO = pathlib.Path(".").resolve()
MANIFEST = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
files = MANIFEST["files"]

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
    "session-distill/": "the curator pipeline that authors instructions content. Users get the "
                        "workflow guide, not the authoring machinery",
    ".githooks/": "the pre-commit gate; enabled per clone with core.hooksPath",
    "workenv/contracts/examples/": "contract byte fixtures and their expectations. They are "
                                   "test material, and some are deliberately malformed — one "
                                   "is not UTF-8 at all — so a shipped-content scan could "
                                   "never call them clean without being weakened",
}

# Author-side FILES inside shipped directories. Promote — certifying an instruction
# package as globally distributable — is an administrator/developer action, so its
# machinery stays in the checkout even though it lives beside the shipped capture
# flow in learn/. A directory rule cannot express this: learn/ ships.
AUTHOR_SIDE_FILES = {
    "workenv/contracts/examples.py": "runs the contract byte fixtures, which do not ship; a "
                                     "shipped copy would name a directory the user lacks",
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

# This gate matches literal paths and directory prefixes. A glob in files[] would
# be mis-classified rather than understood, so it fails instead of guessing.
GLOB = re.compile(r"[*?\[\]{}!]")
_globs = sorted(e for e in files if GLOB.search(e))
if _globs:
    sys.exit(f"check-package: FAILED — files[] contains glob pattern(s) {_globs}; this "
             "gate models literal paths and directory prefixes only, and would answer "
             "both directions wrongly rather than fail")

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
    # right to. normpath collapses that to the path actually referenced. npm reads a
    # leading "/" as the package root, so "/gates/" is "gates": left in place, it matched
    # no author-side prefix and no shipped file while npm packed the whole subtree.
    return posixpath.normpath(raw.rstrip("/")).lstrip("/")


# npm also packs every file package.json names as a `bin` or as `main`, whatever files[] says,
# so a file named there ships as surely as one files[] names.
_bins = MANIFEST.get("bin") or {}
NAMED_PACKED = {rel_key(target) for target in
                (_bins.values() if isinstance(_bins, dict) else [_bins])}
if MANIFEST.get("main"):
    NAMED_PACKED.add(rel_key(MANIFEST["main"]))


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
queue = [s for s in SOURCES if s.endswith(".py")] + [r for r in found if r.endswith(".py")]
seen = set()
while queue:
    rel = queue.pop()
    if rel in seen or not (REPO / rel).exists():
        continue
    seen.add(rel)
    for m in IMPORT.finditer((REPO / rel).read_text(encoding="utf-8")):
        mod = m.group(1) or m.group(2)
        for d in MODULE_DIRS:
            sib = f"{d}/{mod}.py"
            if (REPO / sib).exists():
                found.setdefault(sib, set()).add(rel)
                queue.append(sib)

def shipped(rel):
    # npm treats a directory entry as its whole subtree whether or not the entry
    # carries a trailing slash, and resolves `./gates/` to the same subtree as
    # `gates/`. Both spellings are normalized here, through the same rel_key the
    # runtime scan uses: comparing raw entries let `./gates/` satisfy neither this
    # test nor author_side(), so npm packed the tree while the gate reported OK.
    if always_packed(rel) or rel in NAMED_PACKED:
        return True
    for entry in files:
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
# npm reads an ignore file inside a packed directory and drops what it names, so a directory
# entry would no longer ship its whole subtree and every "shipped" answer above would be wrong.
# There is none today; one appearing fails here rather than being modelled.
ignore_bad = sorted({str(p.relative_to(REPO)) for entry in files
                     if (REPO / rel_key(entry)).is_dir()
                     for p in (REPO / rel_key(entry)).rglob("*")
                     if p.name in (".npmignore", ".gitignore")})
leaked += [f"{rel} (packed as a package.json bin or main)"
           for rel in author_paths if rel in NAMED_PACKED]
leaked += [f"{rel} (packed by a directory entry in files[])"
           for rel in author_paths if shipped(rel) and rel not in NAMED_PACKED]
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

# The work-environment runtime is one tree whose owners are still being written, so the
# question is asked of its FILES rather than of files[]: each one is either in the payload or
# declared author-side. An unshipped runtime path is invisible from a clone and fatal on npm,
# and a per-file payload list would have to be extended by every node that lands one — which is
# the edit everybody forgets. `__pycache__` is skipped because git ignores it and npm packs
# what git tracks.
workenv_root = REPO / "workenv"
workenv_files = sorted(str(f.relative_to(REPO)) for f in workenv_root.rglob("*")
                       if f.is_file() and "__pycache__" not in f.parts) \
    if workenv_root.is_dir() else []
if not workenv_files:
    sys.exit("check-package: FAILED — no file under workenv/, so the payload boundary for the "
             "work-environment runtime would pass over nothing")
stranded = [rel for rel in leg("workenv payload boundary", workenv_files)
            if not shipped(rel) and not author_side(rel)]
if stranded:
    sys.exit("check-package: FAILED — under workenv/ and neither in package.json files[] nor "
             "declared author-side: " + ", ".join(stranded[:6])
             + (f" and {len(stranded) - 6} more" if len(stranded) > 6 else ""))

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
    ("prepublishOnly", "bash gates/check-publish.sh --guard",
     "directory-form publishes lose the clean-tree and live-origin checks"),
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

checked = sum(1 for r in found if r not in EXEMPT and not author_side(r) and (REPO / r).exists())
if missing or leaked or prose_bad or unguarded or prov_bad or ignore_bad:
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
    for rel in ignore_bad:
        print(f"check-package: FAILED — ignore file inside a shipped directory, which npm obeys: "
              f"{rel}")
    for msg in prov_bad:
        print(f"check-package: FAILED — {msg}")
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

print("check-package: OK — " + ", ".join(f"{n} {c}" for n, c in sorted(LEGS.items()))
      + f" ({len(EXEMPT)} exempt by name)")
PY
