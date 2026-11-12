#!/usr/bin/env python3
"""One identity contract for an operation's target (WP-21, review round 2, item C).

Four places judged what a target IS and judged it differently. `runlib/drift.py` refused
`./claude/CLAUDE.md` while `runlib/journal.py` accepted it, so one spelling was two answers
depending on which surface was asked. `claude/guides/to-root/CLAUDE.md` passed every lexical rule
there was, and with `to-root` a symlink to `claude/` that path REACHES the always-loaded global file
while being classified as a guide — the global-file judgment, the merge requirement and the ceiling
all belong to the layer the path was classified as, so a symlink moved an operation out from under
all three. And on a case-insensitive filesystem `claude/guides/G.md` and `claude/guides/g.md` are
one file and two identities: two operations, each with its own before-hash, neither seeing the
other's write.

So there is one owner for the question, and `drift`, `journal`, sequencing and application all ask
it here. The contract has three layers, and each says what it cannot establish rather than guessing:

* **lexical** — the spelling. A target is a relative path inside the checkout in canonical form.
  Two spellings of one file are REFUSED, never normalized: the owner approved the text they read,
  and an approval naming `claude/guides//g.md` must not apply to `claude/guides/g.md`.
* **filesystem** — the path as the kernel will walk it, from the DECLARED checkout root, one
  component at a time with `O_NOFOLLOW`. A symlink anywhere in the chain is refused. A component
  that does not exist yet is not a defect (a `create` names a path that should not be there), and
  the walk stops there rather than claiming anything about what follows.
* **identity collision** — two targets of one approved set that name one file. Case is the live
  case: whether two spellings collide depends on the filesystem, so the filesystem is asked, and
  when it cannot be established the collision is refused rather than allowed.

`identity()` answers what the identity IS; the `*_problems` functions answer why a target may not be
applied. The hash chain, the layer map, the journal and the application all key on `identity()`, so
there is one string per file rather than one per spelling.

    targets.py --self-test
"""
import errno
import os
import stat
import pathlib
import posixpath
import unicodedata
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# Whether a root's filesystem folds case, by root. Probed READ-ONLY (see `folds_case`) and cached,
# because the answer cannot change under one run and the probe costs a directory listing.
_FOLDS_CASE = {}


def identity(target):
    """The identity of the file this target names, or None when the target is not a path.

    Canonical, relative, POSIX. `drift.layer_of`, the hash chain, the journal and the application
    all key on this, so one file has one identity however it was spelled — anything less makes two
    spellings of one file into two files, and the chain keyed on the raw string let one file be
    edited twice with neither operation seeing the other's after-hash.
    """
    if not isinstance(target, str) or not target:
        return None
    # NFC, because a name is bytes on disk and a CHARACTER SEQUENCE here. `é` composed and `é`
    # decomposed are the same file on macOS and were two identities: the chain, the journal and the
    # layer map keyed on different strings for one file, and the collision check grouped them apart
    # (the round-4 review). The policy is NFC everywhere identity is taken, and the spelling on disk
    # is compared as the directory entry gives it — see `_spelling_on_disk`.
    return unicodedata.normalize("NFC", posixpath.normpath(target))


CONTROL_CATEGORIES = ("Cc", "Cf", "Zl", "Zp")


def control_characters(text):
    """The control, format and line/paragraph-separator characters in `text`, as `U+XXXX`, sorted."""
    return sorted({f"U+{ord(ch):04X}" for ch in str(text)
                   if unicodedata.category(ch) in CONTROL_CATEGORIES})


def lexical_problems(target):
    """Why this target's SPELLING may not be applied, by name. Empty means it is canonical."""
    if not isinstance(target, str) or not target:
        return [f"TARGET_ABSENT {target!r}: an operation names a path"]
    problems = []
    held_controls = control_characters(target)
    if held_controls:
        # Before any other rule and before any filesystem call: a NUL reached `os.open` and came
        # back as a ValueError rather than a named problem, and a newline in a target is a second
        # line in every record that carries it (the round-6 review). The journal holds its records
        # to this same function.
        return [f"TARGET_CONTROL_CHARACTER {target!r}: it carries {', '.join(held_controls)}, and "
                f"a path is written into records a line at a time"]
    if target.startswith("/") or target.startswith("~"):
        problems.append(f"TARGET_ABSOLUTE {target!r}: a target is a path inside the checkout")
    parts = target.split("/")
    if ".." in parts:
        problems.append(f"TARGET_TRAVERSAL {target!r}: a `..` segment leaves the checkout")
    if "." in parts or "" in parts[1:] or target.endswith("/"):
        problems.append(f"TARGET_SPELLING {target!r}: an empty or `.` component makes two spellings "
                        f"of one file, and the chain, the layer and the journal would key on "
                        f"different ones")
    if target != posixpath.normpath(target):
        problems.append(f"TARGET_UNCANONICAL {target!r}: its canonical form is "
                        f"{posixpath.normpath(target)!r}")
    return problems


def folds_case(root):
    """Whether this root's filesystem treats two cases of one name as one file, or None if unknown.

    Probed WITHOUT WRITING: an existing entry's name is stat'd in a flipped case and compared by
    inode. The checkout is the owner's working tree, and a containment contract that creates a probe
    file in it to decide a question about it has already failed at its own job.

    None means the filesystem did not say — an empty directory, or no entry with a letter in its
    name. Callers refuse a case collision under None rather than allowing it: 'nobody knows whether
    these two names are one file' is not a licence to apply both.
    """
    base = pathlib.Path(root)
    key = str(base)
    if key in _FOLDS_CASE:
        return _FOLDS_CASE[key]
    # Three answers, not two: True folds, False does not, and None means THIS PROBE COULD NOT TELL.
    # An `OSError` from the flipped stat used to be read as False — "case-sensitive" — so a
    # directory the run may list but not stat answered "sensitive" and `CASE_ALIAS` stopped being
    # reported. Only ENOENT answers the question (the flipped name is absent, so names are
    # distinct); every other error is an unanswered probe, and an unanswered probe refuses rather
    # than assumes (the round-3 review).
    answer = None
    try:
        with os.scandir(base) as entries:
            for entry in entries:
                flipped = entry.name.swapcase()
                if flipped == entry.name:          # no letters to flip
                    continue
                try:
                    answer = os.stat(base / flipped, follow_symlinks=False).st_ino == \
                        os.stat(base / entry.name, follow_symlinks=False).st_ino
                except FileNotFoundError:
                    answer = False                 # the flipped name is not there: distinct names
                except OSError:
                    answer = None                  # cannot tell, which is not "sensitive"
                break
    except OSError:
        answer = None
    _FOLDS_CASE[key] = answer
    return answer


def filesystem_problems(target, checkout):
    """Why the path the KERNEL will walk is not the path the target names, by name.

    The walk starts at the declared checkout root and opens one component at a time with
    `O_NOFOLLOW`, so a symlink anywhere in the chain is refused rather than followed. `O_NOFOLLOW`
    on the leaf alone protects nothing: `claude/guides/to-root/CLAUDE.md` has its symlink in the
    middle, and that is the case that reached the global file while being judged a guide.
    """
    held = lexical_problems(target)
    if held:
        return held                      # an unspellable target has no path to walk
    problems = []
    parts = identity(target).split("/")
    try:
        root_fd = os.open(checkout, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        return [f"CHECKOUT_UNOPENABLE {checkout}: {exc.strerror} — the declared checkout root must "
                f"be a real directory that is not itself a symlink, or no target under it can be "
                f"judged"]
    open_fds = [root_fd]
    try:
        for index, part in enumerate(parts):
            last = index == len(parts) - 1
            flags = os.O_RDONLY | os.O_NOFOLLOW | (0 if last else os.O_DIRECTORY)
            try:
                held_fd = os.open(part, flags, dir_fd=open_fds[-1])
            except OSError as exc:
                reached = "/".join(parts[:index + 1])
                # WHAT the component is decides, not which errno the platform chose to report.
                # `O_DIRECTORY|O_NOFOLLOW` over a symlink to a directory raises ELOOP on Linux and
                # ENOTDIR on macOS (measured on darwin 25.5), so a rule written on either errno
                # alone reads a symlink as an ordinary non-directory on the other platform — and
                # this walk is the containment, so it may not depend on that.
                linked = False
                try:
                    linked = stat.S_ISLNK(os.lstat(part, dir_fd=open_fds[-1]).st_mode)
                except OSError:
                    linked = False
                if linked or exc.errno in (errno.ELOOP, errno.EMLINK):
                    problems.append(f"TARGET_SYMLINK {target!r}: {reached} is a symbolic link, so "
                                    f"the path the kernel walks is not the path this target names "
                                    f"and the layer it was classified as is not the layer it "
                                    f"reaches")
                elif exc.errno == errno.ENOENT:
                    # Nothing there yet. A `create` names exactly that, and what lies beyond a
                    # component that does not exist is not a question this walk can answer.
                    pass
                elif exc.errno == errno.ENOTDIR:
                    problems.append(f"TARGET_NOT_A_DIRECTORY {target!r}: {reached} is not a "
                                    f"directory, so the components after it name nothing")
                else:
                    problems.append(f"TARGET_UNWALKABLE {target!r}: {reached} could not be opened "
                                    f"({exc.strerror}), so containment cannot be established")
                break
            open_fds.append(held_fd)
            if last:
                # A second NAME for the leaf's bytes is a second path to them, and no walk over this
                # name can see where the other one lies: a file outside the checkout hard-linked to
                # an approved name inside it is written and truncated through that name (the round-5
                # review). The descriptor is asked, not the path, so the answer is about the file
                # the walk reached.
                held_stat = os.fstat(held_fd)
                if stat.S_ISREG(held_stat.st_mode) and held_stat.st_nlink != 1:
                    problems.append(f"TARGET_HARD_LINKED {target!r}: the file has "
                                    f"{held_stat.st_nlink} names, so writing it through this one "
                                    f"changes a file this walk cannot place inside the checkout")
            # EVERY component that exists, each through its own parent descriptor. Comparing only
            # the last one let `CLAUDE/CLAUDE.md` pass on a case-folding filesystem: the directory
            # opened happily under a spelling nobody approved, and the leaf matched (the round-3
            # review). The spelling of a directory is as much a name as the file's.
            problems += _spelling_on_disk(parts[:index + 1], open_fds[-2], target)
    finally:
        for held_fd in open_fds:
            try:
                os.close(held_fd)
            except OSError:
                pass
    return problems


def _spelling_on_disk(parts, parent_fd, target):
    """Whether the entry's own spelling is the one the target used.

    On a case-folding filesystem `os.open` of `G.md` happily opens `g.md`, so the walk succeeding
    says nothing about which name the owner approved. The approved spelling must be the spelling on
    disk: otherwise the journal, the chain and the file itself carry two different names for one
    thing.
    """
    name = parts[-1]
    try:
        held = os.listdir(parent_fd)
    except OSError as exc:
        # An unreadable parent is not an approved spelling. It used to return `[]`, which reads as
        # "the name on disk is the name the owner approved" from a directory nobody could list.
        return [f"TARGET_SPELLING_UNREADABLE {target!r}: {'/'.join(parts)}'s parent could not be "
                f"listed ({exc.strerror}), so whether the name on disk is the approved one cannot "
                f"be established"]
    if name in held:
        return []
    # Canonical equivalence is ONE NAME, not a different one: `é` composed and `é` decomposed are
    # the same characters and the same file, which is why `identity` normalises to NFC. An entry
    # that is canonically equal to the approved name is therefore the approved name, and `in` is
    # the only test that could not see it (the round-4 review). A CASE difference is a different
    # name and stays reported below.
    if any(unicodedata.normalize("NFC", entry) == unicodedata.normalize("NFC", name)
           for entry in held):
        return []
    folded = [entry for entry in held if entry.casefold() == name.casefold()
              or unicodedata.normalize("NFC", entry).casefold()
              == unicodedata.normalize("NFC", name).casefold()]
    if folded:
        return [f"TARGET_CASE_ON_DISK {target!r}: the file is spelled {folded[0]!r} on disk, and an "
                f"operation that names it otherwise writes under a name the owner did not approve"]
    # No entry matches, which is the ordinary case for a `create`: the walk runs over the components
    # that EXIST, and a leaf that does not exist yet has no entry to be spelled differently from. A
    # refusal here would refuse every creation.
    return []


def collision_problems(targets, checkout=None):
    """Two targets of one set that name ONE file, by name.

    Identity collisions are refused for the set, not for one target: whether two spellings are one
    file is a property of the pair. An exact repeat is one file by any rule; a case difference is
    one file only where the filesystem folds case, so the filesystem is asked — and when it will
    not say, the pair is refused rather than applied, because the cost of being wrong is two
    operations writing one file with neither seeing the other's hash.
    """
    held = [identity(target) for target in targets or () if identity(target)]
    problems = []
    # A REPEATED identity is not a collision. §10.5 sequences a chain through one file — `a` creates
    # it, `b` deletes it, `c` routes to it — and each operation carries the before-state hash of
    # what the previous one left, which is exactly how the chain governs the repeat. Refusing it
    # rejected valid approved sets (the round-3 review: z-first a->b, a-second b->c). What IS a
    # collision is two DISTINCT SPELLINGS that name one file, because then neither operation's
    # before-hash describes the state the other overwrote, and nothing orders them.
    folds = folds_case(checkout) if checkout else None
    groups = {}
    for one in held:
        groups.setdefault(one.casefold(), set()).add(one)
    for folded, spellings in sorted(groups.items()):
        if len(spellings) < 2:
            continue
        if folds is True:
            problems.append(f"TARGET_CASE_ALIAS {', '.join(sorted(spellings))}: this filesystem "
                            f"folds case, so these are one file under two identities and each "
                            f"operation's before-hash describes a state the other overwrote")
        elif folds is None:
            problems.append(f"TARGET_CASE_UNDECIDED {', '.join(sorted(spellings))}: whether this "
                            f"filesystem folds case could not be established, so whether these are "
                            f"one file or two is unknown and the set is refused rather than applied")
    return problems


def problems(target, checkout=None):
    """Every reason this target may not be applied: the spelling, and the path the kernel walks.

    With no checkout the answer is the spelling alone, and the caller is told so rather than being
    left to read silence as containment.
    """
    if checkout is None:
        return lexical_problems(target)
    return filesystem_problems(target, checkout)


def set_problems(targets, checkout=None):
    """Every target of a set judged, plus the collisions between them."""
    held = []
    for target in targets or ():
        held += problems(target, checkout)
    return held + collision_problems(targets, checkout)


SPELLING_TESTS = (
    ('".." in', "a traversal test"),
    ('startswith("/")', "an absolute-path test"),
    ("startswith('/')", "an absolute-path test"),
    ('startswith("~")', "a home-prefix test"),
    ("posixpath.normpath(", "a canonicalisation"),
    ("os.path.normpath(", "a canonicalisation"),
)
SPELLING_SUBJECTS = ("target", "carrier")
# Keyed to the CODE, not to a line number, so it lapses when that code changes rather than when the
# file moves. Each entry says why its subject is not an approved target's spelling.
SPELLING_EXEMPT = {
    ("inventory.py", "target = pathlib.Path(os.path.normpath(str(base / label)))"):
        "S2's copy-label containment (`inventory.confined`): the subject is a label out of the "
        "owner's state being joined to a fixture base, and the question is whether the result stays "
        "under that base — containment, not whether an approved target is spelled canonically. The "
        "line itself is the second layer behind a string test and is unguarded-accepted "
        "(ruled 2026-10-24).",
}


def second_validator_problems(root=None):
    """Any module of `runlib` other than this one that tests a TARGET's spelling itself.

    The contract has one owner, and the way that stops being true is quiet: `placement` had its own
    carrier rules and accepted `./claude/CLAUDE.md` and `claude//CLAUDE.md` while this module
    refused them, so one spelling was approved in the review and refused at the apply (the round-3
    review). Decidable by source: a spelling TEST applied to a value named like a target or a
    carrier, in any runlib module but this one.

    Containment is NOT this contract — `destinations._inside` asks whether a path lies under a root,
    which is a different question about a value that is already a valid path — so the scan is scoped
    to the subject names, not to the predicates alone.
    """
    base = pathlib.Path(root or pathlib.Path(__file__).resolve().parent)
    problems, scanned = [], 0
    for held in sorted(base.glob("*.py")):
        if held.name == pathlib.Path(__file__).name:
            continue
        scanned += 1
        for number, line in enumerate(held.read_text(encoding="utf-8",
                                                     errors="replace").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("#", '"', "'")):
                continue
            lowered = line.lower()
            if not any(subject in lowered for subject in SPELLING_SUBJECTS):
                continue
            if (held.name, stripped) in SPELLING_EXEMPT:
                continue
            for mark, why in SPELLING_TESTS:
                if mark in line:
                    problems.append(f"SECOND_TARGET_VALIDATOR {held.name}:{number}: {why} on a "
                                    f"target or carrier ({stripped[:70]!r}) — the spelling contract "
                                    f"has one owner, and a second one disagrees with it in some "
                                    f"case nobody has found yet")
                    break
    if not scanned:
        problems.append("SECOND_TARGET_VALIDATOR_NO_MODULES: no runlib module was read, so the "
                        "scan would pass over an empty set")
    # The exemptions are declared about THIS runlib's files, so their staleness is asked only when
    # that is what is being scanned; a control scanning its own planted tree is not evidence that
    # the licence here has lapsed.
    own = base == pathlib.Path(__file__).resolve().parent
    for (name, code), reason in sorted(SPELLING_EXEMPT.items()) if own else ():
        held_file = base / name
        if not held_file.is_file() or code not in held_file.read_text(encoding="utf-8",
                                                                      errors="replace"):
            problems.append(f"SECOND_TARGET_VALIDATOR_EXEMPTION_STALE {name}: the exemption names "
                            f"code this file no longer carries ({code[:50]!r}), so it excuses "
                            f"nothing and the reason it carried is no longer about anything")
    return problems


def _with_exemption(key, reason, call):
    """Run `call` with one more entry in SPELLING_EXEMPT, restoring it however the call ends."""
    held = dict(SPELLING_EXEMPT)
    try:
        SPELLING_EXEMPT[key] = reason
        return call()
    finally:
        SPELLING_EXEMPT.clear()
        SPELLING_EXEMPT.update(held)


def self_test():
    """One identity contract, each rule with a planted violation and its clean counterpart.

    The body is wrapped so a control that DIES still speaks: a traceback is not a control firing,
    and a revert trial that reads any output counts one as if it were.
    """
    failures, ran = [], []
    try:
        return _self_test_body(failures, ran)
    except BaseException as exc:  # noqa: BLE001 - the suite must speak before it dies
        held = ran[-1] if ran else "<no control ran>"
        print(f"targets --self-test [FAIL] the suite died after {held!r}: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        for name, detail in failures:
            print(f"targets --self-test [FAIL] {name}: {detail}", file=sys.stderr)
        print(f"targets --self-test: INCOMPLETE ({len(ran)} controls ran, {len(failures)} failed "
              f"before the suite died)", file=sys.stderr)
        raise


def _self_test_body(failures, ran):
    # Imported here, before anything uses them: a later import inside this function makes the name
    # a local for the WHOLE function. The module itself touches no filesystem of its own.
    import json
    import shutil
    import tempfile

    import shutil
    import tempfile

    def control(name, got, want):
        ran.append(name)
        if want not in str(got):
            failures.append((name, f"expected {want!r} in {str(got)[:400]!r}"))

    def clean(name, held):
        ran.append(name)
        if held:
            failures.append((name, f"expected nothing, got {held}"))

    def guarded(call):
        try:
            return call()
        except BaseException as exc:  # noqa: BLE001 - the exception is the answer here
            return f"RAISED {type(exc).__name__}: {exc}"

    for label, spelled in (("a newline", "claude/guides/g.md\nowner approved"),
                           ("a NUL", "claude/guides/g\x00.md"),
                           ("a zero-width joiner", "claude/guides/g\u200d.md")):
        control(f"{label} in a target is one named problem, before any other rule",
                [p.split()[0] for p in lexical_problems(spelled)], "['TARGET_CONTROL_CHARACTER']")
    control("and a NUL never reaches the filesystem walk as an exception",
            [p.split()[0] for p in guarded(lambda: filesystem_problems("claude/g\x00.md", "/tmp")) or ["<none>"]]
            if isinstance(guarded(lambda: filesystem_problems("claude/g\x00.md", "/tmp")), list)
            else guarded(lambda: filesystem_problems("claude/g\x00.md", "/tmp")),
            "['TARGET_CONTROL_CHARACTER']")
    # ---- the identity ----------------------------------------------------------------------------
    control("one file has one identity however it was spelled",
            identity("claude/guides//g.md"), "claude/guides/g.md")
    control("and a leading `./` is the same file", identity("./claude/CLAUDE.md"),
            "claude/CLAUDE.md")
    control("a target that is not a path has no identity", str(identity(None)), "None")

    # ---- the spelling ----------------------------------------------------------------------------
    clean("a canonical relative path is spelled correctly",
          lexical_problems("claude/guides/g.md"))
    for bad, want in (("/etc/passwd", "TARGET_ABSOLUTE"), ("~/x", "TARGET_ABSOLUTE"),
                      ("a/../../x", "TARGET_TRAVERSAL"), ("a/./x", "TARGET_SPELLING"),
                      ("claude/guides//g.md", "TARGET_SPELLING"),
                      ("claude/guides/", "TARGET_SPELLING"), ("", "TARGET_ABSENT"),
                      (None, "TARGET_ABSENT")):
        control(f"a target spelled {bad!r} is refused by name",
                "; ".join(lexical_problems(bad)), want)
    # The two surfaces disagreed on exactly this one: drift refused it and the journal took it.
    control("`./claude/CLAUDE.md` is refused, and by the ONE contract both surfaces ask",
            "; ".join(lexical_problems("./claude/CLAUDE.md")), "TARGET_SPELLING")

    root = pathlib.Path(tempfile.mkdtemp(prefix="targets-", dir="/tmp"))
    try:
        # ---- the path the kernel walks -----------------------------------------------------------
        (root / "claude" / "guides").mkdir(parents=True)
        (root / "claude" / "CLAUDE.md").write_text("global\n", encoding="utf-8")
        (root / "claude" / "guides" / "g.md").write_text("guide\n", encoding="utf-8")
        clean("a real path inside the checkout walks clean",
              filesystem_problems("claude/guides/g.md", root))
        clean("and so does a path that does not exist yet, which is what a `create` names",
              filesystem_problems("claude/guides/new.md", root))
        # The review's case: a symlinked DIRECTORY in the middle, reaching the global file while the
        # path says guides.
        os.symlink(root / "claude", root / "claude" / "guides" / "to-root")
        held_link = filesystem_problems("claude/guides/to-root/CLAUDE.md", root)
        control("a symlinked component in the MIDDLE is refused, which `O_NOFOLLOW` on the leaf "
                "alone does not catch", "; ".join(held_link), "TARGET_SYMLINK")
        control("and the refusal names the component that is the link",
                "; ".join(held_link), "claude/guides/to-root is a symbolic link")
        control("and says what it costs: the layer it reaches is not the layer it was classified as",
                "; ".join(held_link), "not the layer it")
        os.symlink(root / "claude" / "CLAUDE.md", root / "claude" / "guides" / "leaf.md")
        control("a symlinked LEAF is refused too",
                "; ".join(filesystem_problems("claude/guides/leaf.md", root)), "TARGET_SYMLINK")
        control("a component that is a file where a directory was named is refused by its own name",
                "; ".join(filesystem_problems("claude/CLAUDE.md/x.md", root)),
                "TARGET_NOT_A_DIRECTORY")
        control("a checkout root that is itself a symlink is refused, since nothing under it can "
                "be judged",
                "; ".join(filesystem_problems("claude/guides/g.md",
                                              guarded(lambda: _linked_root(root)))),
                "CHECKOUT_UNOPENABLE")
        control("and an unspellable target is refused before any walk",
                "; ".join(filesystem_problems("../x", root)), "TARGET_TRAVERSAL")

        # ---- case -------------------------------------------------------------------------------
        folds = folds_case(root)
        control("the filesystem's case behaviour is established by reading, never by writing a "
                "probe into the checkout",
                "answered" if folds in (True, False) else f"unknown ({folds})", "answered")
        clean("two files that differ by more than case are two files",
              collision_problems(["claude/guides/g.md", "claude/guides/h.md"], root))
        # A repeat is a CHAIN, not a collision: §10.5 sequences several operations through one file
        # and each carries the before-state hash of what the previous one left. Refusing it rejected
        # valid approved sets, so the set is clean and the hash chain governs the order.
        clean("two spellings of ONE identity in a set are a chain, not a collision: the hash chain "
              "is what orders them",
              collision_problems(["claude/guides/g.md", "claude/guides//g.md"], root))
        control("while two DISTINCT spellings of one file stay a collision, because then neither "
                "operation's before-hash describes what the other overwrote",
                "; ".join(collision_problems(["claude/guides/G.md", "claude/guides/g.md"], root))
                or "no collision reported",
                "TARGET_CASE" if folds_case(root) is not False else "no collision reported")
        held_case = collision_problems(["claude/guides/G.md", "claude/guides/g.md"], root)
        if folds:
            control("on a case-folding filesystem two cases of one name are refused as one file",
                    "; ".join(held_case), "TARGET_CASE_ALIAS")
        else:
            clean("on a case-sensitive filesystem they are genuinely two files", held_case)
        # Whatever this machine does, both answers are exercised: the probe's answer is forced.
        _FOLDS_CASE[str(root)] = True
        control("with the filesystem folding case, the pair is refused",
                "; ".join(collision_problems(["claude/guides/G.md", "claude/guides/g.md"], root)),
                "TARGET_CASE_ALIAS")
        _FOLDS_CASE[str(root)] = False
        clean("with it case-sensitive, the same pair is two files",
              collision_problems(["claude/guides/G.md", "claude/guides/g.md"], root))
        _FOLDS_CASE[str(root)] = None
        control("and when it will not say, the pair is REFUSED rather than applied: unknown is not "
                "a licence",
                "; ".join(collision_problems(["claude/guides/G.md", "claude/guides/g.md"], root)),
                "TARGET_CASE_UNDECIDED")
        del _FOLDS_CASE[str(root)]
        # The PROBE itself, over trees this control builds. Its three answers are not two: an
        # OSError from the flipped stat used to read as "case-sensitive", so a directory the run may
        # list and not stat answered the question with a guess, and CASE_ALIAS stopped being
        # reported for every pair under it.
        probe_root = pathlib.Path(tempfile.mkdtemp(prefix="targets-probe-", dir="/tmp"))
        try:
            (probe_root / "letters").mkdir()
            (probe_root / "letters" / "Aa.md").write_text("x", encoding="utf-8")
            _FOLDS_CASE.pop(str(probe_root / "letters"), None)
            held_answer = folds_case(probe_root / "letters")
            control("the probe answers from the filesystem it is given, True or False, never from "
                    "a guess", json.dumps(held_answer in (True, False)), "true")
            _FOLDS_CASE.pop(str(probe_root / "letters"), None)
            unreadable = probe_root / "closed"
            unreadable.mkdir()
            (unreadable / "Bb.md").write_text("x", encoding="utf-8")
            held_listing = os.listdir(unreadable)
            control("and the directory this control closed is readable before it is closed, so the "
                    "next answer is about the closing and not about an empty directory",
                    json.dumps(held_listing), '["Bb.md"]')
            os.chmod(unreadable, 0o000)
            try:
                _FOLDS_CASE.pop(str(unreadable), None)
                control("a probe that cannot read the directory answers None — cannot tell — and "
                        "not False, which would have meant case-sensitive",
                        json.dumps(folds_case(unreadable)), "null")
                _FOLDS_CASE.pop(str(unreadable), None)
                control("and a set judged against that checkout is REFUSED by name rather than "
                        "applied",
                        "; ".join(collision_problems(["claude/guides/G.md", "claude/guides/g.md"],
                                                     unreadable)),
                        "TARGET_CASE_UNDECIDED")
            finally:
                os.chmod(unreadable, 0o700)
                _FOLDS_CASE.pop(str(unreadable), None)
            # Only ENOENT answers "distinct names": the flipped name is absent, so the two names are
            # not one file. Asked of the probe over a tree with exactly one entry.
            (probe_root / "single").mkdir()
            (probe_root / "single" / "Zz.md").write_text("x", encoding="utf-8")
            _FOLDS_CASE.pop(str(probe_root / "single"), None)
            control("an absent flipped name is the one error that answers the question",
                    json.dumps(folds_case(probe_root / "single") in (True, False)), "true")
            # EVERY existing component's spelling, not the leaf's alone: a directory opened under a
            # spelling nobody approved is as wrong as a file, and on this machine the open succeeds.
            (probe_root / "CLAUDE" / "guides").mkdir(parents=True)
            (probe_root / "CLAUDE" / "guides" / "g.md").write_text("x", encoding="utf-8")
            control("a target whose DIRECTORY is spelled otherwise on disk is refused, which "
                    "comparing the leaf alone could not see",
                    "; ".join(filesystem_problems("claude/guides/g.md", str(probe_root))),
                    "TARGET_CASE_ON_DISK")
            control("and the refusal names the spelling the disk carries",
                    "; ".join(filesystem_problems("claude/guides/g.md", str(probe_root))),
                    "spelled 'CLAUDE' on disk")
            clean("while the spelling the disk carries passes",
                  filesystem_problems("CLAUDE/guides/g.md", str(probe_root)))
            # ---- the Unicode identity policy ----------------------------------------------
            #
            # `é` composed (U+00E9) and `é` decomposed (U+0065 U+0301) are the same file on macOS
            # and were two identities: the chain, the journal and the layer map keyed on different
            # strings for one file, and the collision check grouped them apart (the round-4 review).
            composed = unicodedata.normalize("NFC", "guides/\u00e9.md")
            decomposed = unicodedata.normalize("NFD", "guides/\u00e9.md")
            control("the two spellings really are different strings, so this control is not "
                    "comparing a value with itself",
                    json.dumps(composed != decomposed), "true")
            control("and they resolve to ONE identity, so the chain and the journal key on one file",
                    json.dumps(identity(composed) == identity(decomposed)), "true")
            clean("so an approved set naming both is a chain over one file, which §10.5 sequences, "
                  "and not two files the collision rule must separate",
                  collision_problems([composed, decomposed]))
            # And the spelling on disk is the entry's own: a decomposed entry does not make a
            # composed operation approved.
            (probe_root / "nfd").mkdir()
            (probe_root / "nfd" / unicodedata.normalize("NFD", "\u00e9.md")).write_text(
                "x", encoding="utf-8")
            held_entries = os.listdir(probe_root / "nfd")
            control("the fixture really carries the decomposed entry, so what follows is not a "
                    "filesystem that normalised it away",
                    json.dumps([unicodedata.normalize("NFD", name) == name
                                for name in held_entries]), "[true]")
            clean("a composed operation over a decomposed entry is the SAME name — canonical "
                  "equivalence is one name, which is why identity normalises — and `in` was the "
                  "only test that could not see it",
                  filesystem_problems(f"nfd/{unicodedata.normalize('NFC', chr(0xe9))}.md",
                                      str(probe_root)))
            clean("and so is the entry's own spelling",
                  filesystem_problems(f"nfd/{unicodedata.normalize('NFD', chr(0xe9))}.md",
                                      str(probe_root)))
            # A CASE difference is a different name, canonical equivalence or not: the policy
            # separates the two questions rather than folding one into the other.
            (probe_root / "nfd" / unicodedata.normalize("NFD", "\u00c9x.md")).write_text(
                "x", encoding="utf-8")
            control("while a case difference over canonically equal characters is still refused, so "
                    "normalising did not swallow the case rule",
                    "; ".join(filesystem_problems(
                        f"nfd/{unicodedata.normalize('NFC', chr(0xe9))}x.md", str(probe_root))),
                    "TARGET_CASE_ON_DISK")

            # An unreadable parent is not an approved spelling. The realistic cause is a
            # permission, and macOS checks that at OPEN: a descriptor taken while the directory was
            # readable keeps listing after the mode drops, so the branch is reached here through the
            # other error that gets to it — a descriptor that is not a directory at all. What is
            # being held is that the function REPORTS instead of returning "the spelling is fine"
            # from a listing it never read.
            held_file_fd = os.open(probe_root / "CLAUDE" / "guides" / "g.md", os.O_RDONLY)
            try:
                control("a parent that cannot be listed is reported rather than read as approval",
                        "; ".join(_spelling_on_disk(["CLAUDE", "guides", "g.md"], held_file_fd,
                                                    "CLAUDE/guides/g.md")),
                        "TARGET_SPELLING_UNREADABLE")
                control("and the refusal says the question could not be answered, not that the "
                        "name matched",
                        "; ".join(_spelling_on_disk(["CLAUDE", "guides", "g.md"], held_file_fd,
                                                    "CLAUDE/guides/g.md")),
                        "cannot be established")
            finally:
                os.close(held_file_fd)
        finally:
            shutil.rmtree(probe_root, ignore_errors=True)
        # The on-disk spelling, which a case-folding filesystem would otherwise hide.
        held_spelling = _spelling_on_disk(["claude", "guides", "G.md"],
                                          os.open(root / "claude" / "guides", os.O_RDONLY),
                                          "claude/guides/G.md")
        control("a file spelled one way on disk and another in the approval is refused by name",
                "; ".join(held_spelling), "TARGET_CASE_ON_DISK")
        control("and the refusal carries the spelling that is really there",
                "; ".join(held_spelling), "'g.md'")

        # ---- ONE owner for the spelling, held by source ------------------------------------------
        #
        # The contract stops having one owner quietly: `placement` carried its own carrier rules and
        # accepted `./claude/CLAUDE.md` and `claude//CLAUDE.md` while this module refused them, so a
        # spelling was approved in the review and refused at the apply. The lead asked for this
        # control by source, with its negative.
        clean("no runlib module but this one tests a target's or a carrier's spelling itself",
              second_validator_problems())
        planted_root = pathlib.Path(tempfile.mkdtemp(prefix="targets-second-", dir="/tmp"))
        try:
            for held_name in ("alpha.py", "beta.py"):
                (planted_root / held_name).write_text("x = 1\n", encoding="utf-8")
            clean("and the scan is clean over a tree that has none",
                  second_validator_problems(planted_root))
            (planted_root / "beta.py").write_text(
                'def check(target):\n    return target.startswith("/")\n', encoding="utf-8")
            control("a second absolute-path test on a target is reported, with the file and the "
                    "line", "; ".join(second_validator_problems(planted_root)),
                    "SECOND_TARGET_VALIDATOR beta.py:2")
            (planted_root / "beta.py").write_text(
                'def check(carrier):\n    return ".." in carrier.split("/")\n', encoding="utf-8")
            control("and so is a traversal test on a carrier",
                    "; ".join(second_validator_problems(planted_root)),
                    "SECOND_TARGET_VALIDATOR beta.py:2")
            (planted_root / "beta.py").write_text(
                'def check(root, path):\n    return path.startswith("/") and root\n',
                encoding="utf-8")
            clean("while the same test on a value that is not a target or a carrier is not this "
                  "contract's: containment asks a different question about a path that is already "
                  "valid", second_validator_problems(planted_root))
            control("a scan that reads no module at all says so rather than passing",
                    "; ".join(second_validator_problems(
                        pathlib.Path(tempfile.mkdtemp(prefix="targets-empty-", dir="/tmp")))),
                    "SECOND_TARGET_VALIDATOR_NO_MODULES")
        finally:
            shutil.rmtree(planted_root, ignore_errors=True)
        control("an exemption that names code its file no longer carries is reported, so the one "
                "licence here cannot outlive its reason",
                "; ".join(_with_exemption(("inventory.py", "code nobody wrote"), "planted",
                                         second_validator_problems)),
                "SECOND_TARGET_VALIDATOR_EXEMPTION_STALE inventory.py")

        # ---- the set ----------------------------------------------------------------------------
        held_set = set_problems(["claude/guides/g.md", "claude/guides/to-root/CLAUDE.md",
                                 "claude/guides/g.md"], root)
        control("a set is judged target by target", "; ".join(held_set), "TARGET_SYMLINK")
        # A hard link: no symlink anywhere, the walk succeeds, and the bytes are a file outside.
        outside_file = pathlib.Path(tempfile.mkdtemp(dir=root.parent)) / "outside.md"
        outside_file.write_text("outside\n", encoding="utf-8")
        os.link(outside_file, root / "claude" / "guides" / "twin.md")
        held_twin = filesystem_problems("claude/guides/twin.md", root)
        control("a leaf with a second name is refused by name: the other name may lie outside the "
                "checkout, and writing through this one writes that file",
                [p.split()[0] for p in held_twin], "['TARGET_HARD_LINKED']")
        single = root / "claude" / "guides" / "single.md"
        single.write_text("one name\n", encoding="utf-8")
        clean("and a file with one name passes the same walk",
              filesystem_problems("claude/guides/single.md", root))
        clean("and a target it names twice is not reported as a collision",
              [p for p in held_set if "TARGET_REPEATED" in p])
        clean("with no checkout the answer is the spelling alone, and a real path passes it",
              problems("claude/guides/g.md"))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print(f"targets --self-test: {'FAILED' if failures else 'OK'} ({len(ran)} controls: one "
          f"identity per file, the spelling rules both surfaces now share, the component walk that "
          f"refuses a symlink anywhere in the chain, the on-disk spelling, and a case collision "
          f"refused where the filesystem folds case and where it will not say)")
    for name, detail in failures:
        print(f"targets --self-test [FAIL] {name}: {detail}")
    return 1 if failures else 0


def _linked_root(root):
    """A symlink pointing at `root`, for the control that refuses a linked checkout root."""
    held = pathlib.Path(str(root) + "-link")
    if not held.exists():
        os.symlink(root, held)
    return held


def main(argv):
    if "--self-test" in argv:
        return self_test()
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
