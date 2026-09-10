#!/usr/bin/env python3
"""Derive the promotion manifest from the ledger (collection loop, Phase 4).

`learn/promotions.json` names the personal learnings that have been PROMOTED
into the shared corpus, so the user-side migrate rule can clear the now-absorbed
personal copy (learn/migrate-learnings.py). The manifest is DERIVED — never
hand-edited: a promoted user learning is a ledger entry with `status == placed`
AND a `learning_id` (the Phase 3 dedup key kept on merge). Session-distill
entries have no `learning_id`, so they are never in the manifest.

F3 hardening (the one silent-loss path in the safety design): the audience a
promotion belongs to (which users' bundles carry it) is derived from where the
bullet ACTUALLY landed — the placed entry's `placed_anchor`, resolved against
`compose/domains.json` (the placement source of truth) — NOT the ledger's free
`domain` tag. A placed+learning_id entry with a missing or unresolvable
`placed_anchor` FAILS the build/--check, so a promotion can neither ship with a
wrong audience nor ship without actually landing in the corpus.

Manifest shape (no PII — learning_id + the derived audience):
  { "version": 1, "promotions": [
      { "learning_id": "<uuid>", "tier": "core|infra|domain", "domains": ["<key>", ...] } ] }
(`domains` is empty for the universal tiers core/infra.)

Release step: regenerate before a push. `--check` fails if the on-disk manifest
is stale vs the ledger (a check-parity gate). `--self-test` runs the derivation.
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "compose"))
import pkgid  # noqa: E402  (package-identity primitive owned by compose/)
import assemble  # noqa: E402  (the tier vocabulary's owner — asked, never restated here)

REPO = pathlib.Path(__file__).resolve().parent.parent
LEDGER = REPO / "design" / "session-distill" / "ledger.json"
DOMAINS = REPO / "compose" / "domains.json"
MANIFEST = REPO / "learn" / "promotions.json"
FIXTURE = REPO / "design" / "collection-loop" / "fixtures" / "ledger-promote-sample.json"
MANIFEST_VERSION = 2


class ManifestError(Exception):
    pass


def resolve_audience(anchor, domains_manifest):
    """(tier, [domains]) for a placed anchor, or None if it does not resolve.
    Bullets match by their `anchor` field; a whole guide/hook/agent matches by
    key. This is the authoritative placement audience (mirrors what assemble.py
    reads to decide who gets the bullet)."""
    for b in domains_manifest.get("bullets", []):
        if b.get("anchor") == anchor:
            return b.get("tier"), list(b.get("domains", []))
    for kind in ("guides", "hooks", "agents"):
        entry = domains_manifest.get(kind, {}).get(anchor)
        if entry is not None:
            return entry.get("tier"), list(entry.get("domains", []))
    return None


def build_manifest(ledger, domains_manifest):
    """Ledger + domains manifest -> the promotion manifest. Raises ManifestError
    on a placed+learning_id entry whose placement can't be verified (missing or
    unresolvable placed_anchor) — the F3 silent-loss guard. Sorted by
    learning_id for a stable, deterministic artifact."""
    promotions = []
    for e in ledger.get("entries", []):
        if not isinstance(e, dict):
            continue
        lid = e.get("learning_id")
        if e.get("status") != "placed" or not (isinstance(lid, str) and lid):
            continue
        anchor = e.get("placed_anchor")
        if not anchor:
            raise ManifestError(
                f"placed learning {e.get('id')!r} ({lid}) has no `placed_anchor` — "
                "record where the bullet landed (a compose/domains.json anchor/key) "
                "before promoting")
        aud = resolve_audience(anchor, domains_manifest)
        if aud is None:
            raise ManifestError(
                f"placed_anchor {anchor!r} (learning {lid}) does not resolve in "
                "compose/domains.json — the promotion has no verifiable placement")
        tier, domains = aud
        # A promotion says "this landed in the shared corpus, so the personal copy is
        # now redundant." An env-personal anchor never reaches any bundle — assemble.py
        # maps that tier to NEVER and migrate-learnings' in_bundle answers False — so
        # promoting one emits a row that both consumers are structurally unable to act
        # on, and the counted promotion is a claim nothing downstream can honour. This
        # is the same silent-loss guard as the two above, one step earlier.
        if assemble.audience({"tier": tier, "domains": domains}) == "NEVER":
            raise ManifestError(
                f"placed_anchor {anchor!r} (learning {lid}) resolves to tier {tier!r}, "
                f"which assemble.py never puts in a bundle — so neither the assembler "
                f"nor migrate-learnings could ever act on this promotion")
        pid = pkgid.resolve(e, "placed_package_id")
        if not pkgid.is_valid(pid):
            raise ManifestError(
                f"placed_package_id {pid!r} (learning {lid}) is not @scope/name")
        # `anchor` ships alongside the derived audience because the consumer
        # (migrate-learnings) must verify the bullet is REALLY in the user's
        # deployed corpus before deleting their personal copy. Audience metadata
        # alone cannot answer that — it is a build-time projection that drifts.
        promotions.append({"learning_id": lid.lower(), "package_id": pid,
                           "anchor": anchor, "tier": tier, "domains": domains})
    promotions.sort(key=lambda p: p["learning_id"])
    return {"version": MANIFEST_VERSION, "promotions": promotions}


def render(manifest):
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def _self_test():
    ledger = json.loads(FIXTURE.read_text(encoding="utf-8"))
    # Fixture domains manifest the fixture's placed_anchors resolve against.
    domains = {
        "bullets": [
            {"anchor": "universal placed rule", "tier": "core", "domains": []},
            {"anchor": "builder placed rule", "tier": "domain", "domains": ["builder-base"]},
            # The tier assemble.py maps to NEVER. Present so the promotability check below
            # has a real subject: compose/domains.json carries exactly one such bullet, and
            # a control that indexes a live list stops testing the day that list empties.
            {"anchor": "environment-personal placed rule", "tier": "env-personal", "domains": []},
        ],
        "guides": {}, "hooks": {}, "agents": {},
    }
    m = build_manifest(ledger, domains)
    by = {p["learning_id"]: p for p in m["promotions"]}
    a1 = "0f8c1c2a-4d1e-4abc-9def-0000000000a1"
    b2 = "0f8c1c2a-4d1e-4abc-9def-0000000000b2"

    checks = [
        ("only placed+learning_id promoted (cardinality > 0)", set(by) == {a1, b2}),
        ("session-distill (no learning_id) excluded",
         all(p["learning_id"] for p in m["promotions"])),
        ("incubating excluded",
         "0f8c1c2a-4d1e-4abc-9def-0000000000c1" not in by),
        ("audience DERIVED from the anchor, not the ledger domain tag",
         by[a1]["tier"] == "core" and by[a1]["domains"] == []
         and by[b2]["tier"] == "domain" and by[b2]["domains"] == ["builder-base"]),
        ("sorted + deterministic",
         [p["learning_id"] for p in m["promotions"]] == sorted(by)
         and render(build_manifest(ledger, domains)) == render(m)),
    ]

    # F3 guards: missing / unresolvable placed_anchor must FAIL.
    def raises(mut):
        led = json.loads(FIXTURE.read_text(encoding="utf-8"))
        mut(led)
        try:
            build_manifest(led, domains)
            return False
        except ManifestError:
            return True

    checks.append(("missing placed_anchor fails",
                   raises(lambda l: l["entries"][0].pop("placed_anchor", None))))
    checks.append(("unresolvable placed_anchor fails",
                   raises(lambda l: l["entries"][0].__setitem__("placed_anchor", "no-such-anchor"))))

    # v2 identity + locator. Without these the manifest looks fine while the
    # consumer that must verify placement has nothing to verify against.
    checks.append(("manifest is v2", m["version"] == 2))
    checks.append(("every promotion carries its anchor",
                   all(p.get("anchor") for p in m["promotions"])))
    checks.append(("absent placed_package_id resolves to core",
                   all(p.get("package_id") == pkgid.CORE for p in m["promotions"])))
    led2 = json.loads(FIXTURE.read_text(encoding="utf-8"))
    led2["entries"][0]["placed_package_id"] = "@acme/security"
    checks.append(("declared placed_package_id is carried through",
                   any(p["package_id"] == "@acme/security"
                       for p in build_manifest(led2, domains)["promotions"])))
    checks.append(("malformed placed_package_id fails",
                   raises(lambda l: l["entries"][0].__setitem__("placed_package_id", "Acme/Sec"))))

    # A promotion asserts "this landed in the shared corpus". An anchor whose tier the
    # assembler maps to NEVER lands in no bundle, so the row it produced was one neither
    # the assembler nor migrate-learnings could ever act on — counted as a promotion and
    # inert by construction. The pair is what makes this a check: the same shape with a
    # promotable anchor must still build.
    never = next((b.get("anchor") for b in domains.get("bullets", [])
                  if assemble.audience(b) == "NEVER" and b.get("anchor")), None)
    lands = next((b.get("anchor") for b in domains.get("bullets", [])
                  if assemble.audience(b) != "NEVER" and b.get("anchor")), None)
    if not never or not lands:
        checks.append(("tier-promotability subjects exist in domains.json", False))
    else:
        checks.append(("an unassembled tier cannot be promoted",
                       raises(lambda l: l["entries"][0].__setitem__("placed_anchor", never))))
        checks.append(("an assembled tier still promotes",
                       not raises(lambda l: l["entries"][0].__setitem__("placed_anchor", lands))))

    failed = [n for n, ok in checks if not ok]
    if failed:
        for n in failed:
            print(f"build-promotions --self-test: FAIL: {n}", file=sys.stderr)
        sys.exit(1)
    print(f"build-promotions --self-test: OK ({len(checks)} manifest-derivation checks)")


def _load_and_build():
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    domains = json.loads(DOMAINS.read_text(encoding="utf-8"))
    try:
        return render(build_manifest(ledger, domains))
    except ManifestError as e:
        print(f"build-promotions: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Derive learn/promotions.json from the ledger.")
    ap.add_argument("--check", action="store_true",
                    help="fail if learn/promotions.json is stale vs the ledger (gate)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        _self_test()
        return

    want = _load_and_build()

    if args.check:
        have = MANIFEST.read_text(encoding="utf-8") if MANIFEST.is_file() else ""
        if have != want:
            print("build-promotions --check: learn/promotions.json is STALE vs the "
                  "ledger — run `python3 learn/build-promotions.py` and commit.",
                  file=sys.stderr)
            sys.exit(1)
        print("build-promotions --check: promotions.json is current with the ledger")
        return

    MANIFEST.write_text(want, encoding="utf-8")
    n = want.count('"learning_id"')
    print(f"build-promotions: wrote {MANIFEST} ({n} promotion(s))")


if __name__ == "__main__":
    main()
