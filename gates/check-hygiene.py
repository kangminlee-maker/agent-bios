#!/usr/bin/env python3
"""Content-hygiene gate: the shipped distribution carries no org or personal
binding outside a declared slot.

Measured 2026-08-19 (v0.13.0 payload plus the ko instructions trees): the distribution
is already lexically clean — zero org identifiers, two author identifiers, both
declared in EXEMPT below. This gate keeps it that way. It is the regression bar
for the already-public scope (package + instructions are one distribution,
D-20260818-71be4e) and the seed of the admission bar for the future public-repo
tree (the org→public boundary the 2026-08-19 roadmap names).

Declared exceptions have different scopes:

  - the private-binding marker ``(private)`` on a line declares an author or
    environment binding an adopter swaps (README's Adopting checklist is the
    human half of the convention). The marker excuses AUTHOR identifiers only —
    never org identifiers: the org's endpoints and names are exactly what the
    open-source split exists to keep out of core.
  - EXEMPT names individual (file, pattern) pairs, each bound to an ANCHORED
    line shape with its reason — the exemption covers the line its reason
    describes, never the file and never a longer line that smuggles a second
    token past the declared shape (hygiene rounds 1 #4, 2 #2). A pair whose
    file is gone or whose shape no longer matches anything fails as stale.
  - PUBLIC_INSTALL_REQUESTS admits only each named README's exact one-line
    installation request in a text code block, using repository.url as identity.
    It excuses the repository's author identifier, never additional bindings.

Fail-closed rules a clean summary depends on (rounds 1-2): a files[] entry that
exists as neither tracked file nor directory must be a DECLARED pack-time
artifact or the derivation fails; a tracked subject missing from the worktree is
a named failure, not a silent shrink; an authored subject that cannot be read
as UTF-8 text fails. Only the exact upstream wheel set admitted by the offline
UI bundle validator is binary content rather than authored prose. The npm
force-include set below was probed against the
installed npm (12.0.2 — 2026-08-19: README/LICENSE/LICENCE/COPYING + the bin and
main targets, CHANGELOG and NOTICE NOT force-included; 2026-08-20: the bin ARRAY
form packs every entry, and a `browser` target is force-included like `main`) —
re-probe with a scratch `npm pack --dry-run` before editing it.

Accepted residual, by the criterion's misclassification lean: the spaced idiom
"AI litmus test" is NOT matched (round 2 #6 — plausible shipped English), while
`ai-litmus`, `ai_litmus` and `ailitmus` are; a spaced product mention would pass
this gate and is left to the per-item human admission pass the roadmap names.

  (no args)     scan; exit 1 listing pattern: file:line per hit
  --self-test   plant each violation class into a scratch copy of the real
                subjects and require the gate to fail BY NAME; positive control
                first, so a failure is attributable to the mutation
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import types

REPO = pathlib.Path(__file__).resolve().parents[1]

PRIVATE_MARKER = "(private)"

# The wrapper's own exact token — the ONLY day1 form the bare pattern tolerates.
# Scrubbed before matching rather than excluded by lookahead, because a lookahead
# cannot demand boundaries on both sides at once: `myday1-agent-bios` and
# `day1-agent-bios-extra` must still fire (round 2, #3).
WRAPPER_TOKEN = re.compile(r"(?<![a-z0-9-])day1-agent-bios(?![a-z0-9-])", re.I)

# Ordered: name, compiled pattern, whether the private-binding marker excuses a
# hit, and an optional scrub applied to the line before matching. Org
# identifiers are never excusable. `day1co` subsumes `day1company` and the org
# mail domain (both contain it), so the alternation stays provable branch by
# branch (round 2, #4).
PATTERNS = (
    ("org identifier",
     re.compile(r"day1co|ai[-_]?litmus|alice@", re.I),
     False, None),
    ("bare day1",
     re.compile(r"day1(?!co)", re.I),
     False, WRAPPER_TOKEN),
    ("author identifier",
     re.compile(r"kangmin", re.I),
     True, None),
)

# (file, pattern name) -> (ANCHORED line shape, reason). Anchoring is load-
# bearing: an unanchored shape exempted every hit on a line that also carried
# the declared one (round 2, #2).
EXEMPT = {
    ("LICENSE", "author identifier"): (
        re.compile(r"^Copyright \(c\) \d{4} Kangmin Lee$"),
        "the MIT copyright line names the licensor — removing it would misstate the license",
    ),
    ("package.json", "author identifier"): (
        re.compile(r'^\s*"url": "git\+https://github\.com/kangminlee-maker/agent-bios\.git",?\s*$'),
        "npm metadata names the repository the package declares",
    ),
}

# Each localized copy request is a complete line, never a host or file allowance.
PUBLIC_INSTALL_REQUESTS = {
    "README.md": ("Install ", "", "the public installation request names the package's declared source"),
    "ko/README.md": ("", " 설치해줘", "the Korean installation request names the same declared source"),
}


def public_install_request_lines(root: pathlib.Path, subjects: list) -> tuple:
    """Return exact admitted (path, line) pairs and named contract failures."""
    declared = {name: row for name, row in PUBLIC_INSTALL_REQUESTS.items() if name in subjects}
    if not declared:
        return set(), []
    try:
        raw = json.loads((root / "package.json").read_text(encoding="utf-8"))["repository"]["url"]
        uri = raw.removeprefix("git+").removesuffix(".git")
        if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", uri):
            raise ValueError("repository.url must identify one HTTPS repository")
    except (AttributeError, KeyError, OSError, TypeError, ValueError) as exc:
        return set(), [("package.json", f"public install request identity cannot be derived: {exc}")]
    admitted, problems = set(), []
    for name, (prefix, suffix, _reason) in declared.items():
        try:
            lines = (root / name).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            problems.append((name, f"public install request cannot be read: {exc}"))
            continue
        expected = prefix + uri + suffix
        matches = [index + 1 for index, line in enumerate(lines)
                   if line == expected and index > 0 and index + 1 < len(lines)
                   and lines[index - 1] == "```text" and lines[index + 1] == "```"]
        if len(matches) != 1:
            problems.append((name, "public install request must appear exactly once as the metadata-derived "
                             "single line in a text code block"))
        else:
            admitted.add((name, matches[0]))
    return admitted, problems

# files[] entries that legitimately do not exist in the tree because packing
# creates them. Each carries its reason; anything else missing fails.
GENERATED = {
    "provenance.json":
        "stamped by gates/check-publish.sh at prepack from HEAD; fixed machine "
        "keys (commit, committedAt, dirty) — no prose ever enters it",
}

# Probed, not quoted from docs — see the module docstring before editing.
ALWAYS_INCLUDED = re.compile(r"^(README|LICENSE|LICENCE|COPYING)(\.|$)", re.I)

UI_BINARY_SCOPE = (
    "compose/ui_runtime/",
    "upstream UI distribution archives are binary dependencies, not authored prose; "
    "the shipped validator must verify their exact manifest, hashes, purity, and licenses",
)


def fail(message: str) -> "NoReturn":
    print(f"FAIL: {message}")
    sys.exit(1)


def _ls_files(root: pathlib.Path, prefix: str = "") -> list:
    proc = subprocess.run(
        ["git", "ls-files", "--", prefix] if prefix else ["git", "ls-files"],
        capture_output=True, text=True, cwd=root,
    )
    if proc.returncode != 0:
        fail(f"git ls-files failed under {root}: {proc.stderr.strip()[:120]}")
    return [line for line in proc.stdout.splitlines() if line]


def derive_subjects(root: pathlib.Path, package: dict, tracked: list) -> tuple:
    """(subjects, problems) — pure, so the self-test can plant derivation holes."""
    problems = []
    entries = package.get("files")
    if not isinstance(entries, list) or not entries:
        return [], ["package.json files[] is missing or empty; the subject set cannot be derived"]
    subjects = {"package.json"}
    for name in tracked:
        if "/" not in name and ALWAYS_INCLUDED.match(name):
            subjects.add(name)
    # npm force-includes the bin and main targets whatever files[] says (probed).
    # The ARRAY form packs every entry too (probed on npm 12.0.2, 2026-08-20 —
    # `bin: ["cli-a.js","cli-b.js"]` packed both).
    bin_field = package.get("bin")
    if isinstance(bin_field, str):
        subjects.add(bin_field)
    elif isinstance(bin_field, dict):
        subjects.update(v for v in bin_field.values() if isinstance(v, str))
    elif isinstance(bin_field, list):
        subjects.update(v for v in bin_field if isinstance(v, str))
    for key in ("main", "browser"):   # both probed force-included, 2026-08-20
        if isinstance(package.get(key), str):
            subjects.add(package[key])
    for entry in entries:
        if any(char in entry for char in "*?["):
            problems.append(
                f"files[] entry {entry!r} is a glob; this derivation does not "
                f"expand globs, so it cannot claim coverage over one"
            )
            continue
        # npm normalizes a leading ./ (round 2, #8).
        clean = entry
        while clean.startswith("./"):
            clean = clean[2:]
        clean = clean.rstrip("/")
        under = [name for name in tracked if name == clean or name.startswith(clean + "/")]
        if under:
            subjects.update(under)
        elif (root / clean).is_file():
            subjects.add(clean)
        elif clean in GENERATED:
            continue
        else:
            problems.append(
                f"files[] names {entry!r}, which is neither tracked nor a declared "
                f"pack-time artifact — the npm pack would ship something this scan "
                f"never saw, or ship nothing where the manifest promises a file"
            )
    subjects.update(name for name in tracked if name.startswith("ko/"))
    # A derived subject absent from the worktree is a named failure, not a
    # silent shrink of the denominator (round 2, #0).
    missing = sorted(name for name in subjects if not (root / name).is_file())
    for name in missing[:5]:
        problems.append(
            f"subject {name!r} is derived from the manifest or the tracked tree "
            f"but is not a file in this worktree — it cannot be scanned, so it "
            f"cannot be called clean"
        )
    ordered = sorted(subjects - set(missing))
    if not ordered:
        problems.append("the derived subject set is empty; an empty set satisfies everything")
    elif "claude/CLAUDE.md" not in ordered:
        problems.append("the subject set lost claude/CLAUDE.md, so the derivation is broken")
    return ordered, problems


def subject_paths(root: pathlib.Path) -> list:
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    subjects, problems = derive_subjects(root, package, _ls_files(root))
    for problem in problems:
        print(f"FAIL: {problem}")
    if problems:
        sys.exit(1)
    return subjects


def validated_binary_subjects(root: pathlib.Path, subjects: list) -> tuple:
    """Admit only the verified, fully represented upstream UI wheel inventory."""
    prefix, _reason = UI_BINARY_SCOPE
    scoped = {name for name in subjects if name.startswith(prefix)}
    if not scoped:
        return set(), []
    manifest_path = prefix + "manifest.json"
    loader = root / "compose/instructions_ui_runtime.py"
    try:
        if loader.is_symlink() or not loader.is_file():
            raise ValueError("the shipped UI bundle validator is missing or unsafe")
        module = types.ModuleType("hygiene_ui_bundle_validator")
        module.__file__ = str(loader)
        # Read the judged source bytes directly: module/bytecode caches must not
        # retain a different validator across scratch mutations or snapshots.
        exec(compile(loader.read_bytes(), str(loader), "exec"), module.__dict__)
        inventory = module.runtime_inventory(root)
        if not isinstance(inventory, dict) or inventory.get("status") != "available":
            detail = inventory.get("issues", []) if isinstance(inventory, dict) else inventory
            raise ValueError(f"UI bundle validation failed: {detail}")
        packages = inventory.get("packages")
        if not isinstance(packages, list) or not packages:
            raise ValueError("the UI validator admitted no wheel inventory")
        archives = {prefix + row["filename"] for row in packages}
        if len(archives) != len(packages) or any(not name.endswith(".whl") for name in archives):
            raise ValueError("the UI validator did not admit a unique wheel inventory")
        if scoped != archives | {manifest_path}:
            raise ValueError("the binary subject set differs from the validated UI manifest")
        return archives, []
    except (AttributeError, ImportError, KeyError, OSError, RuntimeError, SyntaxError, TypeError, ValueError) as exc:
        return set(), [("invalid binary bundle", manifest_path, 0, str(exc))]


def scan(root: pathlib.Path, subjects: list) -> tuple:
    """(findings, exercised): (kind, file, line number, line) per undeclared hit."""
    if not subjects:
        fail("scan called over no subjects; an empty set satisfies everything")
    binary_subjects, findings = validated_binary_subjects(root, subjects)
    public_lines, public_problems = public_install_request_lines(root, subjects)
    findings.extend(("public install request", name, 0, message) for name, message in public_problems)
    exercised = set()
    for name in subjects:
        if name in binary_subjects:
            continue
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            findings.append((
                "unreadable subject", name, 0,
                f"cannot be read as UTF-8 text ({type(exc).__name__}); a subject "
                f"this scan cannot read is not a subject it may call clean",
            ))
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if (name, number) in public_lines:
                exercised.add((name, "public install request"))
            for pattern_name, pattern, marker_escapes, scrub in PATTERNS:
                probe_line = scrub.sub("", line) if scrub is not None else line
                if not pattern.search(probe_line):
                    continue
                if pattern_name == "author identifier" and (name, number) in public_lines:
                    continue
                exempt = EXEMPT.get((name, pattern_name))
                if exempt is not None and exempt[0].search(line):
                    exercised.add((name, pattern_name))
                    continue
                if marker_escapes and PRIVATE_MARKER in line:
                    continue
                findings.append((pattern_name, name, number, line.strip()[:100]))
    for pair, (shape, _reason) in EXEMPT.items():
        if pair in exercised:
            continue
        if pair[0] not in subjects:
            findings.append((
                "stale exemption", pair[0], 0,
                f"EXEMPT declares {pair[1]!r} here but the file is no longer a "
                f"subject — the exemption was never exercised",
            ))
        else:
            findings.append((
                "stale exemption", pair[0], 0,
                f"EXEMPT declares {pair[1]!r} matching {shape.pattern!r} but no "
                f"line matches — a stale declaration excuses nothing",
            ))
    return findings, exercised


def run_scan() -> int:
    subjects = subject_paths(REPO)
    findings, exercised = scan(REPO, subjects)
    if findings:
        for kind, name, number, line in findings:
            print(f"FAIL: {kind}: {name}:{number}: {line}")
        print(f"check-hygiene: {len(findings)} undeclared hit(s) over "
              f"{len(subjects)} shipped files")
        return 1
    summary = ", ".join(f"{k} 0" for k, _, _, _ in PATTERNS)
    binary_count = sum(name.startswith(UI_BINARY_SCOPE[0]) and name.endswith(".whl") for name in subjects)
    print(f"check-hygiene: OK — {len(subjects)} shipped files, {summary}, "
          f"{len(exercised)}/{len(EXEMPT) + sum(name in subjects for name in PUBLIC_INSTALL_REQUESTS)} exemption(s) exercised on their "
          f"declared line shapes; {binary_count} validated upstream wheel archives")
    return 0


def self_test() -> int:
    subjects = subject_paths(REPO)
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="check-hygiene-"))
    try:
        for name in subjects:
            target = scratch / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / name, target)

        def findings_now(subject_list=None):
            return scan(scratch, subject_list or subjects)[0]

        def expect(label, wanted_kind, wanted_file, needle=None, subject_list=None):
            hits = [f for f in findings_now(subject_list)
                    if f[0] == wanted_kind and f[1] == wanted_file
                    and (needle is None or needle in f[3])]
            if not hits:
                fail(f"self-test: {label} was not caught by name"
                     + (f" carrying {needle!r}" if needle else ""))

        def expect_clean(label):
            found = findings_now()
            if found:
                fail(f"self-test: {label} — expected clean, got "
                     f"{[(f[0], f[1]) for f in found][:4]}")

        guide = "claude/guides/review-request.md"
        original = (scratch / guide).read_text(encoding="utf-8")

        def plant(line):
            (scratch / guide).write_text(original + "\n" + line + "\n", encoding="utf-8")

        # Positive control FIRST: the copy of the real tree must be clean.
        expect_clean("the unmodified copy of the shipped set")
        repository = json.loads((scratch / "package.json").read_text(encoding="utf-8"))["repository"]["url"]
        uri = repository.removeprefix("git+").removesuffix(".git")
        base, owner, repo_name = uri.rsplit("/", 2)
        for name, prefix, suffix in (("README.md", "Install ", ""), ("ko/README.md", "", " 설치해줘")):
            if name not in subjects:
                fail(f"self-test: public install request subject {name} is absent")
            content = (scratch / name).read_text(encoding="utf-8")
            request = prefix + uri + suffix
            for label, changed in (
                ("owner", prefix + f"{base}/{owner}-other/{repo_name}" + suffix),
                ("repository", prefix + f"{base}/{owner}/{repo_name}-other" + suffix),
                ("suffix", prefix + uri + "/tree/main" + suffix),
                ("extra URL", request + " https://github.com/other/repo"),
                ("fixture URL", request + " https://extra.test"),
                ("personal binding", request + " kangmin-private"),
                ("marked personal binding", request + " kangmin-private (private)"),
            ):
                (scratch / name).write_text(content.replace(request, changed, 1), encoding="utf-8")
                expect(f"{name} public install request {label}", "public install request", name)
            (scratch / name).write_text(content.replace("```text\n" + request + "\n```", request, 1), encoding="utf-8")
            expect(f"{name} request outside its code block", "public install request", name)
            (scratch / name).write_text(content + "\n```text\n" + request + "\n```\n", encoding="utf-8")
            expect(f"{name} duplicate public request", "public install request", name)
            (scratch / name).write_text(content, encoding="utf-8")
        package_content = (scratch / "package.json").read_text(encoding="utf-8")
        changed_package = json.loads(package_content)
        changed_package["repository"]["url"] = f"git+{base}/{owner}/{repo_name}-other.git"
        (scratch / "package.json").write_text(json.dumps(changed_package), encoding="utf-8")
        expect("public request drift from repository metadata", "public install request", "README.md")
        (scratch / "package.json").write_text(package_content, encoding="utf-8")
        expect_clean("the restored public installation requests")
        # Each org branch proven by a plant EXCLUSIVE to it (round 2, #4), plus
        # the subsumed forms as input coverage.
        for token, needle in (
            ("day1co", "day1co"), ("ai-litmus", "ai-litmus"),
            ("ai_litmus", "ai_litmus"), ("ailitmus", "ailitmus"),
            ("alice@example.org", "alice@"),
            ("day1company", "day1company"), ("x@day1company.co.kr", "day1company.co.kr"),
        ):
            plant(f"the {token} endpoint")
            expect(f"a planted org reference ({token})", "org identifier", guide, needle)
        # The marker does NOT excuse an org reference.
        plant(f"the day1co endpoint {PRIVATE_MARKER}")
        expect("a MARKED org reference", "org identifier", guide, "day1co")
        # The spaced idiom stays clean — the documented residual, so a future
        # widening that catches it announces itself here.
        plant("use this as an AI litmus test for the design")
        expect_clean("the spaced English idiom")
        # Bare day1: embedded, near-miss and boundary-extended forms fire; only
        # the wrapper's exact token is scrubbed (round 2, #3).
        for token in ("the day1 sink", "endpoint=https://day1-agent.internal",
                      "myDay1Client", "myday1-agent-bios", "day1-agent-bios-extra"):
            plant(token)
            expect(f"a planted bare day1 ({token})", "bare day1", guide, "ay1")
        plant("day1-agent-bios is the wrapper")
        expect_clean("the wrapper's own name")
        # Author identifiers: unmarked fails, the same line marked passes.
        plant("kangmin's setup")
        expect("a planted author identifier", "author identifier", guide, "kangmin")
        plant(f"kangmin's setup {PRIVATE_MARKER}")
        expect_clean("a marked author binding")
        (scratch / guide).write_text(original, encoding="utf-8")
        # Exemption is per ANCHORED line shape: a second author token in the
        # exempted file fails, and so does a single line carrying the declared
        # shape PLUS an undeclared token (round 2, #2).
        license_text = (scratch / "LICENSE").read_text(encoding="utf-8")
        (scratch / "LICENSE").write_text(
            license_text + "\ninternal maintainer: kangmin\n", encoding="utf-8")
        expect("a second author token in the exempted file", "author identifier",
               "LICENSE", "maintainer")
        (scratch / "LICENSE").write_text(license_text, encoding="utf-8")
        package_text = (scratch / "package.json").read_text(encoding="utf-8")
        (scratch / "package.json").write_text(
            package_text + '\n"maintainer": "kangmin-private", '
            '"url": "git+https://github.com/kangminlee-maker/agent-bios.git"\n',
            encoding="utf-8")
        expect("a combined line smuggling a token past the declared shape",
               "author identifier", "package.json", "kangmin-private")
        (scratch / "package.json").write_text(package_text, encoding="utf-8")
        # A copyright line without the licensor is a stale exemption...
        (scratch / "LICENSE").write_text(
            license_text.replace("Kangmin Lee", "The Author"), encoding="utf-8")
        expect("a copyright line without the licensor", "stale exemption", "LICENSE")
        (scratch / "LICENSE").write_text(license_text, encoding="utf-8")
        # ...and so is the file leaving the subject set (round 1 review, #5).
        without_license = [s for s in subjects if s != "LICENSE"]
        gone = [f for f in scan(scratch, without_license)[0]
                if f[0] == "stale exemption" and f[1] == "LICENSE"
                and "no longer a subject" in f[3]]
        if not gone:
            fail("self-test: a vanished exempted file was not reported stale")
        # An unreadable subject is a finding, never a silent skip.
        (scratch / guide).write_bytes(b"day1co\xff\xfe\x00clean?\n")
        expect("an unreadable subject", "unreadable subject", guide)
        (scratch / guide).write_text(original, encoding="utf-8")
        expect_clean("the restored tree")
        # A .whl suffix grants no scope outside the exact validated bundle.
        binary_subjects, binary_problems = validated_binary_subjects(scratch, subjects)
        if binary_problems or not binary_subjects:
            fail("self-test: the shipped UI wheel control set is empty or invalid")
        wheel = sorted(binary_subjects)[0]
        original_wheel = (scratch / wheel).read_bytes()
        outside = "claude/guides/unverified-dependency.whl"
        (scratch / outside).write_bytes(original_wheel)
        expect("a wheel outside the declared bundle", "unreadable subject", outside,
               subject_list=[*subjects, outside])
        (scratch / outside).unlink()
        # Changing either the wheel bytes or manifest revokes binary admission.
        corrupted = bytearray(original_wheel)
        corrupted[len(corrupted) // 2] ^= 1
        (scratch / wheel).write_bytes(corrupted)
        manifest = UI_BINARY_SCOPE[0] + "manifest.json"
        expect("a corrupted admitted wheel", "invalid binary bundle", manifest, "SHA256")
        (scratch / wheel).write_bytes(original_wheel)
        manifest_bytes = (scratch / manifest).read_bytes()
        changed_manifest = json.loads(manifest_bytes)
        changed_manifest["root_requirement"] = "textual==0.0.0"
        (scratch / manifest).write_text(json.dumps(changed_manifest), encoding="utf-8")
        expect("a changed binary manifest", "invalid binary bundle", manifest, "fingerprint")
        (scratch / manifest).write_bytes(manifest_bytes)
        rogue = UI_BINARY_SCOPE[0] + "unlisted-py3-none-any.whl"
        (scratch / rogue).write_bytes(original_wheel)
        expect("an unlisted wheel inside the bundle", "invalid binary bundle", manifest,
               "exact wheel inventory", subject_list=[*subjects, rogue])
        (scratch / rogue).unlink()
        validator = scratch / "compose/instructions_ui_runtime.py"
        validator_bytes = validator.read_bytes()
        validator.write_text("def runtime_inventory(repo):\n    return {'status': 'unavailable', 'issues': ['validation disabled']}\n",
                             encoding="utf-8")
        expect("disabled shipped bundle validation", "invalid binary bundle", manifest, "validation disabled")
        validator.write_bytes(validator_bytes)
        expect_clean("the restored binary bundle and validator")
        # Derivation holes fail rather than shrinking the denominator.
        package = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
        tracked = [s for s in subjects if s != "provenance.json"]
        clean_subjects, problems = derive_subjects(REPO, package, tracked)
        if problems:
            fail(f"self-test: the real manifest derived with problems: {problems[:2]}")
        holed = dict(package, files=list(package["files"]) + ["no-such-file.js"])
        _, problems = derive_subjects(REPO, holed, tracked)
        if not any("no-such-file.js" in p for p in problems):
            fail("self-test: a files[] entry shipping nothing was not refused by name")
        globbed = dict(package, files=list(package["files"]) + ["docs/*.md"])
        _, problems = derive_subjects(REPO, globbed, tracked)
        if not any("glob" in p for p in problems):
            fail("self-test: a glob files[] entry was not refused by name")
        # A leading ./ is npm-normalized, never reported missing (round 2, #8).
        dotted = dict(package, files=["./" + package["files"][0]] + list(package["files"][1:]))
        dotted_subjects, problems = derive_subjects(REPO, dotted, tracked)
        if problems or dotted_subjects != clean_subjects:
            fail(f"self-test: a ./-prefixed files[] entry changed the derivation: {problems[:1]}")
        # A tracked subject missing from the worktree is refused by name (round 2, #0).
        _, problems = derive_subjects(REPO, package, tracked + ["claude/guides/no-such-tracked.md"])
        if not any("no-such-tracked.md" in p and "worktree" in p for p in problems):
            fail("self-test: a tracked-but-absent subject was not refused by name")
        # bin and main targets are subjects even when files[] omits them,
        # proven through the pure derivation, not a file files[] already packs
        # (round 2, #5). The synthetic targets exist on disk via the scratch copy.
        synth_bin = dict(package, files=["claude/CLAUDE.md"],
                         bin={"x": "install.sh"}, main="session-cost.py")
        got, problems = derive_subjects(REPO, synth_bin, tracked)
        if problems or "install.sh" not in got or "session-cost.py" not in got:
            fail("self-test: bin/main targets outside files[] did not join the subjects")
        # browser and the ARRAY bin form are force-included too (probed
        # 2026-08-20). Each gets its own assertion: this package declares
        # neither, so nothing else here would notice their removal.
        synth_browser = dict(package, files=["claude/CLAUDE.md"],
                             browser="session-cost.py")
        got, problems = derive_subjects(REPO, synth_browser, tracked)
        if problems or "session-cost.py" not in got:
            fail("self-test: a browser target outside files[] did not join the subjects")
        synth_arr = dict(package, files=["claude/CLAUDE.md"],
                         bin=["install.sh", "session-cost.py"])
        got, problems = derive_subjects(REPO, synth_arr, tracked)
        if problems or not {"install.sh", "session-cost.py"} <= set(got):
            fail("self-test: an ARRAY bin outside files[] did not join the subjects")
        # The force-include set matches the PROBED npm behavior: COPYING ships
        # whatever files[] says; CHANGELOG does not (round 2, #1 — a wrong set
        # is a false PASS on one side and a false failure on the other). Run
        # against the scratch tree, where the planted files actually exist.
        for extra in ("COPYING", "CHANGELOG.md"):
            (scratch / extra).write_text("planted\n", encoding="utf-8")
        got, problems = derive_subjects(scratch, package, tracked + ["COPYING", "CHANGELOG.md"])
        if problems or "COPYING" not in got:
            fail(f"self-test: COPYING was not force-included (npm packs it): {problems[:1]}")
        if "CHANGELOG.md" in got:
            fail("self-test: CHANGELOG.md was force-included (npm does not pack it)")
        # The empty-subject refusal cannot be silent.
        proc = subprocess.run(
            [sys.executable, __file__, "--scan-nothing-probe"],
            capture_output=True, text=True,
        )
        if proc.returncode == 0 or "empty" not in (proc.stdout + proc.stderr):
            fail("self-test: a scan over no subjects did not refuse")
        print("check-hygiene --self-test: OK — every planted class failed by name")
        return 0
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv: list) -> int:
    if argv[1:] == ["--self-test"]:
        return self_test()
    if argv[1:] == ["--scan-nothing-probe"]:
        scan(REPO, [])
        return 0
    if argv[1:]:
        fail(f"unknown arguments: {argv[1:]}")
    return run_scan()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
