# Installation, migration, and recovery

[← Overview](../README.md) · [Setup](setup.md) · [Corpus](corpus.md) · [Sessions](session-model.md) · [Recovery](recovery.md) · [Launch](advanced-launch.md) · [Understand!](understand.md)

Start with `agent-bios status`. This reference describes the current source; from its
retained checkout use `bash install.sh <command>`. For first installation and app
setup recovery, see [Setup](setup.md). Commands below are **operation references, not a sequence to paste and run**. Preview the specific action you need; do not delete an ownership conflict just to make installation succeed.

## Command reference

The npm package and command are both named `agent-bios`. Installation is always
explicit—never a package-manager postinstall side effect—and the default path stores
an immutable release and baseline under agent-bios-owned state. It installs the
`agent-launch` entrypoint and its own profile/catalog files, but does not change native
Claude/Codex globals, settings or hooks. Optional app registration adds only its
owned discovery link, and optional shell connection changes only its owned startup
wiring. Neither activates corpus in a task.

| Command | Purpose |
| --- | --- |
| `agent-bios install` | open the guided installation UI |
| `agent-bios install --non-interactive --corpus none` | store runtime with no active corpus |
| `agent-bios onboard --non-interactive --domains builder-base,multi-agent-orchestration` | store the named domains with compatibility core/infra selection |
| `agent-bios setup status --review-id ID` / `resume --review-id ID` | inspect the setup receipt / prepare a safe continuation without executing it |
| `agent-bios verify` | verify stored bytes/catalog/baseline; not host activation |
| `agent-bios status` | show the private release, baseline, conflicts, and evidence state |
| `agent-bios corpus` | rich Corpus Studio in a TTY; list in a non-TTY |
| `agent-launch claude` | open the launch TUI for Claude |
| `agent-launch codex` | open the launch TUI for Codex |
| `agent-bios shell restore` | opt in: bare claude/codex opens the TUI |
| `agent-bios shell remove` | remove only that optional shell connection |
| `agent-bios reset` | preview reset; keep sources, snapshots, and pins |
| `agent-bios reset --apply --yes --expected-revision REV` | use the revision returned by preview |
| `agent-bios migrate` | preview legacy global cleanup; --apply --yes performs it |
| `agent-bios update` | git pull + reinstall (clone), or print the npm update line |
| `agent-bios uninstall` | remove owned runtime entries; retain user corpus and pinned sessions |

The published npm package `agent-bios@0.18.0` has its own included command reference;
it does not provide the current source conversation setup or bundled UI.

`agent-launch` examples assume `~/.local/bin` is on `PATH`; otherwise use `"$HOME/.local/bin/agent-launch"`. From a checkout, deploy with `bash install.sh install` at its root, not the globally installed CLI. A blocked npm postinstall message does not deploy the corpus; the explicit `install` command remains necessary.

## Ownership and legacy migration

`install`, `onboard`, `reset`, `migrate`, and `uninstall` expose dry-run or preview
paths appropriate to their mutations. A pre-existing owned launcher/profile path whose
bytes no longer match the recorded copy is reported as an owned-path conflict rather than
overwritten. `migrate` is the separate recovery-backed operation for a legacy global
installation: preview is the default, applying requires `--apply --yes`, ambiguous
ownership refuses the apply, and later private operations do not fall through to a
global writer. Setting `AGENT_BIOS_LEGACY_INSTALL=1` selects the old deployer only for
compatibility and migration regression work; it is not the user default.

The legacy compatibility deployer preserves guide paths named only by a previous
manifest when the current source no longer establishes their ownership. It names
these remnants for manual inspection and leaves them out of the new ownership
manifest, so later uninstall does not claim them. Current source-owned members
retain normal backup and selection cleanup; private snapshot installation uses its
own authoritative inventory.

After updating a legacy global installation, run `agent-bios migrate` before the
first private `install`. Its preview identifies exact managed regions, legacy
manifest paths and learning sources. `agent-bios migrate --apply --yes` backs up
the originals, transfers and verifies learning records, retires the legacy paths,
then installs the private release. A central-only Codex file and the unmodified
empty Claude learning seed do not require a learning JSONL file; actual learning
content without its source still requires attention.

An interrupted migration is visible in `status` and blocks configuration readers
and unrelated writes. Re-run `agent-bios migrate --apply --yes` to resume its
pinned release and recorded path versions. A completed private installation is
not repeated, and later cleanup cannot delete its replacement launcher/profile.
Intervening edits are preserved and reported instead of overwritten. Older
incomplete journals without replay evidence require reconciliation from their
backups rather than a guessed replay. Existing private-session replay retains the
previous confirmed release until migration completes.

Before applying or resuming, stop the old global collectors that can still append a native
learning JSONL or rewrite its native prose/entry file. The migration checks the
recorded native state immediately before commit, but no filesystem check can make
a noncooperating writer atomic after that final observation. If it reports a
changed native target, preserve only the affected paths and restore only those
paths to the journal's recorded `after` state before resuming the old migration.
Do not replace a whole native directory or edit the journal.

For a validated late-input recovery, set `JOURNAL` to the one `NEEDS_RECOVERY`
migration journal and pass only the specific changed JSONL, prose, or entry paths
that its error named. This makes a new durable copy under that journal's existing
`backup_root`, verifies the copy, and then restores a changed target from its
recorded `after` bytes/existence/mode or an input-only path to its recorded
unchanged existence. It rejects a path absent from the journal, symlinks, and
non-regular files before writing any backup. New private journals retain exact
bytes for input-only native files, so the command can restore an originally
present input while preserving its current mode (or using `0600` if it is
absent). Historic digest-only journals still need an external byte-identical
backup; the command refuses to invent their missing bytes.

```sh
JOURNAL="${AGENT_BIOS_STATE_DIR:-$HOME/.local/share/agent-bios}/runtime/migrations/<migration-id>/journal.json"
python3 - "$JOURNAL" \
  "$HOME/.codex/personal/learnings.jsonl" <<'PY'
import base64, hashlib, json, os, sys, tempfile
from pathlib import Path

journal = Path(sys.argv[1])
data = json.loads(journal.read_text(encoding="utf-8"))
backup_root = Path(data.get("backup_root", ""))
if data.get("kind") != "migrate" or data.get("state") != "NEEDS_RECOVERY" or backup_root != journal.parent / "backup":
    raise SystemExit("expected one validated NEEDS_RECOVERY migration journal")
targets = {Path(entry["path"]): entry for entry in data["paths"]}
inputs = {Path(path): version for path, version in data["inputs"].items()}
selected = [Path(value).expanduser() for value in sys.argv[2:]]
unknown = [str(path) for path in selected if path not in targets and path not in inputs]
if not selected or unknown:
    raise SystemExit("name one or more exact journal paths; unknown: " + ", ".join(unknown))

planned = []
for path in selected:
    entry = targets.get(path)
    version = entry["after"] if entry is not None else inputs[path]
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise SystemExit(f"refusing unsafe native path: {path}")
    root = next((parent for parent in (path.parent, *path.parents)
                 if parent.name in {".claude", ".codex"}), None)
    if root is None or root.is_symlink():
        raise SystemExit(f"recovery supports an exact Claude/Codex native path, not: {path}")
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if current.is_symlink():
            raise SystemExit(f"refusing symlink ancestor: {current}")
    planned.append((path, entry, version))

if backup_root.is_symlink() or (backup_root.exists() and not backup_root.is_dir()):
    raise SystemExit(f"refusing unsafe recovery root: {backup_root}")
backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
recovery = Path(tempfile.mkdtemp(prefix="recovery-before-resume-", dir=backup_root)) / "files"
for path, entry, version in planned:
    if path.exists():
        saved = recovery / str(path).lstrip("/")
        saved.parent.mkdir(parents=True, exist_ok=True)
        before = path.read_bytes()
        saved.write_bytes(before)
        saved.chmod(path.stat().st_mode & 0o777)
        if saved.read_bytes() != before:
            raise SystemExit(f"backup did not verify: {saved}")
    if not version["exists"]:
        path.unlink(missing_ok=True)
        continue
    encoded = version.get("bytes_b64")
    if not isinstance(encoded, str):
        raise SystemExit(f"journal records only a digest for existing input; restore it from an exact external backup: {path}")
    body = base64.b64decode(encoded.encode("ascii"), validate=True)
    if hashlib.sha256(body).hexdigest() != version["sha256"]:
        raise SystemExit(f"journal after bytes are invalid: {path}")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(body)
            output.flush()
            os.fsync(output.fileno())
        mode = entry["mode"] if entry is not None else (path.stat().st_mode & 0o777 if path.exists() else 0o600)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
print(recovery)
PY
```

Resume the old journal with `agent-bios migrate --apply --yes`. After it commits,
restore only the preserved late record (`B`) from the printed recovery directory
to its original native path, then run a fresh `agent-bios migrate` preview and
`agent-bios migrate --apply --yes`. The new migration imports `B` through the
normal learning-id deduplication path. Leave every other recovery copy in place
as evidence; it is not an instruction to restore all saved native files.

```sh
RECOVERY_BACKUP='<the directory printed above>'
B="$HOME/.codex/personal/learnings.jsonl"  # the one path you deliberately preserved
cp "$RECOVERY_BACKUP/${B#/}" "$B"
agent-bios migrate
agent-bios migrate --apply --yes
```

## Installation and rollback

Installation and rollback validate the target baseline and personal field/member
changes together. Conflicts preserve the current selection rather than dropping
items from a successful snapshot. Installation publishes a complete corpus/config
association under the same lock used by readers. Pending publication is disclosed
by status and prevents a new configured launch from reading mixed state; bare and
pinned replay can use the last confirmed immutable release.

## Full reset

Full reset returns an `expected_revision` in its preview. Pass that value with
`--apply --yes`; a changed preview is refused. Retry the accepted revision to finish
an interrupted reset, or review and accept a fresh revision to replace a stale
reset intent. Later user changes and replacement credentials are not overwritten
by the old intent. Nonsecret settings are archived; token bytes never are.

Reset also clears individual on/off overrides and the active trophy display generation. It is not a deletion of uploaded learning records. See [corpus controls](corpus.md) and [learning discoveries](understand.md).
