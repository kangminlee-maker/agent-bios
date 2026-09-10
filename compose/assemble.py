#!/usr/bin/env python3
"""Per-selection assembler: canonical corpus + domains.json -> deployed trees.

Claude side (central-managed tree, overwritten on every run):
  <claude-dir>/central/bundle.md     core+infra+selected-domain bullets, the
                                     monolith's section structure preserved,
                                     guide references rewritten to central/guides/
  <claude-dir>/central/guides|hooks|agents/   audience-filtered copies
  <claude-dir>/settings.json         merge, not overwrite: entries whose hook
                                     command lives under central/hooks/ are
                                     central-owned (path IS the ownership
                                     marker); user-owned entries untouched
Entry file (<claude-dir>/CLAUDE.md) is personal-owned: seeded once when absent
(or when it byte-matches the legacy deployed monolith), read-checked otherwise
— never rewritten. Exit 2 = entry file needs user action.

Codex side: AGENTS.md central region between markers is replaced; text outside
the markers is preserved (weaker-guarantee realization; AGENTS.md has no
imports). Codex guides deploy filtered to <codex-dir>/guides as today.

env-personal is never assembled. The domains gate must be green first.
"""
import argparse
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
MARK_START = "<!-- agent-bios:central:start -->"
MARK_END = "<!-- agent-bios:central:end -->"
IMPORT_LINE = "@central/bundle.md"
PERSONAL_IMPORT_LINE = "@personal/learnings.md"
CLAUDE_VAR = "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CODEX_VAR = "${CODEX_HOME:-$HOME/.codex}"
CODEX_ONLY_PREFIX = "- Codex-only standing authorization:"
# Where that bullet belongs. Owned here because the payload cannot import from gates/,
# and `gates/emit-mirrors.py` — which pins the same position in the STATIC projection —
# imports it from this module instead, the same direction check-package.sh already takes
# for `author_only`. The two were independent before, and they disagreed: the projection
# put the bullet under this heading while the assembler appended it to the end of the
# bundle, so the deployed AGENTS.md filed a multi-model rule under whatever section
# happened to come last.
CODEX_ONLY_ANCHOR = "## Multi-Model Workflow"

ENTRY_SEED = f"""# CLAUDE.md

{IMPORT_LINE}
{PERSONAL_IMPORT_LINE}

## Personal
<!-- Yours. The installer never rewrites this file after seeding. The first
     import pulls in the centrally managed bundle; the second pulls in your
     session learning file ({CLAUDE_VAR}/personal/learnings.md — automation-owned,
     written by `learn!`). Add your own personal rules below. -->
"""

# Automation-owned personal learnings file, pulled in by PERSONAL_IMPORT_LINE.
# Kept in sync with learn/collect-learning.py (the light-flow submit tool),
# which appends learnings here; seeding it keeps the import from dangling.
PERSONAL_LEARNINGS_HEADER = """# Personal learnings

<!-- Automation-owned: written by the session learning flow (`learn!`,
     learn/collect-learning.py). Do NOT hand-edit — promote→migrate clears
     applied items by learning_id when the org redistributes them. Your own
     personal rules belong in the entry CLAUDE.md '## Personal' section, never
     here. This file is pulled into context by the entry file's
     `@personal/learnings.md` import. -->
"""


def die(msg, code=1):
    print(f"assemble: {msg}", file=sys.stderr)
    sys.exit(code)


def audience(entry):
    tier = entry.get("tier")
    if tier in ("core", "infra"):
        return "UNIVERSAL"
    if tier == "domain":
        return frozenset(entry.get("domains", []))
    return "NEVER"  # env-personal


def kept(entry, selection):
    aud = audience(entry)
    return aud == "UNIVERSAL" or (isinstance(aud, frozenset) and aud & selection)


def parse_monolith(text):
    """-> (title, [(header, [bullets])])"""
    title, sections, cur = None, [], None
    for ln in text.splitlines():
        if ln.startswith("# ") and title is None:
            title = ln
        elif ln.startswith("## "):
            cur = (ln, [])
            sections.append(cur)
        elif ln.startswith("- "):
            if cur is None:
                die("bullet before first section header")
            cur[1].append(ln)
    return title, sections


def place_codex_only(bundle, bullet):
    """Put the Codex-only bullet first under CODEX_ONLY_ANCHOR, or refuse.

    Appending was the old behaviour and it is what put a multi-model rule under Session
    Learning in every deployed AGENTS.md: the bundle's sections are whatever the selection
    kept, so "the end" is a different heading depending on what the user installed.

    Refuses rather than falling back to appending. The bullet is only added when
    `multi-agent-orchestration` is selected, and that domain is what carries the anchor
    heading, so a missing anchor means the bundle is not the shape this rule assumes —
    quietly filing the rule somewhere else is how the defect looked in the first place.
    """
    lines = bundle.split("\n")
    hits = [i for i, line in enumerate(lines) if line == CODEX_ONLY_ANCHOR]
    if len(hits) != 1:
        die(f"codex bundle must hold exactly one {CODEX_ONLY_ANCHOR!r} to place "
            f"{CODEX_ONLY_PREFIX!r} under; found {len(hits)}")
    index = hits[0] + 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    lines.insert(index, bullet)
    return "\n".join(lines)


def build_bundle(monolith_text, manifest, selection, tool):
    entry_of = {}
    for e in manifest["bullets"]:
        entry_of[e["anchor"]] = e
    title, sections = parse_monolith(monolith_text)
    out, kept_anchors = [], set()
    out.append(title if tool == "claude" else "# AGENTS.md")
    for header, bullets in sections:
        keep = []
        for b in bullets:
            matches = [a for a in entry_of if a in b]
            if len(matches) != 1:
                die(f"bullet has {len(matches)} manifest anchors (gate should have failed): {b[:60]!r}")
            if kept(entry_of[matches[0]], selection):
                keep.append(b)
                kept_anchors.add(matches[0])
        if keep:
            out.extend(["", header, ""])
            out.extend(keep)
    text = "\n".join(out) + "\n"
    if tool == "claude":
        text = text.replace(f"{CLAUDE_VAR}/guides/", f"{CLAUDE_VAR}/central/guides/")
        # Canary marker: a plain, verbatim-quotable line the activation canary
        # asks a live session to echo back — proves the bundle entered context.
        import hashlib
        rev = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
        text += f"\nagent-bios-bundle-rev: {rev}\n"
    else:
        text = text.replace(CLAUDE_VAR, CODEX_VAR)
    expected = {e["anchor"] for e in manifest["bullets"] if kept(e, selection)}
    if kept_anchors != expected:
        die(f"extracted set != manifest expectation ({len(kept_anchors)} vs {len(expected)}): "
        	f"missing={sorted(expected - kept_anchors)[:3]} extra={sorted(kept_anchors - expected)[:3]}")
    return text, len(kept_anchors)


def filtered_files(manifest, key, selection):
    return sorted(n for n, e in manifest.get(key, {}).items() if kept(e, selection))


def author_only(path):
    """Does this file's own frontmatter say it is for the corpus author?

    A guide declaring `audience: author` documents a step only the author can
    perform, and names repository paths that exist in a checkout and nowhere
    else. The tier says who NEEDS the subject; this says who can ACT on it, and
    the two are independent — the distill workflow is `infra`, so tier alone
    delivered it to every selection.

    The declaration in the file is the authority, deliberately not restated in
    `domains.json`: a second copy is one more thing that can disagree, and until
    this read existed the label was consumed only by the gate that the label
    exempts. A clone is a checkout, so `install.sh`'s non-packaged path still
    deploys these; this filter is the packaged one.

    THE single reader of that declaration. `gates/check-package.sh` imports this
    rather than parsing the frontmatter again: the gate tolerates references that
    only this withholding makes safe, so a second parser drifting from this one
    would exempt a file the assembler still installs — precisely the defect the
    pair exists to close. The direction is fixed: author-side may import shipped
    code, never the reverse, because the payload cannot depend on `gates/`.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if not text.startswith("---\n"):
        return False
    front = text.split("---\n", 2)[1]
    return any(ln.split(":", 1)[1].strip() == "author"
               for ln in front.splitlines() if ln.startswith("audience:"))


class GuideMemberError(ValueError):
    """A guide source tree does not have the primary-plus-companions shape."""


def _guide_primaries(root):
    """Return the top-level primary Markdown files after validating `root`.

    A guide is one manifest item even when it has resources.  Its primary remains the
    top-level ``<name>.md`` and its optional resource tree is exactly ``<name>/``.  This
    small structural contract lets delivery and every author-side consumer agree on the
    member set without adding a second manifest entry for each resource.

    The source is shipped verbatim for non-Markdown resources, so accepting a symlink
    (or a FIFO/device) would make the shipped package's bytes depend on the checkout at
    copy time.  Refuse those shapes before a caller starts copying anything.
    """
    if root.is_symlink() or not root.is_dir():
        raise GuideMemberError(f"guide root must be a real directory: {root}")
    primaries = []
    entries = sorted(root.iterdir(), key=lambda p: p.name)
    for path in entries:
        if path.is_symlink():
            raise GuideMemberError(f"guide source must not contain symlinks: {path}")
        if path.is_file():
            if path.suffix != ".md":
                raise GuideMemberError(
                    f"unsupported top-level guide resource {path}; companion resources belong "
                    f"under a same-stem directory")
            primaries.append(path.name)
            continue
        if path.is_dir():
            primary = root / f"{path.name}.md"
            if not primary.is_file() or primary.is_symlink():
                raise GuideMemberError(
                    f"orphan guide companion tree {path}; expected primary {primary.name}")
            continue
        raise GuideMemberError(f"unsupported guide source path: {path}")
    if not primaries:
        raise GuideMemberError(f"guide root has no primary Markdown files: {root}")
    return primaries


def _tree_members(root):
    """Return regular-file members under `root`, refusing every other entry type."""
    out = []
    for path in sorted(root.iterdir(), key=lambda p: p.name):
        if path.is_symlink():
            raise GuideMemberError(f"guide companion tree must not contain symlinks: {path}")
        if path.is_file():
            out.append(path)
        elif path.is_dir():
            children = _tree_members(path)
            if not children:
                raise GuideMemberError(f"empty guide companion directory: {path}")
            out.extend(children)
        else:
            raise GuideMemberError(f"unsupported guide companion path: {path}")
    return out


def guide_members(root: pathlib.Path, name: str) -> list[str]:
    """Return one guide item's source-relative files in deterministic order.

    ``name`` is the manifest's existing top-level ``*.md`` key.  The primary is first;
    optional companions live below ``Path(name).stem/`` and retain their relative path.
    Validating all top-level entries on every call intentionally catches an orphan companion
    tree even when the caller happens to ask about a different guide.
    """
    root = pathlib.Path(root)
    primaries = _guide_primaries(root)
    if name not in primaries or pathlib.PurePath(name).name != name or not name.endswith(".md"):
        raise GuideMemberError(f"guide primary {name!r} is not a top-level Markdown file in {root}")
    members = [name]
    companion = root / pathlib.Path(name).stem
    if companion.exists():
        if companion.is_symlink() or not companion.is_dir():
            raise GuideMemberError(f"guide companion {companion} must be a real directory")
        companion_members = _tree_members(companion)
        if not companion_members:
            raise GuideMemberError(f"empty guide companion tree: {companion}")
        members.extend(str(path.relative_to(root).as_posix()) for path in companion_members)
    return members


def guide_member_map(root: pathlib.Path) -> dict[str, list[str]]:
    """Every guide's exact source-relative member paths, keyed by its manifest key."""
    root = pathlib.Path(root)
    return {name: guide_members(root, name) for name in _guide_primaries(root)}


def copy_filtered(src_dir, names, dest, rewrite=None, dry=False, backup=None):
    """Write the selected files, and remove the ones we deployed and no longer select.

    Writing alone leaves the destination describing a selection nobody chose: a machine that
    took every domain and later narrowed to one kept the whole set on disk, so selection.json
    stopped describing what was deployed. merge_settings already drops a deselected hook's
    REGISTRATION through `owned_names`; this is the same reconciliation for the files.

    Ownership is "the name exists in our source tree", which is what keeps a file the user put
    in the same directory safe — it is not in `src_dir`, so it is never a candidate.
    """
    if not dry:
        dest.mkdir(parents=True, exist_ok=True)
    keep_names = set(names)
    if dest.is_dir() and src_dir.is_dir():
        ours = {p.name for p in src_dir.iterdir() if p.is_file()}
        for path in sorted(dest.iterdir()):
            if not path.is_file() or path.name in keep_names or path.name not in ours:
                continue
            print(f"  {'[dry] ' if dry else ''}deselected, removed {path}")
            if dry:
                continue
            # Backed up first, the way every other removal here is: these are copies of repo
            # content, but a machine offline from the repo has no other way back.
            if backup is not None:
                kept = backup / "deselected" / str(path).lstrip("/")
                kept.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, kept)
            path.unlink()
    for n in names:
        if dry:
            print(f"  [dry] copy {n} -> {dest}")
            continue
        body = (src_dir / n).read_text(encoding="utf-8")
        if rewrite:
            body = body.replace(*rewrite)
        target = dest / n
        # Replacing is as destructive as removing, and README promises a copy of the exact
        # prior bytes under the state backup dir. install.sh's deploy_file kept that promise;
        # the assembler is the default path now, so writing straight over a guide the user had
        # edited broke it for every file it deploys. Identical content is not a replacement,
        # and copying it would fill the backup dir on every no-op reinstall.
        if backup is not None and target.is_file():
            try:
                changed = target.read_text(encoding="utf-8") != body
            except (OSError, UnicodeDecodeError):
                changed = True   # unreadable is not "unchanged"; keep the bytes
            if changed:
                kept = backup / "replaced" / str(target).lstrip("/")
                kept.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, kept)
        target.write_text(body, encoding="utf-8")


def _backup_member(path, backup, reason):
    """Keep a recoverable copy of one exact deployed member before changing it."""
    if backup is None:
        return
    kept = backup / reason / str(path).lstrip("/")
    kept.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, kept)


def validate_guide_destination_members(dest, members):
    """Refuse member paths that would traverse a symlink below the chosen guide root.

    ``dest`` itself is deliberately outside this check: a user may configure the whole
    guides root as a symlink, and that pre-existing top-level behavior is not claimed by a
    bundle.  A same-stem companion directory below it is different — following it would let
    an install replace or deselect a file outside the configured root.  Validate every
    source-owned member up front, including currently deselected ones, so no earlier member
    can be changed before a later nested path reveals the unsafe shape.
    """
    dest = pathlib.Path(dest)
    for rel in sorted(set(members)):
        target = dest / rel
        if target.is_symlink():
            die(f"refusing guide member destination symlink: {target}")
        ancestor = target.parent
        while ancestor != dest:
            if ancestor.is_symlink():
                die(f"refusing guide member ancestor symlink: {ancestor}")
            if ancestor.exists() and not ancestor.is_dir():
                die(f"guide member ancestor is not a directory: {ancestor}")
            ancestor = ancestor.parent


def prior_guide_candidates(prior_deployed, dest, current_members):
    """Former guide paths a prior manifest names but the current source does not.

    Historic manifests over-claimed guide directories, so a prior row is not deletion
    authority.  This parser only bounds the warning to the configured guide root; current
    source members retain the existing source-derived cleanup rule in ``copy_guide_members``.
    """
    dest = pathlib.Path(dest)
    current = set(current_members)
    candidates = set()
    for raw in prior_deployed:
        if not raw or "\0" in raw:
            continue
        try:
            path = pathlib.Path(raw)
        except (TypeError, ValueError):
            continue
        if not path.is_absolute():
            continue
        try:
            rel = path.relative_to(dest)
        except ValueError:
            continue
        # `relative_to` is lexical and preserves `..`; never allow a handcrafted manifest
        # row to escape the configured root when the target path is joined below.
        if not rel.parts or any(part in ("", ".", "..") for part in rel.parts):
            continue
        rel_text = rel.as_posix()
        if rel_text not in current:
            candidates.add(rel_text)
    return sorted(candidates)


def disclose_prior_guide_remnants(dest, candidates, dry=False):
    """Report, but never alter, prior-only guide paths that remain on disk.

    The existing installer keeps the previous manifest as its recovery record.  A user can
    inspect that record and remove a remnant manually if it is known to be old product data;
    this assembler cannot safely distinguish that case from a user-created same-named file.
    """
    dest = pathlib.Path(dest)
    for rel in sorted(set(candidates)):
        target = dest / rel
        # Inspect existence only. A link is also a remnant for manual review; never open
        # or modify its target as part of this disclosure.
        if not target.exists() and not target.is_symlink():
            continue
        print(f"  {'[dry] ' if dry else ''}prior guide remnant left in place: {target}")
        print("    inspect it and remove it manually if it is an obsolete agent-bios resource")


def copy_guide_members(src_dir, names, dest, rewrite=None, dry=False, backup=None):
    """Copy selected guide bundles and reconcile only their exact source members.

    A companion directory is not an ownership boundary: it may contain a file a user added
    after installation.  Membership is therefore resolved from the source tree and every
    replace/deselect action is addressed to one known file path.  Empty directories are left
    behind deliberately; an installer can remove them with ``rmdir`` only after all manifest
    owned members are gone.

    Markdown is rewritten only where the old file-only guide path already was.  Other regular
    files are copied byte-for-byte (and with their mode) so scripts and render assets remain
    one source of truth rather than becoming text projections.
    """
    src_dir = pathlib.Path(src_dir)
    dest = pathlib.Path(dest)
    all_members = guide_member_map(src_dir)
    unknown = set(names) - set(all_members)
    if unknown:
        die(f"selected guide(s) not found in source tree: {sorted(unknown)}")
    owned = {member for members in all_members.values() for member in members}
    selected = {member for name in names for member in all_members[name]}
    validate_guide_destination_members(dest, owned)
    if not dry:
        dest.mkdir(parents=True, exist_ok=True)

    # Deselecting a guide means deleting files, never a same-named directory wholesale.
    # The latter would claim a user's nested note merely because it shares our guide stem.
    for rel in sorted(owned - selected):
        target = dest / rel
        if not target.is_file():
            continue
        print(f"  {'[dry] ' if dry else ''}deselected, removed {target}")
        if dry:
            continue
        _backup_member(target, backup, "deselected")
        target.unlink()

    for rel in sorted(selected):
        source = src_dir / rel
        target = dest / rel
        if dry:
            print(f"  [dry] copy {rel} -> {dest}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == ".md":
            body = source.read_text(encoding="utf-8")
            if rewrite:
                body = body.replace(*rewrite)
            changed = True
            if target.is_file():
                try:
                    changed = target.read_text(encoding="utf-8") != body
                except (OSError, UnicodeDecodeError):
                    changed = True
            if changed and target.is_file():
                _backup_member(target, backup, "replaced")
            if changed:
                target.write_text(body, encoding="utf-8")
            continue

        # Read the bytes directly.  `filecmp` caches stat signatures, which can report a
        # same-size rewrite clean on filesystems whose mtime granularity is coarse; source
        # code is small and byte identity is the contract here.
        changed = not target.is_file() or source.read_bytes() != target.read_bytes()
        if changed and target.is_file():
            _backup_member(target, backup, "replaced")
        if changed:
            shutil.copy2(source, target)


def replace_atomically(path, text):
    """Write via a temp file + os.replace, so a write that fails partway cannot truncate.

    Every file this is used on is one the USER owns and edits — their settings.json, their
    AGENTS.md — and a plain write_text truncates first and fills after. A short write (a full
    disk, a crash) left AGENTS.md holding a fragment of our marker and none of their text,
    with no copy in reach: the backup taken beside these calls is of the PREVIOUS content,
    which is exactly what a half-written file destroys the value of.

    learn/migrate-learnings.py has had this discipline and states the reason; it now shares
    this one implementation rather than keeping a second. The temp file is a sibling so the
    replace stays on one filesystem, where os.replace is atomic.

    An existing target's permission bits ride through the swap: the temp is born with
    umask mode, so replacing a user-restricted file — a 0600 AGENTS.md — silently widened
    it to world-readable. Ownership is not copied; this never runs with the privilege to
    change it, and a same-owner rename keeps it anyway.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-agent-bios")
    try:
        tmp.write_text(text, encoding="utf-8")
        if path.exists():
            tmp.chmod(path.stat().st_mode & 0o777)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def hook_command_matches(command, name):
    """Does an argv TOKEN of this command end in `/hooks/<name>`?

    One matcher for the merge below AND the domain gate's settings leg — the gate used a
    substring test, so `central/hooks/<name>.disabled` passed the gate while this merge
    skipped it, and the install carried no hook under a green gate.

    Split as a shell would, not delimited by spaces. The registration this file writes is
    `shlex.quote`d so a config home containing a space works, and the quoting puts a `'`
    right after the filename — so a matcher wanting end-of-string or a following space
    could not recognize the line it had just written, and every reinstall on a
    `/Users/First Last` home appended another copy of the same hook. Splitting the way the
    shell will is the only reading that survives its own quoting.

    Still a PATH match and never a bare name: `wrap.py --inner <name>` passes the name as
    an argument to somebody else's wrapper, and deleting a stranger's hook is not a right
    this ownership rule ever claimed."""
    try:
        tokens = shlex.split(command)
    except ValueError:            # unbalanced quotes: not a command we wrote
        tokens = command.split()
    return any(token.endswith("/hooks/" + name) for token in tokens)


def merge_settings(claude_dir, hook_names, template_path, dry=False, owned_names=None):
    """Merge our hook registrations into the user's settings, owning by NAME.

    `hook_names` is what to register now (the selection); `owned_names` is every
    hook the manifest declares, which is what we may remove. Ownership is the
    manifest name rather than a path marker because the same hook has lived at
    two paths — `<claude>/hooks/` on the old full-install layout and
    `central/hooks/` now — and a path-marker drop would leave the old entry
    behind, registering the hook twice after the move. Dropping every declared
    name and re-adding only the selected ones also makes deselection work.

    Entries we do not own are never touched: `<claude>/hooks/` is shared with
    other tools' hooks and state.
    """
    owned = set(owned_names if owned_names is not None else hook_names)
    spath = claude_dir / "settings.json"
    existed = spath.exists()
    settings = json.loads(spath.read_text(encoding="utf-8")) if existed else {}
    template = json.loads(template_path.read_text(encoding="utf-8")) if template_path.exists() else {}
    hooks = settings.setdefault("hooks", {})

    def ours(hook):
        # The same matcher the re-add below uses, which `hook_command_matches` already
        # describes itself as being ("one matcher for the merge below AND the domain
        # gate"). Only the ADD half honoured that; removal asked whether the name appeared
        # anywhere in the command, so a user's own entry was deleted for mentioning ours —
        # `wrap.py --inner tooling-gotchas-hook.py`, a `.bak` copy, a directory named after
        # it. Deleting a stranger's hook out of their settings is not something the
        # ownership rule above ever claimed the right to do.
        return any(hook_command_matches(hook.get("command", ""), n) for n in owned)

    # Pruned per HOOK, not per entry. Ownership is a name on one command, and the entry is
    # a matcher that can hold several — so `{"matcher": "Bash", "hooks": [ours, theirs]}`
    # answered "ours" and took the stranger's hook with it. That is the same overreach the
    # matcher above was narrowed to stop, one level up: the granularity of the removal has
    # to match the granularity of the claim. An entry left with no hooks was only ever ours,
    # so it still goes whole.
    for event, entries in list(hooks.items()):
        pruned = []
        for en in entries:
            children = en.get("hooks") if isinstance(en, dict) else None
            if not isinstance(children, list):
                pruned.append(en)          # not a shape we wrote; not ours to judge
                continue
            keep = [h for h in children if not (isinstance(h, dict) and ours(h))]
            if len(keep) == len(children):
                pruned.append(en)          # nothing of ours in it — untouched
            elif keep:
                en["hooks"] = keep         # ours dropped, their siblings stay where they are
                pruned.append(en)
        hooks[event] = pruned
    for event, entries in template.get("hooks", {}).items():  # re-add per selection
        for en in entries:
            cmds = [h.get("command", "") for h in en.get("hooks", [])]
            owner = next((n for n in hook_names
                          if any(hook_command_matches(c, n) for c in cmds)), None)
            if owner is None:
                continue
            clone = json.loads(json.dumps(en))
            for h in clone.get("hooks", []):
                # Quoted, because this lands in a shell command line. A config home with a
                # space in it — `/Users/First Last/.claude` — split into separate argv
                # words, so the shell tried to run `/Users/First` and the deployed hook
                # simply never fired. Nothing reported it: a hook that does not run looks
                # exactly like a hook with nothing to say.
                #
                # A function replacement rather than a string one: shlex.quote emits
                # backslashes for some paths and re.sub reads those as group references in
                # a replacement string.
                target = shlex.quote(str(claude_dir / "central" / "hooks" / owner))
                h["command"] = re.sub(r"\S*/hooks/" + re.escape(owner),
                                      lambda _match, value=target: value,
                                      h["command"])
            hooks.setdefault(event, []).append(clone)
    if dry:
        print(f"  [dry] merge settings.json ({len(hook_names)} central hooks)")
        return
    if not existed and not any(hooks.values()):
        # Nothing of ours to register and no file to preserve. Writing one would create a
        # settings.json the user did not have — and this branch is reached by uninstall on a
        # machine where the claude dir is gone, where creating the directory to hold it
        # crashed on a missing parent instead.
        return
    if existed:
        shutil.copy2(spath, spath.with_suffix(f".json.bak-{time.strftime('%Y%m%d-%H%M%S')}"))
    replace_atomically(spath, json.dumps(settings, indent=2, ensure_ascii=False) + "\n")


def seed_personal_learnings(claude_dir, dry=False):
    """Create the automation-owned personal learnings file when seeding the entry,
    so the entry's @personal/learnings.md import always resolves before the first
    learn!. learn/collect-learning.py appends to it thereafter."""
    md = claude_dir / "personal" / "learnings.md"
    if md.exists():
        return
    if dry:
        print("  [dry] seed personal/learnings.md")
        return
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(PERSONAL_LEARNINGS_HEADER, encoding="utf-8")


def seed_entry(claude_dir, legacy_monolith, prior_deployed=(), dry=False):
    """Seed the entry, and never rewrite a file the user wrote.

    Telling those apart used to be a byte-comparison against THIS commit's monolith, which
    recognizes only a re-install of the same release. Anyone upgrading from an earlier one had
    that release's monolith on disk — our file, not theirs — and it was reported as user-owned,
    so the import line was never added and the corpus did not load until they edited it by hand.

    `prior_deployed` is the previous install's manifest, which is the repo's existing answer to
    "did we write this": deploy_file records every destination it writes, and the pre-unification
    full install deployed the entry through it. Ownership is read the same way it was written.
    """
    entry = claude_dir / "CLAUDE.md"
    if not entry.exists():
        if dry:
            print("  [dry] seed entry CLAUDE.md")
            seed_personal_learnings(claude_dir, dry)
            return "seeded"
        claude_dir.mkdir(parents=True, exist_ok=True)
        entry.write_text(ENTRY_SEED, encoding="utf-8")
        seed_personal_learnings(claude_dir, dry)
        return "seeded"
    body = entry.read_text(encoding="utf-8")
    if IMPORT_LINE in body:
        return "ok"
    # Ours by content (a re-install of this release) OR by record (any earlier one).
    # Both sides go through pathlib first: the manifest is written by shell, so a config dir
    # with a trailing or doubled slash lands in it verbatim, and raw string equality then
    # misses a path that is the same file.
    if body == legacy_monolith or str(pathlib.Path(entry)) in prior_deployed:
        if dry:
            print("  [dry] replace legacy deployed CLAUDE.md with seed (backup)")
            seed_personal_learnings(claude_dir, dry)
            return "seeded"
        shutil.copy2(entry, entry.with_suffix(f".md.bak-legacy-{time.strftime('%Y%m%d-%H%M%S')}"))
        entry.write_text(ENTRY_SEED, encoding="utf-8")
        seed_personal_learnings(claude_dir, dry)
        return "seeded"
    return "needs-action"  # user content without the import line: report, never rewrite


def merge_codex(codex_dir, central_text, prior_deployed=(), dry=False):
    """Write the central region into AGENTS.md, and never silence a file the user wrote.

    A missing marker pair used to mean "legacy whole-file deploy", so any AGENTS.md without
    them had its active body replaced by the region plus an empty `## Personal`. Every Codex
    user who wrote an AGENTS.md before installing has exactly that file, and their
    instructions stopped loading on the first install — the backup made it recoverable, not
    noticed. Absence of a marker is absence of evidence, in both directions.

    So the same evidence seed_entry uses on the Claude side decides it here: `prior_deployed`
    is the previous install's manifest, and a path in it is ours by record. Anything else is
    theirs, and the markers are adopted ABOVE their text rather than over it — which is what
    the marker pair is for, and it leaves nothing of theirs unloaded. Nothing is lost that
    way, so that branch needs no backup; the by-record branch keeps the one it always had.
    """
    agents = codex_dir / "AGENTS.md"
    region = f"{MARK_START}\n{central_text}{MARK_END}\n"
    if agents.exists():
        body = agents.read_text(encoding="utf-8")
        if MARK_START in body and MARK_END in body:
            pre, rest = body.split(MARK_START, 1)
            _, post = rest.split(MARK_END, 1)
            new = pre + region + post
        elif str(pathlib.Path(agents)) in prior_deployed:
            # Ours by record: an earlier release deployed this file whole, so replacing it
            # with the marked shape is the upgrade, not a loss.
            if not dry:
                shutil.copy2(agents, agents.with_suffix(f".md.bak-legacy-{time.strftime('%Y%m%d-%H%M%S')}"))
            new = region + "\n## Personal\n"
        else:
            new = region + "\n" + body.lstrip("\n")
    else:
        new = region + "\n## Personal\n"
    if dry:
        print(f"  [dry] write AGENTS.md central region ({len(central_text)} bytes)")
        return
    codex_dir.mkdir(parents=True, exist_ok=True)
    replace_atomically(agents, new)


def remove_owned(claude_dir, codex_dir, manifest, dry=False):
    """Undo the two spans this file writes into files it does not own.

    Every merge here needs a matching removal, and for a long time these two did not have one:
    uninstall deleted the deployed hook FILES while leaving their registrations in the user's
    settings.json, and deleted the guides while leaving the AGENTS.md central region that
    references them. The user was left with hooks invoking missing paths and instructions
    pointing at deleted files, after a command that reported success.

    Ownership is read the same way it is written — `merge_settings` owning by manifest NAME, and
    the marker pair for the Codex region — so removal can never reach further than the merge did.
    Text outside the markers, and settings entries this repo did not register, are untouched.
    """
    owned = sorted({h for h in manifest.get("hooks", {})})
    merge_settings(claude_dir, [], REPO / "claude" / "settings.template.json",
                   dry=dry, owned_names=owned)

    agents = codex_dir / "AGENTS.md"
    if not agents.is_file():
        return
    body = agents.read_text(encoding="utf-8")
    if MARK_START not in body or MARK_END not in body:
        return  # nothing of ours in there; a whole-file legacy deploy is not ours to judge
    pre, rest = body.split(MARK_START, 1)
    _, post = rest.split(MARK_END, 1)
    if dry:
        print("  [dry] strip AGENTS.md central region, keep everything outside the markers")
        return
    replace_atomically(agents, (pre + post).lstrip("\n"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--remove-owned", action="store_true",
                    help="undo the settings registrations and the AGENTS.md central region "
                         "(uninstall's half of the merge); writes nothing else")
    ap.add_argument("--domains", help="comma-separated selection; overrides selection.json")
    ap.add_argument("--claude-dir", default=None)
    ap.add_argument("--codex-dir", default=None)
    ap.add_argument("--state-dir", default=None)
    ap.add_argument("--prior-manifest", default=None,
                    help="the previous install's manifest. Ownership of the entry file is read "
                         "from it, so an earlier release's deployed CLAUDE.md is recognized as "
                         "ours instead of being reported as the user's.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selected-skills", action="store_true",
                    help="print the names of the shipped skills the selection delivers, one "
                         "per line, and write nothing. install.sh deploys skills itself (a "
                         "skill is a tree the HOST scans, not a file under central/) and asks "
                         "here which ones, so the selection rule keeps one owner")
    args = ap.parse_args()

    import os
    claude_dir = pathlib.Path(args.claude_dir or os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude")
    codex_dir = pathlib.Path(args.codex_dir or os.environ.get("CODEX_HOME") or pathlib.Path.home() / ".codex")
    state_dir = pathlib.Path(args.state_dir or pathlib.Path.home() / ".local/share/agent-bios")

    if args.remove_owned:
        # No domains gate: removal does not depend on the manifest being well-formed, and an
        # uninstall that refuses to run because the corpus is mid-edit would strand the user.
        # That was the claim; the parse sat ABOVE this branch and ran first, so a malformed
        # domains.json raised out of uninstall before the branch that does not need it. The
        # two halves of the removal need it differently: the Codex region is bounded by our
        # markers and needs nothing, while the settings registrations are owned BY NAME and
        # cannot be found without it. So the region goes either way, and a manifest we cannot
        # read makes the registration half impossible rather than skippable — the caller has
        # to hear that, not read a clean summary over it.
        try:
            manifest = json.loads((REPO / "compose" / "domains.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            remove_owned(claude_dir, codex_dir, {"hooks": {}}, dry=args.dry_run)
            die(f"the AGENTS.md central region was removed, but {REPO / 'compose' / 'domains.json'} "
                f"could not be read ({exc}) — the hook registrations it names are STILL in "
                f"settings.json. Restore that file and re-run uninstall.")
        remove_owned(claude_dir, codex_dir, manifest, dry=args.dry_run)
        return

    manifest = json.loads((REPO / "compose" / "domains.json").read_text(encoding="utf-8"))

    gate = subprocess.run([sys.executable, str(REPO / "compose" / "check-domains.py")],
                          capture_output=True, text=True)
    if gate.returncode != 0:
        die("domains gate FAILED — fix manifest/corpus first:\n" + gate.stdout + gate.stderr)
    if args.domains is not None:
        selection = frozenset(d for d in args.domains.split(",") if d)
    else:
        sel_file = state_dir / "selection.json"
        if not sel_file.exists():
            die(f"no --domains and no {sel_file}; run onboarding or pass --domains")
        selection = frozenset(json.loads(sel_file.read_text(encoding="utf-8"))["domains"])
    unknown = selection - set(manifest["domains"])
    if unknown:
        die(f"unknown domains: {sorted(unknown)} (known: {sorted(manifest['domains'])})")

    if args.selected_skills:
        # The same two rules the guides get: the manifest's audience, then the file's own
        # `audience: author` declaration — the gate that tolerates author-side paths in a
        # declared file assumes the assembler withholds it, and a skill deployed by
        # install.sh from this list must keep that assumption true.
        for name in filtered_files(manifest, "skills", selection):
            if not author_only(REPO / "claude" / "skills" / name / "SKILL.md"):
                print(name)
        return

    monolith = (REPO / "claude" / "CLAUDE.md").read_text(encoding="utf-8")
    bundle, n_bullets = build_bundle(monolith, manifest, selection, "claude")
    codex_src = (REPO / "codex" / "AGENTS.md").read_text(encoding="utf-8")
    codex_bundle, _ = build_bundle(monolith, manifest, selection, "codex")
    if "multi-agent-orchestration" in selection:
        codex_only = next((ln for ln in codex_src.splitlines() if ln.startswith(CODEX_ONLY_PREFIX)), None)
        if codex_only:
            codex_bundle = place_codex_only(codex_bundle, codex_only)

    guide_source = REPO / "claude" / "guides"
    guide_sources = guide_member_map(guide_source)
    codex_guide_sources = guide_member_map(REPO / "codex" / "guides")
    if set(guide_sources) != set(codex_guide_sources):
        die("Claude and Codex guide primary sets differ; regenerate mirrors before assembling")
    for name, members in guide_sources.items():
        if members != codex_guide_sources[name]:
            die(f"Claude and Codex guide members differ for {name}; regenerate mirrors before assembling")
    prior_deployed = set()
    if args.prior_manifest:
        prior = pathlib.Path(args.prior_manifest)
        if prior.is_file():
            prior_deployed = {str(pathlib.Path(ln.strip())) for ln in
                              prior.read_text(encoding="utf-8").splitlines() if ln.strip()}
    current_guide_members = [member for members in guide_sources.values() for member in members]
    current_codex_guide_members = [member for members in codex_guide_sources.values() for member in members]
    prior_claude_candidates = prior_guide_candidates(
        prior_deployed, claude_dir / "central" / "guides", current_guide_members)
    prior_codex_candidates = prior_guide_candidates(
        prior_deployed, codex_dir / "guides", current_codex_guide_members)
    # Do this before withheld cleanup, bundle.md, or any guide copy.  A companion ancestor
    # can be a symlink even when its leaf is an ordinary file; checking leaf targets only
    # would then write outside the selected guides root before the unsafe path was noticed.
    validate_guide_destination_members(
        claude_dir / "central" / "guides",
        current_guide_members,
    )
    validate_guide_destination_members(
        codex_dir / "guides",
        current_codex_guide_members,
    )
    guides = filtered_files(manifest, "guides", selection)
    withheld = [n for n in guides if author_only(guide_source / n)]
    guides = [n for n in guides if n not in withheld]
    # Not writing it is not enough for anyone who installed before this rule: the
    # manifest is rebuilt from the current deploy, so a file that stops being
    # deployed stops being tracked and would sit there for good.
    stale = [d / member for n in withheld for member in guide_sources[n]
             for d in (claude_dir / "central" / "guides", codex_dir / "guides")
             if (d / member).is_file()]
    # Copy before removing, the way install.sh backs up a file it replaces. The
    # name matching ours does not prove we wrote it — a shared or symlinked guides
    # directory can hold somebody's own file under the same name, and a deleted
    # one is not recoverable from anywhere else.
    # One timestamped directory per run, with a subdirectory per reason for the removal:
    # `withheld` is an audience decision, `deselected` is a selection change.
    run_backup = state_dir / "backups" / time.strftime("%Y%m%d-%H%M%S")
    backup = run_backup / "withheld"
    # A source release can remove one resource while retaining its primary guide.  Prior
    # manifests have historically included user files below these roots, so they disclose
    # candidates only; the source-derived member list remains the sole deletion authority.
    disclose_prior_guide_remnants(claude_dir / "central" / "guides", prior_claude_candidates,
                                  dry=args.dry_run)
    disclose_prior_guide_remnants(codex_dir / "guides", prior_codex_candidates,
                                  dry=args.dry_run)
    for path in stale:
        print(f"  {'[dry] ' if args.dry_run else ''}remove withheld {path}")
        if not args.dry_run:
            keep = backup / str(path).lstrip("/")
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, keep)
            path.unlink()
    hooks = filtered_files(manifest, "hooks", selection)
    agents = filtered_files(manifest, "agents", selection)
    dry = args.dry_run

    central = claude_dir / "central"
    if dry:
        print(f"[dry] bundle.md: {n_bullets} bullets; guides={guides} hooks={hooks} agents={agents}")
        if withheld:
            print(f"  [dry] withheld (audience: author): {withheld}")
    else:
        central.mkdir(parents=True, exist_ok=True)
        (central / "bundle.md").write_text(bundle, encoding="utf-8")
    copy_guide_members(guide_source, guides, central / "guides",
                       rewrite=(f"{CLAUDE_VAR}/guides/", f"{CLAUDE_VAR}/central/guides/"),
                       dry=dry, backup=run_backup)
    copy_filtered(REPO / "claude" / "hooks", hooks, central / "hooks", dry=dry, backup=run_backup)
    copy_filtered(REPO / "claude" / "agents", agents, central / "agents", dry=dry,
                  backup=run_backup)
    merge_settings(claude_dir, hooks, REPO / "claude" / "settings.template.json", dry=dry,
                   owned_names=manifest.get("hooks", {}))   # deselected hooks must drop too
    entry_state = seed_entry(claude_dir, monolith, prior_deployed, dry=dry)

    merge_codex(codex_dir, codex_bundle, prior_deployed, dry=dry)
    copy_guide_members(REPO / "codex" / "guides", guides, codex_dir / "guides", dry=dry,
                       backup=run_backup)

    if not dry:
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "selection.json").write_text(
            json.dumps({"version": 1, "domains": sorted(selection)}, indent=2) + "\n", encoding="utf-8")

    print(f"ASSEMBLED: {n_bullets} bullets, {len(guides)} guides, {len(hooks)} hooks, "
          f"{len(agents)} agents for selection {sorted(selection)}; entry={entry_state}"
          + (f"; withheld {len(withheld)} author-only guide(s): {', '.join(withheld)}"
             if withheld else ""))
    if entry_state == "needs-action":
        print(f"ACTION NEEDED: {claude_dir / 'CLAUDE.md'} is user-owned and lacks '{IMPORT_LINE}' — "
              "add the import line manually; the installer will not rewrite your file.")
        sys.exit(2)


if __name__ == "__main__":
    main()
