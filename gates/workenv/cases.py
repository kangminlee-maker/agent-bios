"""The case registry: what every test profile runs, and what each case drives.

`case-index.json` defines each case once; this module holds it against the plan, the test
catalog and the contracts. It judges no acceptance and runs no case.

A profile's bound cases come from three places, each with one owner.

  atomic     the catalog's ids (`profiles.<P>.required_atomic_case_ids`). Meaning and
             prerequisites are the catalog's; the registry adds what each drives and reads.
  bootstrap  the catalog's `bootstrap_cases`, bound to the profile's only family; the
             registry says what runs them.
  new        `<FAMILY>-<SUBJECT>-<POS|NEG>`, defined once in `cases` and selected in `selects`.
             SUBJECT is a contract id or a token naming what the case drives, so one case
             serves every profile whose scope it fits instead of being written once per profile.

A carried binding is one an accepted record already holds. It is kept verbatim, because its
record states its digest and any edit would make that record stale.

A case names the adapter contracts it drives (a contract module's CONTRACT, or `runner` for
the development runner's preflight interface), the closed operation names it submits, and its
fixtures. A new case also names the catalog oracle it holds its profile to and what it asserts;
it may name a runtime rule a contract module declares, which it checks over what the owner
writes. Evidence class and polarity are derived, never stated: `observed` for a family the
catalog marks as requiring real evidence, polarity from the id's suffix, and both polarities for
an atomic case, whose catalog entry states a positive and a negative.

`check` fails by name on:
  - a registry the schema refuses, or a carried binding that no longer digests to its record
  - a bootstrap or atomic set that differs from the catalog's
  - an oracle index, contract, operation, fixture or rule that does not resolve
  - a selection outside the profile's families, a case nobody selects, a selected id nobody
    defines
  - a (profile, family) pair without a positive and a negative
  - a profile whose case map the dated evaluator's own `binding_errors` refuses
  - an operation no case drives, and a runtime rule no case checks at a node that implements it

`binding` is what a profile's case binding is, in the evaluator's own shape. Its two
fingerprints move with what they name and nothing else: the adapter fingerprint with the driver
path, the command each family or bootstrap case runs, the bytes of every contract module and
record schema its cases drive (the runner's dated evaluator and regression suite for `runner`),
and the reader every contract is read through; the fixture fingerprint with the bytes of every
fixture its cases read, each example's expectation beside it, and the case definitions
themselves. An implementation, a host version or a unit test is in neither.

  python3 gates/workenv/cases.py            # check, and print each profile's bound counts
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import subjects  # noqa: E402
from workenv.contracts import canonical, errors, examples, records  # noqa: E402
from workenv.contracts.schema import load_schema  # noqa: E402

ROOT = subjects.ROOT
REGISTRY = pathlib.Path(__file__).with_name("case-index.json")
SCHEMA = pathlib.Path(__file__).with_name("case-index.schema.json")
# The development runner has no contract module: its interface is the dated evaluator's run
# file, fixed by the plan bundle, and the invocation, packet, worker result and report the
# schemas beside its preflight cases state.
RUNNER = "runner"
RUNNER_FIXTURES = "gates/workenv/fixtures/runner"
POSITIVE, NEGATIVE = "positive", "negative"
# A placeholder the case-map probe hands the evaluator: it asks only about the case map.
PROBE = "0" * 64
# What every contract is read through; a change here is a change to every contract.
READER = ("workenv/contracts/canonical.py", "workenv/contracts/schema.py",
          "workenv/contracts/records.py", "workenv/contracts/errors.py",
          "workenv/contracts/errors.json")
EXPECTATION = ".expect.json"


class CaseError(ValueError):
    """A registry this module cannot read, named."""


def load(path: pathlib.Path = REGISTRY) -> dict:
    registry = canonical.parse(path.read_bytes())
    schema = load_schema(canonical.parse(SCHEMA.read_bytes()))
    found = schema.validate(registry)
    if found:
        raise CaseError("; ".join(f"{v.code} at {v.pointer or '/'}" for v in found))
    return registry


def bundle(root: pathlib.Path = ROOT) -> tuple[dict, dict, object]:
    """(plan, catalog, dated evaluator module) — the plan CURRENT.md selects and what it names."""
    plan = subjects.plan(root)
    catalog = json.loads((root / "design/knowledge-and-history" / plan["test_catalog"])
                         .read_bytes())
    spec = importlib.util.spec_from_file_location(
        "dated_evaluator", root / "design/knowledge-and-history" / plan["validator"])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return plan, catalog, module


def contract_modules() -> dict[str, object]:
    return {m.CONTRACT: m for m in errors.OWNERS if hasattr(m, "CONTRACT")}


def runtime_rules() -> dict[str, str]:
    """`Cxx/<name>` -> what the rule says, for every rule a contract module declares."""
    return {f"{contract}/{name}": meaning for contract, module in contract_modules().items()
            for name, meaning in getattr(module, "RUNTIME_RULES", {}).items()}


def family_of(case_id: str) -> str:
    return case_id.split("-", 1)[0]


def polarities(case_id: str, atomic: set[str]) -> set[str]:
    if case_id in atomic:
        return {POSITIVE, NEGATIVE}
    if case_id.endswith(("-POS", "-positive")):
        return {POSITIVE}
    if case_id.endswith(("-NEG", "-negative")):
        return {NEGATIVE}
    return set()


def carried_binding(row: dict) -> dict:
    """The binding a carried row stands for, rebuilt field for field."""
    return {"profile_digest": row["profile_digest"],
            "cases": {case["id"]: case["family"] for case in row["cases"]},
            "adapter_fingerprint": row["adapter_fingerprint"],
            "fixture_fingerprint": row["fixture_fingerprint"]}


def case_map(registry: dict, catalog: dict, profile: str) -> dict[str, str]:
    """case id -> family for one profile that is not carried."""
    wanted = catalog["profiles"][profile]
    atomic = {a["id"]: f["id"] for f in catalog["cases"] for a in f.get("atomic_cases", [])}
    found = {case: atomic[case] for case in wanted.get("required_atomic_case_ids", [])
             if case in atomic}
    families = wanted["family_ids"]
    for case in wanted.get("bootstrap_cases", []):
        if len(families) == 1:
            found[case] = families[0]
    for row in registry["selects"]:
        if row["profile"] == profile:
            found.update({case: family_of(case) for case in row["cases"]})
    return found


def tracked_under(paths: list[str], fixture: str) -> list[str]:
    if fixture.endswith("/"):
        return [p for p in paths if p.startswith(fixture)]
    return [fixture] if fixture in paths else []


def check(registry: dict | None = None, root: pathlib.Path = ROOT,
          loaded: tuple | None = None, paths: list[str] | None = None,
          ) -> tuple[list[str], dict[str, str]]:
    """(problems, one report line per profile)."""
    problems: list[str] = []
    if registry is None:
        try:
            registry = load()
        except (CaseError, canonical.CanonicalError) as error:
            return [f"the registry is unreadable: {error}"], {}
    plan, catalog, evaluator = loaded or bundle(root)
    paths = subjects.tracked(root) if paths is None else paths
    profiles = catalog["profiles"]
    families = {f["id"]: f for f in catalog["cases"]}
    atomic = {a["id"]: f["id"] for f in catalog["cases"] for a in f.get("atomic_cases", [])}
    nodes = {n["id"]: n for n in plan["nodes"]}
    modules = contract_modules()
    rules = runtime_rules()
    if not profiles or not atomic or not nodes:
        return ["the plan or catalog holds nothing to bind"], {}

    carried = {row["profile"]: row for row in registry["carried"]}
    for name, row in carried.items():
        if name not in profiles:
            problems.append(f"carried {name}: no such profile in the catalog")
            continue
        binding = carried_binding(row)
        if evaluator.digest(binding) != row["binding_digest"]:
            problems.append(f"carried {name}: the binding no longer digests to the "
                            f"binding_digest its record states")
        for error in evaluator.binding_errors(profiles[name], binding, atomic):
            problems.append(f"carried {name}: the evaluator refuses it: {error}")

    open_profiles = sorted(set(profiles) - set(carried))
    wanted_bootstrap = {case: name for name in open_profiles
                        for case in profiles[name].get("bootstrap_cases", [])}
    stated_bootstrap = {row["id"] for row in registry["bootstrap"]}
    for case in sorted(set(wanted_bootstrap) - stated_bootstrap):
        problems.append(f"bootstrap {case}: the catalog names it and nothing runs it")
    for case in sorted(stated_bootstrap - set(wanted_bootstrap)):
        problems.append(f"bootstrap {case}: no open profile's catalog entry names it")
    for case, name in sorted(wanted_bootstrap.items()):
        if len(profiles[name]["family_ids"]) != 1:
            problems.append(f"bootstrap {case}: {name} has more than one family to bind it to")

    stated_atomic = {row["id"] for row in registry["atomic"]}
    for case in sorted(set(atomic) - stated_atomic):
        problems.append(f"atomic {case}: the catalog defines it and the registry binds nothing")
    for case in sorted(stated_atomic - set(atomic)):
        problems.append(f"atomic {case}: the catalog defines no such case")

    driven: set[str] = set()
    for row in registry["atomic"] + registry["cases"]:
        case = row["id"]
        named = row["contracts"]
        for contract in named:
            if contract != RUNNER and contract not in modules:
                problems.append(f"{case}: contract {contract} is no contract module's")
        owned = {op for contract in named if contract in modules
                 for op in getattr(modules[contract], "OPERATIONS", ())}
        for operation in row["operations"]:
            if operation not in owned:
                problems.append(f"{case}: operation {operation} belongs to none of "
                                f"{', '.join(named)}")
        driven.update(row["operations"])
        for fixture in row["fixtures"]:
            if not tracked_under(paths, fixture):
                problems.append(f"{case}: fixture {fixture} matches no tracked file")
    for row in registry["cases"]:
        case, family = row["id"], family_of(row["id"])
        if family not in families:
            problems.append(f"{case}: family {family} is not in the catalog")
        elif row["oracle"] >= len(families[family]["oracles"]):
            problems.append(f"{case}: {family} has no oracle {row['oracle']}")
        if "rule" in row and row["rule"] not in rules:
            problems.append(f"{case}: rule {row['rule']} is declared by no contract module")

    defined = {row["id"] for row in registry["cases"]}
    selected: dict[str, set[str]] = {}
    seen_profiles: set[str] = set()
    for row in registry["selects"]:
        name = row["profile"]
        if name in seen_profiles:
            problems.append(f"selects {name}: stated twice")
        seen_profiles.add(name)
        if name not in profiles or name in carried:
            problems.append(f"selects {name}: not a profile the registry binds")
            continue
        for case in row["cases"]:
            selected.setdefault(case, set()).add(name)
            if case not in defined:
                problems.append(f"selects {name}: {case} is defined nowhere")
            elif family_of(case) not in profiles[name]["family_ids"]:
                problems.append(f"selects {name}: {case} is outside its families")
    for case in sorted(defined - set(selected)):
        problems.append(f"{case}: defined and selected by no profile")

    all_operations = {op for module in modules.values() for op in getattr(module, "OPERATIONS", ())}
    for operation in sorted(all_operations - driven):
        problems.append(f"operation {operation}: no case drives it")
    checked = {row["rule"]: row["id"] for row in registry["cases"] if "rule" in row}
    for rule in sorted(set(rules) - set(checked)):
        problems.append(f"rule {rule}: no case checks it")
    for rule, case in sorted(checked.items()):
        contract = rule.split("/")[0]
        implementers = {n["test_profile"] for n in nodes.values()
                        if contract in n.get("contracts", [])}
        if not selected.get(case, set()) & implementers:
            problems.append(f"rule {rule}: {case} is selected by no profile whose node "
                            f"implements {contract}")

    report = {}
    for name in open_profiles:
        bound = case_map(registry, catalog, name)
        for family in profiles[name]["family_ids"]:
            held = set().union(*(polarities(c, set(atomic)) for c, f in bound.items()
                                 if f == family))
            for polarity in (POSITIVE, NEGATIVE):
                if polarity not in held:
                    problems.append(f"{name} {family}: no {polarity} case")
        binding = {"profile_digest": evaluator.digest(profiles[name]), "cases": bound,
                   "adapter_fingerprint": PROBE, "fixture_fingerprint": PROBE}
        for error in evaluator.binding_errors(profiles[name], binding, atomic):
            problems.append(f"{name}: the evaluator refuses its case map: {error}")
        observed = sum(1 for f in bound.values()
                       if families.get(f, {}).get("requires_real_evidence"))
        report[name] = (f"{len(bound)} cases over {len(profiles[name]['family_ids'])} "
                        f"families, {observed} observed")
    for name in sorted(carried):
        report[name] = f"carried, {len(carried[name]['cases'])} cases"
    return problems, report


def contract_files(contract: str, plan: dict) -> list[str]:
    """The files an adapter contract is: a module and its record schemas, or for the runner the
    dated evaluator and regression suite the plan binds and its interface schemas."""
    if contract == RUNNER:
        return ([f"design/knowledge-and-history/{plan[key]}"
                 for key in ("validator", "regression_tests")]
                + sorted(f"{RUNNER_FIXTURES}/{path.name}"
                         for path in (ROOT / RUNNER_FIXTURES).glob("*.schema.json")))
    module = contract_modules()[contract]
    kinds = records.registry(examples.load_schemas())
    schemas = sorted(identifier for kind in module.RECORD_KINDS
                     for identifier in kinds[kind].values())
    return ([f"workenv/contracts/{module.__name__.rsplit('.', 1)[-1]}.py"]
            + [f"workenv/contracts/schemas/{identifier}.schema.json" for identifier in schemas])


def binding(registry: dict, profile: str, loaded: tuple | None = None,
            root: pathlib.Path = ROOT, paths: list[str] | None = None) -> dict:
    """The case binding for one profile, in the shape the dated evaluator reads."""
    plan, catalog, evaluator = loaded or bundle(root)
    paths = subjects.tracked(root) if paths is None else paths
    for row in registry["carried"]:
        if row["profile"] == profile:
            return carried_binding(row)

    def sha(path: str) -> str:
        return hashlib.sha256((root / path).read_bytes()).hexdigest()

    bound = case_map(registry, catalog, profile)
    rows = {row["id"]: row for key in ("bootstrap", "atomic", "cases") for row in registry[key]}
    families = {f["id"]: f for f in catalog["cases"]}
    commands, fixtures, used = {}, {}, set()
    for case, family in sorted(bound.items()):
        row = rows[case]
        used.update(row.get("contracts", []))
        if "command" in row:
            commands[case] = row["command"]
        else:
            fill = {"<conformance-driver>": registry["driver"], "<frozen-profile-id>": profile}
            template = families[family]["command_template"]
            commands[family] = [fill.get(part, part) for part in template]
        for fixture in row.get("fixtures", []):
            for path in tracked_under(paths, fixture):
                fixtures[path] = sha(path)
                beside = path[:-len(".json")] + EXPECTATION if path.endswith(".json") else None
                if beside and not path.endswith(EXPECTATION) and beside in paths:
                    fixtures[beside] = sha(beside)
    ran = {part for argv in commands.values() for part in argv if part in paths}
    adapter = {"driver": registry["driver"], "commands": commands,
               "ran": {path: sha(path) for path in sorted(ran)},
               "contracts": {contract: {path: sha(path) for path in contract_files(contract, plan)}
                             for contract in sorted(used)},
               "reader": {path: sha(path) for path in READER}}
    fixture = {"files": fixtures, "cases": {case: rows[case] for case in sorted(bound)}}
    return {"profile_digest": evaluator.digest(catalog["profiles"][profile]), "cases": bound,
            "adapter_fingerprint": evaluator.digest(adapter),
            "fixture_fingerprint": evaluator.digest(fixture)}


def main(argv: list[str]) -> int:
    if argv:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    problems, report = check()
    for name, line in sorted(report.items()):
        print(f"{name:4} {line}")
    for problem in problems:
        print(f"FAIL {problem}")
    print("CASES OK" if not problems else f"CASES FAIL ({len(problems)})")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
