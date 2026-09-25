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
  inherited  an implementation or verification node also runs every case the registry selects
             for an implementation or package node it depends on, directly or through another.
             A stage is selected once, where it is introduced, and every later stage runs it
             again on the bytes that exist then; the catalog states the same inheritance for
             atomic cases by listing them, because the evaluator reads the catalog alone.

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
  - an operation no case drives, and a runtime rule no case checks: a rule counts for a case
    whose scenario drives the rule's contract, bound at a profile whose scope holds the node that
    serves one of the case's steps of that contract, so code of the contract answers it there
  - a case bound where it cannot pass: a step served in the profile's scope expects a refusal
    that only a layer states, and that layer is not in the scope
  - a profile without its `covers`, a `done_when` item no bound case realizes, a node contract
    no bound case drives and `elsewhere` does not name, and an `elsewhere` its cases do drive
  - a serving table (`conformance/serving.json`, which node answers each operation and at which
    entry, and the layers every request passes through) that misses a declared operation, names
    a node that does not implement its contract, or an entry outside that node's owned paths, or
    whose layer states a refusal its contract does not declare
  - a step addressing a request no step of its scenario submits
  - a profile binding a case on which no code in its scope runs, and a `given` row that no
    longer matches a step the driver answers at every profile binding its case

Every other step the driver answers at every profile binding its case is printed as a NOTE: it
is either setup, or the point of a case that must be bound at a later profile too
(D-20260924-f80d5c), and telling those apart is a judgement.

`binding` is what a profile's case binding is, in the evaluator's own shape. Its two
fingerprints move with what they name and nothing else: the adapter fingerprint with the bytes of
the driver and every command each family or bootstrap case runs, the bytes of every contract
module and record schema its cases drive (the runner's dated evaluator, regression suite and
interface schemas for `runner`), and the reader every contract is read through, and — for a
profile whose cases the driver runs — the driver's core, each feature module its cases use (null
until written), the layers in its scope and the serving rows its steps reach; the fixture
fingerprint with the bytes of every fixture its cases read, each example's expectation beside
it, and the case definitions themselves. An implementation, a host version or a unit test is in
neither: an implementation is measured in its node's subject when that node runs.

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
# Who runs an earlier node's selected cases again, and whose are run again.
INHERITS = ("implementation", "verification")
INHERITED = ("implementation", "package")
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
# Which node answers each operation, and at which entry: the adapter selectors P01 freezes.
SERVING = "gates/workenv/conformance/serving.json"
# What decides a family case's verdict besides the driver path, so it is in the adapter
# fingerprint of every profile whose cases the driver runs: the rule oracles.
CORE = ("gates/workenv/conformance/rules.py",)
FEATURES = "gates/workenv/conformance/features"
# What a scenario states beyond one answered step. Each is a module under FEATURES; a case uses
# the ones its scenario does, and a profile's fingerprint holds only those.
WORLD_FEATURES = ("processes", "clock", "partitions", "faults", "during")
STEP_FEATURES = ("replays", "receipt_of", "runner", "route")
SIGNING = "signing"
# A step the driver exercises itself rather than an owner, which is never given.
DRIVER = "driver"
# The id prefix an addressed operation targets: a request.
ADDRESSED_TARGET = "req"
# The layer that holds every request and result, and so answers an addressed operation when it
# is in scope (D-20260925-3f21bb).
JOURNAL = "journal"


class CaseError(ValueError):
    """A registry this module cannot read, named."""


def scenario_dir(case: str) -> str:
    return f"{SCENARIOS}/{case.lower()}/"


def owners() -> tuple[dict[str, str], dict[str, str]]:
    """(operation -> contract, record kind -> contract), from the modules that declare them."""
    modules = contract_modules()
    return ({op: c for c, m in modules.items() for op in getattr(m, "OPERATIONS", ())},
            {kind: c for c, m in modules.items() for kind in getattr(m, "RECORD_KINDS", ())})


def load_serving(root: pathlib.Path = ROOT) -> dict:
    return json.loads((root / SERVING).read_bytes())


def module_files(module: str) -> tuple[str, str]:
    """The two paths a dotted module can live at: a file, or a package's __init__.py."""
    base = module.replace(".", "/")
    return f"{base}.py", f"{base}/__init__.py"


def scope(node: str, nodes: dict[str, dict]) -> set[str]:
    """The node and every node it depends on, directly or through another (D-20260924-3bb074)."""
    found, pending = {node}, list(nodes.get(node, {}).get("depends_on", []))
    while pending:
        name = pending.pop()
        if name not in found:
            found.add(name)
            pending.extend(nodes.get(name, {}).get("depends_on", []))
    return found


def features_of(built: dict) -> set[str]:
    """The features a generated scenario uses beyond answered steps."""
    world = built.get("world", {})
    found = {name for name in WORLD_FEATURES if world.get(name)}
    found |= {f"event_{event['kind']}" for event in world.get("events", [])}
    found |= {name for step in built["steps"] for name in STEP_FEATURES if name in step}

    def keyed(value, key: str) -> bool:
        if isinstance(value, dict):
            return key in value or any(keyed(v, key) for v in value.values())
        if isinstance(value, list):
            return any(keyed(v, key) for v in value)
        return False
    if any(keyed(r["record"], "sshsig") or keyed(r["record"], "public_key")
           for r in built["records"]):
        found.add(SIGNING)
    return found


def served_steps(built: dict, serving: dict) -> tuple[list[dict], list[str]]:
    """Each step's name and the node that answers it, and the steps that cannot be routed.

    A step without a request (a runner situation) is the driver's. An addressed operation is
    answered by the node serving the operation of the step whose request carries the id it
    targets, wherever that step sits (D-20260924-7e9a10)."""
    held = {r["name"]: r["record"] for r in built["records"]}
    rows = serving["operations"]
    by_request = {held[s["request"]].get("request_id"): held[s["request"]].get("operation")
                  for s in built["steps"] if "request" in s}
    steps, problems = [], []
    for step in built["steps"]:
        if "request" not in step:
            steps.append({"name": step["name"], "node": DRIVER})
            continue
        operation = held[step["request"]].get("operation")
        row = rows.get(operation, {})
        if row.get("addressed"):
            target = held[step["request"]].get("target", {}).get("resource_id")
            addressed = by_request.get(target)
            if addressed not in rows or rows[addressed].get("addressed"):
                problems.append(f"step {step['name']}: {operation} addresses {target}, and no "
                                f"step of this scenario submits a request under that id")
                continue
            steps.append({"name": step["name"], "operation": operation,
                          "node": rows[addressed]["node"], "addresses": addressed,
                          "expects": expects(held, step)})
            continue
        if "node" not in row:
            problems.append(f"step {step['name']}: {operation} has no serving row")
            continue
        steps.append({"name": step["name"], "operation": operation, "node": row["node"],
                      "expects": expects(held, step)})
    return steps, problems


def expects(held: dict[str, dict], step: dict) -> list[str]:
    """The refusal codes the step's stated result carries."""
    outcome = held.get(step.get("result"), {}).get("outcome", {})
    return sorted({gap["code"] for gap in outcome.get("material_gaps", []) if "code" in gap})


def serving_problems(serving: dict, plan: dict) -> list[str]:
    """The serving table held against the contracts and the plan. Whether an entry exists is
    not asked: a node that has not been built has not written it, and running a case that
    reaches it answers `blocked` by name."""
    by_operation = owners()[0]
    declared = scenarios.operations()
    nodes = {n["id"]: n for n in plan["nodes"]}
    rows = serving.get("operations", {})
    problems = [f"serving {operation}: the contracts declare it and no row serves it"
                for operation in sorted(set(by_operation) - set(rows))]
    problems += [f"serving {operation}: no contract declares it"
                 for operation in sorted(set(rows) - set(by_operation))]

    def held(where: str, node: str, entry: str, contract: str | None) -> None:
        row = nodes.get(node)
        if row is None or row["kind"] != IMPLEMENTATION:
            problems.append(f"serving {where}: {node} is not an implementation node")
            return
        if contract is not None and contract not in row.get("contracts", []):
            problems.append(f"serving {where}: {node} does not implement {contract}")
        module, _, name = entry.partition(":")
        owned = row.get("owned_paths", [])
        if not name or not any(path == own or (own.endswith("/") and path.startswith(own))
                               for path in module_files(module) for own in owned):
            problems.append(f"serving {where}: {entry} is not under {node}'s owned paths")

    for operation, row in sorted(rows.items()):
        if operation not in by_operation:
            continue
        if row.get("addressed"):
            if ADDRESSED_TARGET not in declared[operation]["targets"]:
                problems.append(f"serving {operation}: marked addressed and it targets no request")
            continue
        held(operation, row.get("node", "?"), row.get("entry", ""), by_operation[operation])
    names = [layer.get("name") for layer in serving.get("layers", [])]
    if JOURNAL not in names:
        problems.append(f"serving layers: no {JOURNAL} layer, so no one holds requests and results")
    for name in sorted({n for n in names if names.count(n) > 1}):
        problems.append(f"serving layers: {name} is stated twice")
    table = errors.table()
    for layer in serving.get("layers", []):
        held(f"layer {layer.get('name')}", layer.get("node", "?"), layer.get("entry", ""),
             layer.get("contract", "?"))
        for code in layer.get("states", []):
            if table.get(code, {}).get("owner", "").upper() != layer.get("contract"):
                problems.append(f"serving layer {layer.get('name')}: it states {code}, which "
                                f"{layer.get('contract')} does not declare")
    for node, entry in sorted(serving.get("places", {}).items()):
        held(f"places {node}", node, entry, None)
    for kind, row in sorted(serving.get("events", {}).items()):
        held(f"events {kind}", row.get("node", "?"), row.get("entry", ""), None)
    return problems


def answered_in(step: dict, reach: set[str], layers: dict[str, str]) -> bool:
    """Whether code in this scope, not the driver's stated answer, gives the step's answer: its
    serving node, or for an addressed operation the journal that holds the request."""
    if step["node"] == DRIVER or step["node"] in reach:
        return True
    return "addresses" in step and layers.get(JOURNAL) in reach


def unexercised(registry: dict, catalog: dict, nodes: dict[str, dict], open_profiles: list[str],
                derived: dict[str, dict], serving: dict) -> tuple[list[str], list[str]]:
    """(problems, disclosures) about given steps (D-20260924-f80d5c, D-20260925-3768a8).

    A problem: a profile binds a case on which no code in its scope runs, neither a step's
    serving node nor a layer, so running it there is evidence of nothing. A disclosure: a step
    whose answer is the driver's at every profile that binds its case, though a layer may still
    run on it; whether that step is setup or the point of its case is a judgement this does not
    make. A step the registry's `given` rows accept is not disclosed, and a row that accepts a
    step no longer answered by the driver everywhere, or a step or case that does not exist, is
    a problem: an exemption that outlived its reason would excuse whatever took its place."""
    accepted: dict[str, set[str]] = {}
    twice = []
    for row in registry.get("given", []):
        if row["case"] in accepted:
            twice.append(f"given {row['case']}: stated twice")
        accepted.setdefault(row["case"], set()).update(row["steps"])
    by_profile = {n["test_profile"]: n["id"] for n in nodes.values() if n.get("test_profile")}
    layers = {layer["name"]: layer["node"] for layer in serving.get("layers", [])}
    binders: dict[str, list[str]] = {}
    problems = twice
    for name in open_profiles:
        if name not in by_profile:
            continue
        reach = scope(by_profile[name], nodes)
        layered = any(node in reach for node in layers.values())
        for case in sorted(case_map(registry, catalog, name, nodes)):
            steps = derived.get(case, {}).get("steps")
            if not steps:
                continue
            binders.setdefault(case, []).append(name)
            if not layered and not any(answered_in(s, reach, layers) for s in steps):
                problems.append(f"{name}: {case} runs no code in its scope, neither a serving "
                                f"node nor a layer, so nothing in it is evidence there")
    disclosures = []
    for case, profiles in sorted(binders.items()):
        reaches = [scope(by_profile[p], nodes) for p in profiles]
        names = {step["name"] for step in derived[case]["steps"]}
        for step in derived[case]["steps"]:
            always = not any(answered_in(step, r, layers) for r in reaches)
            excused = step["name"] in accepted.get(case, set())
            if always and not excused:
                disclosures.append(f"{case} {step['name']} ({step['operation']}, served by "
                                   f"{step['node']}) is answered by the driver at every profile "
                                   f"that binds it: {', '.join(profiles)}")
            elif excused and not always:
                problems.append(f"given {case}: {step['name']} is answered by code at some "
                                f"profile that binds the case, so the row no longer excuses it")
        for missing in sorted(accepted.get(case, set()) - names):
            problems.append(f"given {case}: {missing} is not a step of its scenario")
    for case in sorted(set(accepted) - set(binders)):
        problems.append(f"given {case}: no profile binds a case by that id with a scenario")
    return problems, disclosures


def unpassable(registry: dict, catalog: dict, nodes: dict[str, dict], open_profiles: list[str],
               derived: dict[str, dict], serving: dict) -> list[str]:
    """A case bound where it cannot pass. A step served in the profile's scope is answered by
    code there, so a refusal it expects that only layers state can come from nowhere while none
    of them is in scope; a step the driver answers states whatever its result says."""
    stated: dict[str, list[dict]] = {}
    for layer in serving.get("layers", []):
        for code in layer.get("states", []):
            stated.setdefault(code, []).append(layer)
    layers = {layer["name"]: layer["node"] for layer in serving.get("layers", [])}
    by_profile = {n["test_profile"]: n["id"] for n in nodes.values() if n.get("test_profile")}
    problems = []
    for name in open_profiles:
        if name not in by_profile:
            continue
        reach = scope(by_profile[name], nodes)
        for case in sorted(case_map(registry, catalog, name, nodes)):
            for step in derived.get(case, {}).get("steps", []):
                if step["node"] == DRIVER or not answered_in(step, reach, layers):
                    continue
                for code in step.get("expects", []):
                    held = stated.get(code, [])
                    if held and not any(layer["node"] in reach for layer in held):
                        names = " and ".join(layer["name"] for layer in held)
                        where = ", ".join(layer["node"] for layer in held)
                        stated_by = (f"the {names} layer states, and {where} is not"
                                     if len(held) == 1 else
                                     f"the {names} layers state, and none of {where} is")
                        problems.append(f"{name}: {case} cannot pass here: {step['name']} expects "
                                        f"{code}, which only {stated_by} in its scope")
    return problems


def derive(registry: dict, root: pathlib.Path = ROOT,
           serving: dict | None = None) -> tuple[dict[str, dict], list[str]]:
    """case -> {"operations", "contracts", "fixtures", "features", "steps"} read from its
    scenario, and the problems that kept a case from having one. `steps` routes each step by the
    serving table under `root` unless one is handed in."""
    by_operation, by_kind = owners()
    serving = load_serving(root) if serving is None else serving
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
        steps, routing = served_steps(built, serving)
        problems.extend(f"{case}: {problem}" for problem in routing)
        derived[case] = {"operations": operations, "contracts": contracts, "fixtures": fixtures,
                         "features": features_of(built), "steps": steps}
    return derived, problems


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


def case_map(registry: dict, catalog: dict, profile: str,
             nodes: dict[str, dict]) -> dict[str, str]:
    """case id -> family for one profile that is not carried: its own cases, and the selected
    cases of every implementation or package node its node depends on when it inherits."""
    wanted = catalog["profiles"][profile]
    atomic = {a["id"]: f["id"] for f in catalog["cases"] for a in f.get("atomic_cases", [])}
    found = {case: atomic[case] for case in wanted.get("required_atomic_case_ids", [])
             if case in atomic}
    families = wanted["family_ids"]
    for case in wanted.get("bootstrap_cases", []):
        if len(families) == 1:
            found[case] = families[0]
    owner = next((n for n in nodes.values() if n.get("test_profile") == profile), None)
    selectors = {profile}
    if owner is not None and owner["kind"] in INHERITS:
        selectors |= {nodes[name]["test_profile"] for name in scope(owner["id"], nodes)
                      if nodes[name]["kind"] in INHERITED}
    for row in registry["selects"]:
        if row["profile"] in selectors:
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

    all_operations = {op for module in modules.values() for op in getattr(module, "OPERATIONS", ())}
    for operation in sorted(all_operations - driven):
        problems.append(f"operation {operation}: no case drives it")
    checked: dict[str, list[str]] = {}
    for row in registry["cases"]:
        for rule in row.get("rules", []):
            checked.setdefault(rule, []).append(row["id"])
    for rule in sorted(set(rules) - set(checked)):
        problems.append(f"rule {rule}: no case checks it")
    # A rule is checked by a case that drives its contract, where the case is bound at a
    # profile whose scope serves one of the case's steps of that contract: code of the contract
    # answers the step there. That a node in scope lists the contract is not enough, because
    # the node that serves the case's steps may be another one, and the contract freeze lists
    # every contract and implements none.
    serving = load_serving(root)
    layers = {layer["name"]: layer["node"] for layer in serving.get("layers", [])}
    by_operation = owners()[0]
    by_profile = {n["test_profile"]: n["id"] for n in nodes.values() if n.get("test_profile")}
    binders = {name: set(case_map(registry, catalog, name, nodes)) for name in open_profiles}
    for rule, case in sorted((rule, case) for rule, held in checked.items() for case in held):
        contract = rule.split("/")[0]
        if contract not in derived.get(case, {}).get("contracts", set()):
            problems.append(f"rule {rule}: {case} drives no operation or record of {contract}")
            continue
        steps = [step for step in derived[case]["steps"]
                 if step["node"] != DRIVER and by_operation.get(step["operation"]) == contract]
        if not any(answered_in(step, scope(by_profile[name], nodes), layers)
                   for name, bound in binders.items() if case in bound and name in by_profile
                   for step in steps):
            problems.append(f"rule {rule}: {case} is bound at no profile whose scope serves one "
                            f"of its {contract} steps")

    problems.extend(coverage(registry, catalog, nodes, open_profiles, derived))
    problems.extend(serving_problems(serving, plan))
    problems.extend(unexercised(registry, catalog, nodes, open_profiles, derived, serving)[0])
    problems.extend(unpassable(registry, catalog, nodes, open_profiles, derived, serving))

    report = {}
    for name in open_profiles:
        bound = case_map(registry, catalog, name, nodes)
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
    qualifier = set(case_map(registry, catalog, QUALIFIER, nodes)) if QUALIFIER in open_profiles \
        else set()
    for name in open_profiles:
        node = next((n for n in nodes.values() if n.get("test_profile") == name), None)
        if node is None:
            continue
        if name not in rows:
            problems.append(f"covers {name}: no row maps its done_when items")
            continue
        bound = set(case_map(registry, catalog, name, nodes))
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


def executed(plan: dict, profile: str, bound: dict[str, str], derived: dict[str, dict],
             serving: dict, paths: list[str], sha) -> dict:
    """What the driver executes a profile's family cases with, beyond its own path: the core,
    each feature module its cases use (null until it is written, which is itself a fact the
    fingerprint holds), and the serving rows its steps reach, each row by its content. So adding
    a feature moves only the profiles that use it, and a row edit moves only the profiles whose
    steps reach that row."""
    nodes = {n["id"]: n for n in plan["nodes"]}
    node = next((n["id"] for n in plan["nodes"] if n.get("test_profile") == profile), None)
    reach = scope(node, nodes) if node else set()
    features, operations, gives = set(), {}, False
    for case in bound:
        drives = derived.get(case, {})
        features |= drives.get("features", set())
        for step in drives.get("steps", []):
            if step["node"] == DRIVER:
                continue
            for operation in (step["operation"], step.get("addresses")):
                if operation:
                    operations[operation] = serving["operations"][operation]
            gives = gives or step["node"] not in reach
    events = {kind: serving["events"][kind] for kind in sorted(
        f[len("event_"):] for f in features if f.startswith("event_"))
        if kind in serving.get("events", {})}
    places = {name: entry for name, entry in sorted(serving.get("places", {}).items())
              if gives and name in reach}
    modules = {name: f"{FEATURES}/{name}.py" for name in sorted(features)}
    layers = [layer for layer in serving.get("layers", []) if layer["node"] in reach]
    return {"core": {path: sha(path) for path in CORE}, "layers": layers,
            "features": {name: sha(path) if path in paths else None
                         for name, path in modules.items()},
            "serving": {"operations": dict(sorted(operations.items())), "events": events,
                        "places": places}}


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

    bound = case_map(registry, catalog, profile, {n["id"]: n for n in plan["nodes"]})
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
    if registry["driver"] in ran:
        adapter.update(executed(plan, profile, bound, derived, load_serving(root), paths, sha))
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
    if not problems:
        registry, (plan, catalog, _) = load(), bundle()
        nodes = {n["id"]: n for n in plan["nodes"]}
        carried = {row["profile"] for row in registry["carried"]}
        for line in unexercised(registry, catalog, nodes,
                                sorted(set(catalog["profiles"]) - carried),
                                derive(registry)[0], load_serving())[1]:
            print(f"NOTE {line}")
    print("CASES OK" if not problems else f"CASES FAIL ({len(problems)})")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
