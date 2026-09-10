#!/usr/bin/env python3
"""Private captures are retained; promotion suppression is a snapshot projection.

The default entrypoint performs no source deletion. CorpusStore requires exact
source and replacement evidence before omitting a duplicate from one snapshot.
The functions below implement only the explicit AGENT_BIOS_LEGACY_INSTALL=1
compatibility path, whose removal contract is described here.

After a push lands, a learning that was promoted into the shared corpus is now
loaded from the corpus — its personal copy (written by `learn!`,
learn/collect-learning.py) would double-load. This user-side tool removes the
absorbed personal copy, and ONLY it (never the user's hand-written entry
CLAUDE.md `## Personal` section).

THE SAFETY RULE (design/corpus-domain-packaging.md:161-168): remove a personal
copy ONLY after verifying the promoted item is actually in THIS user's assembled
bundle. Per-domain opt-in means a promotion into a package the user did NOT
install must NOT trigger removal — that would silently lose the learning. When
unsure, KEEP (a kept duplicate is redundant; a wrong removal is data loss).

HOW THAT RULE IS ENFORCED (contract v2): audience metadata SELECTS candidates,
presence in the deployed corpus AUTHORIZES the delete. Metadata is a build-time
projection — it cannot see that this user runs a package or version whose bundle
never received the promoted bullet — so it is never the authority for an
irreversible act. Every uncertainty resolves to KEEP: a foreign package we
cannot confirm, an audience miss, an anchor absent from the corpus, a v1 record
with no anchor to verify.

Candidate selection (mirrors compose/assemble.py `kept`): universal tier
(core/infra) -> always installed; a domain key -> installed iff in the user's
selection; anything else (env-personal / unclassified / unknown) -> KEEP. There
is one install shape — what used to be a "full" install is every domain
selected — so a selection always answers this.

Run per host (mirrors collect-learning: --host + --config-dir); install.sh calls
it after the corpus deploy. Manifest absent/empty -> no-op.
"""
import argparse
import importlib.util
import json
import os
import pathlib
import re
import shutil
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "compose"))
import pkgid  # noqa: E402  (package-identity primitive owned by compose/)
import assemble  # noqa: E402  (owns the atomic-replace primitive both packages write with)

REPO = pathlib.Path(__file__).resolve().parent.parent
# Same home compose/corpus-state.py uses; the canary writes its activation proof here.
STATE_DIR = pathlib.Path(os.environ.get("AGENT_BIOS_STATE_DIR")
                         or pathlib.Path.home() / ".local/share/agent-bios")
MANIFEST = REPO / "learn" / "promotions.json"
UNIVERSAL_TIERS = frozenset({"core", "infra"})  # == assemble.audience UNIVERSAL
# learning_id inside a personal bullet's TRAILING comment (collect-learning
# prose_bullet: "... <!-- learning_id: <uuid> created: <ts> -->"). Anchored to
# end-of-line so a lesson body that quotes a `<!-- learning_id: … -->` string
# can never shadow the bullet's own id (this corpus is about agent tooling).
BULLET_LID_RE = re.compile(r"<!--\s*learning_id:\s*([0-9a-fA-F-]+)[^>]*-->\s*$")


def die(msg, code=1):
    print(f"migrate-learnings: {msg}", file=sys.stderr)
    sys.exit(code)


def _load(name, filename):
    path = REPO / "learn" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_collect():
    """Reuse collect-learning.py's host/home/marker constants (single source)."""
    return _load("collect_learning", "collect-learning.py")


def load_manifest(path=MANIFEST):
    # "Manifest absent/empty -> no-op" is this module's stated contract, and an existing
    # zero-byte file is the empty case it was missing: json.loads("") raised out of the
    # update path as a traceback. Whitespace-only reads as empty; anything else that
    # will not parse is a REAL manifest that is broken, and says so through die().
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        die(f"manifest is not valid JSON: {path} ({exc})")
    if not isinstance(data, dict):
        die(f"manifest is not an object: {path}")
    return [p for p in data.get("promotions", [])
            if isinstance(p, dict) and isinstance(p.get("learning_id"), str)]


def make_in_bundle(selection):
    """A promotion's placement AUDIENCE (tier + domains, derived by
    build-promotions from where the bullet actually landed) -> is it in THIS
    user's bundle? Mirrors assemble.py `kept`. Biased to KEEP on anything not
    provably installed.

    There is one install shape now: what used to be a "full" install is every domain
    selected, so a selection always answers this and there is no mode to branch on."""
    selection = set(selection or ())

    def in_bundle(tier, domains):
        if tier in UNIVERSAL_TIERS:
            return True
        if tier == "domain":
            return bool(set(domains or ()) & selection)
        return False  # env-personal / unknown tier -> keep

    return in_bundle


def corpus_surfaces(home):
    """Files and dirs that hold the DEPLOYED corpus for this host.

    Deliberately excludes `personal/` — the user's own copy of a promoted
    learning quotes the same lesson, so searching it would find the very thing
    we are deciding whether to delete and always answer yes.
    """
    texts = [home / "central" / "bundle.md",          # the assembled corpus
             home / "CLAUDE.md", home / "AGENTS.md"]  # entry files, for a pre-convergence layout
    dirs = [home / "central" / d for d in ("guides", "hooks", "agents")]
    dirs += [home / d for d in ("guides", "hooks", "agents")]
    return texts, dirs


def corpus_text(path, collect=None):
    """A corpus file's text with the user's personal region removed.

    On codex the personal copy lives INSIDE AGENTS.md, and a promoted bullet is
    written FROM the user's lesson — so its anchor can legitimately appear in
    their own bullet. Searching the region would let a personal copy authorize
    its own deletion. Strip it before matching.
    """
    body = path.read_text(encoding="utf-8", errors="replace")
    if collect is None:
        return body
    start, end = getattr(collect, "PERSONAL_START", None), getattr(collect, "PERSONAL_END", None)
    if start and end and start in body:
        pre, rest = body.split(start, 1)
        return pre + (rest.split(end, 1)[1] if end in rest else "")
    return body


# A placement is one of two kinds and they are verified differently, so the kind has to
# be readable. It is derived from the anchor rather than carried as a new manifest field
# because the two shapes do not overlap: a whole-file anchor is a bare filename, and a
# bullet anchor is a phrase lifted from the rule, which always has spaces in it.
FILE_ANCHOR_SUFFIXES = (".md", ".py", ".toml", ".json", ".sh")


def anchor_names_a_file(anchor):
    return (not any(ch.isspace() for ch in anchor)
            and anchor.endswith(FILE_ANCHOR_SUFFIXES))


def placed_here(home, anchor, collect=None):
    """Is the promoted item REALLY in this user's deployed corpus?

    This is the authorization for an irreversible delete, so it asks the
    filesystem rather than trusting build-time audience metadata, which is a
    projection that goes stale the moment packages or versions diverge. A whole
    guide/hook/agent placement is a deployed file; a bullet placement is its
    anchor appearing in the deployed corpus text.
    """
    if not isinstance(anchor, str) or not anchor:
        return False
    texts, dirs = corpus_surfaces(home)
    if anchor_names_a_file(anchor):
        # A whole-file placement is proven by the deployed FILE and by nothing else. It
        # used to fall through to the text scan below, where any corpus document that
        # merely NAMES the guide counted as proof the guide was installed — and the
        # corpus names its guides constantly. This is the reachable case rather than the
        # hypothetical one: the live manifest's only anchor is `tooling-gotchas.md`.
        return any((d / anchor).is_file() for d in dirs)
    for f in texts:
        if f.is_file() and anchor in corpus_text(f, collect):
            return True
    return False


def backup(path):
    shutil.copy2(path, path.with_suffix(path.suffix + f".bak-migrate-{time.strftime('%Y%m%d-%H%M%S')}"))


def atomic_write(path, text):
    """Back up, then replace atomically so a crash mid-write can never truncate the
    durable personal file.

    The replace itself is compose/assemble.py's — that module needed the same discipline
    for the user's settings.json and AGENTS.md, and a four-line primitive written twice is
    two places for the next `os.replace` subtlety to be got right in only one of them. The
    BACKUP stays here: its `.bak-migrate-<ts>` name is what prune-backups.py matches to
    know the copy is ours, and assemble's writes carry a different one.
    """
    backup(path)
    assemble.replace_atomically(path, text)


def prune_jsonl(jsonl, remove_ids, dry):
    """Drop records whose learning_id is being removed. Returns count removed."""
    if not jsonl.is_file():
        return 0
    kept, removed = [], 0
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s:
            try:
                rec = json.loads(s)
                if isinstance(rec, dict) and rec.get("learning_id") in remove_ids:
                    removed += 1
                    continue
            except json.JSONDecodeError:
                pass  # keep malformed lines untouched
        kept.append(line)
    if removed and not dry:
        atomic_write(jsonl, "\n".join(kept) + ("\n" if kept else ""))
    return removed


def prune_bullets(text, remove_ids):
    """Drop bullet lines whose comment learning_id is being removed. Returns
    (new_text, count). Non-bullet lines (header/comments) are preserved."""
    out, removed = [], 0
    for line in text.splitlines():
        m = BULLET_LID_RE.search(line)
        if m and m.group(1) in remove_ids:
            removed += 1
            continue
        out.append(line)
    new = "\n".join(out) + ("\n" if text.endswith("\n") and out else "")
    return new, removed


def prune_claude_prose(home, remove_ids, dry):
    md = home / "personal" / "learnings.md"
    if not md.is_file():
        return 0
    new, removed = prune_bullets(md.read_text(encoding="utf-8"), remove_ids)
    if removed and not dry:
        atomic_write(md, new)
    return removed


def prune_codex_prose(home, remove_ids, collect, dry):
    """Bullets removed, or None when the personal region is MALFORMED.

    None rather than 0, because the caller has to tell "nothing matched" from "this file
    cannot be pruned at all". Both used to read as 0, and the jsonl prune ran anyway —
    deleting the durable record out from under a bullet still on screen, which is the
    opposite of the no-op the malformed case promises.
    """
    agents = home / "AGENTS.md"
    if not agents.is_file():
        return 0     # no personal prose here at all — nothing to strand
    body = agents.read_text(encoding="utf-8")
    start, end = collect.PERSONAL_START, collect.PERSONAL_END
    if start not in body:
        return 0     # region never opened — same as above
    pre, rest = body.split(start, 1)
    if end not in rest:   # malformed (missing, or END before START) → touch nothing
        return None
    region, post = rest.split(end, 1)
    new_region, removed = prune_bullets(region, remove_ids)
    if removed and not dry:
        atomic_write(agents, f"{pre}{start}{new_region}{end}{post}")
    return removed


def claude_corpus_loaded(home, state_dir=None):
    """Is the shared corpus actually LOADED for this claude home?

    Removing a personal copy while the corpus copy is not loaded makes the rule
    vanish (Review F2). The entry import line is necessary and NOT sufficient. Testing
    whether the file contains `@central/bundle.md` also passes on the string in a
    fenced block or in prose, and no reading of the file can see an import the
    harness was told not to load — the case PU-13 exists to name. So the
    authorization is the activation canary's proof, written only after a live
    session echoed the deployed bundle's rev back, and only for THAT rev: a later
    reassembly invalidates it rather than inheriting it.

    No proof means KEEP, not prune. A plain `install` runs no canary, so it now
    prunes nothing and the next run after `onboard` does it — a kept duplicate is
    redundant, a wrong removal is data loss.
    """
    entry = home / "CLAUDE.md"
    if not entry.is_file():
        return False
    # ACTIVE import, not raw containment. The paragraph above already says a fenced or
    # prose occurrence loads nothing; the test did not implement that, so the necessary
    # half of the authorization passed on text that imports nothing. The proof below is
    # bound to the bundle's rev and not to this file, so an entry edited after a passing
    # canary keeps a matching proof — which is exactly when the weak half decides.
    if not load_collect().has_active_import(
            entry.read_text(encoding="utf-8"), collect_central_import()):
        return False
    bundle = home / "central" / "bundle.md"
    proof = (state_dir or STATE_DIR) / "activation.txt"
    if not (bundle.is_file() and proof.is_file()):
        return False
    rev = next((ln for ln in bundle.read_text(encoding="utf-8").splitlines()
                if ln.startswith("agent-bios-bundle-rev: ")), None)
    return bool(rev) and rev.strip() == proof.read_text(encoding="utf-8").strip()


def collect_central_import():
    return "@central/bundle.md"


def migrate(home, host, promotions, in_bundle, collect, dry=False, corpus_loaded=True):
    """Remove personal copies of promoted+in-bundle learnings present locally.
    corpus_loaded=False (the corpus is not actually loaded for this host) -> keep
    everything (never orphan a personal copy)."""
    if not corpus_loaded:
        return {"removed": 0, "jsonl_removed": 0, "prose_removed": 0,
                "kept_not_in_bundle": 0, "skipped": "corpus-not-loaded"}
    jsonl = home / "personal" / "learnings.jsonl"
    local_ids = set()
    if jsonl.is_file():
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                rec = json.loads(s)
            except json.JSONDecodeError:
                continue
            lid = rec.get("learning_id") if isinstance(rec, dict) else None
            if isinstance(lid, str):
                local_ids.add(lid)

    # Metadata SELECTS candidates; presence in the deployed corpus AUTHORIZES the
    # delete (contract v2 §4). Audience metadata is a build-time projection: it
    # cannot see that this user is on a package or version whose bundle never
    # received the promoted bullet, and acting on it alone loses the learning.
    # Every uncertainty below resolves to KEEP.
    remove_ids, kept_not_in_bundle, kept_not_placed, kept_foreign_pkg = set(), 0, 0, 0
    for p in promotions:
        lid = p["learning_id"]
        if lid not in local_ids:
            continue  # not held locally (never captured here, or already migrated)
        pid = pkgid.resolve(p)
        if pid != pkgid.CORE:
            # Stage 3 resolves a package selection; until then the only package
            # whose composition we can confirm is core.
            kept_foreign_pkg += 1
            continue
        if not in_bundle(p.get("tier"), p.get("domains", [])):
            kept_not_in_bundle += 1  # promoted but not in THIS user's audience
            continue
        if not placed_here(home, p.get("anchor"), collect):
            kept_not_placed += 1     # audience says yes, the corpus does not have it
            continue
        remove_ids.add(lid)

    # Prune PROSE first, jsonl second: the gate keys off ids still in the jsonl
    # (line ~"if lid not in local_ids: continue"), so if a prose write fails, the
    # id survives in jsonl and a re-run re-enters and converges. The reverse order
    # would strand the prose bullet forever after a jsonl-only success (Review F4).
    if host == "codex":
        prose_removed = prune_codex_prose(home, remove_ids, collect, dry)
        if prose_removed is None:
            # The malformed-marker contract is "touch nothing", and it used to hold for
            # exactly one of the two representations. A record and the bullet keyed by it
            # move together or not at all.
            return {"removed": 0, "jsonl_removed": 0, "prose_removed": 0,
                    "kept_not_in_bundle": kept_not_in_bundle,
                    "kept_not_placed": kept_not_placed,
                    "kept_foreign_package": kept_foreign_pkg,
                    "skipped": "personal-region-malformed"}
    else:
        prose_removed = prune_claude_prose(home, remove_ids, dry)
    jsonl_removed = prune_jsonl(jsonl, remove_ids, dry)

    return {"removed": len(remove_ids), "jsonl_removed": jsonl_removed,
            "prose_removed": prose_removed, "kept_not_in_bundle": kept_not_in_bundle,
            "kept_not_placed": kept_not_placed, "kept_foreign_package": kept_foreign_pkg}


def main():
    ap = argparse.ArgumentParser(description="Clear personal copies of promoted learnings.")
    # Not argparse-required, so --self-test runs standalone; validated below.
    ap.add_argument("--host", choices=("claude", "codex"))
    ap.add_argument("--config-dir", default=None,
                    help="config home (default: $CLAUDE_CONFIG_DIR / $CODEX_HOME by host)")

    ap.add_argument("--selection-file",
                    help="packaged install: selection.json ({\"domains\":[...]})")
    ap.add_argument("--domains", help="packaged: comma-separated selection (overrides --selection-file)")
    ap.add_argument("--manifest", default=None,
                    help="promotion manifest (default: learn/promotions.json)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        _self_test()
        return

    if os.environ.get("AGENT_BIOS_LEGACY_INSTALL") != "1":
        print("migrate-learnings: private capture sources retained; promotion suppression is resolved per session snapshot")
        return

    if not args.host:
        die("--host claude|codex is required")
    if args.selection_file is None and args.domains is None:
        die("pass --selection-file or --domains")

    promotions = load_manifest(pathlib.Path(args.manifest) if args.manifest else MANIFEST)
    if not promotions:
        print("migrate-learnings: no promotions in the manifest — nothing to migrate")
        return

    collect = load_collect()
    home = collect.resolve_home(args.host, args.config_dir)

    # F2 gate: only prune where the shared corpus is actually loaded. Codex always
    # loads AGENTS.md's central region; claude loads central only via the entry
    # import (or inline in a full install).
    corpus_loaded = True if args.host == "codex" else claude_corpus_loaded(home)

    if args.domains is not None:
        selection = [d for d in args.domains.split(",") if d]
    else:
        sel_path = pathlib.Path(args.selection_file)
        if not sel_path.is_file():
            die(f"selection file not found: {sel_path}")
        selection = json.loads(sel_path.read_text(encoding="utf-8")).get("domains", [])
    in_bundle = make_in_bundle(selection)

    s = migrate(home, args.host, promotions, in_bundle, collect,
                dry=args.dry_run, corpus_loaded=corpus_loaded)
    tag = "[dry] " if args.dry_run else ""
    if s.get("skipped"):
        print(f"migrate-learnings: {tag}host={args.host} skipped ({s['skipped']}) — "
              "kept every personal copy")
        return
    print(f"migrate-learnings: {tag}host={args.host} removed={s['removed']} "
          f"(jsonl={s['jsonl_removed']} prose={s['prose_removed']}) "
          f"kept_not_in_bundle={s['kept_not_in_bundle']}")


# What a "full" install now means: every domain selected. The fixtures that used to
# pass `full=True` say it this way, because that is the shape the code has.
ALL_DOMAINS = ["builder-base", "llm-pipeline-dev", "multi-agent-orchestration",
               "office-work", "visualization-docs"]


def _self_test():
    """Temp-home verification: the safety gate (keep a promotion not in the
    user's bundle), removal of an in-bundle promotion from BOTH prose + jsonl,
    idempotency, and that the user's own '## Personal' text is untouched. Uses
    collect-learning's own writers so the seeded format is authoritative."""
    import tempfile

    collect = load_collect()

    def rec(lid, domain):
        return {"lesson": f"lesson for {domain} " + "x" * 10, "domain": domain,
                "supporting_sessions": ["claude:abcd1234"],
                "learning_id": lid, "schema_version": 1, "created": "2026-07-21T00:00:00Z"}

    L = {"core": "0f8c1c2a-4d1e-4abc-9def-0000000000a1",
         "bb": "0f8c1c2a-4d1e-4abc-9def-0000000000b2",
         "off": "0f8c1c2a-4d1e-4abc-9def-0000000000c3"}
    A = {"core": "universal corpus rule", "bb": "builder corpus rule",
         "off": "office corpus rule"}
    promos = [{"learning_id": L["core"], "anchor": A["core"], "tier": "core", "domains": []},
              {"learning_id": L["bb"], "anchor": A["bb"], "tier": "domain", "domains": ["builder-base"]},
              {"learning_id": L["off"], "anchor": A["off"], "tier": "domain", "domains": ["office-work"]}]

    def seed_claude(placed=("core", "bb", "off")):
        """`placed` = which promoted anchors this user's DEPLOYED corpus actually
        carries. Deletion is authorized by that, not by the audience metadata, so
        a fixture without a corpus would let a metadata-only bug pass."""
        home = pathlib.Path(tempfile.mkdtemp(prefix="migrate-selftest-"))
        (home / "personal").mkdir(parents=True)
        (home / "central").mkdir(parents=True)
        (home / "central" / "bundle.md").write_text(
            "# bundle\n" + "".join(f"- {A[k]}\n" for k in placed), encoding="utf-8")
        jsonl = home / "personal" / "learnings.jsonl"
        with open(jsonl, "w", encoding="utf-8") as f:
            for k, dom in (("core", "core"), ("bb", "builder-base"), ("off", "office-work")):
                r = rec(L[k], dom)
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                collect.apply_claude(home, collect.prose_bullet(r), dry=False)
        # a user-owned '## Personal' line that migrate must never touch
        entry = home / "CLAUDE.md"
        entry.write_text(entry.read_text(encoding="utf-8") + "\n## Personal\n- my own rule\n", encoding="utf-8")
        return home

    def local_ids(home):
        return {json.loads(l)["learning_id"]
                for l in (home / "personal" / "learnings.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}

    def md_has(home, lid):
        return lid in (home / "personal" / "learnings.md").read_text(encoding="utf-8")

    checks = []

    # 1) Packaged, selection={builder-base}: core (universal) + builder-base
    #    removed; office-work KEPT (the silent-loss guard).
    home = seed_claude()
    in_bundle = make_in_bundle(["builder-base"])
    s = migrate(home, "claude", promos, in_bundle, collect)
    ids = local_ids(home)
    checks.append(("packaged: removed core+builder-base", s["removed"] == 2 and s["kept_not_in_bundle"] == 1))
    checks.append(("packaged: office-work KEPT (not selected)", L["off"] in ids and md_has(home, L["off"])))
    checks.append(("packaged: core+bb gone from jsonl", L["core"] not in ids and L["bb"] not in ids))
    checks.append(("packaged: core+bb gone from prose", not md_has(home, L["core"]) and not md_has(home, L["bb"])))
    checks.append(("user '## Personal' untouched", "my own rule" in (home / "CLAUDE.md").read_text(encoding="utf-8")))
    # idempotent re-run removes nothing more
    s2 = migrate(home, "claude", promos, in_bundle, collect)
    checks.append(("idempotent re-run", s2["removed"] == 0))

    # 1b) CONTRAST CONTROL for the v2 authorization. Same audience metadata as
    #     above — builder-base IS selected — but this user's deployed corpus does
    #     NOT carry the bullet (a package/version whose bundle never got it). The
    #     metadata-only rule deletes here and loses the learning; presence keeps.
    #     If placed_here() ever returns True unconditionally, this check fails.
    home = seed_claude(placed=("core",))
    s = migrate(home, "claude", promos, make_in_bundle(["builder-base"]), collect)
    checks.append(("audience says yes but corpus lacks it -> KEEP",
                   s["removed"] == 1 and s["kept_not_placed"] == 1
                   and L["bb"] in local_ids(home) and md_has(home, L["bb"])))

    # 1c) A promotion from a package whose composition cannot be confirmed is
    #     never acted on (stage 3 resolves package selections).
    home = seed_claude()
    foreign = [dict(promos[1], package_id="@acme/security")]
    s = migrate(home, "claude", foreign, make_in_bundle(ALL_DOMAINS), collect)
    checks.append(("foreign package -> KEEP",
                   s["removed"] == 0 and s["kept_foreign_package"] == 1))

    # 1d) The personal copy must not authorize its own deletion: on codex the
    #     copy lives inside AGENTS.md, so the anchor can appear there legitimately.
    ahome = pathlib.Path(tempfile.mkdtemp(prefix="migrate-selfauth-"))
    (ahome / "AGENTS.md").write_text(
        f"# AGENTS.md\n{collect.PERSONAL_START}\n- {A['bb']}\n{collect.PERSONAL_END}\n",
        encoding="utf-8")
    checks.append(("personal region cannot authorize its own delete",
                   placed_here(ahome, A["bb"], collect) is False
                   and placed_here(ahome, A["bb"], None) is True))

    # 2) Full (non-packaged) install: everything in bundle -> all removed.
    home = seed_claude()
    s = migrate(home, "claude", promos, make_in_bundle(ALL_DOMAINS), collect)
    checks.append(("full install: all 3 removed", s["removed"] == 3 and not local_ids(home)))

    # 3) dry-run changes nothing on disk.
    home = seed_claude()
    before = (home / "personal" / "learnings.jsonl").read_text(encoding="utf-8")
    migrate(home, "claude", promos, make_in_bundle(ALL_DOMAINS), collect, dry=True)
    checks.append(("dry-run writes nothing",
                   (home / "personal" / "learnings.jsonl").read_text(encoding="utf-8") == before))

    # 4) codex host: seed the AGENTS.md region, migrate prunes it there.
    chome = pathlib.Path(tempfile.mkdtemp(prefix="migrate-codex-"))
    (chome / "personal").mkdir(parents=True)
    (chome / "AGENTS.md").write_text(f"# AGENTS.md\n- {A['bb']}\n", encoding="utf-8")
    with open(chome / "personal" / "learnings.jsonl", "w", encoding="utf-8") as f:
        r = rec(L["bb"], "builder-base")
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
        collect.apply_codex(chome, collect.prose_bullet(r), dry=False)
    s = migrate(chome, "codex", promos, make_in_bundle(ALL_DOMAINS), collect)
    agents_txt = (chome / "AGENTS.md").read_text(encoding="utf-8")
    checks.append(("codex: bullet removed from AGENTS.md region",
                   s["prose_removed"] == 1 and L["bb"] not in agents_txt))

    # 5) F2 gate: a packaged claude entry lacking @central/bundle.md means the
    #    corpus is NOT loaded -> keep everything (never orphan a personal copy).
    home = seed_claude()  # apply_claude writes an entry WITHOUT @central/bundle.md
    checks.append(("F2: unwired packaged entry -> corpus not loaded",
                   claude_corpus_loaded(home) is False))
    s = migrate(home, "claude", promos, make_in_bundle(["builder-base"]),
                collect, corpus_loaded=False)
    checks.append(("F2: corpus-not-loaded keeps ALL",
                   s.get("skipped") == "corpus-not-loaded"
                   and local_ids(home) == {L["core"], L["bb"], L["off"]}))
    entry = home / "CLAUDE.md"
    entry.write_text(entry.read_text(encoding="utf-8") + "\n@central/bundle.md\n", encoding="utf-8")
    # The import line is necessary and NOT sufficient. Reading the file cannot see an import the
    # harness declined, which is what the canary exists to detect, so the authorization is its
    # recorded proof — and the proof is bound to a rev, so a reassembly does not inherit it.
    checks.append(("F2: wired entry, no activation proof -> KEEP",
                   claude_corpus_loaded(home, state_dir=home / "state") is False))
    bundle = home / "central" / "bundle.md"
    bundle.write_text(bundle.read_text(encoding="utf-8") + "\nagent-bios-bundle-rev: deadbeef\n",
                      encoding="utf-8")
    state = home / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "activation.txt").write_text("agent-bios-bundle-rev: deadbeef\n", encoding="utf-8")
    checks.append(("F2: wired entry + matching proof -> corpus loaded",
                   claude_corpus_loaded(home, state_dir=state) is True))
    (state / "activation.txt").write_text("agent-bios-bundle-rev: 00000000\n", encoding="utf-8")
    checks.append(("F2: proof for a different rev -> KEEP",
                   claude_corpus_loaded(home, state_dir=state) is False))
    # CONTRAST CONTROL for the substring hole: the import string inside a fenced block is not an
    # import, and before the proof requirement this alone authorized the delete.
    fenced = pathlib.Path(tempfile.mkdtemp(prefix="migrate-fenced-"))
    (fenced / "CLAUDE.md").write_text("# CLAUDE.md\n```\n@central/bundle.md\n```\n", encoding="utf-8")
    checks.append(("F2: import string with no activation proof -> KEEP",
                   claude_corpus_loaded(fenced, state_dir=fenced) is False))
    # …and the same file WITH a matching proof, which is the case the line above cannot
    # separate: it passes whether the import test is honest or not, because the missing
    # proof decides it either way. The proof is bound to the bundle's rev and not to this
    # file, so an entry edited after a passing canary keeps one — and then the import test
    # is the only thing left standing between a fenced example and a delete.
    (fenced / "central").mkdir(parents=True, exist_ok=True)
    (fenced / "central" / "bundle.md").write_text(
        "# bundle\nagent-bios-bundle-rev: deadbeef\n", encoding="utf-8")
    (fenced / "activation.txt").write_text("agent-bios-bundle-rev: deadbeef\n", encoding="utf-8")
    checks.append(("F2: FENCED import + matching proof -> still KEEP",
                   claude_corpus_loaded(fenced, state_dir=fenced) is False))
    (fenced / "CLAUDE.md").write_text("# CLAUDE.md\n@central/bundle.md\n", encoding="utf-8")
    checks.append(("F2: the same proof with a REAL import -> loaded",
                   claude_corpus_loaded(fenced, state_dir=fenced) is True))

    # placed_here verifies a whole-file placement as a FILE and a bullet anchor as TEXT.
    # They used to be OR'd, so any corpus document that merely NAMED a guide authorized
    # deleting the personal copy of a learning placed in it — and the live manifest's one
    # anchor is `tooling-gotchas.md`, which the entry file names in prose.
    mention = pathlib.Path(tempfile.mkdtemp(prefix="migrate-anchor-"))
    (mention / "guides").mkdir(parents=True)
    (mention / "CLAUDE.md").write_text(
        "# CLAUDE.md\nsee guides/tooling-gotchas.md for the traps\nthe bullet text itself\n",
        encoding="utf-8")
    checks.append(("anchor: a named-but-absent guide is NOT placed",
                   placed_here(mention, "tooling-gotchas.md") is False))
    checks.append(("anchor: a phrase anchor still matches corpus TEXT",
                   placed_here(mention, "the bullet text itself") is True))
    (mention / "guides" / "tooling-gotchas.md").write_text("# guide\n", encoding="utf-8")
    checks.append(("anchor: the deployed guide file IS placed",
                   placed_here(mention, "tooling-gotchas.md") is True))
    # (The old "full install is always loaded" case is gone with full mode: there is no shape
    # whose corpus loads without the entry import, so nothing is exempt from the proof.)

    # 6) F5: the TRAILING comment's id wins; a learning_id quoted in the lesson
    #    body must never shadow it (else a jsonl/prose desync).
    twin = ("- [core] cf <!-- learning_id: aaaa0000-0000-0000-0000-000000000000 "
            "created: x --> here  <!-- learning_id: 11112222-3333-4444-5555-666677778888 "
            "created: y -->\n")
    _, r_real = prune_bullets(twin, {"11112222-3333-4444-5555-666677778888"})
    _, r_quoted = prune_bullets(twin, {"aaaa0000-0000-0000-0000-000000000000"})
    checks.append(("F5: trailing id removed, quoted id ignored", r_real == 1 and r_quoted == 0))

    # 7) malformed codex markers (END before START) -> no-op, no corruption. "No-op" is a
    #    claim about BOTH representations: reporting 0 removed said the same thing as
    #    "nothing matched", so migrate() went on to delete the durable jsonl record while
    #    the visible bullet stayed on screen. None is the signal that distinguishes them.
    bad = pathlib.Path(tempfile.mkdtemp(prefix="migrate-badcodex-"))
    (bad / "personal").mkdir(parents=True)
    agents = bad / "AGENTS.md"
    agents.write_text(f"x {collect.PERSONAL_END} y {collect.PERSONAL_START} z", encoding="utf-8")
    before = agents.read_text(encoding="utf-8")
    rem = prune_codex_prose(bad, {"anything"}, collect, dry=False)
    checks.append(("malformed codex markers -> no-op",
                   rem is None and agents.read_text(encoding="utf-8") == before))
    bad_rec = rec(L["bb"], "builder-base")
    (bad / "personal" / "learnings.jsonl").write_text(
        json.dumps(bad_rec, ensure_ascii=False) + "\n", encoding="utf-8")
    s = migrate(bad, "codex", promos, make_in_bundle(ALL_DOMAINS), collect)
    checks.append(("malformed markers -> the jsonl record survives too",
                   s.get("skipped") == "personal-region-malformed"
                   and s["removed"] == 0 and local_ids(bad) == {L["bb"]}))
    # The control for that: a WELL-FORMED region under the same call really does delete,
    # so the assertion above is not passing because migrate() stopped working.
    ok_home = pathlib.Path(tempfile.mkdtemp(prefix="migrate-okcodex-"))
    (ok_home / "personal").mkdir(parents=True)
    (ok_home / "AGENTS.md").write_text(f"# AGENTS.md\n- {A['bb']}\n", encoding="utf-8")
    with open(ok_home / "personal" / "learnings.jsonl", "w", encoding="utf-8") as f:
        r = rec(L["bb"], "builder-base")
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
        collect.apply_codex(ok_home, collect.prose_bullet(r), dry=False)
    s = migrate(ok_home, "codex", promos, make_in_bundle(ALL_DOMAINS), collect)
    checks.append(("well-formed markers -> both representations go",
                   s.get("skipped") is None and s["removed"] == 1 and not local_ids(ok_home)))

    # 8) "Manifest absent/empty -> no-op" covers an existing zero-byte file, which used to
    #    reach json.loads("") and raise out of the update path.
    empty_dir = pathlib.Path(tempfile.mkdtemp(prefix="migrate-manifest-"))
    empty = empty_dir / "promotions.json"
    empty.write_text("", encoding="utf-8")
    checks.append(("empty manifest file -> no-op", load_manifest(empty) == []))
    (empty_dir / "whitespace.json").write_text("  \n\t\n", encoding="utf-8")
    checks.append(("whitespace-only manifest -> no-op",
                   load_manifest(empty_dir / "whitespace.json") == []))
    valid = empty_dir / "valid.json"
    valid.write_text('{"version": 2, "promotions": [{"learning_id": "x"}]}', encoding="utf-8")
    checks.append(("a real manifest still loads", len(load_manifest(valid)) == 1))

    failed = [n for n, ok in checks if not ok]
    if failed:
        for n in failed:
            print(f"migrate-learnings --self-test: FAIL: {n}", file=sys.stderr)
        sys.exit(1)
    print(f"migrate-learnings --self-test: OK ({len(checks)} migrate checks)")


if __name__ == "__main__":
    main()
