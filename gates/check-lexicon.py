#!/usr/bin/env python3
"""Lexicon gate: forbid deprecated terminology tokens in live files.

LEXICON.md is the terminology SSOT (canonical concept names + deprecated
aliases). This gate operates it: a deprecated token that resurfaces as a live
identifier fails here, before it spreads. Two properties keep the gate honest:

  1. Self-consistency — every token this gate enforces must be documented in
     LEXICON.md, so the enforced set can never drift from the written one.
  2. Non-vacuity — the scanned file set and the denylist are both asserted
     non-empty, so a green run cannot pass over nothing.

Only unambiguous compound / identifier tokens are gated. Bare nouns that stay
valid ("learning" the artifact, "distillation" as in "upward distillation")
are deliberately NOT listed — see LEXICON.md.

  (no args)     scan every tracked text file outside ARCHIVE for DENY tokens;
                exit 1 listing file:line for each hit.
  --self-test   prove the detector fires on a planted token and stays silent
                on a clean string; exits 0 only if both hold.
"""
import json
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
LEXICON = REPO / "LEXICON.md"

# Deprecated tokens -> forbidden as live identifiers. Every entry MUST appear
# in LEXICON.md (enforced by the self-consistency check below).
DENY = [
    "session-learning",
    "session_learning",
    "SESSION_LEARNING",
    "LEARNING_MODE",
    "LEARNING_PRESET",
    "learning_hub",
    "learning-status",
    "learning-state.py",
    "AGENT_BIOS_LEARNING_STATUS",
    "learning-rollback",
    "distillation.schema",
    "check-distillation",
    "distillations.md",
    "pending-distillations",
]

# Dated records, never revised after the day they describe. A dated claim becomes
# historical rather than false, so nothing here needs maintaining to stay true —
# which is why it is also the one place a live file must never point at.
ARCHIVE_DIR = "design/archive/"

# Dated history + the files that must hold the deprecated literals to operate
# the lexicon (this gate carries DENY as string constants; LEXICON.md documents
# them). Keep this in sync with LEXICON.md's "Archive allowlist" section.
ARCHIVE = (
    "LEXICON.md",
    "gates/check-lexicon.py",
    # LEXICON.md is now generated from the ontology, so the file that AUTHORS the
    # deprecated literals moved here. ontology/check-ontology.py holds this tuple
    # against that block in both directions.
    "ontology/instances/graph.json",
    "design/session-distill/REVIEW-",
    "design/session-distill/DESIGN-v13-exploration-record.md",
    "design/session-distill/BUNDLE-ko-review.md",
    "design/collection-loop/DISCUSSION-",
    "session-distill/out/",
    # Dated records, never revised. Recording a rename means writing the old token down, so
    # scanning the archive would make every rename a gate failure.
    ARCHIVE_DIR,
)


def tracked_text_files():
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    files = []
    for rel in out:
        p = REPO / rel
        if not p.is_file():
            continue
        try:
            p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        files.append(rel)
    return files


def is_archived(rel):
    return any(rel == a or rel.startswith(a) for a in ARCHIVE)


def scan_text(text):
    """Return [(lineno, token)] for every DENY token occurrence.

    Case-insensitive: a deprecated proper noun is deprecated in every casing
    ("Session-Learning" is as stale as "session-learning"). No DENY token has a
    valid different-case counterpart, so this never masks a legitimate token.
    """
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        lowered = line.lower()
        for tok in DENY:
            if tok.lower() in lowered:
                hits.append((i, tok))
    return hits


def self_consistency():
    """Every enforced token must be documented in LEXICON.md."""
    if not LEXICON.is_file():
        return [f"LEXICON.md missing at {LEXICON}"]
    doc = LEXICON.read_text(encoding="utf-8")
    problems = [f"DENY token {tok!r} is not documented in LEXICON.md" for tok in DENY if tok not in doc]
    problems += documentation_mention_errors(DOC_MENTIONS, tracked_text_files())
    return problems


# Trees organized on an axis other than the concept graph: the instructions are laid out by
# target because the harness loads fixed paths, and these hold dated records. A slug
# appearing under them is a mention of a concept, not a home for it.
NOT_A_HOME = ("claude/", "codex/", "ko/", "design/", "benchmarks/", "research/",
              "packages/")

# These two files describe a concept; they do not implement it. Keep the
# exceptions by name so placing machinery under docs/ still fails the home rule.
DOC_MENTIONS = {
    "docs/instructions-compatibility.md": "user reference for named legacy instruction interfaces and retained storage",
    "docs/instructions.md": "user reference for inspecting and editing instructions items",
    "docs/assets/instructions-studio.svg": "static screenshot of the instructions UI, not runtime machinery",
}


def documentation_mention_errors(entries, files):
    problems = []
    for path, reason in entries.items():
        if not path.startswith("docs/") or not path.endswith((".md", ".svg")):
            problems.append(f"{path}: documentation mention must be named prose or SVG, not machinery")
        if path not in files or not isinstance(reason, str) or not reason.strip():
            problems.append(f"{path}: documentation mention is missing, untracked, or has no reason")
    return problems

HOME_ROW = re.compile(r"^\|[^|]+\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|\s*$", re.M)


def concept_homes():
    """(slug, home) pairs declared in LEXICON's `Concept homes` section.

    LEXICON owns the semantic call — which slug belongs to which concept, and which
    directory is that concept's home. This function only reads the declaration."""
    doc = LEXICON.read_text(encoding="utf-8")
    section = doc.split("## Concept homes", 1)
    if len(section) != 2:
        return []
    body = section[1].split("\n## ", 1)[0]
    return [(slug, home) for slug, home in HOME_ROW.findall(body)]


def planned_paths(read=None):
    """(plan, paths): the development plan CURRENT.md selects, as the plan gate selects it, and
    every path it assigns to a node or to the integrator. A planned path is a file the day its
    node is written, so its concept home is held from the day it is planned."""
    sys.path.insert(0, str(REPO / "gates"))
    from current_selector import PLAN_SELECTOR, current_selector_prose
    folder = REPO / "design" / "knowledge-and-history"
    read = read or (lambda path: path.read_text(encoding="utf-8"))
    names = re.findall(PLAN_SELECTOR, current_selector_prose(read(folder / "CURRENT.md")))
    if len(names) != 1:
        return None, []
    plan = json.loads(read(folder / names[0]))
    paths = set(plan.get("shared_integrator_paths", []))
    for node in plan.get("nodes", []):
        paths.update(node.get("owned_paths", []))
    return names[0], sorted(paths)


def misplaced(plan, paths, homes):
    """Planned paths carrying a concept slug outside that concept's home."""
    if plan is None:
        return ["planned paths: CURRENT.md selects no single implementation task graph"]
    if not paths:
        return [f"planned paths: {plan} assigns no path (vacuous)"]
    return [f"{path}: {plan} assigns it, and it carries concept slug {slug!r} outside its "
            f"declared home {home} (see LEXICON.md 'Concept homes')"
            for path in paths if not path.startswith(NOT_A_HOME) and path not in DOC_MENTIONS
            for slug, home in homes if slug in path and not path.startswith(home)]


def scattered(files, homes):
    """Machinery files carrying a concept slug from outside that concept's home."""
    problems = []
    for slug, home in homes:
        subjects = [rel for rel in files
                    if not rel.startswith(NOT_A_HOME) and rel not in DOC_MENTIONS and slug in rel]
        # Non-empty subject: a home whose slug matches nothing is a stale declaration,
        # and "no file violates it" would be true for the wrong reason.
        if not subjects:
            problems.append(f"concept slug {slug!r} matches no machinery file — "
                            f"stale LEXICON home declaration ({home})")
            continue
        for rel in subjects:
            if not rel.startswith(home):
                problems.append(f"{rel}: carries concept slug {slug!r} but lives outside "
                                f"its declared home {home} (see LEXICON.md 'Concept homes')")
    return problems


# -- guide reference form ---------------------------------------------------------------
# A guide is named by PATH. The rule is here rather than in the shipped domains gate because
# it needs LEXICON.md and the ko/ tree, and neither is in the npm payload — the first version
# of this lived in compose/check-domains.py and failed every packaged install, verified against
# the real tarball.
#
# The earlier shape was detection: find prose that reads like a reference. That set is open —
# four review rounds each found the next phrasing. This is the inversion. A bare token run that
# identifies exactly ONE guide is a reference the code cannot resolve, and it fails. The open
# axis (how the sentence was worded) disappears; what is left is the set of names that are also
# concepts, and LEXICON already owns and gates that set.
#
# A declared concept keeps the old heuristic instead of a free pass: `session-distill` is the
# pipeline, but "the session-distill guide" is still a reference. Closed for every guide whose
# name is not a concept, heuristic for the ones that are — measured at one.
GUIDE_TREES = ("claude/guides/", "ko/claude/guides/")

# The atom carries its own boundaries: a Korean particle attaches with no space, so
# `\b가이드\b` never matches `가이드를` and the KO half would be silently inert.
def _referring():
    """The referring-word alternation. EN words come from the shipped resolver
    (compose/check-domains.py REFERRING_WORDS), so the two gates cannot drift on what
    counts as a reference — refs_from hard-coding "guide" while this gate knew four words
    is exactly the divergence that let "read the staged-workflow document" through one
    gate and not the other. The Korean words are this gate's own: the shipped gate scans
    the EN canonical only."""
    en = _cd_module().referring_alternation()
    return rf"(?:\b(?:{en})\b|가이드|문서|지침)"


def _cd_module():
    """The shipped gate's module, loaded once. Author-side importing shipped is the
    allowed direction (AGENTS.md §6); the reverse would make the payload depend on
    gates/. Both the name-reading rule and the referring vocabulary come from here, so
    the two gates judge "is this a reference" with one set of definitions."""
    import importlib.util
    if not hasattr(_cd_module, "_mod"):
        src = REPO / "compose" / "check-domains.py"
        spec = importlib.util.spec_from_file_location("_cd", src)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _cd_module._mod = mod
    return _cd_module._mod


def _prose_handles():
    return _cd_module().prose_handles


def identifying_runs(guide_names, handles=None):
    """run -> the one guide it names. A run two guides share identifies no file, so it can
    never be a reference and is not judged — EXCEPT a run that is some guide's entire stem:
    naming the whole filename is not ambiguous even where it prefixes a sibling's, and
    refs_from() in the shipped gate already resolves it that way. Review caught the two
    implementations apart: "the llm-capability-boundary guide" was a reference the shipped
    resolver could follow and this gate could not see."""
    handles = handles or _prose_handles()
    owner = {}
    for n in guide_names:
        for r in handles(n):
            owner.setdefault(r, set()).add(n)
    out = {}
    for r, g in owner.items():
        if len(g) == 1:
            out[r] = next(iter(g))
        else:
            exact = [n for n in g if n[:-3] == r]
            if len(exact) == 1:
                out[r] = exact[0]
    return out


def guide_reference_form(files, read=None, concepts=(), runs=None):
    """Bare guide names outside a path reference."""
    read = read or (lambda rel: (REPO / rel).read_text(encoding="utf-8"))
    runs = identifying_runs(sorted({rel.rsplit("/", 1)[-1] for rel in files})) if runs is None \
        else runs
    concepts = set(concepts)
    REFERRING = _referring()
    problems = []
    def loose(run):
        """The run with hyphens relaxed to hyphen-or-space, for the referring-adjacent
        test only. "the concept economy guide" is a reference a reader cannot follow,
        and the hyphenated pattern never saw it. The BARE test keeps the literal hyphen:
        dehyphenated, a run is ordinary English — "keeps the concept economy compact" is
        a mention, and a bare test that fired on it would cry wolf on every guide that
        discusses the concept it is named after."""
        return r"[-\s]+".join(re.escape(tok) for tok in run.split("-"))

    for rel in sorted(files):
        body = read(rel)
        parts = body.split("---", 2)
        prose = parts[2] if body.startswith("---") and len(parts) == 3 else body
        # EVERY guide path goes first, not just the current target's: a sibling's path
        # extends the base's stem (guides/llm-capability-boundary-patterns.md contains the
        # run llm-capability-boundary), so target-only stripping reported a resolvable
        # sibling link as a bare reference — a finding whose instruction was to add the
        # path already present.
        pathless = re.sub(r"\S*guides/[a-z0-9-]+\.md\S*", "", prose)
        for run, target in sorted(runs.items(), key=lambda kv: -len(kv[0])):
            if rel.endswith("/" + target) or any(
                rel.startswith(tree + target.removesuffix(".md") + "/") for tree in GUIDE_TREES
            ):
                continue
            stripped = pathless
            # ASCII boundaries, not \b: Korean particles attach with no space, and
            # `staged-workflow의` puts a Hangul word character right after the stem —
            # \b sees word-to-word and never matches, so the attached form sailed
            # through while the spaced form was caught. The boundary is "not an ASCII
            # word character", which a particle satisfies and a longer identifier
            # (workflows) does not.
            B0, B1 = r"(?<![0-9A-Za-z_])", r"(?![0-9A-Za-z_])"
            near = (rf"{B0}{loose(run)}{B1}[^.\n]{{0,20}}{REFERRING}"
                    rf"|{REFERRING}[^.\n]{{0,20}}{B0}{loose(run)}{B1}")
            if run in concepts:
                pat = near
                why = f"names {target} as the {run!r} guide"
            else:
                pat = rf"{B0}{re.escape(run)}{B1}|{near}"
                why = f"names {target} as bare {run!r}"
            if re.search(pat, stripped, re.I):
                problems.append(f"{rel}: {why} — reference a guide by its path so the "
                                f"reference resolves, or declare {run!r} in LEXICON if it "
                                f"is a concept name")
                break
    return problems


# Trees that carry runtime authority: what an agent loads or the installer executes. A live
# file pointing into the archive would make a dated record authoritative again, which is the
# property the archive exists to remove. AGENTS.md is in this list on purpose — it means the
# method it carries has to be self-contained rather than a stub deferring to history.
RUNTIME_AUTHORITY = (
    "claude/", "codex/", "ko/", "compose/", "launch/", "learn/", "wrappers/",
    "gates/", "ontology/", "docs/", "install.sh", "AGENTS.md", "CLAUDE.md", "README.md", "CONTRIBUTING.md",
)

# The two files that OPERATE this rule must name the path to enforce and author it, exactly as
# they must hold the deprecated tokens. LEXICON.md is not listed: it is a projection and sits
# outside RUNTIME_AUTHORITY, so exempting it would be a registration nothing reads.
ARCHIVE_OPERATORS = ("gates/check-lexicon.py", "ontology/instances/graph.json")

# Naming the directory DECLARES the prohibition; naming a file inside it DEPENDS on the content.
# Only the second makes a dated record authoritative again, and AGENTS.md has to be able to state
# the rule it is bound by. So the bare directory passes and a path into it fails — the difference
# is whether a filename character follows the slash.
ARCHIVE_FILE_REF = re.compile(re.escape(ARCHIVE_DIR) + r"[A-Za-z0-9_.-]")


def archive_referenced_by_runtime(files, read=None):
    """Runtime-authority files that point into the archive.

    `read` is injectable so the negative controls can plant a reference without writing into
    the working tree — a control that mutates a tracked file leaves the plant behind if the
    process dies between the write and the restore.
    """
    read = read or (lambda rel: (REPO / rel).read_text(encoding="utf-8"))
    subjects = [rel for rel in files
                if rel.startswith(RUNTIME_AUTHORITY) and rel not in ARCHIVE_OPERATORS]
    # Non-empty subject: "no runtime file references the archive" is vacuously true over an
    # empty set, so a tree list that stopped matching reality would read as compliance.
    if not subjects:
        return ["no runtime-authority file was scanned — the archive-reference check ran "
                "over an empty subject"]
    problems = []
    for rel in subjects:
        for i, line in enumerate(read(rel).splitlines(), 1):
            if ARCHIVE_FILE_REF.search(line):
                problems.append(f"{rel}:{i}: points at a file under {ARCHIVE_DIR} — dated "
                                f"records carry no runtime authority, and a live pointer makes "
                                f"one authoritative again")
    return problems


# The live findings queue holds open items only; closing one is a deletion, and the reasoning
# goes to the dated round record. A per-entry status field is the part that goes stale, because
# closure often arrives as a side effect of a decision taken under another name and nobody walks
# back to mark it. A file with no status field cannot drift that way, so the markers that would
# reintroduce one are refused here rather than trusted not to come back.
FINDINGS = "FINDINGS.md"
RESOLUTION_MARKERS = ("RESOLVED", "SUPERSEDED", "Superseded")


def findings_queue_open_only(read=None):
    read = read or (lambda rel: (REPO / rel).read_text(encoding="utf-8"))
    try:
        text = read(FINDINGS)
    except OSError:
        return [f"{FINDINGS} is missing — the open-findings queue has no home, so nothing "
                f"holds a defect between the round that finds it and the one that fixes it"]
    return [f"{FINDINGS}:{i}: carries a resolution marker ({marker!r}) — closing a finding "
            f"means deleting its entry, not annotating it (design/archive/ keeps the reasoning)"
            for i, line in enumerate(text.splitlines(), 1)
            for marker in RESOLUTION_MARKERS if marker in line]


def gate():
    failures = list(self_consistency())
    if not DENY:
        failures.append("DENY list is empty (vacuous gate)")

    files = [rel for rel in tracked_text_files() if not is_archived(rel)]
    if not files:
        failures.append("no non-archive tracked text files to scan (vacuous)")

    for rel in files:
        for lineno, tok in scan_text((REPO / rel).read_text(encoding="utf-8")):
            failures.append(f"{rel}:{lineno}: deprecated token {tok!r} (see LEXICON.md)")

    homes = concept_homes()
    if not homes:
        failures.append("LEXICON.md declares no concept homes (vacuous layout gate)")
    failures += scattered(tracked_text_files(), homes)
    plan, planned = planned_paths()
    failures += misplaced(plan, planned, homes)
    failures += archive_referenced_by_runtime(tracked_text_files())
    failures += findings_queue_open_only()

    guide_files = [rel for rel in tracked_text_files()
                   if rel.startswith(GUIDE_TREES) and rel.endswith(".md")]
    guide_names = {rel[len(tree):] for rel in guide_files for tree in GUIDE_TREES
                   if rel.startswith(tree) and "/" not in rel[len(tree):]}
    runs = identifying_runs(sorted(guide_names))
    if not guide_files:
        failures.append("no guide files to check for reference form (vacuous)")
    if not runs:
        failures.append("no guide name identifies a single guide, so reference form judged "
                        "nothing (vacuous)")
    failures += guide_reference_form(guide_files, concepts=[s for s, _ in homes], runs=runs)

    if failures:
        print("check-lexicon: FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"check-lexicon: OK ({len(files)} files scanned, {len(DENY)} deprecated tokens enforced, "
          f"{len(homes)} concept homes held over files and {len(planned)} planned paths, "
          f"{ARCHIVE_DIR} unreferenced by runtime, "
          f"{len(guide_files)} guides name each other by path over {len(runs)} identifying runs)")
    return 0


def self_test():
    failures = []
    failures += self_consistency()
    if not scan_text(f"a line using {DENY[0]} here"):
        failures.append("detector did NOT fire on a planted deprecated token")
    # case-insensitivity: a title-cased variant must still be caught.
    if not scan_text(f"a line using {DENY[0].title()} here"):
        failures.append("detector missed a title-cased deprecated token")
    if scan_text("a clean line using session-distill and learning"):
        failures.append("detector fired on a clean line (false positive)")
    # the gate must exempt its own file, else it flags its DENY literals.
    if not is_archived("gates/check-lexicon.py"):
        failures.append("gate does not exempt its own file (would flag DENY literals)")
    # Concept-home controls: the declaration parses, a scattered file is caught, a
    # mention under a target-axis tree is not, and a slug matching nothing is caught.
    homes = concept_homes()
    if not homes:
        failures.append("concept-home declaration did not parse out of LEXICON.md")
    elif scattered(tracked_text_files(), homes):
        failures.append("concept-home check fires on the real tree (should be clean)")
    else:
        slug, home = homes[0]
        one = [(slug, home)]
        planted = f"elsewhere/{slug}-tool.py"
        if not scattered([f"{home}{slug}.py", planted], one):
            failures.append(f"concept-home check missed a scattered file ({planted})")
        if scattered([f"{home}{slug}.py", f"design/{slug}-notes.md"], one):
            failures.append("concept-home check fired on an in-home file or a design/ mention")
        if not scattered([f"{home}{slug}.py"], [("no-such-slug-xyz", home)]):
            failures.append("concept-home check accepted a slug matching nothing (vacuous)")

    # Closed, independent fixtures: document exceptions cannot excuse machinery
    # or count as the implementation that a concept home must actually contain.
    if scattered(["compose/instructions.py", "docs/instructions.md", "docs/assets/instructions-studio.svg"], [("instructions", "compose/")]):
        failures.append("concept-home check rejected the declared documentation mentions")
    if not scattered(["compose/instructions.py", "docs/instructions.py"], [("instructions", "compose/")]):
        failures.append("concept-home check exempted machinery placed under docs/")
    if not scattered(["docs/instructions.md"], [("instructions", "compose/")]):
        failures.append("a documentation mention incorrectly satisfied an implementation home")
    if documentation_mention_errors({"docs/example.md": "prose"}, ["docs/example.md"]):
        failures.append("documentation mention positive control failed")
    for entries, files in (({"docs/example.md": "prose"}, []),
                           ({"docs/example.md": ""}, ["docs/example.md"]),
                           ({"docs/instructions.py": "claimed documentation"}, ["docs/instructions.py"])):
        if not documentation_mention_errors(entries, files):
            failures.append("documentation mention accepted a stale, unexplained, or machinery exemption")

    # Archive-reference controls. `read` is injected, so none of these touch the working tree.
    cited = {"install.sh": f"see {ARCHIVE_DIR}round-2026-07.md",
             "design/notes.md": f"see {ARCHIVE_DIR}round-2026-07.md",
             "gates/check-lexicon.py": f'ARCHIVE_DIR = "{ARCHIVE_DIR}"',
             "AGENTS.md": f"nothing under `{ARCHIVE_DIR}` may be referenced from a runtime file",
             "claude/CLAUDE.md": "no reference here"}
    look = cited.get
    if not archive_referenced_by_runtime(["install.sh", "claude/CLAUDE.md"], look):
        failures.append("archive-reference check missed a runtime file citing the archive")
    # Declaring the rule names the directory; depending on a record names a file in it.
    if archive_referenced_by_runtime(["AGENTS.md", "claude/CLAUDE.md"], look):
        failures.append("archive-reference check fired on a bare directory mention, which is "
                        "how a runtime file states the prohibition it is bound by")
    if archive_referenced_by_runtime(["design/notes.md", "claude/CLAUDE.md"], look):
        failures.append("archive-reference check fired on a design/ file, which may cite freely")
    # Paired with a clean runtime file on purpose: the operator alone would empty the subject
    # set and trip the vacuity guard instead of testing the exemption.
    if archive_referenced_by_runtime(["gates/check-lexicon.py", "claude/CLAUDE.md"], look):
        failures.append("archive-reference check flags its own operator, which must name the path")
    if not archive_referenced_by_runtime([], look):
        failures.append("archive-reference check passed over an empty subject (vacuous)")
    for doc in ("docs/recovery.md", "docs/assets/instructions-studio.svg", "CONTRIBUTING.md"):
        if not archive_referenced_by_runtime([doc], lambda _: f"see {ARCHIVE_DIR}past.md"):
            failures.append(f"active documentation escaped archive-reference checking: {doc}")
    if ARCHIVE_DIR not in ARCHIVE:
        failures.append(f"{ARCHIVE_DIR} is not archive-exempt — recording a rename would fail the gate")

    # Reference-form controls, read-injected. The pair that matters is the last two: a bare
    # name fails, and the SAME name declared a concept does not. Without the second, "it fires"
    # would be equally true of a rule that flags every occurrence and exempts nothing, which is
    # the rule this one was rewritten to stop being.
    r_runs = {"staged-workflow": "coding-staged-workflow.md",
              "session-distill": "session-distill-workflow.md"}
    def rf(text, concepts=()):
        return guide_reference_form(["claude/guides/host.md"], lambda _: text,
                                    concepts=concepts, runs=r_runs)
    if not rf("see the staged-workflow rules for the ladder"):
        failures.append("reference-form check missed a bare guide name")
    if not rf("나머지는 staged-workflow 가이드를 본다"):
        failures.append("reference-form check missed a bare guide name in the KO tree")
    if not rf("read the staged workflow guide for the ladder"):
        failures.append("reference-form check missed a DEHYPHENATED name next to a "
                        "referring word — prose renders filenames as plain words")
    if not rf("staged-workflow의 가이드를 읽는다"):
        failures.append("reference-form check missed a Korean particle attached to the "
                        "stem — 의 is a word character and \\b never fires between them")
    if not rf("read the staged-workflow document for the ladder"):
        failures.append("reference-form check missed a referring synonym the shipped "
                        "resolver knows — the vocabulary must be shared, not copied")
    if not rf("read the staged workflow guides for the ladder"):
        failures.append("reference-form check missed the PLURAL referring form")
    if rf("the staged-workflows here are three, then review"):
        failures.append("reference-form check fired inside a longer identifier")
    if rf("the staged workflow here is three stages, then review"):
        failures.append("reference-form check fired on a dehyphenated run with no "
                        "referring word, which is ordinary prose, not a reference")
    if rf("see `~/.claude/guides/coding-staged-workflow.md` for the ladder"):
        failures.append("reference-form check fired on a proper path reference")
    if guide_reference_form(["claude/guides/coding-staged-workflow/RUNBOOK.md"],
                            lambda _: "The staged-workflow guide owns this companion.", runs=r_runs):
        failures.append("reference-form check treats a companion's own guide as another unit")
    if not guide_reference_form(["claude/guides/coding-staged-workflow/RUNBOOK.md"],
                                lambda _: "Read the session-distill guide.", runs=r_runs):
        failures.append("reference-form check skipped a companion's bare reference to another guide")
    if guide_reference_form(["claude/guides/host.md"],
                            lambda _: "see `~/.claude/guides/aa-bb-cc.md` for the patterns",
                            runs={"aa-bb": "aa-bb.md", "aa-bb-cc": "aa-bb-cc.md"}):
        failures.append("reference-form check fired on a sibling guide's path whose name "
                        "extends the base stem — a resolvable link read as a bare mention")
    if rf("the heavy session-distill pipeline mines many sessions",
          concepts=["session-distill"]):
        failures.append("reference-form check fired on a LEXICON-declared concept name, which "
                        "is what makes the rule closable rather than a ban on every mention")
    if not rf("read the session-distill guide for the flow", concepts=["session-distill"]):
        failures.append("reference-form check let a declared concept name carry a real "
                        "reference — the concept exemption must not be a free pass")
    if guide_reference_form([], lambda _: "", runs=r_runs):
        failures.append("reference-form check produced a finding over no files (vacuous)")
    # Overlapping stems: the full stem must survive as its guide's unique owner even where
    # it prefixes a sibling, and a genuinely shared partial run must still identify nothing.
    ir = identifying_runs(["aa-bb.md", "aa-bb-cc.md", "aa-bb-dd.md"])
    if ir.get("aa-bb") != "aa-bb.md":
        failures.append(f"identifying_runs dropped a full stem shared as a sibling prefix "
                        f"(got {ir.get('aa-bb')!r}) — the base guide becomes unreferencable")
    if "aa-bb-cc" not in ir or ir.get("aa-bb-cc") != "aa-bb-cc.md":
        failures.append("identifying_runs lost a unique full stem")
    if not guide_reference_form(["claude/guides/host.md"],
                                lambda _: "read the aa bb guide for details",
                                runs={"aa-bb": "aa-bb.md"}):
        failures.append("reference-form check missed a dehyphenated full-stem reference "
                        "that prefixes a sibling guide's name")

    # Planned-path controls: a planned module outside its home is caught, one inside or with no
    # slug is not, and a plan assigning nothing, or no plan selected, is not a pass.
    home = [("instructions", "compose/")]
    if not misplaced("plan.json", ["workenv/instructions_adapter.py"], home):
        failures.append("planned-path check missed a planned path carrying a concept slug "
                        "outside its home")
    if misplaced("plan.json", ["workenv/roles.py", "compose/instructions_store.py"], home):
        failures.append("planned-path check fired on paths inside their home or with no slug")
    if not misplaced("plan.json", [], home) or not misplaced(None, [], home):
        failures.append("planned-path check passed a plan assigning nothing, or no plan")
    fake = {"CURRENT.md": "- **Implementation task graph:** [graph](p.json). Current.\n",
            "p.json": json.dumps({"shared_integrator_paths": ["install.sh"],
                                  "nodes": [{"owned_paths": ["workenv/x.py"]}]})}
    if planned_paths(lambda path: fake[path.name]) != ("p.json", ["install.sh", "workenv/x.py"]):
        failures.append("planned-path reader did not return the selected plan's paths")

    # Findings-queue controls, also read-injected.
    if not findings_queue_open_only(lambda _: "### F-1 · RESOLVED 2026-07-31 — closed"):
        failures.append("findings check missed a resolution marker")
    if findings_queue_open_only(lambda _: "### F-10 · rollback is unreachable\n\nAlternatives:"):
        failures.append("findings check fired on an entry that is genuinely open")
    if not findings_queue_open_only(lambda _: (_ for _ in ()).throw(OSError("gone"))):
        failures.append("findings check passed with the queue file missing")

    if failures:
        print("check-lexicon --self-test: FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("check-lexicon --self-test: OK (planted + title-case caught, clean silent, "
          "self-exempt, concept homes held with scatter/vacuity controls, archive "
          "unreferenced with operator/design/vacuity controls, findings queue open-only "
          "with marker/open-entry/missing-file controls, planned paths with outside-home/"
          "inside/vacuity/reader controls, guide reference form with "
          "bare-name/KO/path/concept-exempt/concept-still-referring/vacuity controls)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    sys.exit(gate())
