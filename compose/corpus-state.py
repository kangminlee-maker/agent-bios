#!/usr/bin/env python3
"""Corpus-version state: project status for the launcher, list, and rollback.

Corpus versions are CONTENT versions of the instruction corpus (globals,
guides, hooks), distinct from deployment/system versions. Git is the content
store: design/session-distill/versions.json maps each closed mining window
to the repo commit whose corpus reflects it. Rollback materializes that
commit, runs the commit's OWN assembler against the live domain selection,
and deploys the corpus files plus the two assembled surfaces the agent
actually reads — the Claude bundle and the Codex central region; the system
(launcher, wrappers, scripts) stays at its current deployment.

Subcommands:
  project   write ~/.local/share/agent-bios/corpus-status.json from the
            repo ledger + versions registry (called by agent-bios install)
  list      print registered corpus versions
  rollback  --version V [--dry-run]: deploy the corpus as of that version
"""
import argparse
import datetime
import io
import json
import contextlib
import fcntl
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid

# compose/ travels as one directory — checkout and npm package alike — so the sibling
# assembler is present wherever this script is, and it owns the payload's one
# temp-write + os.replace primitive. Imported rather than copied: a second copy is a
# second thing that can disagree, and gates/ code is not importable from shipped code.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from assemble import MARK_END, MARK_START, merge_codex, replace_atomically  # noqa: E402

STATE_DIR = pathlib.Path.home() / ".local/share/agent-bios"
STATUS = pathlib.Path(
    os.environ.get("AGENT_BIOS_CORPUS_STATUS", str(STATE_DIR / "corpus-status.json"))
)
CLAUDE_DIR = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR", str(pathlib.Path.home() / ".claude")))
CODEX_DIR = pathlib.Path(os.environ.get("CODEX_HOME", str(pathlib.Path.home() / ".codex")))

# Managed corpus paths (repo-relative) and their deploy roots. The ko/
# tree is repo-only reference; wrappers and agent templates are system, not
# corpus content.
#
# The entry files are deliberately absent. `claude/CLAUDE.md` is seeded once and is the
# USER'S thereafter, and `codex/AGENTS.md` is ours only between the central markers — so a
# whole-file write of either is not a rollback, it is overwriting somebody's file. They used
# to be here, from the era when full mode wrote the corpus into the entry and the entry was
# therefore ours. compose/assemble.py owns both surfaces now — which is why rollback runs
# the target commit's assembler (`_assemble_at`) instead of touching them from here: the
# Claude entry stays the user's, and the Codex region moves only between the markers.
#
# Guides and hooks deploy under `central/`, which is where the assembler writes and where the
# corpus is read from. The pre-unification paths (`<claude>/guides`, `<claude>/hooks`) are
# swept by the installer but never read, so writing there rolls nothing back.
CORPUS = [
    ("claude/guides/", lambda p: CLAUDE_DIR / "central" / "guides" / pathlib.Path(p).name),
    ("claude/hooks/", lambda p: CLAUDE_DIR / "central" / "hooks" / pathlib.Path(p).name),
    ("codex/guides/", lambda p: CODEX_DIR / "guides" / pathlib.Path(p).name),
]


def repo_root(explicit: str | None) -> pathlib.Path:
    if explicit:
        return pathlib.Path(explicit).resolve()
    return pathlib.Path(__file__).resolve().parents[1]


def git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def deploy_target(rel: str) -> pathlib.Path | None:
    for prefix, to in CORPUS:
        if rel == prefix or (prefix.endswith("/") and rel.startswith(prefix)):
            return to(rel)
    return None


def corpus_files(repo: pathlib.Path, ref: str) -> list[str]:
    paths = [p.rstrip("/") for p, _ in CORPUS]
    out = git(repo, "ls-tree", "-r", "--name-only", ref, "--", *paths)
    return [line for line in out.splitlines() if line]


# The mining registries are author-side and deliberately outside `package.json` files[]:
# they carry curation history, and an npm rollback would still lack the git history it
# needs. So a packaged install has the DOMAIN half of this projection and not the VERSION
# half, and the two must not fail together. `None` means "this install cannot know", which
# is not `[]`/`{}` ("known, and empty") — the same distinction `domains_projection` already
# draws for `applied`. Consumers must render None as unavailable rather than as zero;
# `_corpus_summary_lines` in the launcher keys on `versions is None` for exactly that.
def load_versions(repo: pathlib.Path) -> dict | None:
    path = repo / "design/session-distill/versions.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def require_versions(repo: pathlib.Path, command: str) -> list | None:
    """For the commands that are ABOUT versions. They cannot degrade — a rollback with no
    version registry and no git history has nothing to roll back to — so they refuse by
    name instead of dying on a FileNotFoundError the caller has to decode."""
    doc = load_versions(repo)
    if doc is None:
        print(f"corpus-state {command}: the corpus version registry is not part of a "
              f"packaged install, and a rollback needs the repository history as well — "
              f"run this from a checkout", file=sys.stderr)
        return None
    return doc["versions"]


def ledger_summary(repo: pathlib.Path) -> dict | None:
    path = repo / "design/session-distill/ledger.json"
    if not path.is_file():
        return None
    ledger = json.loads(path.read_text())
    entries = ledger["entries"]
    by_status: dict[str, int] = {}
    by_layer: dict[str, int] = {}
    for e in entries:
        by_status[e["status"]] = by_status.get(e["status"], 0) + 1
        if e["status"] == "placed":
            layer = (e.get("classification") or {}).get("layer") or "?"
            by_layer[layer] = by_layer.get(layer, 0) + 1
    return {"entries": len(entries), "by_status": by_status, "placed_by_layer": by_layer}


def domains_projection(repo: pathlib.Path) -> dict:
    """Available domains from the manifest, applied selection from the state dir.

    The launcher's corpus checklist reads BOTH from here rather than from repo
    paths it cannot know: the installer owns this file, and every install run
    rewrites the projection, so a stale list is impossible without a stale
    install. `applied` is null (never []) when no selection was ever assembled —
    "nothing chosen yet" and "core+infra only" must not read the same."""
    available = sorted(
        json.loads((repo / "compose" / "domains.json").read_text())["domains"]
    )
    applied = None
    selection = STATE_DIR / "selection.json"
    if selection.is_file():
        try:
            applied = sorted(json.loads(selection.read_text())["domains"])
        except (ValueError, KeyError):
            applied = None
    return {"available": available, "applied": applied}


def cmd_project(args: argparse.Namespace) -> int:
    repo = repo_root(args.repo)
    versions_doc = load_versions(repo)
    versions = versions_doc["versions"] if versions_doc is not None else None
    current = STATUS_current_override = None
    last_apply = None
    deployed_corpus = None
    # Read and write under one lock: unlocked, a concurrent record-apply or
    # rollback landing between this read and the write below is reverted whole.
    with _status_lock():
        if STATUS.is_file():
            try:
                prior = json.load(STATUS.open())
                STATUS_current_override = prior.get("rolled_back_to")
                # The apply outcome is recorded by `record-apply` at the end of an
                # onboard run; a reprojection must carry it, not erase it.
                last_apply = prior.get("last_apply")
                # What rollback last deployed; the next rollback's removal operand.
                deployed_corpus = prior.get("deployed_corpus")
            except ValueError as exc:
                # Quarantined, never discarded: an unreadable status is where the
                # rollback/apply record LIVES, and a projection that shrugs over it
                # replaces "the corpus is at v1" with "the corpus is at latest"
                # without a word. The bytes move aside so a person can still read
                # what the record held, and the loss is reported, not silent.
                quarantine = STATUS.with_name(
                    STATUS.name
                    + f".corrupt-{datetime.datetime.now():%Y%m%d-%H%M%S}"
                )
                os.replace(STATUS, quarantine)
                print(
                    f"corpus status at {STATUS} was unreadable ({exc}); the damaged "
                    f"file is quarantined at {quarantine}, and any rollback/apply "
                    "state it held could not be carried into this projection",
                    file=sys.stderr,
                )
        latest = versions[-1]["version"] if versions else None
        current = STATUS_current_override or latest
        status = {
            "repo": str(repo),
            "current_version": current,
            "latest_version": latest,
            "rolled_back_to": STATUS_current_override,
            "versions": versions,
            "summary": ledger_summary(repo),
            "domains": domains_projection(repo),
            "last_apply": last_apply,
            "deployed_corpus": deployed_corpus,
            "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        _write_status(status)
    print(f"corpus-status written: {STATUS} (current={current}, latest={latest})")
    return 0


# What a rollback target must carry to be deployable. The live corpus is `central/bundle.md`,
# assembled from these two, so a commit without them cannot produce one — the guides would move
# and the bundle, which is what the agent reads, would stay. Asked in one place because `list`
# has to advertise exactly what `rollback` will accept.
ASSEMBLY_PARTS = ("compose/assemble.py", "compose/domains.json")


def deployable(repo: pathlib.Path, commit: str) -> str | None:
    """None if the commit can be rolled back to, else the part that makes it impossible."""
    for part in ASSEMBLY_PARTS:
        if subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{commit}:{part}"],
                          capture_output=True).returncode != 0:
            return part
    return None


def cmd_list(args: argparse.Namespace) -> int:
    repo = repo_root(args.repo)
    versions = require_versions(repo, "list")
    if versions is None:
        return 2
    usable = 0
    for v in versions:
        blocker = deployable(repo, v["commit"])
        usable += blocker is None
        note = "" if blocker is None else f"  [UNAVAILABLE: predates {blocker}]"
        print(f"{v['version']}  commit={v['commit'][:12]}  closed={v['closed']}  "
              f"{v.get('summary', '')}{note}")
    # Listing targets that all refuse is how a recovery path looks available while being gone.
    if versions and not usable:
        print("\nNo registered version can be rolled back to: every one predates the assembled "
              "layout. Register a corpus version from a commit that carries "
              f"{' and '.join(ASSEMBLY_PARTS)} before relying on this.", file=sys.stderr)
    return 0


def _applied_selection() -> tuple[list[str] | None, str]:
    """The live domain selection, or (None, why) — the assembly cannot run blind.

    Read from the installer-owned projection rather than asked: a rollback that
    guessed a selection would assemble a bundle nobody chose."""
    selection = STATE_DIR / "selection.json"
    if not selection.is_file():
        return None, f"no applied domain selection at {selection}; run onboarding first"
    try:
        return sorted(json.loads(selection.read_text())["domains"]), ""
    except (ValueError, KeyError, TypeError) as exc:
        return None, f"unreadable domain selection at {selection} ({exc})"


def _deployed_previously(repo: pathlib.Path, versions: list[dict]) -> tuple[set[str] | None, str]:
    """The managed corpus set the live homes hold NOW, or (None, why it is unknowable).

    HEAD is only the answer while the deployment tracks HEAD. After a rollback it
    does not, and deriving removals from HEAD is exactly how rolling forward left
    a file that only the rolled-back version deploys. Preference order: the
    manifest the last rollback recorded; else the recorded rollback version's own
    commit; else HEAD. A state that names a version the registry no longer
    carries is refused rather than guessed around."""
    prior = None
    if STATUS.is_file():
        try:
            prior = json.loads(STATUS.read_text())
        except ValueError as exc:
            return None, (f"cannot establish the deployed corpus: the status at "
                          f"{STATUS} is unreadable ({exc}); run `project` first "
                          "(it quarantines the damaged file)")
    if isinstance(prior, dict):
        deployed = prior.get("deployed_corpus")
        if isinstance(deployed, dict):
            files = deployed.get("files")
            if isinstance(files, list) and all(isinstance(f, str) for f in files):
                return set(files), ""
            return None, ("cannot establish the deployed corpus: the recorded "
                          "deployed_corpus manifest is malformed")
        rolled = prior.get("rolled_back_to")
        if isinstance(rolled, str) and rolled:
            match = [v for v in versions if v["version"] == rolled]
            if not match:
                return None, (f"cannot establish the deployed corpus: the live corpus "
                              f"is version {rolled}, which the registry no longer carries")
            return set(corpus_files(repo, match[0]["commit"])), ""
    return set(corpus_files(repo, "HEAD")), ""


def _assemble_at(repo: pathlib.Path, commit: str, domains: list[str]) -> tuple[bytes, str]:
    """Assemble the corpus AS OF a commit, in a sandbox; nothing live is touched.

    The commit's own assemble.py runs against its own tree — `deployable` already
    holds targets to carrying one, and the current assembler has never been asked
    about that corpus — with the LIVE selection, into empty sandbox homes. Returns
    the two things rollback takes from here: the Claude bundle's bytes, and the
    codex CENTRAL TEXT extracted from between the sandbox's markers. The region,
    never the merged file: publication merges it into AGENTS.md as that file
    exists AT PUBLICATION, so an edit the user lands while this runs rides
    through instead of being overwritten by a stale snapshot. Raises RuntimeError
    with the assembler's own words on any failure, before a single live write."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="corpus-rollback-assemble-"))
    try:
        src = root / "tree"
        src.mkdir()
        archive = subprocess.run(["git", "-C", str(repo), "archive", commit],
                                 check=True, capture_output=True)
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            try:
                tar.extractall(src, filter="data")
            except TypeError:      # Python < 3.12: no filter parameter
                tar.extractall(src)
        claude = root / "claude-home"
        codex = root / "codex-home"
        state = root / "state-home"
        for directory in (claude, codex, state):
            directory.mkdir()
        run = subprocess.run(
            [sys.executable, str(src / "compose" / "assemble.py"),
             "--domains", ",".join(domains),
             "--claude-dir", str(claude), "--codex-dir", str(codex),
             "--state-dir", str(state)],
            capture_output=True, text=True)
        if run.returncode != 0:
            tail = (run.stdout + run.stderr).strip().splitlines()[-3:]
            raise RuntimeError(
                f"the assembler at {commit[:9]} failed: {' | '.join(tail) or 'no output'}")
        bundle = claude / "central" / "bundle.md"
        agents = codex / "AGENTS.md"
        for produced in (bundle, agents):
            if not produced.is_file():
                raise RuntimeError(
                    f"the assembler at {commit[:9]} reported success but produced "
                    f"no {produced.name}")
        agents_text = agents.read_text(encoding="utf-8")
        if MARK_START not in agents_text or MARK_END not in agents_text:
            raise RuntimeError(
                f"the assembler at {commit[:9]} produced an AGENTS.md without the "
                "owned marker region")
        central = agents_text.split(MARK_START, 1)[1].split(MARK_END, 1)[0]
        # merge_codex writes MARK_START + "\n" + central_text; give it back
        # exactly what it will re-wrap.
        central = central[1:] if central.startswith("\n") else central
        return bundle.read_bytes(), central
    finally:
        shutil.rmtree(root, ignore_errors=True)


def cmd_rollback(args: argparse.Namespace) -> int:
    if os.environ.get("AGENT_BIOS_LEGACY_INSTALL") != "1":
        print("corpus-state rollback: global rollback is retired; use agent-bios corpus plan with op=rollback and a private baseline_ref", file=sys.stderr)
        return 2
    repo = repo_root(args.repo)
    versions = require_versions(repo, "rollback")
    if versions is None:
        return 2
    match = [v for v in versions if v["version"] == args.version]
    if not match:
        known = ", ".join(v["version"] for v in versions)
        print(f"unknown corpus version: {args.version} (known: {known})", file=sys.stderr)
        return 2
    commit = match[0]["commit"]
    blocker = deployable(repo, commit)
    if blocker is not None:
        print(f"refusing rollback to {args.version}: that corpus predates the assembled layout "
              f"({blocker} is absent at {commit[:9]}), so its bundle cannot be rebuilt and only "
              "part of the corpus would move. `list` marks which versions are available.",
              file=sys.stderr)
        return 2
    # One deployment at a time, held from target/backup calculation through the
    # final status update. The status lock covers only status writes; two
    # unserialized rollbacks interleaved their file writes and BOTH reported
    # success over a corpus split between their targets. Every input read again
    # inside is validated inside: a wait behind another deployment is exactly
    # when the world changes.
    with _deploy_lock():
        return _locked_rollback(args, repo, versions, commit)


def _locked_rollback(args: argparse.Namespace, repo: pathlib.Path,
                     versions: list[dict], commit: str) -> int:
    # Validated UNDER the lock, where it is read: a selection that vanishes while
    # this rollback waits behind another deployment must be a named refusal, not
    # whatever error an unchecked read escalates into.
    domains, why = _applied_selection()
    if domains is None:
        print(f"refusing rollback to {args.version}: {why} — without the applied "
              "selection the bundle for that corpus cannot be assembled.", file=sys.stderr)
        return 2
    target_files = corpus_files(repo, commit)
    previous, why = _deployed_previously(repo, versions)
    if previous is None:
        print(f"refusing rollback to {args.version}: {why} — removals cannot be "
              "derived, so files from the deployed version would silently survive.",
              file=sys.stderr)
        return 2
    # The union: HEAD names what an install deploys, `previous` names what a
    # rollback deployed, and files from either side that the target lacks must go.
    removal_candidates = sorted(
        (previous | set(corpus_files(repo, "HEAD"))) - set(target_files))
    # Per-transaction and collision-proof: two rollbacks in one second shared a
    # second-granularity directory and overwrote each other's undo copies.
    backup = (STATE_DIR / "backups"
              / f"corpus-rollback-{datetime.datetime.now():%Y%m%d-%H%M%S}"
                f"-{os.getpid()}-{uuid.uuid4().hex[:8]}")
    # Assembled BEFORE any live write: an assembly that cannot run refuses the
    # whole rollback with nothing to restore.
    try:
        bundle, codex_central = _assemble_at(repo, commit, domains)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"refusing rollback to {args.version}: {exc} — nothing was written.",
              file=sys.stderr)
        return 1
    written = removed = 0
    # Every step is recorded so it can be undone. A corpus is a SET of files that agree
    # about which version they are: a run that stopped in the middle left nine files at
    # the target and twenty-six at the previous one, wrote no status, and reported a raw
    # OSError — so the record on disk went on naming the version the corpus no longer
    # was. The backup taken a line below already holds what each write replaced, which
    # makes putting it back the cheap half of this; saying so when even that fails is
    # the half that matters.
    undo: list[tuple[pathlib.Path, pathlib.Path | None]] = []

    def restore() -> list[str]:
        """Put every applied file back. Returns the ones that could not be restored."""
        stuck = []
        for target, saved in reversed(undo):
            try:
                if saved is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_bytes(saved.read_bytes())
            except OSError:
                stuck.append(str(target))
        return stuck

    try:
        for rel in target_files:
            dst = deploy_target(rel)
            if dst is None:
                continue
            content = subprocess.run(
                ["git", "-C", str(repo), "show", f"{commit}:{rel}"],
                check=True, capture_output=True,
            ).stdout
            if args.dry_run:
                print(f"[dry-run] write  {dst}")
                continue
            bak = None
            if dst.is_file():
                bak = backup / rel
                bak.parent.mkdir(parents=True, exist_ok=True)
                bak.write_bytes(dst.read_bytes())
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(content)
            undo.append((dst, bak))
            if rel.startswith("claude/hooks/"):
                dst.chmod(0o755)
            written += 1
        for rel in removal_candidates:
            dst = deploy_target(rel)
            if dst is None or not dst.is_file():
                continue
            if args.dry_run:
                print(f"[dry-run] remove {dst} (absent in {args.version})")
                continue
            bak = backup / rel
            bak.parent.mkdir(parents=True, exist_ok=True)
            bak.write_bytes(dst.read_bytes())
            dst.unlink()
            undo.append((dst, bak))
            removed += 1
        # The assembled surfaces land LAST: the bundle is what the agent reads, so
        # it names the target version only once every guide it references has.
        bundle_dst = CLAUDE_DIR / "central" / "bundle.md"
        if args.dry_run:
            print(f"[dry-run] write  {bundle_dst} (assembled at {args.version})")
        else:
            bak = None
            if bundle_dst.is_file():
                bak = backup / "assembled/claude-central-bundle.md"
                bak.parent.mkdir(parents=True, exist_ok=True)
                bak.write_bytes(bundle_dst.read_bytes())
            bundle_dst.parent.mkdir(parents=True, exist_ok=True)
            bundle_dst.write_bytes(bundle)
            undo.append((bundle_dst, bak))
            written += 1
        codex_dst = CODEX_DIR / "AGENTS.md"
        if args.dry_run:
            print(f"[dry-run] merge  {codex_dst} central region (assembled at {args.version})")
        else:
            bak = None
            if codex_dst.is_file():
                bak = backup / "assembled/codex-AGENTS.md"
                bak.parent.mkdir(parents=True, exist_ok=True)
                bak.write_bytes(codex_dst.read_bytes())
            # Merged into the file AS IT EXISTS NOW, through the same merge every
            # install uses — atomic, mode-preserving, marker-bounded — never a
            # whole-file write of a snapshot: an edit the user landed while the
            # guides were copying rides through; only the region is ours to move.
            merge_codex(CODEX_DIR, codex_central)
            undo.append((codex_dst, bak))
            written += 1
    except (OSError, subprocess.CalledProcessError) as exc:
        stuck = restore()
        if stuck:
            print(
                f"rollback to {args.version} failed ({exc}) and {len(stuck)} file(s) could "
                f"not be put back: {', '.join(stuck[:5])}. The corpus is SPLIT between "
                f"versions; the previous content of every file this touched is at {backup}.",
                file=sys.stderr,
            )
            return 1
        print(
            f"rollback to {args.version} failed ({exc}); every file it had already written "
            f"was restored, so the corpus is unchanged. Nothing is split.",
            file=sys.stderr,
        )
        return 1
    if args.dry_run:
        return 0
    # Re-project, then mark the rollback (a plain project would report latest).
    cmd_project(args)
    # Sequential with cmd_project's lock, never nested inside it: flock on a
    # second open of the same lock file would deadlock this process.
    with _status_lock():
        status = json.load(STATUS.open())
        status["current_version"] = args.version
        status["rolled_back_to"] = None if args.version == status["latest_version"] else args.version
        # The next rollback's removal operand: exactly what is deployed now.
        status["deployed_corpus"] = {
            "version": args.version,
            "files": sorted(rel for rel in target_files if deploy_target(rel) is not None),
        }
        _write_status(status)
    print(
        f"corpus rolled back to {args.version} ({commit[:12]}): "
        f"{written} files written, {removed} removed; backup at {backup}. "
        "System deployment (launcher, wrappers) unchanged. Roll forward by "
        "rolling back to the latest version."
    )
    return 0


APPLY_OUTCOMES = ("applied", "canary_failed", "install_failed")


@contextlib.contextmanager
def _flock(lock_path: pathlib.Path):
    """Exclusive advisory lock at `lock_path`, held for the with-block."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # O_NOFOLLOW and no truncation: a "w" open follows a planted symlink and
    # truncates its target merely by running the command.
    fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def _status_lock():
    """Exclusive advisory lock over corpus-status writes. `project` and
    `record-apply` both read-modify-write the whole file; unlocked, whichever
    writes second silently reverts the other's fields."""
    return _flock(STATUS.with_name(STATUS.name + ".lock"))


def _deploy_lock():
    """Exclusive advisory lock over corpus deployment. One rollback at a time,
    target to status: file writes serialized only by the status lock let two
    rollbacks both report success over a split corpus. A DIFFERENT file from the
    status lock, deliberately — rollback takes the status lock inside this one,
    and flock on a second open of one file deadlocks a single process."""
    return _flock(STATUS.with_name(STATUS.name + ".deploy.lock"))


def _write_status(status: dict) -> None:
    """Every status write goes through the shared temp-write + os.replace: a
    plain write_text truncates first and fills after, so an interrupted writer
    left `{"current_version":` as the record and the next projection silently
    replaced what it could not read."""
    replace_atomically(STATUS, json.dumps(status, ensure_ascii=False, indent=1) + "\n")


def cmd_record_apply(args: argparse.Namespace) -> int:
    """Record the outcome of one onboard apply into the existing status file.

    Read-modify-write of `last_apply` only: the projection owns every other
    field, and an outcome recorded against a status that does not exist yet
    would invent one — refuse instead, loudly."""
    with _status_lock():
        if not STATUS.is_file():
            print(f"no corpus status to record into: {STATUS}", file=sys.stderr)
            return 1
        try:
            status = json.loads(STATUS.read_text())
        except ValueError as exc:
            print(f"corpus status unreadable: {exc}", file=sys.stderr)
            return 1
        status["last_apply"] = {
            "requested": sorted(d for d in args.requested.split(",") if d),
            "outcome": args.outcome,
            "at": datetime.datetime.now().isoformat(timespec="seconds"),
            "error_tail": args.error_tail or None,
        }
        try:
            _write_status(status)
        except OSError as exc:
            print(f"cannot record last_apply ({exc}); the prior status is intact",
                  file=sys.stderr)
            return 1
    print(f"last_apply recorded: {args.outcome}")
    return 0


def self_test() -> int:
    """A rollback that fails partway must leave the corpus at ONE version — and a
    clean one must move EVERY reader surface, remove what the deployed version
    alone carried, refuse when it cannot know what is deployed, run one at a
    time, and never leave the status file truncated.

    Driven against a throwaway git repo rather than the real registry, because every
    version registered today is UNAVAILABLE (it predates the assembled layout), so the
    write loop is unreachable from `list` and this path would otherwise be covered by
    nothing at all. The failing run and the clean one differ only in whether one write
    raises — without the clean one, a rollback that wrote nothing would satisfy the
    failing case too. The fixture's assemble.py is a runnable stand-in with the real
    assembler's calling convention; the convention itself is pinned against the real
    compose/assemble.py by the --help probe below.
    """
    # The variables that relocate a repository — git's own list, `local_repo_env` in
    # environment.c, the ones it clears before entering another repo. The pre-commit hook
    # exports GIT_DIR / GIT_WORK_TREE / GIT_INDEX_FILE so the gates read the real index
    # against the materialised stage, and this self-test runs under it. Inherited by the
    # fixture they make `git init` re-initialise the REAL repository — writing
    # core.worktree = the stage directory into its config, which outlives the stage and
    # leaves the primary worktree unable to run `git status` — and point every later
    # command, `cmd_rollback`'s included, at that repo instead of the fixture. So the
    # fixture is only a fixture inside this scrub, and everything that touches it runs
    # inside it.
    REPO_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_IMPLICIT_WORK_TREE", "GIT_INDEX_FILE",
                "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_PREFIX", "GIT_GRAFT_FILE", "GIT_SHALLOW_FILE", "GIT_NO_REPLACE_OBJECTS",
                "GIT_REPLACE_REF_BASE", "GIT_CONFIG")

    @contextlib.contextmanager
    def own_repo_env():
        saved = {name: os.environ.pop(name) for name in REPO_ENV if name in os.environ}
        try:
            yield
        finally:
            os.environ.update(saved)

    def git(repo, *command):
        return subprocess.run(["git", "-C", str(repo), *command], check=True,
                              capture_output=True, text=True).stdout.strip()

    MINI_ASSEMBLER = r'''#!/usr/bin/env python3
"""Self-test stand-in with the REAL assembler's calling convention. It does what
cmd_rollback relies on the assembler for: build the bundle from ITS OWN tree and
merge the codex AGENTS.md marker region, preserving text outside the markers."""
import argparse
import pathlib
ap = argparse.ArgumentParser()
ap.add_argument("--domains", required=True)
ap.add_argument("--claude-dir", required=True)
ap.add_argument("--codex-dir", required=True)
ap.add_argument("--state-dir", required=True)
a = ap.parse_args()
repo = pathlib.Path(__file__).resolve().parents[1]
claude = pathlib.Path(a.claude_dir)
codex = pathlib.Path(a.codex_dir)
(claude / "central").mkdir(parents=True, exist_ok=True)
stamp = (repo / "BUNDLE_STAMP").read_text().strip()
(claude / "central" / "bundle.md").write_text("BUNDLE " + stamp + "\n")
start = "<!-- agent-bios:central:start -->"
end = "<!-- agent-bios:central:end -->"
agents = codex / "AGENTS.md"
region = start + "\nCODEX " + stamp + "\n" + end + "\n"
if agents.is_file():
    body = agents.read_text()
    if start in body and end in body:
        pre, rest = body.split(start, 1)
        _, post = rest.split(end, 1)
        body = pre + region + post
    else:
        body = region + "\n" + body
else:
    codex.mkdir(parents=True, exist_ok=True)
    body = region + "\n## Personal\n"
agents.write_text(body)
'''

    def build_fixture(repo):
        """Two corpus commits plus the registry: t1 carries a version-only file
        (legacy.md) that t2 deletes, and each commit's stand-in assembler stamps
        its own bundle — so a rollback that skips assembly, or derives removals
        from the wrong version, is visible in the files."""
        (repo / "claude" / "guides").mkdir(parents=True)
        for index in range(6):
            (repo / "claude" / "guides" / f"g{index}.md").write_text(f"TARGET {index}\n")
        (repo / "claude" / "guides" / "legacy.md").write_text("OLD ONLY\n")
        (repo / "BUNDLE_STAMP").write_text("one\n")
        # `deployable` refuses a commit that predates the assembled layout, and it is
        # right to: without these the bundle cannot be rebuilt. The fixture carries a
        # RUNNABLE assemble.py so the assembly step is REACHED — a self-test that
        # stops at that refusal would report OK having exercised nothing.
        (repo / "compose").mkdir(parents=True, exist_ok=True)
        (repo / "compose" / "assemble.py").write_text(MINI_ASSEMBLER)
        (repo / "compose" / "domains.json").write_text(json.dumps({"domains": []}) + "\n")
        with own_repo_env():
            git(repo, "init", "-q")
            git(repo, "add", "-A")
            git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "old")
            old = git(repo, "rev-parse", "HEAD")
        for index in range(6):
            (repo / "claude" / "guides" / f"g{index}.md").write_text(f"NEWER {index}\n")
        (repo / "claude" / "guides" / "legacy.md").unlink()
        (repo / "claude" / "guides" / "fresh.md").write_text("NEW ONLY\n")
        (repo / "BUNDLE_STAMP").write_text("two\n")
        with own_repo_env():
            git(repo, "add", "-A")
            git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "new")
            new = git(repo, "rev-parse", "HEAD")
        registry = repo / "design" / "session-distill"
        registry.mkdir(parents=True)
        (registry / "versions.json").write_text(json.dumps({"versions": [
            {"version": "t1", "commit": old, "closed": "2026-01-01", "summary": "old"},
            {"version": "t2", "commit": new, "closed": "2026-01-02", "summary": "new"},
        ]}))
        (registry / "ledger.json").write_text(json.dumps({"entries": []}))
        with own_repo_env():
            git(repo, "add", "-A")
            git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "registry")
        return old, new

    problems = []
    root = pathlib.Path(tempfile.mkdtemp(prefix="corpus-state-selftest-"))
    try:
        # Control for the scrub, run FIRST and under the hook's environment whether or
        # not the hook is present: an "outer" repo stands in for the real one, GIT_DIR
        # points at it, and building a fixture must leave it untouched — its
        # core.worktree unset, the fixture holding its own HEAD. Without the scrub the
        # first `git init` rewrites the outer config, which is exactly the defect.
        outer = root / "outer"
        outer.mkdir()
        with own_repo_env():
            git(outer, "init", "-q")
            git(outer, "-c", "user.email=t@t", "-c", "user.name=t",
                "commit", "-q", "--allow-empty", "-m", "outer")
        stage = root / "stage"
        stage.mkdir()
        planted = {"GIT_DIR": str(outer / ".git"), "GIT_WORK_TREE": str(stage),
                   "GIT_INDEX_FILE": str(outer / ".git" / "index")}
        saved_env = {name: os.environ.get(name) for name in planted}
        os.environ.update(planted)
        try:
            build_fixture(root / "control")
        except subprocess.CalledProcessError as exc:
            # Caught rather than propagated so this reads as the defect it is: an
            # uninsulated fixture's commands land in the outer repo and fail there.
            problems.append(
                "building the fixture under an exported GIT_DIR did not build one — "
                f"`git {' '.join(exc.cmd[3:])}` failed against the wrong repository")
        finally:
            for name, value in saved_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        with own_repo_env():
            outer_worktree = subprocess.run(
                ["git", "-C", str(outer), "config", "--get", "core.worktree"],
                capture_output=True, text=True).stdout.strip()
        if outer_worktree:
            problems.append(
                "building the fixture under an exported GIT_DIR rewrote the outer repo's "
                f"core.worktree to {outer_worktree} — the fixture is not insulated")
        if not (root / "control" / ".git" / "HEAD").exists():
            problems.append(
                "building the fixture under an exported GIT_DIR left it without a "
                "repository of its own")

        repo = root / "repo"
        build_fixture(repo)

        # The calling convention the mini-assembler stands in for, pinned against
        # the REAL assembler: if compose/assemble.py stops answering for these
        # flags, every fixture here keeps passing while live rollbacks break.
        real_assembler = repo_root(None) / "compose" / "assemble.py"
        probe = subprocess.run([sys.executable, str(real_assembler), "--help"],
                               capture_output=True, text=True)
        missing = [flag for flag in ("--domains", "--claude-dir", "--codex-dir",
                                     "--state-dir")
                   if flag not in probe.stdout]
        if probe.returncode != 0 or missing:
            problems.append(
                "cmd_rollback dispatches --domains/--claude-dir/--codex-dir/--state-dir "
                "to the target commit's assemble.py, but the real assembler no longer "
                f"answers for: {missing or probe.stderr.strip()[:120]}")

        codex_seed = ("<!-- agent-bios:central:start -->\nCODEX two\n"
                      "<!-- agent-bios:central:end -->\n\n## Personal\nMY OWN CODEX LINE\n")

        def attempt(fail_at):
            home = root / f"home-{fail_at}"
            claude = home / ".claude"
            codex_home = home / ".codex"
            saved_claude = globals()["CLAUDE_DIR"]
            globals()["CLAUDE_DIR"] = claude
            # Located through deploy_target, not by guessing the layout: the corpus root
            # moved once already, and a fixture that seeds the wrong directory asserts
            # that an untouched file is untouched.
            seeded = deploy_target("claude/guides/g0.md")
            globals()["CLAUDE_DIR"] = saved_claude
            seeded.parent.mkdir(parents=True, exist_ok=True)
            seeded.write_text("PREVIOUS\n")
            (claude / "central" / "bundle.md").write_text("LIVE BUNDLE\n")
            codex_home.mkdir(parents=True, exist_ok=True)
            (codex_home / "AGENTS.md").write_text(codex_seed)
            # A user-restricted mode must ride through the region merge.
            (codex_home / "AGENTS.md").chmod(0o600)
            counter = [0]
            real_write = pathlib.Path.write_bytes

            def flaky(self, data):
                if str(self).startswith(str(claude)) and "backups" not in str(self):
                    counter[0] += 1
                    if counter[0] == fail_at:
                        raise OSError("self-test write failure")
                return real_write(self, data)

            real_assemble_at = globals()["_assemble_at"]

            def editing_assemble_at(repo_arg, commit_arg, domains_arg):
                # The user's edit landing in the window between the assembly
                # snapshot and publication: the merge must carry it through,
                # never overwrite it with the pre-assembly state of the file.
                result = real_assemble_at(repo_arg, commit_arg, domains_arg)
                agents = codex_home / "AGENTS.md"
                agents.write_text(agents.read_text().replace(
                    "MY OWN CODEX LINE", "MY OWN CODEX LINE\nMID-FLIGHT EDIT"))
                return result

            saved = (globals()["CLAUDE_DIR"], globals()["CODEX_DIR"],
                     globals()["STATE_DIR"], globals()["STATUS"],
                     globals()["cmd_project"], globals()["_assemble_at"])
            globals()["CLAUDE_DIR"] = claude
            globals()["CODEX_DIR"] = codex_home
            globals()["STATE_DIR"] = home / "state"
            globals()["STATUS"] = home / "state" / "corpus-status.json"
            # The projection reads the real ledger and is a different question; what this
            # asserts is that the FILES end up at one version. Stubbed so the fixture does
            # not have to carry a ledger to answer a question it is not asking.
            (home / "state").mkdir(parents=True, exist_ok=True)
            (home / "state" / "selection.json").write_text(
                json.dumps({"version": 1, "domains": []}))
            globals()["STATUS"].write_text(json.dumps(
                {"current_version": "before", "latest_version": "t1"}))
            globals()["cmd_project"] = lambda _args: 0
            globals()["_assemble_at"] = editing_assemble_at
            pathlib.Path.write_bytes = flaky
            try:
                code = cmd_rollback(argparse.Namespace(
                    repo=str(repo), version="t1", dry_run=False))
            except Exception as exc:      # a raise is itself the defect this asserts against
                code = f"raised {type(exc).__name__}"
            finally:
                pathlib.Path.write_bytes = real_write
                (globals()["CLAUDE_DIR"], globals()["CODEX_DIR"],
                 globals()["STATE_DIR"], globals()["STATUS"],
                 globals()["cmd_project"], globals()["_assemble_at"]) = saved
            landed = sorted(q.name for q in seeded.parent.glob("*.md"))
            return (code, landed, seeded.read_text(),
                    (claude / "central" / "bundle.md").read_text(),
                    (codex_home / "AGENTS.md").read_text(),
                    (codex_home / "AGENTS.md").stat().st_mode & 0o777)

        # `cmd_rollback` reads the fixture through `git -C <repo>`, which the hook's
        # GIT_DIR would redirect at the real repository — same scrub, same reason.
        with own_repo_env():
            code, landed, seeded, bundle_text, agents_text, agents_mode = attempt(0)
        if code != 0 or len(landed) < 6 or seeded.strip() != "TARGET 0":
            problems.append(
                f"clean rollback did not apply the corpus (code={code} files={len(landed)})")
        if "MID-FLIGHT EDIT" not in agents_text:
            problems.append(
                "a user edit landing between the assembly snapshot and publication "
                "was overwritten — AGENTS.md must be merged as it exists at "
                "publication, never replaced by a stale snapshot")
        if agents_mode != 0o600:
            problems.append(
                f"publishing the codex region widened a user-restricted AGENTS.md "
                f"from 0o600 to {oct(agents_mode)}")
        # The surfaces the agent actually reads must move WITH the guides: the
        # defect was a rollback that reported an older version while the bundle
        # and the codex central region silently stayed current.
        if bundle_text.strip() != "BUNDLE one":
            problems.append(
                "rollback moved the guides but left the live bundle at the current "
                "version — the assembled surface the agent reads did not roll back")
        if "CODEX one" not in agents_text or "CODEX two" in agents_text:
            problems.append(
                "rollback did not rewrite the codex AGENTS.md central region to the "
                "target version")
        if "MY OWN CODEX LINE" not in agents_text:
            problems.append("rollback destroyed the user's text outside the codex markers")
        with own_repo_env():
            code, landed, seeded, bundle_text, agents_text, agents_mode = attempt(3)
        if code == 0:
            problems.append("a rollback whose write failed reported success")
        elif not isinstance(code, int):
            problems.append(f"a failed rollback escaped as an exception ({code})")
        if seeded.strip() != "PREVIOUS":
            problems.append(
                "a failed rollback left a file at the target version — the corpus is split")
        if bundle_text.strip() != "LIVE BUNDLE":
            problems.append(
                "a failed rollback moved the live bundle — the reader surface is split")
        if "CODEX two" not in agents_text or "MY OWN CODEX LINE" not in agents_text:
            problems.append("a failed rollback did not leave the codex surface as it was")

        # ---- The real CLI end to end, subprocess-driven against one fixture. ----
        fx_home = root / "fx-home"
        fx_claude = root / "fx-claude"
        fx_codex = root / "fx-codex"
        fx_tmp = root / "fx-tmp"
        fx_state = fx_home / ".local" / "share" / "agent-bios"
        fx_status = fx_state / "corpus-status.json"
        for directory in (fx_home, fx_claude, fx_codex, fx_tmp, fx_state):
            directory.mkdir(parents=True, exist_ok=True)
        (fx_state / "selection.json").write_text(json.dumps({"version": 1, "domains": []}))
        guides_live = fx_claude / "central" / "guides"
        guides_live.mkdir(parents=True)
        for index in range(6):
            (guides_live / f"g{index}.md").write_text(f"NEWER {index}\n")
        (guides_live / "fresh.md").write_text("NEW ONLY\n")
        (fx_claude / "central" / "bundle.md").write_text("BUNDLE two\n")
        (fx_codex / "AGENTS.md").write_text(codex_seed)
        env = {name: value for name, value in os.environ.items() if name not in REPO_ENV}
        env.update({"HOME": str(fx_home), "TMPDIR": str(fx_tmp),
                    "CLAUDE_CONFIG_DIR": str(fx_claude), "CODEX_HOME": str(fx_codex),
                    "AGENT_BIOS_CORPUS_STATUS": str(fx_status)})
        me = pathlib.Path(__file__).resolve()

        def run_cli(*argv):
            return subprocess.run([sys.executable, str(me), *argv, "--repo", str(repo)],
                                  capture_output=True, text=True, env=env)

        project = run_cli("project")
        if project.returncode != 0:
            problems.append(f"subprocess project failed: {project.stderr.strip()[:200]}")
        back = run_cli("rollback", "--version", "t1")
        legacy = guides_live / "legacy.md"
        fresh = guides_live / "fresh.md"
        if back.returncode != 0:
            problems.append("subprocess rollback to t1 failed: "
                            f"{(back.stdout + back.stderr).strip()[:200]}")
        else:
            if not legacy.is_file():
                problems.append(
                    "rolling back did not deploy the file only the older version carries")
            if fresh.exists():
                problems.append("rolling back left a file the target version does not carry")
        forward = run_cli("rollback", "--version", "t2")
        if forward.returncode != 0:
            problems.append("subprocess roll-forward to t2 failed: "
                            f"{(forward.stdout + forward.stderr).strip()[:200]}")
        else:
            # THE removal control: the operand must be what is deployed, and a
            # gutted removal loop must be caught by a surviving file, not by a
            # count nobody asserts.
            if legacy.exists():
                problems.append(
                    "rolling forward left a file that only the rolled-back version "
                    "deploys — the removal operand ignores what is actually deployed")
            if (not fresh.is_file()
                    or (fx_claude / "central" / "bundle.md").read_text().strip() != "BUNDLE two"):
                problems.append("rolling forward did not restore the newer corpus and bundle")
            state = json.loads(fx_status.read_text())
            if state.get("current_version") != "t2" or state.get("rolled_back_to") is not None:
                problems.append("roll-forward status does not name the target version")
        marks = [result.stdout.partition("backup at ")[2].partition(". System")[0]
                 for result in (back, forward)]
        if all(marks) and marks[0] == marks[1]:
            problems.append(
                "two rollbacks shared one backup directory — their undo copies collide")

        # ---- Mutual exclusion: a held deploy lock must queue a second rollback. ----
        deploy_lock_path = fx_status.with_name(fx_status.name + ".deploy.lock")
        lock_fd = os.open(str(deploy_lock_path), os.O_CREAT | os.O_WRONLY, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        g0_live = guides_live / "g0.md"
        held = subprocess.Popen(
            [sys.executable, str(me), "rollback", "--version", "t1", "--repo", str(repo)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        try:
            held.wait(timeout=1.5)
            problems.append(
                "a rollback proceeded while another deployment held the deploy lock "
                "— concurrent rollbacks would both report success over a split corpus")
        except subprocess.TimeoutExpired:
            if g0_live.read_text() != "NEWER 0\n":
                problems.append("a lock-blocked rollback wrote files before holding the lock")
        os.close(lock_fd)
        try:
            queued = held.wait(timeout=60)
        except subprocess.TimeoutExpired:
            held.kill()
            held.wait()
            queued = None
            problems.append("a queued rollback never completed after the lock was released")
        if queued is not None and (queued != 0 or g0_live.read_text() != "TARGET 0\n"):
            problems.append("the queued rollback failed after the deploy lock was released")

        # ---- A selection that vanishes while waiting is refused BY NAME. ----
        # The wait behind another deployment is exactly when the world changes:
        # unvalidated, the locked read escalated into a raw TypeError.
        selection_path = fx_state / "selection.json"
        saved_selection = selection_path.read_text()
        lock_fd = os.open(str(deploy_lock_path), os.O_CREAT | os.O_WRONLY, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        vanish = subprocess.Popen(
            [sys.executable, str(me), "rollback", "--version", "t2", "--repo", str(repo)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        try:
            vanish.wait(timeout=1.0)
            problems.append(
                "a rollback proceeded while the deploy lock was held (selection leg)")
        except subprocess.TimeoutExpired:
            selection_path.unlink()
        os.close(lock_fd)
        try:
            vanish_out, vanish_err = vanish.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            vanish.kill()
            vanish_out, vanish_err = vanish.communicate()
            problems.append("the selection-vanish rollback never completed")
        if vanish.returncode != 2 or "no applied domain selection" not in vanish_err:
            problems.append(
                "a selection that vanished while waiting for the deploy lock was not "
                f"refused by name (rc={vanish.returncode}: "
                f"{vanish_err.strip().splitlines()[-1][:120] if vanish_err.strip() else 'no stderr'})")
        if g0_live.read_text() != "TARGET 0\n":
            problems.append("a selection-refused rollback still moved files")
        selection_path.write_text(saved_selection)

        # ---- Refusal when the deployed set cannot be established. ----
        fx_status.write_text(json.dumps(
            {"current_version": "ghost", "latest_version": "t2", "rolled_back_to": "ghost"}))
        snapshot = sorted(path.name for path in guides_live.glob("*.md"))
        refused = run_cli("rollback", "--version", "t2")
        if refused.returncode == 0:
            problems.append("a rollback with an unknowable deployed set proceeded anyway")
        elif "cannot establish the deployed corpus" not in refused.stderr:
            problems.append("the refusal does not name the unestablishable deployed set")
        if sorted(path.name for path in guides_live.glob("*.md")) != snapshot:
            problems.append("a refused rollback still moved files")

        # ---- An unreadable status is quarantined and reported, never discarded. ----
        fx_status.write_bytes(b'{"current_version":')
        reproject = run_cli("project")
        quarantines = sorted(fx_state.glob("corpus-status.json.corrupt-*"))
        if reproject.returncode != 0:
            problems.append(
                f"project over a truncated status failed: {reproject.stderr.strip()[:200]}")
        else:
            if not quarantines or quarantines[-1].read_bytes() != b'{"current_version":':
                problems.append(
                    "projecting over a truncated status silently discarded the damaged "
                    "bytes instead of quarantining them")
            if "unreadable" not in reproject.stderr:
                problems.append("the projection did not report the unreadable status")
            try:
                json.loads(fx_status.read_text())
            except ValueError:
                problems.append("the projection left the status unreadable")

        # ---- An interrupted status write must not truncate the record. ----
        ra_home = root / "record-apply"
        ra_home.mkdir()
        seeded_status = {"current_version": "t2", "latest_version": "t2",
                         "rolled_back_to": None, "last_apply": None}
        saved_state = (globals()["STATE_DIR"], globals()["STATUS"])
        globals()["STATE_DIR"] = ra_home
        globals()["STATUS"] = ra_home / "corpus-status.json"
        globals()["STATUS"].write_text(json.dumps(seeded_status))
        real_write_text = pathlib.Path.write_text

        def truncating(self, text, *wargs, **kw):
            # The failure a plain write_text really has: truncate, fill partway, die.
            if self.name.startswith("corpus-status.json"):
                with open(self, "w") as handle:
                    handle.write(text[:19])
                raise OSError("self-test write interruption")
            return real_write_text(self, text, *wargs, **kw)

        pathlib.Path.write_text = truncating
        try:
            code = cmd_record_apply(argparse.Namespace(
                repo=None, requested="alpha", outcome="applied", error_tail=""))
        except Exception as exc:
            code = f"raised {type(exc).__name__}"
        finally:
            pathlib.Path.write_text = real_write_text
        if not isinstance(code, int) or code == 0:
            problems.append(
                f"an interrupted status write did not report failure (code={code})")
        try:
            after = json.loads(globals()["STATUS"].read_text())
        except ValueError:
            after = None
            problems.append(
                "an interrupted status write left the corpus status truncated — "
                "the write is not atomic")
        if after is not None and after != seeded_status:
            problems.append("an interrupted status write altered the recorded status")
        (globals()["STATE_DIR"], globals()["STATUS"]) = saved_state
    except subprocess.CalledProcessError as exc:
        # A fixture command failing outside the control above is the same defect seen
        # from the main run — named here so the gate reports it instead of a traceback.
        problems.append(
            f"a git command against the fixture failed (`git {' '.join(exc.cmd[3:])}`) — "
            "is the fixture insulated from the caller's GIT_DIR?")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    for problem in problems:
        print(f"corpus-state --self-test: FAIL: {problem}", file=sys.stderr)
    if problems:
        return 1
    print("corpus-state --self-test: OK (a failed rollback restores; a clean one moves "
          "every reader surface, removes what only the deployed version carried, runs "
          "one at a time, and status writes stay atomic)")
    return 0


def main() -> int:
    # Before argparse, because --self-test takes none of the subcommands' arguments and
    # every subcommand here is required.
    if "--self-test" in sys.argv[1:]:
        os.environ["AGENT_BIOS_LEGACY_INSTALL"] = "1"
        return self_test()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    commands = {
        name: sub.add_parser(name)
        for name in ("project", "list", "rollback", "record-apply")
    }
    for command in commands.values():
        command.add_argument("--repo", help="repo root (default: derived from this script's path)")
    commands["rollback"].add_argument("--version", required=True)
    commands["rollback"].add_argument("--dry-run", action="store_true")
    commands["record-apply"].add_argument("--requested", required=True,
                                          help="comma-separated domain selection")
    commands["record-apply"].add_argument("--outcome", required=True, choices=APPLY_OUTCOMES)
    commands["record-apply"].add_argument("--error-tail", default="")
    args = parser.parse_args()
    return {
        "project": cmd_project, "list": cmd_list, "rollback": cmd_rollback,
        "record-apply": cmd_record_apply,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
