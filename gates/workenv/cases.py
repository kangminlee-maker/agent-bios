"""The case registry: what every test profile runs, and what each case drives.

`case-index.json` defines each case once; this module holds it against the plan, the test
catalog, the contracts and each case's scenario. It judges no acceptance and runs no case.

A profile's bound cases come from three places, each with one owner.

  atomic     the catalog's ids (`profiles.<P>.required_atomic_case_ids`). Meaning and
             prerequisites are the catalog's.
  bootstrap  the catalog's `bootstrap_cases`, bound to the profile's only family; the
             registry says what runs them.
  selected   `selects`: new cases, `<FAMILY>-<SUBJECT>-<POS|NEG>` defined once in `cases`, and
             catalog atomic cases a profile runs beyond its required ones, in a family it holds.
             SUBJECT is a contract id or a token naming what the case drives, so one case serves
             every profile whose scope it fits instead of being written once per profile.

A carried binding is one an accepted record already holds. It is kept verbatim, because its
record states its digest and any edit would make that record stale.

What a case drives is derived, never stated. Every atomic and new case has a scenario,
`gates/workenv/fixtures/scenarios/<id in lower case>/` (scenarios.py writes it from its spec):
its operations are those of the requests its steps submit or carry; its contracts are the owners
of those operations and of every record kind in it, B03 when its world kills a process, and
`runner` when a step names a runner situation; its fixtures are the scenario directory, the
generator and its schema, the runner's preflight cases for a runner step, the rule fixture of a
case that checks runtime rules (`rules`), and what else the row `reads` (text fixtures, the
entrance dispositions). A new case also names the catalog oracle it holds its profile to and what
it asserts. Its evidence class is derived as well: `observed` for a family the catalog marks as
requiring real evidence. A profile's family needs one bound case, not one of each polarity: the
required set is the happy path and the safety net, so a family may hold only one of them.

`covers` maps each open profile's node `done_when` items, in order, to the cases that realize
each: a case bound to that profile, or one of R0's runner cases, which hold what every node's
dispatch and acceptance go through. `elsewhere` names a contract the node implements that none of
its bound cases can drive, with the reason.

`check` fails by name on:
  - a registry the schema refuses, or a carried binding that no longer digests to its record
  - a bootstrap or atomic set that differs from the catalog's
  - a case without a scenario, or a scenario for no case or written for another
  - an oracle index, `reads` fixture or rule that does not resolve
  - a selection outside the profile's families, a case nobody selects, a selected id nobody
    defines
  - a profile whose case map the dated evaluator's own `binding_errors` refuses
  - an operation no case drives, and a runtime rule no case checks at a node that implements it
  - an implementation profile that joins no case to a predecessor that implements, one that
    joins a case it does not select or joins it to a node it does not depend on, and one that
    states nothing at all — the two profiles with no such predecessor say so with an empty list
  - a profile without its `covers`, a `done_when` item no bound case realizes, a node contract
    no bound case drives and `elsewhere` does not name, and an `elsewhere` its cases do drive

`binding` is what a profile's case binding is, in the evaluator's own shape. Its two
fingerprints move with what they name and nothing else: the adapter fingerprint with the driver
path, the command each family or bootstrap case runs, the bytes of every contract module and
record schema its cases drive (the runner's dated evaluator, regression suite and interface
schemas for `runner`), and the reader every contract is read through; the fixture fingerprint
with the bytes of every fixture its cases read, each example's expectation beside it, and the case
definitions themselves. An implementation, a host version or a unit test is in neither.

  python3 gates/workenv/cases.py            # check, and print each profile's bound counts
  python3 gates/workenv/cases.py --bindings # the case-bindings artifact P01 freezes
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import scenarios  # noqa: E402
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
# The plan kind whose nodes build product, and so can have a predecessor that built some.
IMPLEMENTATION = "implementation"
RUNNER_FIXTURES = "gates/workenv/fixtures/runner"
PREFLIGHT = f"{RUNNER_FIXTURES}/preflight.json"
RULE_FIXTURES = "gates/workenv/fixtures/rules"
SCENARIOS = "gates/workenv/fixtures/scenarios"
GENERATOR = ("gates/workenv/scenarios.py", "gates/workenv/scenario.schema.json")
# The contract whose fault points a scenario's world names.
FAULTS = "B03"
# The profile whose runner cases may realize any node's done_when item about dispatch.
QUALIFIER = "R0"
# A placeholder the case-map probe hands the evaluator: it asks only about the case map.
PROBE = "0" * 64
# What every contract is read through; a change here is a change to every contract.
READER = ("workenv/contracts/canonical.py", "workenv/contracts/schema.py",
          "workenv/contracts/records.py", "workenv/contracts/errors.py",
          "workenv/contracts/errors.json")
EXPECTATION = ".expect.json"


class CaseError(ValueError):
    """A registry this module cannot read, named."""


def scenario_dir(case: str) -> str:
    return f"{SCENARIOS}/{case.lower()}/"


def owners() -> tuple[dict[str, str], dict[str, str]]:
    """(operation -> contract, record kind -> contract), from the modules that declare them."""
    modules = contract_modules()
    return ({op: c for c, m in modules.items() for op in getattr(m, "OPERATIONS", ())},
            {kind: c for c, m in modules.items() for kind in getattr(m, "RECORD_KINDS", ())})


def derive(registry: dict, root: pathlib.Path = ROOT) -> tuple[dict[str, dict], list[str]]:
    """case -> {"operations", "contracts", "fixtures"} read from its scenario, and the problems
    that kept a case from having one."""
    by_operation, by_kind = owners()
    derived, problems = {}, []
    for row in registry["atomic"] + registry["cases"]:
        case = row["id"]
        path = root / scenario_dir(case) / scenarios.GENERATED
        if not path.is_file():
            problems.append(f"{case}: no scenario at {scenario_dir(case)}")
            continue
        built = json.loads(path.read_bytes())
        if built["case"] != case:
            problems.append(f"{case}: its scenario is written for {built['case']}")
            continue
        held = {r["name"]: r["record"] for r in built["records"]}
        sent = [name for step in built["steps"] if "request" in step
                for name in (step["request"], *step["carries"])]
        operations = {held[name]["operation"] for name in sent
                      if held[name].get("kind") == "operation_request"}
        runs = any("runner" in step for step in built["steps"])
        contracts = ({by_operation[op] for op in operations}
                     | {by_kind[r["kind"]] for r in held.values() if r.get("kind") in by_kind}
                     | ({FAULTS} if built.get("world", {}).get("faults") else set())
                     | ({RUNNER} if runs else set()))
        fixtures = ([scenario_dir(case), *GENERATOR] + ([PREFLIGHT] if runs else [])
                    + [f"{RULE_FIXTURES}/{rule.split('/')[1]}.json"
                       for rule in row.get("rules", [])]
                    + row.get("reads", []))
        derived[case] = {"operations": operations, "contracts": contracts, "fixtures": fixtures}
    return derived, problems


def implementation_predecessors(node: dict, nodes: dict[str, dict]) -> list[str]:
    """The nodes this one depends on that implement something."""
    return [name for name in node.get("depends_on", [])
            if nodes.get(name, {}).get("kind") == IMPLEMENTATION]


def joined_problems(rows: dict[str, dict], nodes: dict[str, dict]) -> list[str]:
    """A joined case is one an implementation profile runs against an accepted predecessor's
    real files rather than against anything stood in for it. Every implementation profile
    states its own either way, because a profile that says nothing and a profile with nothing
    to say read alike, and only one of them is correct."""
    found = []
    for identifier in sorted(nodes):
        node = nodes[identifier]
        if node["kind"] != IMPLEMENTATION:
            continue
        row = rows.get(node["test_profile"])
        if row is None:
            continue  # an unbound or miswritten profile is already reported by its own rule
        name, joined = node["test_profile"], row.get("joined")
        predecessors = implementation_predecessors(node, nodes)
        if joined is None:
            found.append(f"selects {name}: {identifier} implements something and the row states "
                         f"no joined cases, not even that it has none")
            continue
        if predecessors and not joined:
            found.append(f"selects {name}: {identifier} depends on {', '.join(predecessors)}, "
                         f"which implement, and no case is joined to any of them")
        if not predecessors and joined:
            found.append(f"selects {name}: {identifier} depends on no node that implements, and "
                         f"{len(joined)} case(s) are joined to one")
        for entry in joined:
            case, predecessor = entry["case"], entry["predecessor"]
            if case not in row["cases"]:
                found.append(f"selects {name}: {case} is joined and not selected")
            if predecessor not in predecessors:
                found.append(f"selects {name}: {case} is joined to {predecessor}, which "
                             f"{identifier} does not depend on as an implementation")
    return found


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
            found.update({case: atomic.get(case, family_of(case)) for case in row["cases"]})
    return found


def tracked_under(paths: list[str], fixture: str) -> list[str]:
    if fixture.endswith("/"):
        return [p for p in paths if p.startswith(fixture)]
    return [fixture] if fixture in paths else []


def check(registry: dict | None = None, root: pathlib.Path = ROOT,
          loaded: tuple | None = None, paths: list[str] | None = None,
          derived: dict[str, dict] | None = None) -> tuple[list[str], dict[str, str]]:
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

    if derived is None:
        derived, missing = derive(registry, root)
        problems.extend(missing)
    defined_cases = {row["id"] for row in registry["atomic"] + registry["cases"]}
    for written in sorted({p.split("/")[4] for p in paths if p.startswith(f"{SCENARIOS}/")}):
        if written.upper() not in defined_cases:
            problems.append(f"scenario {written}: no case is defined for it")
    driven: set[str] = set()
    for case, drives in derived.items():
        driven.update(drives["operations"])
        for fixture in drives["fixtures"]:
            if not tracked_under(paths, fixture):
                problems.append(f"{case}: fixture {fixture} matches no tracked file")
    for row in registry["cases"]:
        case, family = row["id"], family_of(row["id"])
        if family not in families:
            problems.append(f"{case}: family {family} is not in the catalog")
        elif row["oracle"] >= len(families[family]["oracles"]):
            problems.append(f"{case}: {family} has no oracle {row['oracle']}")
        for rule in row.get("rules", []):
            if rule not in rules:
                problems.append(f"{case}: rule {rule} is declared by no contract module")

    defined = {row["id"]: family_of(row["id"]) for row in registry["cases"]}
    defined.update({case: atomic[case] for case in stated_atomic if case in atomic})
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
            elif defined[case] not in profiles[name]["family_ids"]:
                problems.append(f"selects {name}: {case} is outside its families")
    for case in sorted({row["id"] for row in registry["cases"]} - set(selected)):
        problems.append(f"{case}: defined and selected by no profile")
    problems.extend(joined_problems({row["profile"]: row for row in registry["selects"]}, nodes))

    all_operations = {op for module in modules.values() for op in getattr(module, "OPERATIONS", ())}
    for operation in sorted(all_operations - driven):
        problems.append(f"operation {operation}: no case drives it")
    checked: dict[str, list[str]] = {}
    for row in registry["cases"]:
        for rule in row.get("rules", []):
            checked.setdefault(rule, []).append(row["id"])
    for rule in sorted(set(rules) - set(checked)):
        problems.append(f"rule {rule}: no case checks it")
    for rule, case in sorted((rule, case) for rule, held in checked.items() for case in held):
        contract = rule.split("/")[0]
        implementers = {n["test_profile"] for n in nodes.values()
                        if contract in n.get("contracts", [])}
        if not selected.get(case, set()) & implementers:
            problems.append(f"rule {rule}: {case} is selected by no profile whose node "
                            f"implements {contract}")

    problems.extend(coverage(registry, catalog, nodes, open_profiles, derived))

    report = {}
    for name in open_profiles:
        bound = case_map(registry, catalog, name)
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


def coverage(registry: dict, catalog: dict, nodes: dict, open_profiles: list[str],
             derived: dict[str, dict]) -> list[str]:
    """Each open profile's done_when items realized by its cases, and its node's contracts
    driven by them or named elsewhere with a reason."""
    problems = []
    by_operation = owners()[0]
    rows = {}
    for row in registry["covers"]:
        if row["profile"] in rows:
            problems.append(f"covers {row['profile']}: stated twice")
        rows[row["profile"]] = row
    for name in sorted(set(rows) - set(open_profiles)):
        problems.append(f"covers {name}: not a profile the registry binds")
    qualifier = set(case_map(registry, catalog, QUALIFIER)) if QUALIFIER in open_profiles \
        else set()
    for name in open_profiles:
        node = next((n for n in nodes.values() if n.get("test_profile") == name), None)
        if node is None:
            continue
        if name not in rows:
            problems.append(f"covers {name}: no row maps its done_when items")
            continue
        bound = set(case_map(registry, catalog, name))
        items = rows[name]["done_when"]
        if len(items) != len(node.get("done_when", [])):
            problems.append(f"covers {name}: {len(items)} items for "
                            f"{len(node.get('done_when', []))} done_when items")
        for index, realized in enumerate(items):
            for case in realized:
                if case not in bound and case not in qualifier:
                    problems.append(f"covers {name} done_when[{index}]: {case} is bound to "
                                    f"neither {name} nor {QUALIFIER}")
        drives = {by_operation[op] for case in bound for op in derived.get(case, {}).get(
            "operations", ())}
        elsewhere = {row["contract"]: row["reason"] for row in rows[name].get("elsewhere", [])}
        for contract in node.get("contracts", []):
            if contract not in drives and contract not in elsewhere:
                problems.append(f"covers {name}: no bound case drives {contract}")
        for contract in elsewhere:
            if contract not in node.get("contracts", []):
                problems.append(f"covers {name}: elsewhere names {contract}, which "
                                f"{node['id']} does not implement")
            elif contract in drives:
                problems.append(f"covers {name}: elsewhere names {contract}, which a bound "
                                f"case drives")
    return problems


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
            root: pathlib.Path = ROOT, paths: list[str] | None = None,
            derived: dict[str, dict] | None = None) -> dict:
    """The case binding for one profile, in the shape the dated evaluator reads."""
    plan, catalog, evaluator = loaded or bundle(root)
    paths = subjects.tracked(root) if paths is None else paths
    for row in registry["carried"]:
        if row["profile"] == profile:
            return carried_binding(row)

    def sha(path: str) -> str:
        return hashlib.sha256((root / path).read_bytes()).hexdigest()

    bound = case_map(registry, catalog, profile)
    derived = derive(registry, root)[0] if derived is None else derived
    rows = {row["id"]: row for key in ("bootstrap", "atomic", "cases") for row in registry[key]}
    families = {f["id"]: f for f in catalog["cases"]}
    commands, fixtures, used = {}, {}, set()
    for case, family in sorted(bound.items()):
        row = rows[case]
        drives = derived.get(case, {"contracts": set(), "fixtures": []})
        used.update(drives["contracts"])
        if "command" in row:
            commands[case] = row["command"]
        else:
            fill = {"<conformance-driver>": registry["driver"], "<frozen-profile-id>": profile}
            template = families[family]["command_template"]
            commands[family] = [fill.get(part, part) for part in template]
        for fixture in drives["fixtures"]:
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


def bindings(registry: dict | None = None, loaded: tuple | None = None,
             root: pathlib.Path = ROOT, paths: list[str] | None = None) -> dict:
    """Every profile's case binding, in the shape the dated evaluator reads.

    P01 freezes this as its `case-bindings` artifact, and the evaluator holds the artifact
    against the bindings the run states, so both come from here rather than from two
    derivations that agree until one of them moves.
    """
    registry = load() if registry is None else registry
    loaded = bundle(root) if loaded is None else loaded
    paths = subjects.tracked(root) if paths is None else paths
    profiles = sorted({node["test_profile"] for node in loaded[0]["nodes"]})
    return {"bindings": {name: binding(registry, name, loaded=loaded, root=root, paths=paths)
                         for name in profiles}}


def main(argv: list[str]) -> int:
    if argv == ["--bindings"]:
        print(json.dumps(bindings(), ensure_ascii=False, sort_keys=True))
        return 0
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
