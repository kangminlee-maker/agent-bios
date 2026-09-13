#!/usr/bin/env python3
"""Gate: SURFACES.md must still describe the delivery surfaces that exist.

SURFACES.md routes every promoted learning and every new tool. A catalog that has
drifted from the code routes them wrongly while reading as current — the exact decay
this repo already refuses in dated records, committed by the routing reference against
itself.

Two directions, both decidable:

  stale    a surface declares an authority path that matches no file, so the catalog
           describes a mechanism that is gone
  unclaimed  the installer deploys something no surface claims, so a new way to reach
           a model exists and the catalog does not know about it

Everything else about this file — whether an admitted item met its surface's bar,
whether a router line is findable — is judgment and is deliberately NOT gated. Gate a
judgment call and people learn to route around the gate.

  --self-test   plant each failure kind and prove it fires, and prove a clean tree
                stays silent; exits 0 only if all hold.
"""
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
CATALOG = REPO / "SURFACES.md"
INSTALL = REPO / "install.sh"

# The per-surface blocks live under this heading; the catalog's other sections name
# paths too (the checked/unchecked list, the tools axis) and those are prose about
# gates rather than surface declarations.
SECTION = "## What each surface admits"
SURFACE_HEADING = re.compile(r"^### (.+)$")
AUTHORITY = re.compile(r"^- \*\*Authority\*\* — (.*)$")
# Continuation lines of a wrapped Authority bullet: indented, not a new bullet.
CONTINUATION = re.compile(r"^  \S")
BACKTICKED = re.compile(r"`([^`]+)`")
# A backticked span is a path claim only if it looks like one. The Authority prose names
# functions, constants and config keys in the same backticks (`verify_review_receipts`,
# `RECEIPT_KEYS`, `mcp_servers.*`), and reading those as paths failed every surface for a
# reason that was not drift. A path either carries a separator or ends in a known
# extension; an identifier does neither.
PATH_CHARS = re.compile(r"^[A-Za-z0-9_.\-*/]+$")
PATH_SUFFIXES = (".md", ".py", ".sh", ".json", ".toml", ".html", ".zsh")

# Deploy sources that are genuinely not a consumption surface would be justified here
# rather than silently skipped, the same way check-package.sh justifies its exemptions:
# an unexplained exemption is how a real gap gets parked forever. A consumption surface
# is a place knowledge or a tool reaches a MODEL from; a deploy that only a human ever
# sees is delivery, not consumption.
NOT_A_SURFACE: dict[str, str] = {
    # The launcher's UI text catalogs translate interface strings (menus, labels,
    # descriptions) for the HUMAN operating the TUI. Nothing a model consumes is
    # sourced from them — the contract-invariance parity leg holds contract
    # renderers catalog-free, and the AI-consumed instructions are English-unified by
    # user decision (2026-08-10).
    "launch/i18n/$lang.toml": "interface text for the human operator; never reaches a model",
}


def _is_path(span: str) -> bool:
    return bool(PATH_CHARS.match(span)) and (
        "/" in span or span.endswith(PATH_SUFFIXES)
    )


def _authority_blocks(text: str):
    """(surface name, raw authority prose) for each declared surface."""
    if SECTION not in text:
        return []
    body = text.split(SECTION, 1)[1]
    out, surface, collecting, buffer = [], None, False, []

    def flush():
        if surface and buffer:
            out.append((surface, " ".join(buffer)))

    for line in body.splitlines():
        heading = SURFACE_HEADING.match(line)
        if heading:
            flush()
            surface, collecting, buffer = heading.group(1).strip(), False, []
            continue
        if line.startswith("## "):  # the section ended
            break
        found = AUTHORITY.match(line)
        if found:
            collecting, buffer = True, [found.group(1)]
            continue
        if collecting and CONTINUATION.match(line):
            buffer.append(line.strip())
            continue
        collecting = False
    flush()
    return out


def declared_paths(text: str):
    """{surface: [path claim, ...]} — only the spans that look like paths."""
    claims = {}
    for surface, prose in _authority_blocks(text):
        paths = [span for span in BACKTICKED.findall(prose) if _is_path(span)]
        claims[surface] = paths
    return claims


def deploy_sources(text: str):
    """Repo-relative sources the installer writes onto a machine, from real call sites.

    Derived rather than listed, so a deploy added later is covered without anyone
    remembering to update this gate."""
    out = []
    for match in re.finditer(r'^\s*deploy_file\s+"\$REPO/([^"]+)"', text, re.M):
        out.append(match.group(1))
    for match in re.finditer(r'^\s*deploy_glob\s+"\$REPO/([^"]+)"\s+"([^"]+)"', text, re.M):
        out.append(f"{match.group(1)}/{match.group(2)}")
    # deploy_tree deploys a SUBTREE whose leaf name is a loop variable
    # (`"$REPO/claude/skills/$skill"`); the source is the fixed prefix before the first
    # variable component, kept as a directory claim. Until this arm existed the skills
    # deploy was invisible here and the catalog was green about a surface it did not name.
    for match in re.finditer(r'^\s*deploy_tree\s+"\$REPO/([^"]+)"', text, re.M):
        parts = match.group(1).split("/")
        fixed = []
        for part in parts:
            if part.startswith("$"):
                break
            fixed.append(part)
        if not fixed:
            continue
        out.append("/".join(fixed) + "/")
    return sorted(set(out))


def _resolves(claim: str) -> bool:
    if "*" in claim:
        parent = pathlib.Path(claim).parent
        return any((REPO / parent).glob(pathlib.Path(claim).name)) if (REPO / parent).is_dir() else False
    return (REPO / claim).exists()


def _claims(claim: str, source: str) -> bool:
    """Does this declared path cover that deploy source?"""
    if claim.rstrip("/") == source:
        return True
    if claim.endswith("/") and source.startswith(claim):
        return True
    if "*" in claim:
        return pathlib.PurePath(source).match(claim)
    # A declared directory without the trailing slash still covers what is under it.
    return (REPO / claim).is_dir() and source.startswith(claim.rstrip("/") + "/")


def check(catalog_text=None, install_text=None):
    failures = []
    text = CATALOG.read_text(encoding="utf-8") if catalog_text is None else catalog_text
    install = INSTALL.read_text(encoding="utf-8") if install_text is None else install_text

    claims = declared_paths(text)
    if not claims:
        return ["SURFACES.md declares no surface — the check ran over an empty subject"]

    without_paths = sorted(name for name, paths in claims.items() if not paths)
    if without_paths:
        failures.append(
            "surface(s) naming no authority path, so nothing anchors them to code: "
            + ", ".join(without_paths)
        )

    for surface, paths in sorted(claims.items()):
        for claim in paths:
            if not _resolves(claim):
                failures.append(
                    f"{surface!r} names authority {claim!r}, which matches no file — "
                    f"a stale declaration describes a mechanism that is gone"
                )

    sources = deploy_sources(install)
    if not sources:
        failures.append("no deploy source was extracted from install.sh — vacuous")
    every_claim = [claim for paths in claims.values() for claim in paths]
    for source in sources:
        if source in NOT_A_SURFACE:
            continue
        if not any(_claims(claim, source) for claim in every_claim):
            failures.append(
                f"install.sh deploys {source!r} and no surface in SURFACES.md claims it — "
                f"either it is a delivery surface the catalog does not know about, or it "
                f"belongs in NOT_A_SURFACE with a reason"
            )
    return failures


def self_test():
    failures = []
    clean = CATALOG.read_text(encoding="utf-8")
    install = INSTALL.read_text(encoding="utf-8")

    if check(clean, install):
        failures.append("the live tree does not pass, so no negative control means anything")

    # Planted in memory, never on disk: a control that edits a tracked file leaves the
    # plant behind if the process dies between the write and the restore.
    stale = clean.replace(
        "- **Authority** — `gates/`, umbrella at `gates/check-parity.sh`.",
        "- **Authority** — `gates/no-such-file-here.py`.", 1)
    if stale == clean:
        failures.append("could not plant a stale authority — the fixture anchor moved")
    elif not any("matches no file" in f for f in check(stale, install)):
        failures.append("a stale authority path did NOT fail")

    # The planted path must be one no surface claims TODAY, asserted rather than assumed:
    # the previous plant (`compose/domains.json`) became a claimed authority the day the
    # skill surface named it, and the control passed for the wrong reason.
    plant = "compose/prune-backups.py"
    every = [c for paths in declared_paths(clean).values() for c in paths]
    if any(_claims(c, plant) for c in every):
        failures.append(f"control plant {plant!r} is claimed by a surface — pick another")
    unclaimed = install + f'\n  deploy_file "$REPO/{plant}" "$X/x"\n'
    if not any("no surface in SURFACES.md claims it" in f for f in check(clean, unclaimed)):
        failures.append("an unclaimed deploy target did NOT fail")

    # The tree arm: the live installer must yield a tree source (the skills deploy —
    # asserted so this control cannot pass over an extractor that sees no tree at all),
    # and an unclaimed tree must fail the same way a file does.
    if not any(src.endswith("/") for src in deploy_sources(install)):
        failures.append("deploy_sources sees no deploy_tree site in the live install.sh — "
                        "the tree arm has no subject")
    unclaimed_tree = install + '\n  deploy_tree "$REPO/compose/$thing" "$X/$thing"\n'
    if not any("no surface in SURFACES.md claims it" in f and "compose/" in f
               for f in check(clean, unclaimed_tree)):
        failures.append("an unclaimed deploy_tree target did NOT fail")

    if not check("# nothing here", install):
        failures.append("an empty catalog did NOT fail")

    hollow = clean.replace("- **Authority** — `gates/`, umbrella at `gates/check-parity.sh`.",
                           "- **Authority** — the gates, described in prose only.", 1)
    if not any("naming no authority path" in f for f in check(hollow, install)):
        failures.append("a surface with no path claim did NOT fail")

    if failures:
        print("check-surfaces --self-test: FAIL")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("check-surfaces --self-test: OK (stale authority, unclaimed deploy, empty "
          "catalog and path-less surface all caught; clean tree silent)")
    return 0


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    if sys.argv[1:]:
        print(f"check-surfaces: unknown argument: {' '.join(sys.argv[1:])}", file=sys.stderr)
        return 2
    failures = check()
    if failures:
        print("check-surfaces: FAILED")
        for item in failures:
            print(f"  - {item}")
        return 1
    claims = declared_paths(CATALOG.read_text(encoding="utf-8"))
    print(f"check-surfaces: OK ({len(claims)} surfaces declared, "
          f"{sum(len(p) for p in claims.values())} authority paths live, "
          f"{len(deploy_sources(INSTALL.read_text(encoding='utf-8')))} deploy sources claimed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
