#!/usr/bin/env python3
"""Tier bindings against the model catalogues the host CLIs already hold.

Two questions live here and they must not share an exit code — the split is the one
`gates/check-prompting-sources.py` already established for "is this still true against
the outside world".

STRUCTURE is decidable from the repo alone, so it GATES (default mode, wired into the
parity umbrella): every model id this profile names has a `[models]` row, every row is
named somewhere, every `superseded_by` points at a row that exists, and the native
Claude subagent definitions agree with the profile they are supposed to mirror. None of
that needs a catalogue, a network, or an account.

CURRENCY needs the host catalogues, which are per-account files on one developer's
machine, so it only DISCLOSES here — it prints and exits 0 even when every binding is a
generation behind. A commit must never fail because of what some account can see: the
same tree would pass on one laptop and fail on another, and a gate that does that is one
people learn to route around.

The teeth are at publish time. `--publish-guard` runs the same classifier and REFUSES a
release that ships a superseded binding, because that is the moment the stale value
leaves this machine for every installing user. Two answers satisfy it: rebind, or record
`superseded_by` on the model's `[models]` row — a one-line, shipped, git-dated statement
that keeping it was a decision. Naming a successor that is itself superseded does not
satisfy the guard, so one acknowledgement cannot silently cover two generations.

    python3 gates/check-model-currency.py            # structure blocks, currency prints
    python3 gates/check-model-currency.py --propose  # + the [models] rows to paste
    python3 gates/check-model-currency.py --publish-guard   # refuses a stale release
    python3 gates/check-model-currency.py --self-test       # offline controls

WHAT A CATALOGUE IS, AND WHAT IT IS NOT. Each host CLI fetches its model list from its
own vendor and caches it on disk; this tool reads that cache and never writes it, never
runs the CLI, and never reaches the network. The cache is scoped to whoever is logged in,
so "not in the catalogue" means "this account cannot see it", never "this model does not
exist" — that class is reported and deliberately does NOT block, publish included.
Nothing derived from a cache is written into the repo, and no account identifier, cache
path, or token-bearing filename reaches the output; a control asserts that.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import pathlib
import re
import sys
import tempfile
import tomllib

REPO = pathlib.Path(__file__).resolve().parent.parent
PROFILE = REPO / "launch" / "agent-launch.toml"
CLAUDE_AGENTS = REPO / "claude" / "agents"

# Which catalogue answers for an id. A prefix rather than the config path it was found
# at, because a review row names a model beside a provider rather than under a host, and
# an id whose family is unknown must land in NOT JUDGED instead of being asked of the
# wrong vendor.
HOSTS = (("claude", ("claude-",)), ("codex", ("gpt-", "codex-")))

# A Claude catalogue id may carry a release date the bound id omits — the catalogue says
# `claude-haiku-4-5-20251001` where the profile says `claude-haiku-4-5`, and treating
# those as different models reports a live binding as missing. Only this exact shape is
# accepted: `claude-opus-50` must NOT match `claude-opus-5`, which plain `startswith`
# would have allowed.
DATED = re.compile(r"-\d{8}$")

FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
SECRETISH = re.compile(r"[0-9a-f]{32,}")


class Problem(Exception):
    """A structural fault — decidable, so it exits non-zero even though currency does not."""


# ---------------------------------------------------------------- the repo's own claims

def load_profile(path: pathlib.Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise Problem(f"{path}: cannot parse the launch profile ({exc})")


def model_sites(profile: dict) -> list[dict]:
    """Every place this profile names a model, found by walking rather than by a path list.

    A hardcoded list of known locations is how the preset review rows went unnoticed: they
    name a model directly, outside `[hosts.*.tiers.*]`, and nothing was looking there. A
    walk cannot miss a site that a later edit adds.
    """
    sites: list[dict] = []

    def walk(node, trail: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "model" and isinstance(value, str):
                    sites.append({"where": trail or "<root>", "model": value,
                                  "effort": node.get("effort")})
                elif key == "models" and isinstance(value, list) and trail.startswith("hosts."):
                    for i, mid in enumerate(value):
                        if isinstance(mid, str):
                            sites.append({"where": f"{trail}.models[{i}]", "model": mid,
                                          "effort": None})
                else:
                    walk(value, f"{trail}.{key}" if trail else key)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{trail}[{i}]")

    # `[models]` is the row table, not a use of the ids it keys; walking it would make
    # every row cite itself and the "unused row" check could never fire.
    walk({k: v for k, v in profile.items() if k != "models"}, "")
    return sites


def agent_sites() -> list[dict]:
    """The native Claude subagent definitions, which the installed CLI reads directly.

    These ship and they are what actually binds a spawned tier, so they are structure, not
    documentation. The Codex equivalents are already held against the profile by
    `gates/check_parity.py codex_agent_templates`; this side had no check at all.
    """
    sites = []
    for path in sorted(CLAUDE_AGENTS.glob("*.md")):
        front = FRONT.match(path.read_text(encoding="utf-8"))
        if not front:
            continue
        body = front.group(1)
        model = re.search(r"^model:\s*(\S+)\s*$", body, re.M)
        if not model:
            continue
        effort = re.search(r"^effort:\s*(\S+)\s*$", body, re.M)
        sites.append({"where": f"claude/agents/{path.name}", "tier": path.stem,
                      "model": model.group(1),
                      "effort": effort.group(1) if effort else None})
    return sites


def check_structure(profile: dict, sites: list[dict], agents: list[dict]) -> list[str]:
    rows = profile.get("models")
    problems = []
    if not isinstance(rows, dict) or not rows:
        return [f"{PROFILE.name}: no [models] table — nothing declares what the profile's "
                f"model ids are, so neither direction can be judged"]
    if not sites:
        return [f"{PROFILE.name}: no model site found anywhere in the profile — the walk "
                f"is broken, not the tree"]

    named = {s["model"] for s in sites}
    for site in sites:
        if site["model"] not in rows:
            problems.append(f"{site['where']} binds {site['model']!r}, which has no [models] row")
    for mid, row in rows.items():
        if not isinstance(row, dict) or not row.get("display"):
            problems.append(f"[models.\"{mid}\"] carries no display name")
        if mid not in named:
            problems.append(f"[models.\"{mid}\"] is named by nothing in the profile — a row "
                            f"outliving its binding is how a stale id keeps looking current")
        successor = (row or {}).get("superseded_by") if isinstance(row, dict) else None
        if successor and successor not in rows:
            problems.append(f"[models.\"{mid}\"] is acknowledged as superseded by "
                            f"{successor!r}, which has no [models] row of its own")

    # The native agent definitions against the tiers they mirror.
    tiers = (profile.get("hosts", {}).get("claude", {}) or {}).get("tiers", {}) or {}
    for agent in agents:
        bound = tiers.get(agent["tier"])
        if bound is None:
            continue
        if agent["model"] != bound.get("model"):
            problems.append(f"{agent['where']} binds {agent['model']!r} but "
                            f"hosts.claude.tiers.{agent['tier']} binds "
                            f"{bound.get('model')!r} — the CLI reads the agent file")
        if agent["effort"] != bound.get("effort"):
            problems.append(f"{agent['where']} sets effort {agent['effort']!r} but "
                            f"hosts.claude.tiers.{agent['tier']} sets "
                            f"{bound.get('effort')!r}")
    return problems


# ------------------------------------------------------------------- the host catalogues

def claude_catalogue(home: pathlib.Path) -> dict | None:
    """The freshest cache file that actually carries a model list.

    Freshest by the catalogue's OWN `fetchedAt` rather than by mtime, and files that are
    not catalogues are skipped rather than failing the read — the directory holds other
    things, and picking the wrong one silently would be worse than reporting none.
    """
    best = None
    for name in glob.glob(str(home / ".claude" / "cache" / "model-catalog" / "*.json")):
        try:
            data = json.loads(pathlib.Path(name).read_text(encoding="utf-8"))
            models = data["catalog"]["config"]["models"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if not isinstance(models, list) or not models:
            continue
        at = data.get("fetchedAt") or 0
        if best is None or at > best[0]:
            best = (at, models)
    if best is None:
        return None
    entries = {}
    for m in best[1]:
        if not isinstance(m, dict) or not m.get("id"):
            continue
        thinking = m.get("thinking") or {}
        entries[m["id"]] = {
            "display": m.get("name"),
            "current": m.get("section") == "main",
            "judgeable": m.get("section") in ("main", "overflow"),
            "efforts": [o["id"] for o in thinking.get("effort_options", [])
                        if isinstance(o, dict) and o.get("id")],
            "family": family_of(m["id"]),
        }
    return {"entries": entries, "fetched_ms": best[0]}


def codex_catalogue(home: pathlib.Path) -> dict | None:
    path = home / ".codex" / "models_cache.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        models = data["models"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(models, list) or not models:
        return None
    entries = {}
    for m in models:
        if not isinstance(m, dict) or not m.get("slug"):
            continue
        desc = m.get("description") or ""
        entries[m["slug"]] = {
            "display": m.get("display_name"),
            # The vendor states the generation in prose. Reading that is reading what the
            # vendor said; ranking by version number would be this gate inventing an order.
            "current": not re.search(r"\b(Older|Previous generation)\b", desc),
            "judgeable": bool(desc),
            "listed": m.get("visibility") == "list",
            "priority": m.get("priority"),
            "efforts": [e["effort"] for e in m.get("supported_reasoning_levels", [])
                        if isinstance(e, dict) and e.get("effort")],
            "family": family_of(m["slug"]),
        }
    return {"entries": entries, "fetched_at": data.get("fetched_at")}


def family_of(model_id: str) -> str | None:
    """The role name two ids must share before one can be the other's successor.

    `claude-opus-5-5` succeeds `claude-opus-5`; `claude-sonnet-5-5` does not. On the Codex
    side the role is the trailing word — `gpt-6.1-sol` succeeds `gpt-5.6-sol`, while
    `gpt-5.6-terra` has no `gpt-6` counterpart at all, which is exactly the case a human
    has to decide rather than a rule.
    """
    bare = DATED.sub("", model_id)
    parts = bare.split("-")
    if bare.startswith("claude-") and len(parts) >= 3:
        return parts[1]
    if bare.startswith("gpt-") and len(parts) >= 3:
        return parts[-1]
    return None


def host_of(model_id: str) -> str | None:
    for host, prefixes in HOSTS:
        if any(model_id.startswith(p) for p in prefixes):
            return host
    return None


def resolve(model_id: str, entries: dict) -> tuple[str | None, str | None]:
    """(catalogue id, ambiguity reason). Exact match first, then one dated variant."""
    if model_id in entries:
        return model_id, None
    dated = [k for k in entries if k.startswith(model_id + "-") and DATED.search(k[len(model_id):])]
    if len(dated) == 1:
        return dated[0], None
    if len(dated) > 1:
        return None, f"{len(dated)} dated variants"
    return None, None


# -------------------------------------------------------------------------- the verdict

CURRENT = "current"
SUPERSEDED = "SUPERSEDED"
ACKNOWLEDGED = "ACKNOWLEDGED"
EFFORT_BAD = "EFFORT UNSUPPORTED"
ABSENT = "NOT IN CATALOGUE"
OLDER = "OLDER?"
UNJUDGED = "NOT JUDGED"

# What a release may not carry. `ABSENT` is excluded on purpose: a model this account
# cannot see may be perfectly available to the user installing the package.
REFUSING = (SUPERSEDED, EFFORT_BAD)


def classify(sites: list[dict], rows: dict, catalogues: dict) -> list[dict]:
    out = []
    for site in sites:
        mid = site["model"]
        host = host_of(mid)
        cat = catalogues.get(host) if host else None
        verdict = dict(site, host=host, verdict=UNJUDGED, note="", successor=None)
        if host is None:
            verdict["note"] = "no catalogue answers for this id's family"
            out.append(verdict)
            continue
        if cat is None:
            verdict["note"] = f"no {host} catalogue on this machine"
            out.append(verdict)
            continue
        entries = cat["entries"]
        found, ambiguous = resolve(mid, entries)
        if ambiguous:
            verdict["note"] = ambiguous
            out.append(verdict)
            continue
        if found is None:
            verdict["verdict"] = ABSENT
            verdict["note"] = "this account's catalogue does not list it"
            out.append(verdict)
            continue
        entry = entries[found]
        if not entry["judgeable"]:
            verdict["note"] = "catalogue entry states no generation"
            out.append(verdict)
            continue

        # Effort is a property of the model, not of the tier: moving a binding can make a
        # previously valid effort invalid, or make one possible where the old model had none.
        if site["effort"] and entry["efforts"] and site["effort"] not in entry["efforts"]:
            verdict["verdict"] = EFFORT_BAD
            verdict["note"] = f"{found} accepts {', '.join(entry['efforts'])}"
            out.append(verdict)
            continue
        if site["effort"] and not entry["efforts"]:
            verdict["verdict"] = EFFORT_BAD
            verdict["note"] = f"{found} takes no effort setting"
            out.append(verdict)
            continue

        if entry["current"]:
            verdict["verdict"] = CURRENT
            out.append(verdict)
            continue

        successors = sorted(
            k for k, e in entries.items()
            if e["current"] and e["family"] == entry["family"] and k != found
            and (host != "codex" or e.get("listed"))
        )
        if not successors:
            verdict["verdict"] = OLDER
            verdict["note"] = "the catalogue calls it old but names no same-role successor"
            out.append(verdict)
            continue
        verdict["successor"] = successors[0]
        acknowledged = (rows.get(mid) or {}).get("superseded_by")
        if acknowledged:
            ack_entry = entries.get(acknowledged) or {}
            if ack_entry.get("judgeable") and not ack_entry.get("current"):
                # The acknowledged successor has itself been overtaken, so the record no
                # longer describes the choice being made. One line cannot cover two moves.
                verdict["verdict"] = SUPERSEDED
                verdict["note"] = (f"acknowledged successor {acknowledged} is itself superseded")
            else:
                verdict["verdict"] = ACKNOWLEDGED
                verdict["note"] = f"kept deliberately; successor {acknowledged}"
        else:
            verdict["verdict"] = SUPERSEDED
        out.append(verdict)
    return out


def report(verdicts: list[dict], catalogues: dict) -> list[str]:
    lines = []
    for host, cat in sorted(catalogues.items()):
        if cat is None:
            lines.append(f"  {host} catalogue: none on this machine — bindings unjudged")
        else:
            when = cat.get("fetched_at") or f"epoch-ms {cat.get('fetched_ms')}"
            lines.append(f"  {host} catalogue: {len(cat['entries'])} models, fetched {when}")
    counts: dict[str, int] = {}
    for v in verdicts:
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
    for v in verdicts:
        if v["verdict"] == CURRENT:
            continue
        tail = f" -> {v['successor']}" if v["successor"] else ""
        note = f"  ({v['note']})" if v["note"] else ""
        lines.append(f"  {v['verdict']:<18}{v['where']}  {v['model']}{tail}{note}")
    tally = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
    lines.append(f"MODEL CURRENCY: {len(verdicts)} model sites judged — {tally}")
    return lines


def proposals(verdicts: list[dict], rows: dict) -> list[str]:
    out = []
    for v in verdicts:
        if v["verdict"] != SUPERSEDED or not v["successor"]:
            continue
        display = (rows.get(v["model"]) or {}).get("display", v["model"])
        out.append(f'"{v["model"]}" = {{ display = "{display}", '
                   f'superseded_by = "{v["successor"]}" }}')
    return sorted(set(out))


# ------------------------------------------------------------------------------- driving

def run(home: pathlib.Path, profile_path: pathlib.Path = PROFILE,
        agents: list[dict] | None = None) -> dict:
    profile = load_profile(profile_path)
    sites = model_sites(profile)
    agent_rows = agent_sites() if agents is None else agents
    structural = check_structure(profile, sites, agent_rows)
    rows = profile.get("models") or {}
    catalogues = {"claude": claude_catalogue(home), "codex": codex_catalogue(home)}
    judged = classify(sites + [dict(a, effort=a["effort"]) for a in agent_rows],
                      rows, catalogues)
    return {"structural": structural, "verdicts": judged, "catalogues": catalogues,
            "rows": rows}


def publish_problems(result: dict) -> list[str]:
    problems = []
    bound_hosts = {v["host"] for v in result["verdicts"] if v["host"]}
    for host in sorted(bound_hosts):
        if result["catalogues"].get(host) is None:
            problems.append(f"no {host} catalogue on this machine, so its bindings cannot "
                            f"be judged — a release must not ship an unjudged binding")
    for v in result["verdicts"]:
        if v["verdict"] in REFUSING:
            tail = f", superseded by {v['successor']}" if v["successor"] else ""
            extra = f" ({v['note']})" if v["note"] else ""
            problems.append(f"{v['where']} binds {v['model']}{tail}{extra} — rebind, or "
                            f"record superseded_by on its [models] row")
    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--propose", action="store_true",
                    help="print the [models] rows that would acknowledge each stale binding")
    ap.add_argument("--publish-guard", action="store_true",
                    help="refuse (exit 1) a release carrying a superseded or invalid binding")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--fixture-home", help="read catalogues from this HOME instead (controls)")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    home = pathlib.Path(args.fixture_home) if args.fixture_home else pathlib.Path(os.path.expanduser("~"))
    try:
        result = run(home)
    except Problem as exc:
        print(f"FAIL: {exc}")
        return 1

    if result["structural"]:
        for line in result["structural"]:
            print(f"FAIL: {line}")
        print("MODEL BINDINGS FAILED")
        return 1

    for line in report(result["verdicts"], result["catalogues"]):
        print(line)

    if args.propose:
        rows = proposals(result["verdicts"], result["rows"])
        if rows:
            print("\nTo keep these bindings for now, paste into [models]:")
            for row in rows:
                print(f"  {row}")

    if args.publish_guard:
        bad = publish_problems(result)
        for line in bad:
            print(f"PUBLISH BLOCKED: {line}")
        return 1 if bad else 0
    return 0


# ---------------------------------------------------------------------------- controls

def _fixture_home(root: pathlib.Path, claude_models=None, codex_models=None) -> pathlib.Path:
    home = root / "home"
    if claude_models is not None:
        d = home / ".claude" / "cache" / "model-catalog"
        d.mkdir(parents=True, exist_ok=True)
        (d / "cat.json").write_text(json.dumps(
            {"fetchedAt": 2, "catalog": {"config": {"models": claude_models}}}))
        # A non-catalogue file sharing the directory must be skipped, not fail the read.
        (d / "published-floor.json").write_text(json.dumps({"floor": 1}))
    if codex_models is not None:
        d = home / ".codex"
        d.mkdir(parents=True, exist_ok=True)
        (d / "models_cache.json").write_text(json.dumps(
            {"fetched_at": "2026-01-01T00:00:00Z", "identity": "f" * 64,
             "models": codex_models}))
    home.mkdir(parents=True, exist_ok=True)
    return home


def _cl(mid, name, section, efforts=("low", "max")):
    return {"id": mid, "name": name, "section": section,
            "thinking": ({"type": "effort", "effort_options": [{"id": e} for e in efforts]}
                         if efforts else {"type": "none"})}


def _cx(slug, desc, priority, efforts=("low", "max"), visibility="list"):
    return {"slug": slug, "display_name": slug, "description": desc, "priority": priority,
            "visibility": visibility,
            "supported_reasoning_levels": [{"effort": e} for e in efforts]}


def self_test() -> int:
    passed = failed = 0

    def control(name, ok):
        nonlocal passed, failed
        if ok:
            passed += 1
        else:
            failed += 1
            print(f"  CONTROL FAILED: {name}")

    MAIN = [_cl("claude-opus-5-5", "Opus 5.5", "main"),
            _cl("claude-opus-5", "Opus 5", "overflow"),
            _cl("claude-haiku-4-5-20251001", "Haiku 4.5", "overflow", efforts=()),
            _cl("claude-haiku-5-5", "Haiku 5.5", "main")]
    CX = [_cx("gpt-6.1-sol", "Latest workhorse model.", 1),
          # Same role, current, and HIDDEN. It sorts before `gpt-6.1-sol`, so a successor
          # search that ignores visibility picks it — which is why this row exists.
          _cx("gpt-6-sol", "Current but unlisted workhorse.", 3, visibility="hide"),
          _cx("gpt-5.6-sol", "Older generation workhorse model.", 6),
          _cx("gpt-5.6-terra", "Older balanced model.", 8),
          _cx("gpt-reserve", "Hidden model.", 2, visibility="hide")]

    def judge(sites, rows, home, agents=()):
        cats = {"claude": claude_catalogue(home), "codex": codex_catalogue(home)}
        return classify(list(sites) + list(agents), rows, cats), cats

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        home = _fixture_home(root, MAIN, CX)

        # POSITIVE CONTROL FIRST: the mechanism fires on an input whose answer is known.
        v, _ = judge([{"where": "t.helm", "model": "claude-opus-5", "effort": "max"}], {}, home)
        control("an overflow model with a main sibling reads SUPERSEDED",
                v[0]["verdict"] == SUPERSEDED and v[0]["successor"] == "claude-opus-5-5")

        v, _ = judge([{"where": "t.frontier", "model": "claude-opus-5-5", "effort": "max"}], {}, home)
        control("a main model reads current", v[0]["verdict"] == CURRENT)

        v, _ = judge([{"where": "t.helm", "model": "claude-opus-5", "effort": "max"}],
                     {"claude-opus-5": {"superseded_by": "claude-opus-5-5"}}, home)
        control("an acknowledged binding reads ACKNOWLEDGED", v[0]["verdict"] == ACKNOWLEDGED)

        v, _ = judge([{"where": "t.helm", "model": "claude-opus-5", "effort": "max"}],
                     {"claude-opus-5": {"superseded_by": "claude-haiku-4-5-20251001"}}, home)
        control("acknowledging a successor that is itself superseded re-fires",
                v[0]["verdict"] == SUPERSEDED)

        v, _ = judge([{"where": "t.sweep", "model": "claude-haiku-4-5", "effort": None}], {}, home)
        control("a dated catalogue id matches the undated bound id",
                v[0]["verdict"] == SUPERSEDED and v[0]["successor"] == "claude-haiku-5-5")

        v, _ = judge([{"where": "t.sweep", "model": "claude-haiku-4-5", "effort": "xhigh"}], {}, home)
        control("an effort on a model that takes none reads EFFORT UNSUPPORTED",
                v[0]["verdict"] == EFFORT_BAD)

        v, _ = judge([{"where": "t.x", "model": "claude-opus-5-5", "effort": "medium"}], {}, home)
        control("an effort outside the model's own vocabulary reads EFFORT UNSUPPORTED",
                v[0]["verdict"] == EFFORT_BAD)

        v, _ = judge([{"where": "t.x", "model": "claude-opus-50", "effort": "max"}], {}, home)
        control("claude-opus-50 is not claude-opus-5", v[0]["verdict"] == ABSENT)

        v, _ = judge([{"where": "t.helm", "model": "gpt-5.6-sol", "effort": "max"}], {}, home)
        control("the Codex vendor prose decides the generation",
                v[0]["verdict"] == SUPERSEDED and v[0]["successor"] == "gpt-6.1-sol")
        control("a hidden same-role model is never proposed as the successor",
                v[0]["successor"] != "gpt-6-sol")

        v, _ = judge([{"where": "t.wh", "model": "gpt-5.6-terra", "effort": "max"}], {}, home)
        control("an old model with no same-role successor reads OLDER?, not SUPERSEDED",
                v[0]["verdict"] == OLDER and v[0]["successor"] is None)

        v, _ = judge([{"where": "t.x", "model": "llama-9", "effort": None}], {}, home)
        control("an id no catalogue answers for reads NOT JUDGED, never current",
                v[0]["verdict"] == UNJUDGED)

        # Every binding current -> nothing to report, and the denominator still counts.
        v, _ = judge([{"where": "a", "model": "claude-opus-5-5", "effort": "max"},
                      {"where": "b", "model": "gpt-6.1-sol", "effort": "max"}], {}, home)
        control("a correct tree produces no non-current verdict and judges every site",
                len(v) == 2 and all(x["verdict"] == CURRENT for x in v))

        bad_home = _fixture_home(root / "empty", None, None)
        v, cats = judge([{"where": "t.helm", "model": "claude-opus-5", "effort": "max"}], {}, bad_home)
        control("no catalogue reads NOT JUDGED rather than current",
                v[0]["verdict"] == UNJUDGED and cats["claude"] is None)
        control("publish refuses an unjudged host rather than passing it",
                any("cannot be judged" in p for p in publish_problems(
                    {"verdicts": v, "catalogues": cats})))

        # The refusal this whole mechanism exists for: a superseded binding must not ship,
        # an acknowledged one must, and a correct tree must raise nothing at all.
        stale, cats_ok = judge(
            [{"where": "t.helm", "model": "claude-opus-5", "effort": "max"}], {}, home)
        refusals = publish_problems({"verdicts": stale, "catalogues": cats_ok})
        control("publish refuses a superseded binding, naming the site and the successor",
                any("t.helm" in p and "claude-opus-5-5" in p for p in refusals))
        acked, _ = judge([{"where": "t.helm", "model": "claude-opus-5", "effort": "max"}],
                         {"claude-opus-5": {"superseded_by": "claude-opus-5-5"}}, home)
        control("publish allows an acknowledged binding",
                publish_problems({"verdicts": acked, "catalogues": cats_ok}) == [])
        fine, _ = judge([{"where": "t.f", "model": "claude-opus-5-5", "effort": "max"}],
                        {}, home)
        control("publish raises nothing on a tree whose bindings are current",
                publish_problems({"verdicts": fine, "catalogues": cats_ok}) == [])
        bad_effort, _ = judge(
            [{"where": "t.s", "model": "claude-haiku-4-5", "effort": "xhigh"}], {}, home)
        control("publish refuses an effort the bound model does not accept",
                any("t.s" in p for p in publish_problems(
                    {"verdicts": bad_effort, "catalogues": cats_ok})))

        # The report must not leak where it read, nor anything secret-shaped.
        v, cats = judge([{"where": "t.helm", "model": "claude-opus-5", "effort": "max"}], {}, home)
        text = "\n".join(report(v, cats) + proposals(v, {}))
        control("the report names no path and nothing secret-shaped",
                str(home) not in text and "/Users/" not in text
                and not SECRETISH.search(text))

        # --- structure, which is what actually blocks -------------------------------
        prof = {"models": {"m-1": {"display": "M"}},
                "hosts": {"claude": {"tiers": {"helm": {"model": "m-1", "effort": "max"}}}}}
        control("a profile whose rows and sites agree is structurally clean",
                check_structure(prof, model_sites(prof), []) == [])

        prof_missing = {"models": {"m-1": {"display": "M"}},
                        "hosts": {"claude": {"tiers": {"helm": {"model": "m-2"}}}}}
        control("a bound id with no [models] row fails by name",
                any("m-2" in p for p in check_structure(
                    prof_missing, model_sites(prof_missing), [])))

        prof_unused = {"models": {"m-1": {"display": "M"}, "m-9": {"display": "N"}},
                       "hosts": {"claude": {"tiers": {"helm": {"model": "m-1"}}}}}
        control("a [models] row nothing names fails by name",
                any("m-9" in p for p in check_structure(
                    prof_unused, model_sites(prof_unused), [])))

        prof_ack = {"models": {"m-1": {"display": "M", "superseded_by": "m-nope"}},
                    "hosts": {"claude": {"tiers": {"helm": {"model": "m-1"}}}}}
        control("an acknowledgement naming an unknown successor fails by name",
                any("m-nope" in p for p in check_structure(
                    prof_ack, model_sites(prof_ack), [])))

        control("an agent file disagreeing with its tier fails by name",
                any("agents/helm.md" in p for p in check_structure(
                    prof, model_sites(prof),
                    [{"where": "claude/agents/helm.md", "tier": "helm",
                      "model": "m-other", "effort": "max"}])))
        control("an agent file disagreeing on effort alone fails",
                any("effort" in p for p in check_structure(
                    prof, model_sites(prof),
                    [{"where": "claude/agents/helm.md", "tier": "helm",
                      "model": "m-1", "effort": "low"}])))

        control("an empty profile cannot report clean",
                check_structure({}, [], []) != [])
        control("a [models] row without a display name fails by name",
                any("display name" in p for p in check_structure(
                    {"models": {"m-1": {}},
                     "hosts": {"claude": {"tiers": {"helm": {"model": "m-1"}}}}},
                    [{"where": "t", "model": "m-1", "effort": None}], [])))
        broken = root / "broken.toml"
        broken.write_text("this is not = valid = toml\n[")
        try:
            load_profile(broken)
            control("an unparseable profile raises rather than reading as empty", False)
        except Problem as exc:
            control("an unparseable profile raises rather than reading as empty",
                    "cannot parse" in str(exc))
        control("a profile with rows but no site cannot report clean",
                check_structure({"models": {"m-1": {"display": "M"}}}, [], []) != [])

        # A review row names a model outside the tier tables; the walk must see it.
        prof_preset = {"models": {"m-1": {"display": "M"}, "m-2": {"display": "N"}},
                       "hosts": {"claude": {"tiers": {"helm": {"model": "m-1"}}}},
                       "presets": {"p": {"review": {"hosts": {"claude": {
                           "methods": {"deep": {"model": "m-2", "effort": "ultra"}}}}}}}}
        found = {s["model"] for s in model_sites(prof_preset)}
        control("the walk finds a model named inside a preset review row",
                found == {"m-1", "m-2"})

        # `hosts.*.models` is a list of ids, and a row for one of them must still be required.
        prof_list = {"models": {"m-1": {"display": "M"}},
                     "hosts": {"claude": {"models": ["m-1", "m-3"],
                                          "tiers": {"helm": {"model": "m-1"}}}}}
        control("an id listed in hosts.*.models without a row fails by name",
                any("m-3" in p for p in check_structure(
                    prof_list, model_sites(prof_list), [])))

    total = passed + failed
    print(f"model-currency self-test: {passed}/{total} controls passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
