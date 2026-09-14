#!/usr/bin/env python3
"""Hold ontology/ against the real repository.

The ontology's own rule is that a claim must come from the implementation. Prose
cannot enforce that, so this gate does: it re-runs the extractors and fails when the
ontology and the code disagree. Without it the anchors are assertions that decay
silently, and a confidently wrong dependency map is worse than none.

Deliberately narrow — this is the seed's happy path, not full coverage:
  1. anchor liveness      every entity's `evidence` literal is still in its anchored file
  2. derived agreement    counts the ontology states must equal what extraction finds
  3. edge integrity       both ends resolve; every kind is declared and every declared kind used
  4. graph health         single connected component, guard/P6 invariant
  5. prose counts         numbers in dependency_rules.md equal the graph's
  6. happy path coverage  every step of the SERVICE's paths has an entity and a linked hop
  7. purpose extraction   every purpose clause is still quotable from its source
  8. purpose coverage     every golden relationship names the purpose it serves, or why none
  9. licensed asymmetry   a declared exception names the site it excuses, or it is not a licence
 10. decisions           a `violated` verdict is a judgement, so it names what it ruled out
 11. question admission  a question names the purpose whose decisions it serves, or it retires
 12. surfaced conflicts  a contradiction shows every site; an unlinked pair says why not
 13. site agreement       where one value has several authors, the authors still agree
 14. value consumers      a produced value is gate-facing unless registered otherwise, and
                          gate-facing means something reads it
 15. lexicon constants    check-lexicon.py's DENY/ARCHIVE equal the graph's, both ways
 16. competency resolvers every P1 question has something that answers it
 17. no restated counts   authored prose points at derived artifacts, never copies them
 18. no line anchors     prose names symbols, not line numbers, which decay silently
 19. projection freshness every projection regenerates to the same bytes
 20. runtime authorities  statically reached lifecycle modules resolve to impact obligations

`--self-test` runs negative controls: each check is fed a broken graph and must fail.
A gate nobody has watched fail is unproven, not merely untested.

`--coverage` prints the other direction of check 8 — purpose clauses no golden relationship
serves. That one is a disclosure, never a failure: some clauses are not gateable, and failing
on them would push the loop to invent gates to clear a counter.

Usage: ontology/check-ontology.py [--self-test]

Lives here, not in gates/, because LEXICON binds a concept's machinery to its home —
the same reason compose/check-domains.py and learn/check-learning.py sit with their concepts.
Exit 0 clean, 1 on any disagreement.
"""
from __future__ import annotations

import argparse
import collections
import copy
import importlib.util
import json
import pathlib
import re
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent

# Floor for a purpose clause's evidence quote. Set below the shortest real quote and far above
# the empty string, which every file contains — see check_purpose_extraction.
MIN_QUOTE_CHARS = 16

# What a purpose clause with no golden relationship may say about itself. `accepted` is a real
# closure, not a deferral: some clauses are judgements no gate can decide, and pretending
# otherwise is how a loop starts inventing checks to move a number.
ENFORCEMENT_KINDS = {"obligation-needed", "accepted", "elsewhere"}
ONTO = REPO / "ontology"
GRAPH = ONTO / "instances" / "graph.json"


def declared_kinds() -> dict[str, str]:
    """The edge-kind vocabulary and its obligation directions, READ from their documented home.

    This used to be a dict here, restating what `dependency_rules.md` already said. Two authors
    of one value, with nothing comparing them — so a direction flipped in the prose would leave
    the gate quietly enforcing the old one, and the gate would be the real authority while the
    document looked like it. That is PU-15's case, committed by the ontology against itself and
    found by its own A5 audit.

    Parsed, not copied. A parse that finds nothing raises instead of returning an empty mapping:
    an empty vocabulary would make every edge kind undeclared, or — worse, depending on the
    caller — make nothing checkable at all.
    """
    doc = ONTO / "dependency_rules.md"
    pairs = re.findall(r"^\*\*`(\w+)`\*\*.*?^\*Obligation:\*\s+\*\*(\w+)\*\*",
                       doc.read_text(encoding="utf-8"), re.M | re.S)
    if not pairs:
        raise RuntimeError(f"no edge kinds parsed from {doc} — the vocabulary has no readable "
                           f"home, so nothing here can judge an edge's kind")
    return dict(pairs)


DECLARED_KINDS = declared_kinds()


def load_extractors():
    spec = importlib.util.spec_from_file_location("onto_extract", ONTO / "extract.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── checks ───────────────────────────────────────────────────────────────────
# Each returns a list of failure strings. Empty means pass.

# A repo path is checkable; a RUNTIME path ($STATE_DIR/selection.json, $CODEX_DIR/bin/…)
# names a deploy destination that does not exist in the checkout, so requiring it here
# would be a false failure. The shell-variable prefix is what tells the two apart, and
# group 1 capturing it is why this regex does not simply match any path-looking token.
ANCHOR_TOKEN = re.compile(
    r"(\$\{?\w+\}?/)?((?:[\w.-]+/)*[\w.-]+\.(?:py|sh|md|json|toml|zsh|html|yaml|yml))(?::(\d+))?"
)


ANCHOR_GLOB = re.compile(r"((?:[\w.-]+/)+[\w.*-]*\*[\w.*-]*)")


def anchored_files(anchor: str) -> list[pathlib.Path]:
    """Repo files an anchor names. Runtime ($VAR-prefixed) destinations are skipped."""
    out = []
    for runtime, path, _line in ANCHOR_TOKEN.findall(anchor):
        if runtime:
            continue
        f = REPO / path
        if f.is_file():
            out.append(f)
    for glob in ANCHOR_GLOB.findall(anchor):
        out += [f for f in REPO.glob(glob) if f.is_file()]
    return out


def check_anchor_liveness(graph: dict) -> list[str]:
    """Anchors are CONTENT-addressed, not position-addressed.

    A line number decays silently: three prose citations of `check_parity.py:318` came to
    point at unrelated code merely because an earlier commit inserted a function above it,
    and a range check passed the whole time because the file was still long enough. So an
    entity declares an `evidence` literal that must be present in one of its anchored
    files. Position drifts under edits that change nothing; content fails only when the
    thing being named actually changes, which is the signal worth having.
    """
    fails, checked = [], 0
    for e in graph["entities"]:
        files = anchored_files(e["anchor"])
        if not files:
            fails.append(f"{e['id']}: anchor names no existing repo file ({e['anchor']!r})")
            continue
        ev = e.get("evidence")
        if not ev:
            fails.append(f"{e['id']}: has no `evidence` literal — the anchor is unverifiable")
            continue
        checked += 1
        if not any(ev in f.read_text(encoding="utf-8", errors="replace") for f in files):
            fails.append(f"{e['id']}: evidence {ev!r} is no longer in "
                         f"{[str(f.relative_to(REPO)) for f in files]} — the anchor has drifted")
    if not checked:
        fails.append("no entity anchor was verifiable — the check ran over an empty subject")
    return fails


def check_runtime_authorities(graph: dict, ev: dict, repo: pathlib.Path | None = None) -> list[str]:
    """Every statically reached lifecycle module has an actionable impact mapping."""
    spec = importlib.util.spec_from_file_location("onto_impact", ONTO / "impact.py")
    impact = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(impact)
    authorities = ev["runtime_authorities"]
    modules = set(authorities["modules"])
    entrypoints = set(authorities["entrypoints"])
    imports = authorities["local_imports"]
    fails = []
    if not modules or not entrypoints or not imports:
        fails.append("runtime authority extraction has an empty module, entrypoint, or local-import subject")
    if not entrypoints <= modules or any(
            row["source"] not in modules or row["target"] not in modules for row in imports):
        fails.append("runtime authority extraction omits an entrypoint or imported module")
    files = impact.entity_files(graph, REPO if repo is None else repo)
    for path in sorted(modules):
        entities = [eid for eid, paths in files.items() if path in paths]
        if not entities:
            fails.append(f"runtime authority {path}: no entity anchor resolves this module for impact analysis")
        elif not any(ob["other"] != eid for eid in entities for ob in impact.obligations_of(graph, eid)):
            fails.append(f"runtime authority {path}: its entities have no impact obligation to another entity")
    return fails


def check_no_line_anchors(graph: dict) -> list[str]:
    """Hand-authored ontology prose must not cite `path:line`.

    Same defect as the counts: a position read as authoritative while quietly wrong. Names
    are stable and greppable; line numbers are not. Generated documents are exempt because
    they are rebuilt from the graph, which carries no line numbers either.
    """
    fails = []
    scanned = 0
    for name in AUTHORED_PROSE:
        doc = ONTO / name
        if not doc.is_file():
            continue
        scanned += 1
        for i, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            for runtime, path, ln in ANCHOR_TOKEN.findall(line):
                if ln and not runtime:
                    fails.append(f"ontology/{name}:{i}: cites {path}:{ln} — line numbers decay "
                                 f"silently; name the symbol instead")
    if not scanned:
        fails.append("no authored prose scanned — the check ran over an empty subject")
    return fails


def check_derived_agreement(graph: dict, ev: dict) -> list[str]:
    """Counts the ontology asserts must equal what the extractors find in real code."""
    fails = []
    stated = graph.get("derived", {})
    if not stated:
        return ["instances/graph.json has no `derived` block — nothing anchors the stated counts to code"]
    actual = {
        "deploy_targets": ev["gr4_deploy_verify"]["deploy_count"],
        "deploy_uncovered": len(ev["gr4_deploy_verify"]["uncovered"]),
        "guides": len(ev["guides"]),
        "domains": len(ev["domain_manifest"]["domains"]),
        "tier_bindings": len(ev["launch_profile"]["tier_bindings"]),
        "subcommands": len(ev["subcommands"]["implemented"]),
        "payload_files": len(ev["payload_files"]),
    }
    for key, real in actual.items():
        if key not in stated:
            fails.append(f"derived block does not state {key} (code says {real})")
        elif stated[key] != real:
            fails.append(f"derived {key}: ontology says {stated[key]}, code says {real}")
    return fails


def check_prose_counts(graph: dict) -> list[str]:
    """Counts the prose states must equal the graph's.

    Added after dependency_rules.md silently kept saying "eight kinds / 41 edges" through
    a split that made it nine and 42 — the same two-canonical-sites failure (GR-1) the
    ontology names, committed by its own prose. Numbers live in machine-readable tokens
    so the check is exact rather than a fuzzy scrape.
    """
    doc = ONTO / "dependency_rules.md"
    if not doc.is_file():
        return ["dependency_rules.md missing — the edge-kind vocabulary has no declared home"]
    text = doc.read_text(encoding="utf-8")
    rels = graph["relationships"]
    expect = {
        "KIND_COUNT": len({r["kind"] for r in rels}),
        "EDGE_COUNT": len(rels),
        "UNGUARDED_EDGES": sum(1 for r in rels if r["guard"] == "unguarded"),
    }
    fails = []
    for token, real in expect.items():
        m = re.search(rf"{token}:\s*(\d+)", text)
        if not m:
            fails.append(f"dependency_rules.md states no {token} (graph says {real})")
        elif int(m.group(1)) != real:
            fails.append(f"dependency_rules.md {token}={m.group(1)} but the graph says {real}")
    # The per-status table must agree too; it is the number readers act on.
    for status in ("gated", "unguarded", "partial", "derived"):
        real = sum(1 for r in rels if r["guard"] == status)
        m = re.search(rf"^\|\s*`{status}`\s*\|\s*(\d+)\s*\|", text, re.M)
        if not m:
            fails.append(f"dependency_rules.md status table has no row for {status} (graph says {real})")
        elif int(m.group(1)) != real:
            fails.append(f"dependency_rules.md says {status}={m.group(1)}, graph says {real}")
    return fails


def check_purpose_extraction(graph: dict) -> list[str]:
    """Purpose clauses must still be quotable from the source that states them.

    Purpose is the root of the whole chain — it decides which decisions matter, which
    decides which questions are admitted, which decides what the ontology carries. That
    makes it the easiest thing to inflate: a sentence written here would justify any
    question downstream. So a clause is admitted only with a verbatim quote that is still
    present in a named source file, and an INFERRED clause stays unadmitted until the user
    confirms it — onto's rule that an inferred target purpose cannot be projected as ready.
    """
    pu = graph.get("purpose")
    if not pu:
        return ["graph.json declares no purpose block — the question admission bar has no root"]
    fails = []
    checked = 0
    for row in pu.get("stated", []) + pu.get("limits", []):
        src = REPO / row["source"]
        if not src.is_file():
            fails.append(f"{row['id']}: source {row['source']} is missing")
            continue
        checked += 1
        # A membership test passes vacuously on the empty string, and near-vacuously on a
        # fragment short enough to occur by accident — so blanking a quote whose sentence was
        # deleted would keep the gate green and the clause admitted. The floor is what makes
        # the quote evidence rather than a formality; the shortest real quote is well above it.
        quote = row["quote"]
        if len(quote.strip()) < MIN_QUOTE_CHARS:
            fails.append(f"{row['id']}: quote is blank or too short to be evidence "
                         f"({len(quote.strip())} chars, floor {MIN_QUOTE_CHARS}) — a fragment "
                         f"this small can match by accident, so it proves nothing was stated")
        elif quote not in src.read_text(encoding="utf-8", errors="replace"):
            fails.append(f"{row['id']}: quote is no longer in {row['source']} — the purpose "
                         f"clause has lost its source, so it is now authored, not extracted")
    if not checked:
        fails.append("no purpose clause was verifiable — the check ran over an empty subject")
    for row in pu.get("inferred", []) + pu.get("target", []):
        if row.get("confirmed") not in (True, False):
            fails.append(f"{row['id']}: clause has no confirmation decision recorded")
        if row.get("confirmed") is True and not row.get("confirmed_on"):
            fails.append(f"{row['id']}: confirmed with no date — an undated confirmation is not a decision")

    # Purpose extraction claims to be finished only when no inferred clause is still waiting on
    # a user. Holding that as prose made it unfalsifiable — the block could say `settled` with
    # candidates still pending and nothing would notice. The status is the claim; this is its
    # judge. `open` constrains nothing, so ordinary mid-stage work is unaffected.
    status = pu.get("extraction_status")
    if status not in ("open", "settled"):
        fails.append(f"purpose.extraction_status is {status!r} — extraction either claims to be "
                     f"settled or does not; there is no third state")
    elif status == "settled" and pu.get("inferred"):
        pending = ", ".join(r.get("id", "?") for r in pu["inferred"])
        fails.append(f"extraction_status is `settled` but inferred clauses are still pending "
                     f"({pending}) — a stage cannot be complete while its own bar is unmet")

    # Transitional evidence exists because implementation is in flight. It must not become
    # purpose (that hardens a transition into design) and must not become a contradiction
    # (that forces a premature decision). `deferral` must be PRESENT — a quote proving the
    # repo already declared the deferral, or an explicit null, which is itself a finding.
    # Without the explicit-null requirement, "it is WIP" would close any awkward item forever.
    for row in graph.get("verdicts", {}).get("transitional", []):
        if "deferral" not in row:
            fails.append(f"{row['id']}: transitional with no `deferral` field — an unrecorded "
                         f"WIP must be recorded as unrecorded, not omitted")
            continue
        d = row["deferral"]
        if d is None:
            if not row.get("finding"):
                fails.append(f"{row['id']}: deferral is null but no finding is stated — "
                             f"an undeclared transition needs to surface as one")
            continue
        src = REPO / d["source"]
        if not src.is_file():
            fails.append(f"{row['id']}: deferral source {d['source']} is missing")
        elif d["quote"] not in src.read_text(encoding="utf-8", errors="replace"):
            fails.append(f"{row['id']}: deferral quote is no longer in {d['source']} — the "
                         f"transition is no longer declared, so this is now unrecorded WIP")

    # A promoted clause can land ahead of the code, and the places it already condemns are
    # the work it created. Recorded here rather than in prose so they cannot rot silently:
    # the clause must be one this block actually carries, and the site must still exist. A
    # violation naming a deleted file is either fixed (delete the row) or misfiled — either
    # way the list has stopped describing the repo, which is how a debt list becomes decor.
    known = {r["id"] for r in pu.get("stated", []) + pu.get("limits", [])}
    for row in pu.get("open_violations", []):
        if row["clause"] not in known:
            fails.append(f"{row['id']}: names clause {row['clause']}, which no stated purpose "
                         f"or declared limit carries — a violation of nothing is not a debt")
        if not (REPO / row["site"]).exists():
            fails.append(f"{row['id']}: site {row['site']} no longer exists — resolve the row "
                         f"or repoint it; a debt against a deleted site is stale, not open")
    return fails


def check_site_agreement(ev: dict) -> list[str]:
    """Where one value has several authors, the authors must still agree.

    The extractors already return site sets — this is the consumer that was missing. The
    subcommand extractor has computed `advertised_but_absent` since it was written and nothing
    read it, so a command added to the dispatch and not to `usage()` passed every gate: a
    produced value with no reader, which is exactly what the instructions calls inert.

    Only a value declared at two sites and differing fails here. A site that says less than
    another is reported by `extract.py --json`, not failed on, because absence is a different
    finding from conflict and forcing them together produces wrong fixes.
    """
    fails = []
    sub = ev["subcommands"]
    for missing in sub["advertised_but_absent"]:
        fails.append(f"subcommand `{missing}` is advertised in usage() but implemented nowhere")
    for hidden in sub["implemented_but_unadvertised"]:
        fails.append(f"subcommand `{hidden}` is implemented but usage() never advertises it — "
                     f"a command users cannot discover")
    if not (sub["dispatched_in_case"] or sub["early_branch"]):
        fails.append("no subcommand site produced anything — the check ran over an empty subject")

    tb = ev["tier_binding_sites"]
    for row in tb["disagreements"]:
        fails.append(f"tier `{row['tier']}` {row['field']}: launch profile says "
                     f"{row['launch_profile']!r}, the agent template says {row['agent_template']!r}")
    if not tb["sites"]["launch_profile"]:
        fails.append("no tier binding was read — the check ran over an empty subject")

    # The declared span authors cover legacy installation and explicit shell connection.
    # Each row carries its route so compatibility behavior cannot read as the private default.
    uor = ev["user_owned_regions"][0]
    required_authors = {"install.sh", "compose/assemble.py", "launch/shell_integration.py"}
    missing_authors = required_authors - set(uor["authoring_sites"])
    if missing_authors:
        fails.append(f"user-owned regions omit declared authors: {sorted(missing_authors)}")
    for r in uor["regions"]:
        if not r.get("scope"):
            fails.append(f"span `{r['span']}` has no lifecycle scope")
        if not r["ops"]:
            fails.append(f"span `{r['span']}` has no lifecycle op at all — it is written by "
                         f"nothing this extractor can see, so the reading is wrong")

    # The domain classification's three sites are compared and ENFORCED by
    # compose/check-domains.py, which check-parity.sh runs with its own self-test. Re-failing
    # here on the same disagreement would make this a second author of one rule — the thing
    # PU-15 forbids. So what is asserted is that the extractor still reads all three sites over
    # a non-empty subject: the ontology's job is seeing the comparison, not repeating it.
    dm = ev["domain_manifest"]
    if len(dm["sites"]) < 3:
        fails.append(f"domain classification was read from {sorted(dm['sites'])} — fewer than "
                     f"the three sites that author it, so a disagreement could not be seen")
    if not dm["instructions_bullet_count"] or not any(dm["files_on_disk"].values()):
        fails.append("domain classification read an empty instructions or empty tree — the comparison "
                     "would pass vacuously")
    return fails


def check_licensed_asymmetry(graph: dict) -> list[str]:
    """A declared exception must name the site it excuses, or it is not a licence.

    Sites differing is not by itself a defect — some differences are intended. What separates an
    intended one from a contradiction is a declaration that points at the specific
    implementation, as data. "There is a general rule about this" does not qualify: a rule that
    does not name the site would excuse any site, which is how "it's fine, it's declared
    somewhere" becomes permanent cover for a real disagreement.

    So `names` must appear inside the quoted declaration, and the quote must still be present in
    the file it is attributed to. An enumeration that happens to exclude something is not naming
    it — that is the case `reviewer.toml` currently fails, and failing it is the point.
    """
    rows = graph.get("verdicts", {}).get("licensed_asymmetry")
    if rows is None:
        return ["graph.json declares no licensed_asymmetry list — every apparent disagreement "
                "would have to be a contradiction"]
    fails = []
    for row in rows:
        d = row["declaration"]
        src = REPO / d["source"]
        if not src.is_file():
            fails.append(f"{row['id']}: declaration source {d['source']} is missing")
            continue
        if d["quote"] not in src.read_text(encoding="utf-8", errors="replace"):
            fails.append(f"{row['id']}: the declaration is no longer in {d['source']} — what "
                         f"licensed this asymmetry is gone, so it is a contradiction again")
        if d["names"].lower() not in d["quote"].lower():
            fails.append(f"{row['id']}: the declaration does not name {d['names']!r} — a rule "
                         f"that names no site would excuse every site")
        if not row.get("why"):
            fails.append(f"{row['id']}: licensed with no reason stated")
    return fails


def check_surfaced_conflicts(graph: dict) -> list[str]:
    """Stage B's output: a contradiction shows every site, and an unlinked pair says why not.

    Both verdicts exist to stop a wrong move. A contradiction recorded with one site reads as a
    defect at that site, and the next reader "fixes" it there — which is exactly the error stage
    B exists to prevent, so two sites are the floor. An unlinked pair must say what made the two
    claims different, because "these were never the same thing" is the easiest sentence to write
    and the easiest to be wrong about.

    An open contradiction that names a golden relationship it blocks must name a real one: that
    field is how a rootless obligation finds its way back to a decision.
    """
    v = graph.get("verdicts", {})
    if "contradiction" not in v:
        return ["graph.json declares no contradiction list — stage B has nowhere to put what it "
                "refuses to settle"]
    known_gr = {r["id"] for r in graph.get("golden_relationships", [])}
    fails = []
    for row in v["contradiction"]:
        if len(row.get("sites", {})) < 2:
            fails.append(f"{row['id']}: fewer than two sites — a contradiction with one site is "
                         f"a defect report, and it will be fixed at that site")
        if not row.get("no_declaration_because"):
            fails.append(f"{row['id']}: does not say why no declaration covers it, so it cannot "
                         f"be told apart from a licensed asymmetry nobody looked up")
        for gr in row.get("blocks", []):
            if gr not in known_gr:
                fails.append(f"{row['id']}: blocks {gr}, which is no golden relationship")
    for row in v.get("unlinked", []):
        if not row.get("why_not_the_same_claim"):
            fails.append(f"{row['id']}: claims two sites were never the same claim without "
                         f"saying what made them different")
    return fails


def check_question_admission(graph: dict) -> list[str]:
    """A question is admitted only if it serves a decision that some stated purpose requires.

    The ontology exists to make decisions correct, so a question that changes no decision earns
    nothing and there are infinitely many of them — semantic verification and meaning
    reproduction multiply without bound. Naming the purpose is what bounds the set, and it has to
    be the purpose rather than a free-text justification: a decision consumer invented for the
    occasion legitimises the question that invented it.

    Retirement is recorded, not silent. A deleted question leaves no trace of having been judged,
    so the next reader re-adds it; a retired one carries the reason and can be argued with.
    """
    cq = graph.get("competency_questions", {})
    questions = cq.get("questions")
    if not questions:
        return ["no competency questions — the admission bar has an empty subject"]
    known = {r["id"] for r in graph.get("purpose", {}).get("stated", [])}
    fails = []
    for q in questions:
        serves = q.get("serves")
        if not serves:
            fails.append(f"{q['id']}: names no purpose it serves — a question that changes no "
                         f"decision is inadmissible, not merely unanswered")
            continue
        for cid in serves:
            if cid not in known:
                fails.append(f"{q['id']}: serves {cid}, which no stated purpose clause carries")
    for row in cq.get("retired", []):
        if not row.get("reason"):
            fails.append(f"{row['id']}: retired with no reason recorded — indistinguishable from "
                         f"a question that was quietly dropped")
    return fails


def check_decisions(graph: dict) -> list[str]:
    """A verdict that something is broken is a judgement, and judgements name their alternatives.

    `violated` is not a reading — it is the choice to call a gap a defect rather than a licensed
    exemption, and the ontology carried one of those for weeks with no record that the second
    reading existed. So a golden relationship claiming `violated` must be named by a decision,
    and an open decision must list what was not chosen. Otherwise the loop builds on a verdict
    nobody can argue with because nobody can see what it ruled out.
    """
    rows = graph.get("decisions", {}).get("rows")
    if rows is None:
        return ["graph.json declares no decisions block — an authored verdict would have "
                "nowhere to record what it ruled out"]
    known_gr = {r["id"] for r in graph.get("golden_relationships", [])}
    fails, about = [], set()
    for row in rows:
        about.add(row["about"])
        if row["about"] not in known_gr:
            fails.append(f"{row['id']}: decides about {row['about']}, which is no golden "
                         f"relationship")
        if row["status"] == "open" and len(row.get("options", [])) < 2:
            fails.append(f"{row['id']}: open with fewer than two options — a decision with one "
                         f"path is a conclusion wearing a decision's shape")
        if row["status"] == "decided" and not (row.get("decided_on") and row.get("rationale")):
            fails.append(f"{row['id']}: decided with no date or no rationale")
    for gr in graph.get("golden_relationships", []):
        if gr["status"] == "violated" and gr["id"] not in about:
            fails.append(f"{gr['id']}: status `violated` with no decision recording it — calling "
                         f"a gap a defect is a judgement, not an observation")
    return fails


def check_value_consumers(ev: dict, human_facing: dict, sources: dict) -> list[str]:
    """A produced value is gate-facing unless it says otherwise, and gate-facing means read.

    GR-6 says a value nobody reads changes nothing. Measured as "no code reads it" that rule
    condemns every value made for a person, so applying it literally produced 23 findings of
    which one was real. The missing distinction is the intended reader, and the default is what
    makes it safe: a new field is gate-facing, so wiring it and forgetting to read it FAILS.
    That is exactly how `advertised_but_absent` sat computed and unread — a whole gate's worth
    of protection missing behind a green suite.

    Three ways to fail: unread and unregistered (the real defect), registered with no reason (a
    decision indistinguishable from an oversight), and registered but actually read (a stale
    entry, which is how an exception list rots into a permanent excuse).
    """
    patterns = [r'\["{f}"\]', r"\['{f}'\]", r'\.get\(\s*["\']{f}["\']']
    # A negative control that plants a field mentions its name, and this file is one of the
    # sources — so without excluding the self-test body the planted field reads as consumed and
    # the control cannot fail. Found by watching exactly that happen. Test scaffolding is not a
    # consumer on the live path.
    sources = {n: (t.split("def self_test(")[0] if n == pathlib.Path(__file__).name else t)
               for n, t in sources.items()}
    fails, swept = [], 0
    for name, out in ev.items():
        row = out if isinstance(out, dict) else (out[0] if out and isinstance(out[0], dict) else None)
        if not isinstance(row, dict):
            continue
        for field in row:
            swept += 1
            key = f"{name}.{field}"
            read = any(re.search(p.format(f=re.escape(field)), text)
                       for text in sources.values() for p in patterns)
            if key in human_facing:
                if not human_facing[key]:
                    fails.append(f"{key}: registered as human-facing with no reason")
                elif read:
                    fails.append(f"{key}: registered as human-facing but a consumer reads it — "
                                 f"the registration is stale and should be dropped")
            elif not read:
                fails.append(f"{key}: produced and never read. Wire a consumer, delete it, or "
                             f"register it in extract.py HUMAN_FACING with the reason")
    if not swept:
        fails.append("no extractor field was swept — the check ran over an empty subject")
    return fails


def check_purpose_coverage(graph: dict) -> list[str]:
    """Every golden relationship names the purpose it serves, or says why it has none.

    A golden relationship is an obligation the repo says is worth enforcing. If it traces to no
    stated purpose, either the purpose was never extracted or the obligation is habit — and the
    two are told apart by looking, not by assuming. This is the A1 direction that CAN fail
    structurally: a named clause either exists or it does not.

    The other direction — a purpose clause no golden relationship serves — is reported by
    `--coverage` rather than failed on. Some clauses are not gateable (a token budget is a
    judgement), and failing on them would push the loop to manufacture gates to clear a counter,
    which is the Goodhart failure the design names. `orphan_reason` mirrors the transitional
    block's `deferral: null` + finding: an empty set is admissible once, in writing.
    """
    grs = graph.get("golden_relationships", [])
    if not grs:
        return ["graph.json declares no golden relationships — nothing to trace to purpose"]
    known = {r["id"] for r in graph.get("purpose", {}).get("stated", [])}
    if not known:
        return ["no stated purpose clause exists — golden-relationship coverage is vacuous"]
    fails = []
    for r in grs:
        if "serves" not in r:
            fails.append(f"{r['id']}: no `serves` — an obligation with no traced purpose is "
                         f"unexamined, not rootless")
            continue
        for cid in r["serves"]:
            if cid not in known:
                fails.append(f"{r['id']}: serves {cid}, which no stated purpose clause carries")
        if not r["serves"] and not r.get("orphan_reason"):
            fails.append(f"{r['id']}: serves nothing and states no reason — a rootless "
                         f"obligation must say why it is rootless")

    # A1 closes when every clause is either served by an obligation or carries a decision about
    # why it is not. `accepted` counts as closed with no gate — that is what keeps the ratchet
    # from rewarding invented checks. What is refused is silence: an unserved, unclassified
    # clause is one nobody has looked at, which is the state A1 exists to end.
    served = {c for r in grs for c in r.get("serves", [])}
    for row in graph.get("purpose", {}).get("stated", []):
        if row["id"] in served:
            continue
        enf = row.get("enforcement")
        if not enf:
            fails.append(f"{row['id']}: no golden relationship serves it and no enforcement "
                         f"decision is recorded — undecided, not accepted")
        elif enf.get("kind") not in ENFORCEMENT_KINDS:
            fails.append(f"{row['id']}: enforcement kind {enf.get('kind')!r} is not one of "
                         f"{sorted(ENFORCEMENT_KINDS)}")
        elif not enf.get("note"):
            fails.append(f"{row['id']}: enforcement recorded with no reason — an undocumented "
                         f"decision is indistinguishable from an oversight")
    return fails


def check_lexicon_constants(graph: dict) -> list[str]:
    """The terminology gate's own constants must equal the graph's.

    `gates/check-lexicon.py` carries DENY and ARCHIVE as string constants and its
    self-consistency check runs ONE way — every enforced token must appear in
    LEXICON.md. Nothing checked the reverse, so a token added to the table and not to
    the gate would be documented as forbidden and silently unenforced. Now that
    LEXICON.md is generated, the graph is the authority and this closes the loop.

    `distillation` is listed as deprecated but deliberately NOT gated — the heavy
    pipeline legitimately says "upward distillation" — so the intentional exemption is
    carried as data (`enforced: false`) rather than as a prose footnote no check can read.
    """
    lex = graph.get("lexicon")
    if not lex:
        return ["graph.json carries no `lexicon` block — LEXICON.md has no authority to project from"]
    gate = REPO / "gates" / "check-lexicon.py"
    if not gate.is_file():
        return ["gates/check-lexicon.py missing — the terminology gate has no home"]
    spec = importlib.util.spec_from_file_location("onto_check_lexicon", gate)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    fails = []
    enforced = {d["token"] for d in lex["deprecated"] if d.get("enforced")}
    deny = set(mod.DENY)
    if not enforced:
        fails.append("no deprecated token is marked enforced — the denylist would be vacuous")
    for tok in sorted(enforced - deny):
        fails.append(f"deprecated token {tok!r} is marked enforced but check-lexicon.py does not gate it")
    for tok in sorted(deny - enforced):
        fails.append(f"check-lexicon.py gates {tok!r} but the graph does not mark it enforced")

    prefixes = {p for a in lex["archive_allowlist"] for p in a["prefixes"]}
    archive = set(mod.ARCHIVE)
    for p in sorted(prefixes - archive):
        fails.append(f"archive prefix {p!r} is declared but check-lexicon.py does not allow it")
    for p in sorted(archive - prefixes):
        fails.append(f"check-lexicon.py allows archive prefix {p!r} that the graph does not declare")

    # An exemption that names no reason excuses every path it covers, which is the same defect
    # a licence naming no site has. The reason must also survive into the projected text, or
    # LEXICON.md shows a bare path list and the reason is enforced nowhere a reader looks.
    for a in lex["archive_allowlist"]:
        where = a["prefixes"][0]
        reason = (a.get("reason") or "").strip()
        if not reason:
            fails.append(f"archive entry {where!r} declares no reason — an exemption that "
                         f"excuses a path without saying why cannot be argued with")
        elif reason not in a.get("display", ""):
            fails.append(f"archive entry {where!r} has a reason the projected text drops "
                         f"({reason[:40]!r}...) — LEXICON.md would show the path and not the why")
    return fails


# Hand-authored prose only. The generated docs legitimately carry counts — they cannot
# drift, because they are regenerated from the same source that produced the number.
AUTHORED_PROSE = ("domain_scope.md", "concepts.md", "structure_spec.md", "dependency_rules.md")
# Outside ontology/ but hand-authored and holding graph-owned counts: the repo dashboard
# restated entity and edge totals that freeze the moment the graph moves.
AUTHORED_ELSEWHERE = (REPO / "IMPLEMENTATION_MAP.html",)
_COUNT_NOUNS = r"entities|edges|obligation edges|golden relationships|kinds"
# Both word orders. Prose reaches for either — "38 entities" in a sentence, "entities 38" in a
# summary line — and a pattern that knows only one reads as coverage while missing half of them.
COUNT_CLAIM = re.compile(
    rf"(?<![\w:])(\d+)\s+({_COUNT_NOUNS})\b|"
    rf"\b(\d+)\s+of\s+(\d+)\s+(golden relationships|entities|edges)\b|"
    rf"\b({_COUNT_NOUNS})\s+(\d+)\b")


def authored_prose():
    """(name, text) per hand-authored surface; text is None when the file is gone."""
    return [(str(doc.relative_to(REPO)),
             doc.read_text(encoding="utf-8") if doc.is_file() else None)
            for doc in [ONTO / n for n in AUTHORED_PROSE] + list(AUTHORED_ELSEWHERE)]


def check_no_restated_counts(graph: dict, docs=None) -> list[str]:
    """Hand-authored ontology prose must not restate a count the graph owns.

    A number copied into prose freezes the moment the graph moves, and it reads as
    authoritative while being wrong — the failure this ontology exists to remove, committed
    by the ontology against itself. Prose points at a derived artifact instead.

    dependency_rules.md is exempt where it uses the KIND_COUNT/EDGE_COUNT/UNGUARDED_EDGES
    tokens, because those ARE gated (check_prose_counts).

    `docs` is injectable so the negative control can plant a claim without writing into the
    working tree: a control that edits a tracked file leaves the plant behind if the process
    dies between the write and the restore.
    """
    fails = []
    scanned = 0
    for name, text in (authored_prose() if docs is None else docs):
        if text is None:
            fails.append(f"{name} is missing — a declared prose surface vanished")
            continue
        scanned += 1
        for i, line in enumerate(text.splitlines(), 1):
            if "KIND_COUNT:" in line or "EDGE_COUNT:" in line or "UNGUARDED_EDGES:" in line:
                continue
            m = COUNT_CLAIM.search(line)
            if m:
                fails.append(f"{name}:{i}: restates a count the graph owns "
                             f"({m.group(0).strip()!r}) — point at a derived artifact instead")
    if not scanned:
        fails.append("no authored prose file was scanned — the check ran over an empty subject")
    return fails


def check_competency_resolvers(graph: dict) -> list[str]:
    """Every P1 competency question must have something that answers it.

    A question list with no resolvers is a wish list, and the instructions rule is explicit:
    if no gate can judge a criterion, build the judge or do not claim the criterion met.
    So P1 questions must carry a resolver, `query` resolvers must name a script that
    exists, and `graph` resolvers must name a block the graph actually has.
    """
    spec = graph.get("competency_questions", {}).get("questions")
    if not spec:
        return ["graph.json declares no competency questions — the completion criterion has no test"]
    fails = []
    for q in spec:
        r = q.get("resolver", {})
        kind = r.get("kind")
        if kind not in ("query", "graph", "none"):
            fails.append(f"{q['id']}: resolver kind {kind!r} is not one of query/graph/none")
        if q["priority"] == "P1" and kind == "none":
            fails.append(f"{q['id']} is P1 but nothing answers it — either build the resolver "
                         f"or demote the question honestly")
        if kind == "query":
            script = r.get("cmd", "").split()[1:2]
            if not script or not (REPO / script[0]).is_file():
                fails.append(f"{q['id']}: resolver command names a missing script: {r.get('cmd')!r}")
        if kind == "none" and not r.get("gap"):
            fails.append(f"{q['id']}: has no resolver and no stated gap — an unnamed absence")
    if not any(q["priority"] == "P1" for q in spec):
        fails.append("no P1 question declared — the check would pass over an empty subject")
    return fails


def check_happy_path_coverage(graph: dict) -> list[str]:
    """Does the ontology actually describe what the service does?

    Anchor liveness proves the entities point at real code; it does not prove the set is
    *sufficient*. This walks the service's own paths — install, uninstall, the learn loop,
    launch, review dispatch — and fails on two holes an entity list cannot show by itself:
    a step no entity claims, and a step-to-step hop with no edge, which means the graph
    cannot carry impact across a transition the service really makes.
    """
    spec = graph.get("happy_paths", {}).get("paths")
    if not spec:
        return ["graph.json declares no happy_paths — nothing states what the service does"]
    ids = {e["id"] for e in graph["entities"]}
    linked = {(r["from"], r["to"]) for r in graph["relationships"]}
    linked |= {(r["to"], r["from"]) for r in graph["relationships"]}
    precedes = {(r["from"], r["to"]) for r in graph["relationships"] if r["kind"] == "precedes"}

    fails = []
    for name, path in spec.items():
        steps = path["steps"]
        if not steps:
            fails.append(f"happy path {name!r} has no steps — a vacuous path proves nothing")
            continue
        # (1) coverage: a step nothing claims is a hole in the entity set.
        for s in steps:
            if s["entity"] is None:
                fails.append(f"{name}: step {s['step']!r} is claimed by no entity")
            elif s["entity"] not in ids:
                fails.append(f"{name}: step {s['step']!r} names unknown entity {s['entity']!r}")
        # (2) ORDER-BEARING hops only. A path is a temporal sequence: consecutive steps
        # need not be coupled, and demanding an edge for every adjacency would conflate
        # "runs after" with "obliges" — and pressure the graph into inventing edges the
        # code does not have. Only hops the source itself calls order-bearing are checked.
        for a, b in path.get("ordering", []):
            if (a, b) not in precedes:
                fails.append(f"{name}: {a} must precede {b} per the source, but no `precedes` edge says so")
        # (3) the path's entities must at least be reachable from one another; the graph is
        # one component, so this fires only if a path names an entity the graph orphaned.
        for s in steps:
            if s["entity"] in ids and not any(
                (s["entity"], other) in linked for other in ids if other != s["entity"]
            ):
                fails.append(f"{name}: {s['entity']} participates in no edge at all")
    return fails


def check_edge_integrity(graph: dict) -> list[str]:
    fails = []
    ids = {e["id"] for e in graph["entities"]}
    used = collections.Counter()
    for r in graph["relationships"]:
        for end in ("from", "to"):
            if r[end] not in ids:
                fails.append(f"edge {r['id']}: {end} names unknown entity {r[end]!r}")
        if r["kind"] not in DECLARED_KINDS:
            fails.append(f"edge {r['id']}: kind {r['kind']!r} is not declared in dependency_rules.md")
        used[r["kind"]] += 1
    for kind in DECLARED_KINDS:
        if not used[kind]:
            fails.append(f"kind {kind!r} is declared but no edge uses it — dead vocabulary")
    return fails


def check_graph_health(graph: dict) -> list[str]:
    fails = []
    ids = {e["id"] for e in graph["entities"]}
    adj = collections.defaultdict(set)
    for r in graph["relationships"]:
        if r["from"] in ids and r["to"] in ids:
            adj[r["from"]].add(r["to"])
            adj[r["to"]].add(r["from"])
    seen, comps = set(), []
    for start in sorted(ids):
        if start in seen:
            continue
        stack, comp = [start], set()
        while stack:
            n = stack.pop()
            if n in comp:
                continue
            comp.add(n)
            seen.add(n)
            stack += list(adj[n] - comp)
        comps.append(comp)
    if len(comps) > 1:
        detached = sorted(sorted(c) for c in sorted(comps, key=len, reverse=True)[1:])
        fails.append(f"graph splits into {len(comps)} components; detached: {detached}")
    # unguarded <=> no P6 assertion. Two names for one fact must not disagree.
    for e in graph["entities"]:
        if (e["guard"] == "unguarded") != ("P6" not in e["pos"]):
            fails.append(f"{e['id']}: guard={e['guard']} but positions={e['pos']} (unguarded must mean no P6)")
    return fails


def check_projection_fresh() -> list[str]:
    """Every projection of graph.json must be regenerable to the same bytes.

    Both emitters are checked, not just one: a projection nobody checks is how the
    HTML map came to hold its own second copy of the entity data in the first place.
    """
    fails = []
    for emitter, extra, what in (("emit-rdf.py", [], "RDF obligations"),
                                 ("emit-rdf.py", ["--view", "routes"], "RDF routes"),
                                 ("emit-map.py", [], "HTML map"),
                                 ("emit-lexicon.py", [], "LEXICON.md"),
                                 ("emit-questions.py", [], "competency/extension docs")):
        script = ONTO / emitter
        if not script.is_file():
            fails.append(f"{what} emitter missing: ontology/{emitter}")
            continue
        r = subprocess.run([sys.executable, str(script), "--check", *extra], capture_output=True, text=True)
        if r.returncode != 0:
            fails.append(f"{what} projection stale: {(r.stderr or r.stdout).strip()}")
    return fails


# ── self-test: prove each check can fail ─────────────────────────────────────

def _plant_count_claim(text):
    """Fire the guard on a planted claim, over an injected doc rather than the real tree."""
    return "fired" if check_no_restated_counts({}, [("planted.md", text)]) else ""


def self_test(graph: dict, ev: dict, human_facing: dict, sources: dict) -> int:
    controls = []

    spec = importlib.util.spec_from_file_location("subcommand_probe", ONTO / "extract.py")
    extractor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extractor)
    dispatch = 'if [ "$PRIVATE" = 1 ]; then\n  case "$CMD" in\n    reset|migrate) exec manager ;;\n  esac\nfi\ncase "$CMD" in\n  install) install ;;\nesac\n'
    observed = set(extractor.subcommands(dispatch)["implemented"])
    if observed != {"install", "reset", "migrate"}:
        print("FAIL: subcommand extractor missed an indented private dispatch", file=sys.stderr)
        return 1
    without_private = dispatch.split('case "$CMD" in\n  install)', 1)[1]
    if "reset" in extractor.subcommands('case "$CMD" in\n  install)' + without_private)["implemented"]:
        print("FAIL: subcommand extractor accepted a removed private dispatch", file=sys.stderr)
        return 1

    usage_fixture = ('usage() {\n  cat <<\'EOF\'\n'
                     '  agent-bios setup start   inspect the setup entrypoint\n'
                     '  agent-bios install  install the package\n'
                     '  agent-bios help\nEOF\n}\n'
                     '  agent-bios outside  is not a usage advertisement\n'
                     'if [ "$CMD" = "setup" ]; then\n  exec setup\nfi\n'
                     'case "$CMD" in\n  install|help) exec manager ;;\nesac\n')
    advertised = extractor.subcommands(usage_fixture)
    if set(advertised["advertised_in_usage"]) != {"setup", "install", "help"} or advertised["implemented_but_unadvertised"]:
        print("FAIL: subcommand extractor missed nested/bare help or counted text outside usage()", file=sys.stderr)
        return 1
    removed_usage = copy.deepcopy(ev)
    removed_usage["subcommands"] = extractor.subcommands(usage_fixture.replace(
        '  agent-bios setup start   inspect the setup entrypoint\n', ''))
    controls.append(("site agreement catches removal of nested setup advertisement",
                     lambda: check_site_agreement(removed_usage)))

    def runtime_fixture(mutation=None):
        with tempfile.TemporaryDirectory(prefix="ontology-authorities-") as raw:
            root = pathlib.Path(raw)
            (root / "compose").mkdir()
            (root / "launch").mkdir()
            (root / "learn").mkdir()
            (root / "install.sh").write_text(
                'exec python3 "$REPO/compose/manager.py"\n'
                'exec python3 "$REPO/launch/shell.py"\n'
                'collector="$REPO/learn/capture.py"\n', encoding="utf-8")
            sources = {
                "compose/manager.py": "from store import Store\n",
                "compose/store.py": "class Store: pass\n",
                "compose/session.py": 'import importlib\nmodule = "store" if True else "unavailable"\nimportlib.import_module(module)\n',
                "launch/agent-launch.py": "import session\n",
                "launch/shell.py": "from store import Store\n",
                "learn/capture.py": "from store import Store\n",
            }
            for name, body in sources.items():
                (root / name).write_text(body, encoding="utf-8")
            observed = extractor.runtime_authorities(root)
            if set(observed["modules"]) != set(sources):
                raise AssertionError(f"runtime authority extractor disagrees with fixture modules: {observed}")
            expected_imports = {
                ("compose/manager.py", "compose/store.py"),
                ("compose/session.py", "compose/store.py"),
                ("launch/agent-launch.py", "compose/session.py"),
                ("launch/shell.py", "compose/store.py"),
                ("learn/capture.py", "compose/store.py"),
            }
            if {(row["source"], row["target"]) for row in observed["local_imports"]} != expected_imports:
                raise AssertionError(f"runtime authority extractor disagrees with fixture imports: {observed}")
            fixture = {"entities": [{"id": name, "anchor": name} for name in sources],
                       "relationships": [
                           {"from": name, "to": "compose/store.py", "kind": "controls",
                            "name": "uses", "guard": "gated", "desc": "fixture dependency"}
                           for name in sources if name != "compose/store.py"
                       ] + [{"from": "compose/store.py", "to": "compose/session.py", "kind": "controls",
                             "name": "feeds", "guard": "gated", "desc": "fixture dependency"}]}
            if mutation is None:
                if check_runtime_authorities(fixture, {"runtime_authorities": observed}, root):
                    raise AssertionError("runtime authority coverage rejects its complete positive fixture")
                (root / "compose/manager.py").write_text("pass\n", encoding="utf-8")
                removed = extractor.runtime_authorities(root)
                if {"source": "compose/manager.py", "target": "compose/store.py"} in removed["local_imports"]:
                    raise AssertionError("runtime authority extractor retained a removed import")
                return []
            mutation(fixture, observed)
            return check_runtime_authorities(fixture, {"runtime_authorities": observed}, root)

    runtime_fixture()
    for missing in ("compose/manager.py", "compose/session.py", "launch/shell.py", "learn/capture.py"):
        def drop_anchor(fixture, observed, missing=missing):
            fixture["entities"] = [row for row in fixture["entities"] if row["id"] != missing]
        controls.append((f"runtime coverage catches omitted authority {missing}",
                         lambda mutate=drop_anchor: runtime_fixture(mutate)))
    controls.append(("runtime coverage refuses an empty extractor subject", lambda: runtime_fixture(
        lambda fixture, observed: observed.update(modules=[], entrypoints=[], local_imports=[]))))
    controls.append(("runtime coverage catches an imported module missing from its subject", lambda: runtime_fixture(
        lambda fixture, observed: observed["modules"].remove("compose/store.py"))))
    controls.append(("runtime coverage refuses anchors without impact obligations", lambda: runtime_fixture(
        lambda fixture, observed: fixture.update(relationships=[]))))

    missing_shell = copy.deepcopy(ev)
    missing_shell["user_owned_regions"][0]["authoring_sites"] = ["install.sh", "compose/assemble.py"]
    controls.append(("site agreement catches an omitted private shell author",
                     lambda: check_site_agreement(missing_shell)))
    unscoped = copy.deepcopy(ev)
    unscoped["user_owned_regions"][0]["regions"] = [{"span": "fixture", "ops": ["merge"]}]
    controls.append(("site agreement refuses an unscoped user-file writer",
                     lambda: check_site_agreement(unscoped)))

    g = copy.deepcopy(graph)
    g["entities"][0]["anchor"] = "compose/nope-does-not-exist.py"
    controls.append(("anchor liveness catches a dead path", lambda: check_anchor_liveness(g)))

    g0 = copy.deepcopy(graph)
    g0["entities"][0]["evidence"] = "a literal that is certainly not in that file"
    controls.append(("anchor liveness catches drifted evidence", lambda: check_anchor_liveness(g0)))

    g2 = copy.deepcopy(graph)
    g2.setdefault("derived", {})["deploy_targets"] = 999
    controls.append(("derived agreement catches a wrong count", lambda: check_derived_agreement(g2, ev)))

    g3 = copy.deepcopy(graph)
    g3["relationships"][0]["to"] = "ghost-entity"
    controls.append(("edge integrity catches a dangling end", lambda: check_edge_integrity(g3)))

    g4 = copy.deepcopy(graph)
    g4["relationships"][0]["kind"] = "invented_kind"
    controls.append(("edge integrity catches an undeclared kind", lambda: check_edge_integrity(g4)))

    g5 = copy.deepcopy(graph)
    g5["relationships"] = [r for r in g5["relationships"] if "environment-variable" not in (r["from"], r["to"])]
    controls.append(("graph health catches a detached component", lambda: check_graph_health(g5)))

    g6 = copy.deepcopy(graph)
    victim = next(e for e in g6["entities"] if e["guard"] == "unguarded")
    victim["guard"] = "gated"
    controls.append(("graph health catches a guard/P6 disagreement", lambda: check_graph_health(g6)))

    g6b = copy.deepcopy(graph)
    g6b["relationships"] = g6b["relationships"][:5]
    controls.append(("prose counts catch a drifted edge total", lambda: check_prose_counts(g6b)))

    g6c = copy.deepcopy(graph)
    first = next(iter(g6c["happy_paths"]["paths"].values()))
    first["steps"][0]["entity"] = "ghost-entity"
    controls.append(("happy path catches a step with no entity", lambda: check_happy_path_coverage(g6c)))

    g6d = copy.deepcopy(graph)
    g6d["relationships"] = []
    controls.append(("happy path catches an unlinked hop", lambda: check_happy_path_coverage(g6d)))

    g6p = copy.deepcopy(graph)
    g6p["purpose"]["stated"][0]["quote"] = "a sentence no source contains"
    controls.append(("purpose extraction catches an unquotable clause",
                     lambda: check_purpose_extraction(g6p)))

    # These two build the row they mutate rather than indexing the live list. Controls that
    # index one stop testing the moment it empties — which happened three times this round as
    # debts closed and verdicts resolved, twice as a silent pass and once as a bare IndexError.
    # A control's subject should not depend on what the repo currently happens to be arguing
    # about.
    g6t = copy.deepcopy(graph)
    g6t["verdicts"]["transitional"] = [{
        "id": "PT-X", "observation": "planted", "why_in_flight": "planted",
        "deferral": {"source": "README.md", "quote": "a deferral no design record contains"}}]
    controls.append(("purpose extraction catches a transition that lost its declaration",
                     lambda: check_purpose_extraction(g6t)))

    g6u = copy.deepcopy(graph)
    g6u["verdicts"]["transitional"] = [{
        "id": "PT-Y", "observation": "planted", "why_in_flight": "planted", "deferral": None}]
    controls.append(("purpose extraction refuses unrecorded WIP with no finding",
                     lambda: check_purpose_extraction(g6u)))

    g6q = copy.deepcopy(graph)
    g6q["purpose"]["inferred"] = [{"id": "PI-X", "clause": "planted", "evidence": "none"}]
    controls.append(("purpose extraction refuses an unconfirmed inferred clause",
                     lambda: check_purpose_extraction(g6q)))

    # Builds its own row rather than indexing the live list: an empty list makes that index
    # crash, and a repopulated one makes it silently test whatever happens to sit at [0].
    g6v = copy.deepcopy(graph)
    g6v["purpose"]["open_violations"] = [
        {"id": "PV-X", "clause": "PU-nonexistent", "site": "install.sh", "what": "planted"}]
    controls.append(("purpose extraction catches a debt against no clause",
                     lambda: check_purpose_extraction(g6v)))

    g6w = copy.deepcopy(graph)
    g6w["purpose"]["open_violations"] = [
        {"id": "PV-Y", "clause": "PU-13", "site": "gates/deleted-long-ago.py", "what": "planted"}]
    controls.append(("purpose extraction catches a debt against a vanished site",
                     lambda: check_purpose_extraction(g6w)))

    g6blank = copy.deepcopy(graph)
    g6blank["purpose"]["stated"][0]["quote"] = ""
    controls.append(("purpose extraction refuses a blanked quote",
                     lambda: check_purpose_extraction(g6blank)))

    g6serv = copy.deepcopy(graph)
    g6serv["golden_relationships"][0]["serves"] = ["PU-nonexistent"]
    controls.append(("purpose coverage catches an obligation serving no real clause",
                     lambda: check_purpose_coverage(g6serv)))

    g6root = copy.deepcopy(graph)
    for r in g6root["golden_relationships"]:
        r["serves"] = []
        r.pop("orphan_reason", None)
    controls.append(("purpose coverage catches a rootless obligation with no reason",
                     lambda: check_purpose_coverage(g6root)))

    g6drop = copy.deepcopy(graph)
    g6drop["golden_relationships"][0].pop("serves")
    controls.append(("purpose coverage catches an untraced obligation",
                     lambda: check_purpose_coverage(g6drop)))

    evhide = copy.deepcopy(ev)
    evhide["subcommands"]["implemented_but_unadvertised"] = ["ghost"]
    controls.append(("site agreement catches a command usage() never advertises",
                     lambda: check_site_agreement(evhide)))

    evdrift = copy.deepcopy(ev)
    evdrift["tier_binding_sites"]["disagreements"] = [
        {"tier": "workhorse", "field": "model",
         "launch_profile": "gpt-5.6-terra", "agent_template": "gpt-5.6-luna"}]
    controls.append(("site agreement catches a template drifting from the launch profile",
                     lambda: check_site_agreement(evdrift)))

    evfold = copy.deepcopy(ev)
    uor = evfold["user_owned_regions"][0]
    uor["regions"] = [r for r in uor["regions"] if r["authored_in"] == "install.sh"]
    uor["authoring_sites"] = ["install.sh"]
    controls.append(("site agreement catches the region extractor folding to one author",
                     lambda: check_site_agreement(evfold)))

    evnoop = copy.deepcopy(ev)
    evnoop["user_owned_regions"][0]["regions"][0]["ops"] = []
    controls.append(("site agreement catches a span with no lifecycle op",
                     lambda: check_site_agreement(evnoop)))

    evwire = copy.deepcopy(ev)
    evwire["guides"][0]["never_wired"] = True
    controls.append(("value consumers catch a field produced and never read",
                     lambda: check_value_consumers(evwire, human_facing, sources)))

    hf_blank = dict(human_facing)
    hf_blank["gates.path"] = ""
    controls.append(("value consumers refuse a human-facing entry with no reason",
                     lambda: check_value_consumers(ev, hf_blank, sources)))

    hf_stale = dict(human_facing)
    hf_stale["gr4_deploy_verify.uncovered"] = "planted: this field really is read"
    controls.append(("value consumers catch a stale human-facing registration",
                     lambda: check_value_consumers(ev, hf_stale, sources)))

    controls.append(("value consumers refuse an empty subject",
                     lambda: check_value_consumers({}, human_facing, sources)))

    evdm = copy.deepcopy(ev)
    evdm["domain_manifest"]["sites"].pop("filesystem")
    controls.append(("site agreement catches the domain extractor losing a site",
                     lambda: check_site_agreement(evdm)))

    evdmv = copy.deepcopy(ev)
    evdmv["domain_manifest"]["instructions_bullet_count"] = 0
    controls.append(("site agreement refuses a vacuous domain comparison",
                     lambda: check_site_agreement(evdmv)))

    evempty = copy.deepcopy(ev)
    evempty["subcommands"]["dispatched_in_case"] = []
    evempty["subcommands"]["early_branch"] = []
    controls.append(("site agreement refuses an empty subject",
                     lambda: check_site_agreement(evempty)))

    g6c1 = copy.deepcopy(graph)
    g6c1["verdicts"]["contradiction"][0]["sites"] = {"only/one/site.py": "the whole story"}
    controls.append(("surfaced conflicts catch a contradiction with one site",
                     lambda: check_surfaced_conflicts(g6c1)))

    g6c2 = copy.deepcopy(graph)
    g6c2["verdicts"]["contradiction"][0].pop("no_declaration_because")
    controls.append(("surfaced conflicts catch a contradiction that never checked for a licence",
                     lambda: check_surfaced_conflicts(g6c2)))

    g6c3 = copy.deepcopy(graph)
    g6c3["verdicts"]["unlinked"][0].pop("why_not_the_same_claim")
    controls.append(("surfaced conflicts catch an unlinked pair with no reason",
                     lambda: check_surfaced_conflicts(g6c3)))

    g6c4 = copy.deepcopy(graph)
    g6c4["verdicts"]["contradiction"][0]["blocks"] = ["GR-nonexistent"]
    controls.append(("surfaced conflicts catch a contradiction blocking no real obligation",
                     lambda: check_surfaced_conflicts(g6c4)))

    g6q1 = copy.deepcopy(graph)
    g6q1["competency_questions"]["questions"][0].pop("serves")
    controls.append(("question admission catches a question serving no purpose",
                     lambda: check_question_admission(g6q1)))

    g6q2 = copy.deepcopy(graph)
    g6q2["competency_questions"]["questions"][0]["serves"] = ["PU-nonexistent"]
    controls.append(("question admission catches a question serving a clause that does not exist",
                     lambda: check_question_admission(g6q2)))

    g6q3 = copy.deepcopy(graph)
    g6q3["competency_questions"]["retired"][0].pop("reason")
    controls.append(("question admission catches a silent retirement",
                     lambda: check_question_admission(g6q3)))

    # These two construct their own preconditions rather than leaning on the live graph
    # carrying a `violated` status and an open decision. A control that depends on live state
    # stops exercising its branch the moment that state resolves, while still reporting ok.
    g6d1 = copy.deepcopy(graph)
    g6d1["golden_relationships"][0]["status"] = "violated"
    g6d1["decisions"]["rows"] = []
    controls.append(("decisions catch a `violated` status nobody decided",
                     lambda: check_decisions(g6d1)))

    g6d2 = copy.deepcopy(graph)
    g6d2["decisions"]["rows"][0].update(status="open", options=["only one way to see it"])
    controls.append(("decisions refuse an open decision with one option",
                     lambda: check_decisions(g6d2)))

    g6d3 = copy.deepcopy(graph)
    g6d3["decisions"]["rows"][0].update(status="decided", options=[], decided_on="", rationale="")
    controls.append(("decisions refuse a decided row with no date or rationale",
                     lambda: check_decisions(g6d3)))

    g6la = copy.deepcopy(graph)
    g6la["verdicts"]["licensed_asymmetry"][0]["declaration"]["names"] = "a-site-the-quote-omits"
    controls.append(("licensed asymmetry catches a declaration naming no site",
                     lambda: check_licensed_asymmetry(g6la)))

    g6lq = copy.deepcopy(graph)
    g6lq["verdicts"]["licensed_asymmetry"][0]["declaration"]["quote"] = "a rule no gate contains"
    controls.append(("licensed asymmetry catches a licence whose declaration vanished",
                     lambda: check_licensed_asymmetry(g6lq)))

    g6lw = copy.deepcopy(graph)
    g6lw["verdicts"]["licensed_asymmetry"][0].pop("why")
    controls.append(("licensed asymmetry refuses a licence with no reason",
                     lambda: check_licensed_asymmetry(g6lw)))

    g6undec = copy.deepcopy(graph)
    for row in g6undec["purpose"]["stated"]:
        row.pop("enforcement", None)
    controls.append(("purpose coverage catches an unserved clause nobody decided on",
                     lambda: check_purpose_coverage(g6undec)))

    g6mute = copy.deepcopy(graph)
    for row in g6mute["purpose"]["stated"]:
        if "enforcement" in row:
            row["enforcement"] = {"kind": "accepted"}
            break
    controls.append(("purpose coverage refuses an enforcement decision with no reason",
                     lambda: check_purpose_coverage(g6mute)))

    g6settled = copy.deepcopy(graph)
    g6settled["purpose"]["extraction_status"] = "settled"
    g6settled["purpose"]["inferred"] = [{"id": "PI-X", "clause": "still pending", "confirmed": False}]
    controls.append(("purpose extraction refuses `settled` with a clause still pending",
                     lambda: check_purpose_extraction(g6settled)))

    g6e = copy.deepcopy(graph)
    g6e["lexicon"]["deprecated"].append({"token": "ghost-token", "replaced_by": "x",
                                         "reason": "planted", "enforced": True})
    controls.append(("lexicon constants catch a documented-but-ungated token",
                     lambda: check_lexicon_constants(g6e)))

    g6f = copy.deepcopy(graph)
    for d in g6f["lexicon"]["deprecated"]:
        d["enforced"] = False
    controls.append(("lexicon constants refuse a vacuous denylist",
                     lambda: check_lexicon_constants(g6f)))

    g6ar = copy.deepcopy(graph)
    g6ar["lexicon"]["archive_allowlist"][0]["reason"] = ""
    controls.append(("lexicon constants catch an archive exemption with no reason",
                     lambda: check_lexicon_constants(g6ar)))

    g6ad = copy.deepcopy(graph)
    g6ad["lexicon"]["archive_allowlist"][0]["display"] = "`some/path/` and nothing else"
    controls.append(("lexicon constants catch a reason the projection drops",
                     lambda: check_lexicon_constants(g6ad)))

    g6g = copy.deepcopy(graph)
    for q in g6g["competency_questions"]["questions"]:
        if q["priority"] == "P1":
            q["resolver"] = {"kind": "none", "gap": "planted"}
            break
    controls.append(("competency resolvers catch a P1 with no answer",
                     lambda: check_competency_resolvers(g6g)))

    controls.append(("restated-count guard fires on a planted claim",
                     lambda: [f for f in [_plant_count_claim("The map carries 99 entities.")] if f]))
    # Both word orders, because a pattern knowing only one would pass this whole check while
    # reading half the prose it claims to cover.
    controls.append(("restated-count guard fires on the reversed word order",
                     lambda: [f for f in [_plant_count_claim("- entities 99, edges 41")] if f]))
    # No false-positive control here: this harness reads a truthy return as "the control fired",
    # so an inverted one would report failure in the wrong words. Over-firing is caught standing
    # instead — the gate itself runs over the real prose, and a pattern that matched too much
    # would turn it red.

    g7 = {"entities": [], "relationships": [], "derived": {}}
    controls.append(("anchor liveness refuses an empty subject", lambda: check_anchor_liveness(g7)))

    bad = 0
    for label, fn in controls:
        if fn():
            print(f"  ok   {label}")
        else:
            print(f"  FAIL {label} — the check passed over broken input")
            bad += 1
    print(f"self-test: {len(controls) - bad}/{len(controls)} negative controls held")
    return 1 if bad else 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--coverage", action="store_true",
                    help="report purpose clauses no golden relationship serves (never fails)")
    args = ap.parse_args()

    if not GRAPH.is_file():
        print(f"FAIL: {GRAPH} missing", file=sys.stderr)
        sys.exit(1)
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    extractors = load_extractors()
    ev = {name: fn() for name, fn in extractors.EXTRACTORS.items()}
    # Consumers are the ontology's own tools; extract.py counts because one extractor feeding
    # another is a real reader (gr4 consumes deploy_targets).
    consumer_src = {p.name: p.read_text(encoding="utf-8") for p in sorted(ONTO.glob("*.py"))}

    if args.self_test:
        sys.exit(self_test(graph, ev, extractors.HUMAN_FACING, consumer_src))

    if args.coverage:
        served = {c for r in graph["golden_relationships"] for c in r.get("serves", [])}
        rows = [r for r in graph["purpose"]["stated"] if r["id"] not in served]
        print(f"purpose coverage: {len(graph['purpose']['stated']) - len(rows)} of "
              f"{len(graph['purpose']['stated'])} stated clauses have a golden relationship")
        for r in rows:
            enf = r.get("enforcement") or {}
            print(f"  {enf.get('kind', 'UNDECIDED'):18} {r['id']:6} {r['clause'][:70]}")
        for r in graph["golden_relationships"]:
            if not r.get("serves"):
                print(f"  rootless  {r['id']}  {r['title']}")
        sys.exit(0)

    results = [
        ("anchor liveness", check_anchor_liveness(graph)),
        ("runtime authorities", check_runtime_authorities(graph, ev)),
        ("derived agreement", check_derived_agreement(graph, ev)),
        ("edge integrity", check_edge_integrity(graph)),
        ("prose counts", check_prose_counts(graph)),
        ("happy path coverage", check_happy_path_coverage(graph)),
        ("purpose extraction", check_purpose_extraction(graph)),
        ("purpose coverage", check_purpose_coverage(graph)),
        ("licensed asymmetry", check_licensed_asymmetry(graph)),
        ("decisions", check_decisions(graph)),
        ("question admission", check_question_admission(graph)),
        ("surfaced conflicts", check_surfaced_conflicts(graph)),
        ("site agreement", check_site_agreement(ev)),
        ("value consumers", check_value_consumers(ev, extractors.HUMAN_FACING, consumer_src)),
        ("lexicon constants", check_lexicon_constants(graph)),
        ("competency resolvers", check_competency_resolvers(graph)),
        ("no restated counts", check_no_restated_counts(graph)),
        ("no line anchors", check_no_line_anchors(graph)),
        ("graph health", check_graph_health(graph)),
        ("projection freshness", check_projection_fresh()),
    ]
    fail = 0
    for label, problems in results:
        if problems:
            fail = 1
            print(f"FAIL  {label}")
            for p in problems:
                print(f"        {p}")
        else:
            print(f"  OK  {label}")
    if not fail:
        print(f"check-ontology: OK ({len(graph['entities'])} entities, "
              f"{len(graph['relationships'])} edges, {len(DECLARED_KINDS)} kinds)")
    sys.exit(fail)


if __name__ == "__main__":
    main()
