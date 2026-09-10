#!/usr/bin/env python3
"""Emit the Codex-side mirror trees from the Claude-side canonical.

`codex/` and `ko/codex/` are projections, not independently edited copies: every
file in them is derived from its `claude/` or `ko/claude/` counterpart by one
config-home substitution, a title rewrite on the global, and the one declared
Codex-only bullet the host trigger contract requires. Generating them makes a
one-sided hand edit impossible instead of merely detectable, and puts the
projection rule in one place — this file — instead of splitting it between
README prose, the parity gate's normalization, and the editor's fingers.

Not shipped: author-side only, like the other repo-checkout gates. `codex/agents/*.toml`
is Codex-only content with no Claude counterpart and is not a projection.

  (no args) / --write   regenerate the mirror trees in place
  --check               fail if any mirror file differs from its projection
  --self-test           negative controls: prove --check fails on each drift kind
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import sys
import tempfile
import tomllib

REPO = pathlib.Path(__file__).resolve().parents[1]

CONFIG_SRC = "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CONFIG_DST = "${CODEX_HOME:-$HOME/.codex}"
GLOBAL_SRC_TITLE = "# CLAUDE.md"
GLOBAL_DST_TITLE = "# AGENTS.md"

# Imported, not restated. This projector and compose/assemble.py both decide where the
# Codex-only bullet goes — one for the static codex/ tree, one for what a user actually
# receives — and while each held its own copy they disagreed in the direction nobody
# reads: the tracked file was right and every deployed AGENTS.md filed the rule under
# Session Learning. Author-side imports shipped, never the reverse, the same direction
# check-package.sh takes for `author_only`.
sys.path.insert(0, str(REPO / "compose"))
from assemble import (  # noqa: E402
    CODEX_ONLY_ANCHOR as ANCHOR_HEADING,
    GuideMemberError,
    guide_member_map,
)

# The single declared Codex-only addition. Codex's trigger contract needs the
# standing dispatch authorization stated in the global itself; Claude's does not.
AUTHORIZATION = {
    "en": (
        "- Codex-only standing authorization: on root/main local tasks, ordinary subagent dispatch is "
        "authorized when the `When To Spawn` gates fire. Explicit no-fan-out wins. Delegated agents may "
        "re-delegate only when their role allows. This grants no destructive, remote, credential, install, "
        "OAuth, push, live-network-expanding, or broader-sandbox authority."
    ),
    "ko": (
        "- Codex-only standing authorization: root/main local task에서 `When To Spawn` gate가 발동하면 "
        "ordinary subagent dispatch를 상시 허용한다. Explicit no-fan-out이 우선하며 delegated agent는 role이 "
        "허용할 때만 재위임한다. 이는 destructive, remote, credential, install, OAuth, push, "
        "live-network-expanding, broader-sandbox authority를 주지 않는다."
    ),
}

# (claude-side root, codex-side root, language)
TREES = (
    ("claude", "codex", "en"),
    ("ko/claude", "ko/codex", "ko"),
)


class ProjectionError(RuntimeError):
    """The source does not have the shape the projection rule requires."""


def project_guide(text: str) -> str:
    """A guide differs only by the config-home variable."""
    return text.replace(CONFIG_SRC, CONFIG_DST)


def project_global(text: str, bullet: str) -> str:
    """The global differs by title, config-home, and the one declared bullet.

    The bullet lands as the first item under `## Multi-Model Workflow`; pinning
    the position is what makes the check stricter than a presence grep."""
    lines = text.replace(CONFIG_SRC, CONFIG_DST).split("\n")
    if not lines or lines[0] != GLOBAL_SRC_TITLE:
        raise ProjectionError(f"global must start with {GLOBAL_SRC_TITLE!r}, found {lines[0]!r}")
    lines[0] = GLOBAL_DST_TITLE
    hits = [i for i, line in enumerate(lines) if line == ANCHOR_HEADING]
    if len(hits) != 1:
        raise ProjectionError(f"global must hold exactly one {ANCHOR_HEADING!r}, found {len(hits)}")
    i = hits[0]
    if lines[i + 1] != "":
        raise ProjectionError(f"expected a blank line under {ANCHOR_HEADING!r}, found {lines[i + 1]!r}")
    lines.insert(i + 2, bullet)
    return "\n".join(lines)


def render_tree(root: pathlib.Path, src: str, dst: str, lang: str,
                members: dict[str, list[str]], immutable_assets: pathlib.Path | None = None) -> dict[str, bytes]:
    """Render one Codex mirror tree from logical guide members.

    Markdown is language-specific prose and receives the config-home substitution.  Every
    non-Markdown companion is an immutable English asset: it is copied as bytes, including to
    the Korean trees, so a translated guide never grows an independently edited script.
    """
    guide_root = root / src / "guides"
    out = {f"{dst}/AGENTS.md": project_global(
        (root / src / "CLAUDE.md").read_text(encoding="utf-8"), AUTHORIZATION[lang]).encode("utf-8")}
    for name, paths in members.items():
        for rel in paths:
            source = guide_root / rel
            if source.suffix == ".md":
                out[f"{dst}/guides/{rel}"] = project_guide(
                    source.read_text(encoding="utf-8")).encode("utf-8")
            else:
                asset_root = immutable_assets if immutable_assets is not None else guide_root
                out[f"{dst}/guides/{rel}"] = (asset_root / rel).read_bytes()
    return out


def render_config_additions(root: pathlib.Path) -> dict[str, str]:
    """The Codex config fragment's `[agents.*]` block, projected from the agent templates.

    Every field in it already has an owner: WHICH agents belong there is the launch profile's
    `[hosts.codex.agent_templates]`, each description is the template's own, and the config_file
    path is the deploy destination. It was authored by hand and compared by a parity check, which
    made the fragment a second author — the case the repo states as `PU-15` and the reason this
    file exists at all. Generating it means a one-sided edit is impossible rather than merely
    detected.

    Everything above `[agents.` is authored — the header comment and `features.multi_agent` are
    not projections of anything — so it is preserved verbatim rather than regenerated.
    """
    rel = "codex/config-additions.toml"
    lines = (root / rel).read_text(encoding="utf-8").splitlines(keepends=True)
    # Split on a LINE that opens the block, not on the substring: the authored header comment
    # says "[agents.*] tables", and partitioning on that text ate the header and the features
    # table. A table header is a line, so the rule is a line rule.
    start = next((i for i, ln in enumerate(lines) if ln.startswith("[agents.")), None)
    if start is None:
        raise ProjectionError(f"{rel} has no [agents.*] table to project")
    head = "".join(lines[:start])
    profile = tomllib.loads((root / "launch" / "agent-launch.toml").read_text(encoding="utf-8"))
    declared = ((profile.get("hosts", {}).get("codex") or {}).get("agent_templates") or {})
    if not declared:
        raise ProjectionError("launch profile declares no codex agent templates — projecting "
                              "an empty agents block would silently disable every subagent")
    blocks = []
    # Declaration order, not alphabetical: the profile lists the tiers by capability
    # (frontier, workhorse, sweep) and sorting would quietly reorder a meaningful list.
    for name in declared:
        tpl = root / "codex" / "agents" / f"{name}.toml"
        if not tpl.is_file():
            raise ProjectionError(f"declared agent template missing: {tpl}")
        desc = tomllib.loads(tpl.read_text(encoding="utf-8")).get("description")
        if not desc:
            raise ProjectionError(f"{tpl} has no description to project")
        blocks.append(f'[agents.{name}]\ndescription = "{desc}"\n'
                      f'config_file = "${{CODEX_HOME}}/agents/{name}.toml"\n')
    return {rel: head + "\n".join(blocks)}


def _member_sets(root: pathlib.Path, src: str) -> dict[str, list[str]]:
    source = root / src / "guides"
    if not source.is_dir() or not (root / src / "CLAUDE.md").is_file():
        raise ProjectionError(f"missing projection source: {src}")
    try:
        return guide_member_map(source)
    except GuideMemberError as exc:
        raise ProjectionError(str(exc)) from exc


def _validate_korean_members(en_members: dict[str, list[str]],
                             ko_members: dict[str, list[str]]) -> None:
    """Korean authors own Markdown parity; English owns every other companion byte."""
    if set(en_members) != set(ko_members):
        raise ProjectionError("EN/KO primary guide sets differ")
    for name, en_paths in en_members.items():
        ko_paths = ko_members[name]
        en_markdown = {p for p in en_paths if p.endswith(".md")}
        ko_markdown = {p for p in ko_paths if p.endswith(".md")}
        if en_markdown != ko_markdown:
            raise ProjectionError(
                f"EN/KO Markdown member sets differ for {name}: "
                f"EN={sorted(en_markdown)} KO={sorted(ko_markdown)}")
        en_assets = {p for p in en_paths if not p.endswith(".md")}
        extra_assets = {p for p in ko_paths if not p.endswith(".md")} - en_assets
        if extra_assets:
            raise ProjectionError(
                f"Korean guide {name} has non-Markdown members with no English source: "
                f"{sorted(extra_assets)}")


def _stale_members(root: pathlib.Path, dst: str, expected: dict[str, bytes]) -> list[str]:
    guide_root = root / dst / "guides"
    if not guide_root.is_dir():
        return []
    return [f"{dst}/guides/{path.relative_to(guide_root).as_posix()}"
            for path in sorted(guide_root.rglob("*"))
            if path.is_file() and f"{dst}/guides/{path.relative_to(guide_root).as_posix()}" not in expected]


def render(root: pathlib.Path) -> tuple[dict[str, bytes], list[str]]:
    """All projected bytes, including Korean copies of immutable English companions."""
    en_members = _member_sets(root, "claude")
    ko_members = _member_sets(root, "ko/claude")
    _validate_korean_members(en_members, ko_members)

    expected: dict[str, bytes] = {
        rel: body.encode("utf-8") for rel, body in render_config_additions(root).items()
    }
    expected.update(render_tree(root, "claude", "codex", "en", en_members))
    # The Korean Markdown members above are authored in ko/claude.  Non-Markdown resources
    # are deliberately projected there first, then use those same English bytes in ko/codex.
    for paths in en_members.values():
        for rel in paths:
            if not rel.endswith(".md"):
                expected[f"ko/claude/guides/{rel}"] = (root / "claude" / "guides" / rel).read_bytes()
    expected.update(render_tree(root, "ko/claude", "ko/codex", "ko", en_members,
                                immutable_assets=root / "claude" / "guides"))

    stale = _stale_members(root, "codex", expected) + _stale_members(root, "ko/codex", expected)
    return expected, stale


def check(root: pathlib.Path) -> list[str]:
    expected, stale = render(root)
    problems = [f"mirror file has no source behind it: {rel}" for rel in stale]
    # Non-empty subject: a projection over nothing must fail, not pass vacuously.
    if not expected:
        problems.append("no mirror files rendered — a clean result here would be vacuous")
    for rel, want in expected.items():
        path = root / rel
        if not path.is_file():
            problems.append(f"missing mirror file: {rel}")
        elif path.read_bytes() != want:
            problems.append(f"mirror is not the projection of its source: {rel}")
    return problems


def write(root: pathlib.Path) -> tuple[list[str], list[str]]:
    expected, stale = render(root)
    changed = []
    for rel, want in expected.items():
        path = root / rel
        if not path.is_file() or path.read_bytes() != want:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(want)
            changed.append(rel)
    return changed, stale


def _self_test() -> int:
    """Each control mutates a real mirror copy and must make --check fail."""
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        for src, dst, _ in TREES:
            for rel in (src, dst):
                shutil.copytree(REPO / rel, base / rel)
        # The fragment's projection reads the launch profile too; the agent templates already
        # came with the codex tree above. Without this the control would fail for the wrong reason.
        for rel in ("codex/config-additions.toml", "launch/agent-launch.toml"):
            (base / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / rel, base / rel)

        results: list[tuple[str, bool]] = []

        # positive control: the untouched copy is clean, so a FAIL below means the mutation
        results.append(("untouched mirror copy is clean", not check(base)))

        def with_mutation(label: str, rel: str, mutate) -> None:
            path = base / rel
            original = path.read_bytes() if path.exists() else None
            mutate(path)
            results.append((label, bool(check(base))))
            if original is None:
                path.unlink()
            else:
                path.write_bytes(original)

        markdown = sorted(p.relative_to(REPO / "codex" / "guides").as_posix()
                          for p in (REPO / "codex" / "guides").rglob("*.md"))
        if not markdown:
            raise ProjectionError("mirror self-test has no Markdown guide member")
        guide = f"codex/guides/{markdown[0]}"
        with_mutation("a one-sided guide edit is caught", guide,
                      lambda p: p.write_text(p.read_text(encoding="utf-8") + "\ndrift\n", encoding="utf-8"))
        with_mutation("a deleted mirror guide is caught", guide, lambda p: p.unlink())
        with_mutation("an extra mirror guide with no source is caught", "codex/guides/zz-orphan.md",
                      lambda p: p.write_text("orphan\n", encoding="utf-8"))
        with_mutation("a dropped Codex authorization bullet is caught", "codex/AGENTS.md",
                      lambda p: p.write_text(
                          p.read_text(encoding="utf-8").replace(AUTHORIZATION["en"] + "\n", ""), encoding="utf-8"))
        with_mutation("a misplaced Codex authorization bullet is caught", "codex/AGENTS.md",
                      lambda p: p.write_text(
                          p.read_text(encoding="utf-8").replace(AUTHORIZATION["en"] + "\n", "")
                          + AUTHORIZATION["en"] + "\n", encoding="utf-8"))
        with_mutation("an unsubstituted config-home var is caught", guide,
                      lambda p: p.write_text(
                          p.read_text(encoding="utf-8") + f"\n{CONFIG_SRC}\n", encoding="utf-8"))
        nested_markdown = next((rel for rel in markdown if "/" in rel), None)
        if nested_markdown is None:
            raise ProjectionError("mirror self-test has no nested Markdown guide companion")
        with_mutation("a nested Markdown companion drift is caught",
                      f"codex/guides/{nested_markdown}",
                      lambda p: p.write_text(p.read_text(encoding="utf-8") + "\ndrift\n",
                                            encoding="utf-8"))
        with_mutation("a ko-side one-sided edit is caught", "ko/codex/AGENTS.md",
                      lambda p: p.write_text(p.read_text(encoding="utf-8") + "\ndrift\n", encoding="utf-8"))

        immutable = sorted(
            p.relative_to(REPO / "claude" / "guides").as_posix()
            for p in (REPO / "claude" / "guides").rglob("*")
            if p.is_file() and p.suffix != ".md")
        if not immutable:
            raise ProjectionError("mirror self-test has no immutable guide companion")
        asset = immutable[0]
        with_mutation("an immutable Codex companion byte drift is caught", f"codex/guides/{asset}",
                      lambda p: p.write_bytes(p.read_bytes() + b"\x00drift"))
        with_mutation("an immutable Korean-source companion byte drift is caught",
                      f"ko/claude/guides/{asset}",
                      lambda p: p.write_bytes(p.read_bytes() + b"\x00drift"))
        with_mutation("an immutable Korean-Codex companion byte drift is caught",
                      f"ko/codex/guides/{asset}",
                      lambda p: p.write_bytes(p.read_bytes() + b"\x00drift"))

        # The config fragment is a projection too, so a hand edit to it must fail the same way.
        frag = base / "codex" / "config-additions.toml"
        frag.write_text(frag.read_text(encoding="utf-8").replace(
            "Bounded hardest decisions", "hand-edited description"), encoding="utf-8")
        results.append(("a hand-edited config fragment is caught",
                        any("config-additions" in p for p in check(base))))
        shutil.copy2(REPO / "codex" / "config-additions.toml", frag)

        # Deleting a template the profile declares must fail loudly, not project a smaller
        # agents block — a silently shrunk fragment disables a subagent tier at install time.
        (base / "codex" / "agents" / "sweep.toml").unlink()
        try:
            render(base)
            results.append(("a missing declared agent template fails loudly", False))
        except ProjectionError:
            results.append(("a missing declared agent template fails loudly", True))
        shutil.copy2(REPO / "codex" / "agents" / "sweep.toml",
                     base / "codex" / "agents" / "sweep.toml")

        # Non-vacuity: an empty source tree must fail rather than report a clean nothing.
        for orphan in (base / "claude" / "guides").glob("*.md"):
            orphan.unlink()
        (base / "claude" / "CLAUDE.md").unlink()
        try:
            render(base)
            results.append(("an empty projection source fails instead of passing vacuously", False))
        except ProjectionError:
            results.append(("an empty projection source fails instead of passing vacuously", True))

    bad = [label for label, ok in results if not ok]
    for label, ok in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if bad:
        print(f"emit-mirrors self-test: FAILED — {len(bad)} control(s) did not hold")
        return 1
    print(f"emit-mirrors self-test: OK ({len(results)} controls)")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Emit or verify the Codex-side mirror trees.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="verify without writing")
    mode.add_argument("--write", action="store_true", help="regenerate in place (default)")
    mode.add_argument("--self-test", action="store_true", help="run the negative controls")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    try:
        if args.check:
            problems = check(REPO)
            if problems:
                for p in problems:
                    print(f"FAIL: {p}")
                print("emit-mirrors: run `python3 gates/emit-mirrors.py` to regenerate")
                return 1
            expected, _ = render(REPO)
            print(f"emit-mirrors: OK ({len(expected)} mirror files match their projection)")
            return 0

        changed, stale = write(REPO)
        for rel in changed:
            print(f"  wrote {rel}")
        print(f"emit-mirrors: {len(changed)} file(s) written")
        if stale:
            for rel in stale:
                print(f"FAIL: mirror file has no source behind it: {rel}")
            print("emit-mirrors: remove the orphans above (git rm) — the generator will not delete files")
            return 1
        return 0
    except ProjectionError as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
