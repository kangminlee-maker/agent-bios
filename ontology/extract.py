#!/usr/bin/env python3
"""Derive ontology facts from the real repository — the happy path, not a full survey.

Rule this file exists to serve: an ontology claim must come from the implementation.
Everything here is READ OUT of source; nothing is authored. Where an extractor cannot
see a fact, it says so instead of guessing, because a confidently wrong graph is worse
than a visibly incomplete one.

One trap already paid for, encoded as a test of the extractor's own shape: a CLI
subcommand lives at THREE sites in install.sh — an early branch before the flag parser,
the `case "$CMD"` block, and the usage() advertisement. An extractor keyed on the case
block alone reports `learn` as nonexistent. So SUBCOMMANDS unions all three and reports
the disagreement rather than one site's answer.

Usage: extract.py [--json OUT] [--quiet]
"""
from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
INSTALL = REPO / "install.sh"


def read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


# ── F4 · distribution ────────────────────────────────────────────────────────

def deploy_targets() -> list[dict]:
    """(source, destination) pairs the installer writes, from real call sites."""
    text = read(INSTALL)
    out = []
    for m in re.finditer(r'^\s*deploy_file\s+"(\$REPO/[^"]+)"\s+"([^"]+)"(?:\s+"(\+x)")?', text, re.M):
        out.append({"kind": "file", "src": m.group(1), "dst": m.group(2),
                    "mode": m.group(3) or "", "line": text[: m.start()].count("\n") + 1})
    for m in re.finditer(r'^\s*deploy_glob\s+"(\$REPO/[^"]+)"\s+"([^"]+)"\s+"([^"]+)"(?:\s+"(\+x)")?', text, re.M):
        out.append({"kind": "glob", "src": f"{m.group(1)}/{m.group(2)}", "dst": m.group(3),
                    "mode": m.group(4) or "", "line": text[: m.start()].count("\n") + 1})
    # A subtree deployed file by file (skills: SKILL.md plus free subdirectories). The
    # call sits inside a loop over the shipped skills, so its arguments carry `$skill`;
    # the pattern keeps that variable as part of the source and destination it names.
    for m in re.finditer(r'^\s*deploy_tree\s+"(\$REPO/[^"]+)"\s+"([^"]+)"', text, re.M):
        out.append({"kind": "tree", "src": m.group(1), "dst": m.group(2),
                    "mode": "", "line": text[: m.start()].count("\n") + 1})
    # deploy_file's own recursive call inside deploy_glob is machinery, not a target.
    return [d for d in out if "$REPO/" in d["src"]]


def verify_subjects() -> list[dict]:
    """What cmd_verify actually asserts, with the strength of each assertion."""
    text = read(INSTALL)
    out = []
    for fn, strength in (("verify_match", "byte-identity"), ("verify_present", "existence")):
        for m in re.finditer(rf'{fn}\s+"([^"]+)"(?:\s+"([^"]+)")?', text):
            line = text[: m.start()].count("\n") + 1
            # The two one-line definitions are not call sites.
            if re.match(rf"^\s*{fn}\(\)", text.splitlines()[line - 1]):
                continue
            dst = m.group(2) or m.group(1)
            out.append({"fn": fn, "subject": dst, "strength": strength, "line": line})
    return out


def subcommands(source: str | None = None) -> dict:
    """Union of the three sites, plus the disagreements between them."""
    text = read(INSTALL) if source is None else source
    case_blocks = re.findall(r'^\s*case "\$CMD" in$(.*?)^\s*esac$', text, re.M | re.S)
    dispatched = {name for block in case_blocks
                  for name in re.findall(r"^\s+([a-z|h-]+)\)", block, re.M)}
    # Keep `help`: it is dispatched (`help|-h|--help`) and advertised, so filtering it
    # out here invented an "advertised but absent" finding that was the filter's fault,
    # not the installer's. Only the catch-all is not a subcommand.
    dispatched = {t for part in dispatched for t in part.split("|")} - {"*", "-h", "--help"}
    early = set(re.findall(r'\[\s*"\$CMD"\s*=\s*"([a-z-]+)"\s*\]', text))
    usage = re.search(r"^usage\(\)\s*\{(.*?)^\}", text, re.M | re.S)
    advertised = set(re.findall(r"^[ \t]+agent-bios[ \t]+([a-z-]+)(?=[ \t]|$)",
                                usage.group(1) if usage else "", re.M))
    implemented = dispatched | early
    return {
        "dispatched_in_case": sorted(dispatched),
        "early_branch": sorted(early),
        "advertised_in_usage": sorted(advertised),
        "implemented": sorted(implemented),
        "advertised_but_absent": sorted(advertised - implemented),
        "implemented_but_unadvertised": sorted(implemented - advertised),
    }


def payload_files() -> list[str]:
    return json.loads(read(REPO / "package.json"))["files"]


def runtime_authorities(repo: pathlib.Path | None = None) -> dict:
    """Statically named lifecycle entrypoints and their repository-local Python imports.

    The installer supplies compose/launch/learn script roots. The launcher is also a root
    because its session adapter is reached through the installed launcher entrypoint.
    Literal import_module alternatives are followed through assignments. Arbitrary
    computed module names and dynamic file loaders are outside this scan.
    """
    repo = REPO if repo is None else repo
    install = read(repo / "install.sh")
    roots = set(re.findall(r'\$REPO/((?:compose|launch|learn)/[\w-]+\.py)', install))
    roots.add("launch/agent-launch.py")
    visited, imports = set(), set()
    pending = sorted(roots)
    while pending:
        source = pending.pop()
        if source in visited:
            continue
        visited.add(source)
        tree = ast.parse(read(repo / source), filename=source)
        assignments = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assignments.setdefault(target.id, []).append(node.value)

        def module_literals(node, seen=frozenset()):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return [node.value]
            if isinstance(node, ast.IfExp):
                return module_literals(node.body, seen) + module_literals(node.orelse, seen)
            if isinstance(node, ast.Name) and node.id not in seen:
                return [name for value in assignments.get(node.id, [])
                        for name in module_literals(value, seen | {node.id})]
            return []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and node.func.attr == "import_module" and node.args):
                names = module_literals(node.args[0])
            else:
                continue
            for name in names:
                for directory in (pathlib.Path(source).parent, pathlib.Path("compose"),
                                  pathlib.Path("launch"), pathlib.Path("learn")):
                    target = str(directory / (name.replace(".", "/") + ".py"))
                    if (repo / target).is_file():
                        imports.add((source, target))
                        pending.append(target)
                        break
    return {"entrypoints": sorted(roots), "modules": sorted(visited),
            "local_imports": [{"source": source, "target": target}
                              for source, target in sorted(imports)]}


def user_owned_regions() -> list[dict]:
    """Managed user-file spans on the legacy install and explicit shell-connection routes.

    Ops describe each span's own install/remove route. Explicit private migration
    cleanup is owned separately by CorpusInstaller and its pinned cleanup plan.
    """
    install = read(INSTALL)
    assemble = read(REPO / "compose" / "assemble.py")
    shell = read(REPO / "launch" / "shell_integration.py")
    def body_of(fn):
        # No permissive fallback: if the function cannot be located the answer is unknown, and
        # silently substituting the whole file would turn every op into "present" — a gate-shaped
        # lie. `check` means asserted by cmd_verify; cmd_status REPORTS the zsh hook and that is
        # not the same act, which is why the search is scoped to one body rather than the file.
        m = re.search(rf"^{fn}\(\)\s*\{{(.*?)^\}}", install, re.M | re.S)
        if not m:
            raise RuntimeError(f"extract: {fn}() not found in install.sh — cannot derive "
                               f"user-owned-region lifecycle ops without it")
        return m.group(1)

    uninstall_body, verify_body = body_of("cmd_uninstall"), body_of("cmd_verify")

    def ops_for(*, merge, check, remove):
        return sorted(k for k, v in (("merge", merge), ("check", check), ("remove", remove)) if v)

    codex_ops = set(re.findall(r"codex_config_additions\s+(\w+)", install))
    regions = [
        {"span": "zshrc hook line", "target": "$ZDOTDIR/.zshrc", "authored_in": "install.sh",
         "marker": "HOOK_MARK", "kind": "tagged line",
         "ops": ops_for(merge="add_zsh_hook" in install,
                        check="HOOK_MARK" in verify_body,
                        remove="remove_zsh_hook" in uninstall_body)},
        {"span": "codex config additions", "target": "$CODEX_HOME/config.toml",
         "authored_in": "install.sh", "marker": "agent-bios additions", "kind": "marker pair",
         "ops": ops_for(merge="merge" in codex_ops, check="check" in codex_ops,
                        remove="remove" in codex_ops)},
        {"span": "settings hook registrations", "target": "$CLAUDE_CONFIG_DIR/settings.json",
         "authored_in": "compose/assemble.py", "marker": "manifest name", "kind": "owned by name",
         "ops": ops_for(merge="def merge_settings" in assemble,
                        check="settings.json" in verify_body,
                        remove="merge_settings" in uninstall_body or "settings" in uninstall_body)},
        {"span": "AGENTS.md central region", "target": "$CODEX_HOME/AGENTS.md",
         "authored_in": "compose/assemble.py", "marker": "MARK_START/MARK_END",
         "kind": "marker pair",
         "ops": ops_for(merge="def merge_codex" in assemble or "MARK_START" in assemble,
                        check="MARK_START" in verify_body or "agent-bios:central" in verify_body,
                        remove="MARK_START" in uninstall_body
                               or "agent-bios:central" in uninstall_body)},
    ]
    for region in regions:
        region["scope"] = "legacy installation"
    regions.append({
        "span": "optional shell connection block", "target": "$ZDOTDIR/.zshrc",
        "authored_in": "launch/shell_integration.py", "marker": "START/END",
        "kind": "marker pair", "scope": "explicit shell restore/remove",
        "ops": ops_for(merge='action == "restore"' in shell and "def apply(" in shell,
                       check="def plan(" in shell and "def _strip(" in shell,
                       remove='action == "remove"' in shell and "def apply(" in shell),
    })
    return [{
        "regions": regions,
        "authoring_sites": sorted({r["authored_in"] for r in regions}),
        "merge_without_remove": [r["span"] for r in regions if "remove" not in r["ops"]],
        "merge_without_check": [r["span"] for r in regions if "check" not in r["ops"]],
        "codex_ops": sorted(codex_ops),
    }]


# ── F1 · instruction content ─────────────────────────────────────────────────

def guides() -> list[dict]:
    out = []
    for p in sorted((REPO / "claude" / "guides").glob("*.md")):
        head = read(p)[:4000]
        gid = re.search(r"^guide_id:\s*(\S+)", head, re.M)
        out.append({
            "file": p.name,
            "guide_id": gid.group(1) if gid else None,
            "id_matches_filename": bool(gid) and gid.group(1) == p.stem,
            "has_use_when": bool(re.search(r"^use_when:", head, re.M)),
            "has_core_rules": bool(re.search(r"^core_rules:", head, re.M)),
        })
    return out


def domain_manifest() -> dict:
    """The manifest, the corpus text, and the filesystem — three authors of one classification.

    Reading the manifest alone made it the truth by construction: an anchor that no longer
    matched a bullet, or a guide on disk nobody claimed, looked like a well-formed manifest.
    `compose/check-domains.py` already compares all three; the matching rules here are ITS rules
    (a bullet is a line starting with `- `; an anchor matches by substring and must hit exactly
    one), so the two cannot drift into different definitions of the same disagreement.

    What this adds over that gate is visibility: the ontology can now see the comparison exists
    and what it currently says, instead of trusting one site's account.
    """
    d = json.loads(read(REPO / "compose" / "domains.json"))
    bullets = [ln for ln in read(REPO / "claude" / "CLAUDE.md").splitlines() if ln.startswith("- ")]
    sections = {"guides": ("claude/guides", "*.md"),
                "hooks": ("claude/hooks", "*"),
                "agents": ("claude/agents", "*.md"),
                "skills": ("claude/skills", "*")}   # a skill's unit is a directory carrying SKILL.md

    anchor_hits, claimed_count = {}, [0] * len(bullets)
    for entry in d["bullets"]:
        anchor = entry.get("anchor", "")
        hits = [j for j, b in enumerate(bullets) if anchor and anchor in b]
        anchor_hits[anchor or "<empty>"] = len(hits)
        for j in hits:
            claimed_count[j] += 1

    on_disk, claimed_missing, unclaimed = {}, [], []
    for key, (rel, glob) in sections.items():
        if key == "skills":
            files = {p.name for p in (REPO / rel).glob(glob) if (p / "SKILL.md").is_file()}
        else:
            files = {p.name for p in (REPO / rel).glob(glob) if p.is_file()}
        on_disk[key] = sorted(files)
        claimed = set(d.get(key, {}))
        claimed_missing += [f"{key}/{n}" for n in sorted(claimed - files)]
        unclaimed += [f"{key}/{n}" for n in sorted(files - claimed)]

    return {
        "package_id": d["package_id"],
        "tiers": d["tiers"],
        "domains": sorted(d["domains"]),
        "counts": {k: len(d[k]) for k in ("bullets", "guides", "hooks", "agents", "skills")},
        "bullets_untiered": [b.get("anchor", "?") for b in d["bullets"] if not b.get("tier")],
        "guides_unclassified": [k for k, v in d["guides"].items()
                                if not v.get("domains") and v.get("tier") == "domain"],
        "sites": {"manifest": "compose/domains.json",
                  "corpus_text": "claude/CLAUDE.md",
                  "filesystem": sorted(rel for rel, _ in sections.values())},
        "corpus_bullet_count": len(bullets),
        "files_on_disk": on_disk,
        "anchors_not_matching_one_bullet": {a: n for a, n in anchor_hits.items() if n != 1},
        "bullets_not_claimed_once": [bullets[j][:70] for j, n in enumerate(claimed_count) if n != 1],
        "claimed_but_missing": claimed_missing,
        "on_disk_but_unclaimed": unclaimed,
    }


# ── F3 · capability binding ──────────────────────────────────────────────────

def launch_profile() -> dict:
    import tomllib
    t = tomllib.loads(read(REPO / "launch" / "agent-launch.toml"))
    hosts = t.get("hosts", {})
    bindings = []
    for h, hv in hosts.items():
        for tier, tv in (hv.get("tiers") or {}).items():
            bindings.append({"host": h, "tier": tier, "model": tv.get("model"), "effort": tv.get("effort")})
    return {
        "top_level_tables": sorted(k for k, v in t.items() if isinstance(v, dict)),
        "scalars": {k: v for k, v in t.items() if not isinstance(v, dict)},
        "backends": sorted(t.get("backends", {})),
        "capabilities": sorted(t.get("capabilities", {})),
        "review_methods": sorted(t.get("review_methods", {})),
        "presets": sorted(t.get("presets", {})),
        "hosts": sorted(hosts),
        "tier_bindings": bindings,
        "models_declared": sorted({b["model"] for b in bindings if b["model"]}),
    }


def tier_binding_sites() -> dict:
    """Every site that restates a tier's model/effort, and where they disagree.

    Same shape as SUBCOMMANDS and for the same reason: one value, several authors. Folding
    these into one answer would make disagreement structurally invisible, which is how the
    binding drifted before.

    Absence is NOT disagreement. A template that declares a model and no effort is a site
    saying less, not a site saying something else — FRONTIER's effort varies per dispatch, so
    pinning it in the template would be the wrong fix. Only a value declared on both sides and
    differing is a conflict; everything else is reported for a human to classify.

    The guide `Environment Binding` tables restate the same bindings in display names
    ("GPT-5.6 Sol"), not ids. No declared id→display map exists, so they cannot be compared
    here without inventing one. That is recorded as an uncomparable site rather than guessed at.
    """
    import tomllib
    profile = tomllib.loads(read(REPO / "launch" / "agent-launch.toml"))
    codex_tiers = ((profile.get("hosts", {}).get("codex") or {}).get("tiers") or {})
    from_profile = {k: {"model": v.get("model"), "effort": v.get("effort")}
                    for k, v in codex_tiers.items()}

    # WHICH template files are tier templates is declared, not inferred from the directory:
    # `[hosts.codex.agent_templates]` maps a tier to its file. Comparing every *.toml against the
    # tier list instead treated `reviewer.toml` — a review role, never in that mapping — as a
    # tier missing its binding, which is a false contradiction produced by a wrong link rather
    # than by the code. Files outside the mapping are reported, not compared.
    declared = ((profile.get("hosts", {}).get("codex") or {}).get("agent_templates") or {})
    agents_dir = REPO / "codex" / "agents"
    from_templates, unmapped = {}, []
    for path in sorted(agents_dir.glob("*.toml")):
        t = tomllib.loads(read(path))
        entry = {"model": t.get("model"), "effort": t.get("model_reasoning_effort")}
        if path.stem in declared:
            from_templates[path.stem] = entry
        else:
            unmapped.append(path.stem)

    disagreements, undeclared = [], []
    for name in sorted(set(from_profile) & set(from_templates)):
        for field in ("model", "effort"):
            a, b = from_profile[name][field], from_templates[name][field]
            row = {"tier": name, "field": field, "launch_profile": a, "agent_template": b}
            if a is not None and b is not None and a != b:
                disagreements.append(row)
            elif (a is None) != (b is None):
                undeclared.append(row)

    return {
        "sites": {"launch_profile": from_profile, "codex_agent_template": from_templates},
        "delegated_comparisons": [
            {"site": "claude/guides/cli-multi-model-workflow.md",
             "owner": "gates/check_parity.py environment_bindings",
             "why": "compares rendered bindings using the launch profile model_display map"},
        ],
        "disagreements": disagreements,
        "undeclared_on_one_side": undeclared,
        "declared_template_map": sorted(declared),
        "template_files_outside_the_map": sorted(unmapped),
        "tier_without_template": sorted(set(from_profile) - set(declared)),
    }


# ── F5 · assurance ───────────────────────────────────────────────────────────

def gates() -> list[dict]:
    out = []
    for p in sorted(REPO.rglob("*")):
        if not p.is_file() or p.suffix not in (".py", ".sh") or ".git" in p.parts:
            continue
        rel = p.relative_to(REPO)
        if rel.parts[0] not in ("gates", "compose", "learn", "launch"):
            continue
        text = read(p)
        modes = [m for m in ("--check", "--self-test") if m in text]
        if not (modes or rel.parts[0] == "gates"):
            continue
        out.append({"path": str(rel), "modes": modes})
    return out


# ── the derived GR-4 result ──────────────────────────────────────────────────

def gr4() -> dict:
    """Deploy writes minus verify subjects — computed, not asserted."""
    deploys, verifies = deploy_targets(), verify_subjects()
    subj = {v["subject"] for v in verifies}
    rows = []
    for d in deploys:
        dst = d["dst"]
        # A glob deploys into a directory; verify asserts per-basename inside it.
        covering = [v for v in verifies if v["subject"] == dst or v["subject"].startswith(dst.rstrip("/") + "/")]
        rows.append({
            "dst": dst, "src": d["src"], "deploy_line": d["line"],
            "assertions": [{"fn": v["fn"], "line": v["line"], "strength": v["strength"]} for v in covering],
            "covered": bool(covering),
            "strength": (covering[0]["strength"] if covering else None),
        })
    uncovered = [r["dst"] for r in rows if not r["covered"]]
    # No `violation` boolean: it restated `bool(uncovered)` and nothing read it. One value, one
    # owner — a caller that wants the verdict asks whether `uncovered` is empty.
    return {"rows": rows, "deploy_count": len(rows), "verify_subject_count": len(subj),
            "uncovered": uncovered}


# Fields produced for a PERSON to read, not for a gate. Everything an extractor returns is
# gate-facing by default, so a value made and never wired reports as a defect — that default is
# the point, because `advertised_but_absent` sat here computed and unread until it was looked
# for. Registering a field is a decision with a reason attached, and a reason is arguable;
# forgetting to register one fails loudly, which is the safe direction.
#
# A registration whose field DOES get a reader is stale, and check-ontology.py says so: the list
# has to keep describing the code or it becomes a permanent excuse.
HUMAN_FACING = {
    "deploy_targets.mode": "descriptive attribute of a deploy target; whether verify should "
                           "assert the executable bit is an open obligation question, not this "
                           "field's job",
    "subcommands.advertised_in_usage": "one site's account, kept visible so a person can see "
                                       "WHICH site disagreed; the disagreement itself is gated",
    "user_owned_regions.codex_ops": "descriptive — which lifecycle verbs the Codex helper "
                                    "defines; the per-span ops are what a check reads",
    "user_owned_regions.merge_without_remove": "scoped lifecycle inventory for review; private "
                                               "migration cleanup is a separate authority",
    "user_owned_regions.merge_without_check": "scoped verification inventory for review",
    "guides.guide_id": "corpus inventory for a reader of extract.py --json",
    "guides.has_use_when": "corpus inventory; frontmatter completeness is check-parity's job",
    "guides.has_core_rules": "corpus inventory; frontmatter completeness is check-parity's job",
    "domain_manifest.bullets_untiered": "compose/check-domains.py owns this enforcement and "
                                        "check-parity.sh runs it; a second failing site would "
                                        "make this a second author of one rule",
    "domain_manifest.guides_unclassified": "check-domains.py owns this enforcement",
    "domain_manifest.anchors_not_matching_one_bullet": "check-domains.py owns this enforcement",
    "domain_manifest.bullets_not_claimed_once": "check-domains.py owns this enforcement",
    "domain_manifest.claimed_but_missing": "check-domains.py owns this enforcement",
    "domain_manifest.on_disk_but_unclaimed": "check-domains.py owns this enforcement",
    "launch_profile.scalars": "inventory of the profile's top-level scalars for a reader",
    "tier_binding_sites.delegated_comparisons": "names the comparison owner outside this extractor; "
                                               "the parity driver runs that owner's checks",
    "tier_binding_sites.undeclared_on_one_side": "absence is not disagreement — reported so a "
                                                 "person classifies it, never failed on",
    "tier_binding_sites.declared_template_map": "which tiers the launch profile says have a "
                                                "template; the comparison uses it, a reader "
                                                "wants to see it",
    "tier_binding_sites.template_files_outside_the_map": "template files that are not tier "
                                                         "templates — reviewer.toml is a review "
                                                         "role, so this is a list to read, not a "
                                                         "disagreement to fail on",
    "tier_binding_sites.tier_without_template": "helm, licensed as LA-1; reported so a second "
                                                "unlicensed case would be visible",
    "gates.path": "gate inventory for a reader",
    "gates.modes": "gate inventory for a reader",
    "gr4_deploy_verify.verify_subject_count": "descriptive count beside the deploy count; the "
                                              "gated fact is `uncovered`",
}


EXTRACTORS = {
    "deploy_targets": deploy_targets,
    "verify_subjects": verify_subjects,
    "subcommands": subcommands,
    "payload_files": payload_files,
    "runtime_authorities": runtime_authorities,
    "user_owned_regions": user_owned_regions,
    "guides": guides,
    "domain_manifest": domain_manifest,
    "launch_profile": launch_profile,
    "tier_binding_sites": tier_binding_sites,
    "gates": gates,
    "gr4_deploy_verify": gr4,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=pathlib.Path, help="write the evidence bundle here")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    evidence = {name: fn() for name, fn in EXTRACTORS.items()}

    # Non-empty subject guard: an extractor that silently returns nothing would make
    # every downstream "no bad X" claim pass vacuously.
    empty = [k for k, v in evidence.items() if not v]
    if empty:
        print(f"FAIL: extractors returned nothing (source shape changed?): {', '.join(empty)}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        args.json.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.quiet:
        return

    g = evidence["gr4_deploy_verify"]
    sc = evidence["subcommands"]
    lp = evidence["launch_profile"]
    dm = evidence["domain_manifest"]
    print(f"legacy deploy targets   {g['deploy_count']}")
    print(f"  uncovered by verify   {len(g['uncovered'])}  {g['uncovered']}")
    print(f"  existence-only        {sum(1 for r in g['rows'] if r['strength'] == 'existence')}")
    print(f"subcommands             implemented={sc['implemented']}")
    print(f"  advertised-only       {sc['advertised_but_absent']}")
    print(f"  case block alone      {sc['dispatched_in_case']}   early={sc['early_branch']}")
    print(f"guides                  {len(evidence['guides'])}  "
          f"id!=filename: {[x['file'] for x in evidence['guides'] if not x['id_matches_filename']]}")
    print(f"domains.json            tiers={dm['tiers']} domains={len(dm['domains'])} counts={dm['counts']}")
    print(f"launch profile          tables={lp['top_level_tables']}")
    print(f"  tier bindings         {len(lp['tier_bindings'])} over models {lp['models_declared']}")
    print(f"payload files[]         {len(evidence['payload_files'])}")
    print(f"runtime authorities     {len(evidence['runtime_authorities']['modules'])} statically reached modules")
    print(f"gates / self-tests      {len(evidence['gates'])}")


if __name__ == "__main__":
    main()
