#!/usr/bin/env python3
"""The prompting guides' source pins: structure blocks, drift discloses.

Two questions live here and they must not share an exit code.

STRUCTURE is decidable and offline, so it GATES (default mode, wired into the parity
umbrella): every pin names a document `prompting-sources.json` maps, every mapped
document is pinned by some guide, and every guide carries a well-formed `derived_at`
and at least one pin. A pin naming an unmapped document is a check that can never run,
and this repo does not keep those.

DRIFT needs the network, so it only DISCLOSES, and only when asked (`--online`). A gate
that reaches the network fails in a tunnel and teaches people to route around the suite.
It also cannot answer the question people want: "was this guide re-derived correctly" is
a judgement. What a hash settles is "the source moved since it was pinned", and that is
all `--online` claims.

    python3 gates/check-prompting-sources.py             # offline, blocks — in the umbrella
    python3 gates/check-prompting-sources.py --online    # + fetch and compare, discloses
    python3 gates/check-prompting-sources.py --self-test  # offline controls

WHAT THE PINS ARE, AND WHAT THEY ARE NOT. A pin is a baseline taken at `pinned_at`, not
evidence that the guide was written from those bytes. When `pinned_at` is later than
`derived_at`, the guide predates its own pin and has never been checked against it — a
standing debt this tool reports on every run rather than a transient state. Recording
today's hash as though it were the derivation would have manufactured provenance that
nobody could later distinguish from the real thing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
SOURCES = REPO / "gates" / "prompting-sources.json"
GUIDES = ("claude/guides/claude-prompting.md", "claude/guides/gpt-prompting.md")

FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
DERIVED_AT = re.compile(r"^derived_at:\s*(\S+)\s*$", re.M)
PIN = re.compile(
    r"^  - doc:\s*(?P<doc>\S+)\s*\n"
    r"^    sha256:\s*(?P<sha>[0-9a-f]{64})\s*\n"
    r"^    pinned_at:\s*(?P<at>\S+)\s*$",
    re.M,
)


class Problem(Exception):
    """A structural fault — decidable, so it exits non-zero even though drift does not."""


def frontmatter(path: pathlib.Path) -> str:
    m = FRONT.match(path.read_text(encoding="utf-8"))
    if not m:
        raise Problem(f"{path}: no YAML frontmatter")
    return m.group(1)


def read_guide(rel: str) -> dict:
    front = frontmatter(REPO / rel)
    at = DERIVED_AT.search(front)
    if not at:
        raise Problem(f"{rel}: no derived_at in frontmatter")
    pins = [m.groupdict() for m in PIN.finditer(front)]
    if not pins:
        raise Problem(f"{rel}: declares no source_pins — nothing to check against")
    return {"guide": rel, "derived_at": at.group(1), "pins": pins}


def fetch(url: str) -> bytes:
    # A User-Agent is required, not cosmetic: platform.claude.com answers urllib's default
    # with 403 while serving curl a 200, so without this the Anthropic half of the check
    # reports "unreachable" forever and looks like a network problem.
    request = urllib.request.Request(url, headers={"User-Agent": "agent-bios-source-check"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - author-side
        return response.read()


def check(fetcher=fetch, guides=GUIDES, online=True, sources=None) -> tuple[int, list[str]]:
    """Returns (changed_count, lines). Never raises for drift; raises Problem for faults.

    With online=False every structural assertion still runs — the pin/URL correspondence
    is what makes the online mode able to run at all — and no document is fetched."""
    src = sources or SOURCES
    urls = json.loads(src.read_text(encoding="utf-8"))["docs"]
    if not urls:
        raise Problem(f"{src}: maps no documents; every check below would be vacuous")
    lines: list[str] = []
    changed = 0
    seen_docs: set[str] = set()
    for rel in guides:
        info = read_guide(rel)
        lines.append(f"{rel}  (derived_at {info['derived_at']})")
        for pin in info["pins"]:
            doc, sha, at = pin["doc"], pin["sha"], pin["at"]
            seen_docs.add(doc)
            if doc not in urls:
                raise Problem(f"{rel}: pins {doc!r}, which {src.name} does not map to a URL")
            if not online:
                lines.append(f"  pinned       {doc}  {sha[:12]}… ({at})")
                continue
            try:
                live = hashlib.sha256(fetcher(urls[doc])).hexdigest()
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                lines.append(f"  unreachable  {doc} — {exc}")
                continue
            if live == sha:
                lines.append(f"  unchanged    {doc}  (pinned {at})")
            else:
                changed += 1
                lines.append(f"  CHANGED      {doc}  pinned {sha[:12]}… now {live[:12]}… "
                             f"— re-derive {rel} and repin")
        if info["derived_at"] < min(p["at"] for p in info["pins"]):
            lines.append(f"  NOTE         the guide ({info['derived_at']}) predates its pins "
                         f"— it has never been re-derived against these sources")
    unmapped = sorted(set(urls) - seen_docs)
    if unmapped:
        raise Problem(f"{src.name} maps document(s) no guide pins: {', '.join(unmapped)}")
    return changed, lines


def self_test() -> int:
    """Offline. Each case plants one fault and requires this tool to name it."""
    failures = []

    def expect(name: str, condition: bool):
        print(f"  {'PASS' if condition else 'FAIL'}  {name}")
        if not condition:
            failures.append(name)

    real = {doc: hashlib.sha256(f"body-of-{doc}".encode()).digest() for doc in
            json.loads(SOURCES.read_text(encoding="utf-8"))["docs"]}

    def serve(mapping):
        urls = json.loads(SOURCES.read_text(encoding="utf-8"))["docs"]
        by_url = {u: d for d, u in urls.items()}
        def f(url: str) -> bytes:
            return mapping[by_url[url]]
        return f

    # Every body differs from what was pinned, so every pin must report CHANGED. A
    # matching-hash case cannot be constructed without a preimage, and is covered live.
    changed, lines = check(fetcher=serve({d: b"anything-else" for d in real}))
    expect("a moved document is reported as CHANGED for every pin",
           changed == sum(len(read_guide(g)["pins"]) for g in GUIDES))
    expect("and the CHANGED line names the document and both hashes",
           any("CHANGED" in l and "now" in l and "re-derive" in l for l in lines))
    # This control BUILDS its subject. It used to assert the note fired on the real
    # guides, which passed only while both were stale — and went red the moment they
    # were re-derived, which is a control measuring the repo's state rather than the
    # rule. Loud, but still the failure AGENTS.md warns about.
    expect("a guide NOT older than its pins draws no note (the live state)",
           not any("never been re-derived" in l for l in lines))

    def boom(url: str) -> bytes:
        raise urllib.error.URLError("planted network failure")

    changed, lines = check(fetcher=boom)
    expect("an unreachable document is reported, not counted as changed",
           changed == 0 and any("unreachable" in l for l in lines))

    try:
        check(fetcher=serve(real), guides=("gates/prompting-sources.json",))
        expect("a guide with no frontmatter is refused", False)
    except Problem:
        expect("a guide with no frontmatter is refused", True)

    # The BLOCKING paths. These are what the umbrella now depends on, so each is planted.
    import tempfile

    def with_sources(docs: dict, **kw):
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "planted-sources.json"
            f.write_text(json.dumps({"docs": docs}), encoding="utf-8")
            return check(sources=f, online=False, **kw)

    urls = json.loads(SOURCES.read_text(encoding="utf-8"))["docs"]

    try:
        with_sources({k: v for k, v in urls.items() if k != "model-guidance-gpt-6-astra"})
        expect("a pin naming an unmapped document is refused", False)
    except Problem as exc:
        expect("a pin naming an unmapped document is refused", "model-guidance-gpt-6-astra" in str(exc))

    try:
        with_sources({**urls, "never-pinned-doc": "https://example.invalid/x.md"})
        expect("a mapped document no guide pins is refused", False)
    except Problem as exc:
        expect("a mapped document no guide pins is refused", "never-pinned-doc" in str(exc))

    try:
        with_sources({})
        expect("a sources file mapping nothing is refused as vacuous", False)
    except Problem as exc:
        expect("a sources file mapping nothing is refused as vacuous", "vacuous" in str(exc))

    # The derivation-gap note, on a subject this control constructs. REPO / abs_path
    # resolves to abs_path, so a synthetic guide needs no place in the tree.
    with tempfile.TemporaryDirectory() as d:
        stale = pathlib.Path(d) / "stale-guide.md"
        stale.write_text(
            "---\nderived_at: 2020-01-01\nsource_pins:\n"
            "  - doc: only-doc\n"
            f"    sha256: {'0' * 64}\n"
            "    pinned_at: 2026-09-01\n---\n\nbody\n", encoding="utf-8")
        src = pathlib.Path(d) / "sources.json"
        src.write_text(json.dumps({"docs": {"only-doc": "https://example.invalid/x.md"}}),
                       encoding="utf-8")
        _, lines = check(sources=src, guides=(str(stale),), online=False)
        expect("a guide older than its pins IS flagged as never re-derived",
               any("never been re-derived" in l for l in lines))

    total = 9
    print(f"\ncheck-prompting-sources --self-test: "
          f"{'OK' if not failures else 'FAILED: ' + ', '.join(failures)} "
          f"({total - len(failures)}/{total} controls)")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--online", action="store_true",
                    help="also fetch each source and compare its hash (discloses, never fails)")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    try:
        changed, lines = check(online=args.online)
    except Problem as exc:
        print(f"FAIL: {exc}")
        return 1
    if not args.online:
        pinned = sum(1 for line in lines if line.startswith("  pinned"))
        if not pinned:
            print("FAIL: no pins were judged — this run checked nothing")
            return 1
        print(f"check-prompting-sources: OK — {pinned} pin(s) structurally sound "
              f"(run --online to compare them against the live documents)")
        return 0
    for line in lines:
        print(line)
    print()
    unread = sum(1 for line in lines if "unreachable" in line)
    read = sum(1 for line in lines if "unchanged" in line or "CHANGED" in line)
    if changed:
        print(f"{changed} of {read} document(s) read moved since they were pinned. A "
              f"disclosure, not a failure — re-derive the guide, then repin.")
    elif read:
        print(f"None of the {read} document(s) read has moved since it was pinned.")
    # Never absolve what was not read: a summary counted over the reachable subset is how
    # "no bad X" passes over an empty set. Said separately so it survives the sentence above.
    if unread:
        print(f"{unread} document(s) could NOT be read, so nothing above says anything "
              f"about them. Re-run when they are reachable.")
    if not read:
        print("Nothing was read at all — this run checked nothing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
