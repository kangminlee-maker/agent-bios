#!/usr/bin/env python3
"""Design §6.5's planted controls (plan WP-10 done-when 4; F27): planted into every run under ordinary ids, judged like
any candidate, and held to the verdicts `tables/controls.json` gives them.

`plant` builds the §6.5 population for S5 from the run's own material: each control borrows a natural formed
candidate - its events, sessions and quotes - and changes exactly what its kind plants:

- **paraphrase_covered** (two): a paraphrase of an operative unit of the current library, as its lesson, situation
  and action; S5 must retrieve the unit for it, and both judges must find the unit covers it;
- **temporal_order_cause**: the borrowed candidate whose causal support states temporal order as its only reason;
  both judges must mark causal_support unmet, so admission is rejected;
- **task_specific_requirement**: a requirement specific to the task at hand (the purpose record's "not a learning");
  admission must be rejected;
- **altered_quote**: one quote whose text differs from the span of the immutable copy it names; S5's quote check must
  fail it (QUOTE_MISMATCH);
- **fabricated_session**: a session id no census row holds; S5's session check must fail it (SESSION_UNKNOWN).

A control's id is `k-` and sixteen hex digits, as a formed candidate's is, derived from a nonce drawn per run; its record
has exactly the fields of the natural candidate it borrows. What marks it a control - its kind, what it borrowed and
its expected verdict - is written only to `controls.json` (CONTROLS_FILE), which no packet carries and S6 never reads:
`reader_problems` holds the modules to that, naming every site that names the file. The §3.2 gate controls are
declared beside them; the gate judges them over planted call directories of the stage that dispatches calls.

`check_s5` holds S5's checks to the S5 verdicts; `evaluate` holds the judgments and the gate's verdicts to the rest,
and the natural candidates to the rejection share, apart from the controls: CONTROLS_INCOMPLETE (a kind not planted,
or a control with no verdict), CONTROL_FAILED (a control accepted as natural or not given its verdict; the run stops
before S7), REJECTION_SHARE_ZERO (more than twenty natural candidates and none rejected; O4).

  controls.py --self-test
"""
import ast
import copy
import hashlib
import json
import pathlib
import random
import re
import secrets
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import lifecycle_intake
from runlib.records import Refused

HERE = pathlib.Path(__file__).resolve().parents[1]
TABLE_PATH = HERE / "tables" / "controls.json"
CONTROLS_FILE = "controls.json"
ID = re.compile(r"k-[0-9a-f]{16}")
# design 2026-10-20T1942--9684f05--mechanism-design.md §6.5 lines 510-513, copied once and held against the table
DESIGN_6_5 = ("two paraphrases of covered units (must match their unit)", "two admission failures (cause by temporal "
              "order only; a task-specific requirement)", "one altered quote", "one fabricated session id",
              "the model-call gate controls of §3.2")
DESIGN_6_5_COUNTS = {"paraphrase_covered": 2, "temporal_order_cause": 1, "task_specific_requirement": 1,
                     "altered_quote": 1, "fabricated_session": 1}
# §3.2 lines 150-158: the rehearsal controls, each rejected by name and each clean counterpart accepted
DESIGN_3_2 = ("a truncated output", "a real aborted stream", "a planted `response.incomplete` frame", "a refusal",
              "a nonzero exit", "a stale receipt", "a mismatched result hash", "an inherited profile",
              "a contaminated working directory", "an unattested model")
# §6.5 line 513: "More than twenty natural candidates with no rejection fails O4."
DESIGN_REJECTION_SHARE = 20
PARAPHRASE_MIN_KEYS = 6
PARAPHRASE_LAYERS = ("catalog", "overlays", "native_global", "native_project", "native_memory")
# what a control of its kind says in place of the borrowed candidate's words; the paraphrase is made from the unit
TEMPORAL_BASIS = "The outcome came right after this step, so this step is what produced the outcome."
TASK_SPECIFIC = {"lesson": "Name the output file exactly as this task's request spelled it.",
                 "situation": "When this task's request names the file its output goes to",
                 "action": "Write the output to that file name, spelled as the request spelled it",
                 "exception": "Unless this task's request is changed"}

_TABLES = {}


def table():
    """The controls table, read once per process; a control may hold a scratch copy in `_TABLES["t"]`."""
    if "t" not in _TABLES:
        _TABLES["t"] = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    return _TABLES["t"]


def table_problems(held=None):
    """The table against design §6.5 and §3.2 (CONTRACT_DRIFT) and against itself."""
    held = held or table()
    problems = []
    counts = {row["kind"]: row["count"] for row in held["planted"]}
    if counts != DESIGN_6_5_COUNTS:
        problems.append(f"CONTRACT_DRIFT planted: the table plants {counts}, §6.5 {DESIGN_6_5_COUNTS}")
    kinds = [row["kind"] for row in held["gate"]]
    if len(kinds) != len(set(kinds)) or len(kinds) != len(DESIGN_3_2):
        problems.append(f"CONTRACT_DRIFT gate: {len(kinds)} gate controls ({len(set(kinds))} distinct), §3.2 lists "
                        f"{len(DESIGN_3_2)}")
    for row, phrase in zip(held["gate"], DESIGN_3_2):
        if phrase.replace("`", "") not in row["design"].replace("`", ""):
            problems.append(f"CONTRACT_DRIFT gate {row['kind']}: its design text does not hold §3.2's {phrase!r}")
    if held["rejection_share"]["natural_more_than"] != DESIGN_REJECTION_SHARE:
        problems.append(f"CONTRACT_DRIFT rejection_share: {held['rejection_share']['natural_more_than']}, §6.5 "
                        f"{DESIGN_REJECTION_SHARE}")
    for row in held["planted"]:
        if not set(row["expected"]) == set(row["checked_at"]) <= {"S5", "S6"}:
            problems.append(f"TABLE_INVALID planted {row['kind']}: its expected verdicts are not one per stage it is "
                            "checked at (S5, S6)")
            continue
        for stage, verdict in row["expected"].items():
            rule = verdict.get("rule") if isinstance(verdict, dict) else None
            if not isinstance(verdict, dict) or not verdict.get("text") or not isinstance(rule, dict) or not rule \
                    or set(rule) - RULE_KEYS[stage] or ("problem" in rule) != ("of" in rule and "in" in rule):
                problems.append(f"TABLE_INVALID planted {row['kind']} {stage}: an expected verdict is its design text "
                                f"and a rule of {sorted(RULE_KEYS[stage])} (`problem` with `of` and `in`)")
    return problems


# what each stage's evaluator applies of an expected verdict's rule (tables/controls.json)
RULE_KEYS = {"S5": {"retrieved", "problem", "of", "in", "fields"}, "S6": {"unit_diagnosis", "admission", "requirements"}}


def s5_holds(rule, entry, row):
    """Whether S5's row of a planted candidate is the table's verdict: the unit it names retrieved for it, the problem
    it names reported on its subject, and the row's fields as the rule gives them."""
    ok = True
    if "retrieved" in rule:
        ok = ok and entry[rule["retrieved"]] in {u["unit_id"] for u in row["retrieved_units"]}
    if "problem" in rule:
        ok = ok and f"{rule['problem']} {entry[rule['of']]}" in row[rule["in"]]
    return ok and all(row.get(k) == v for k, v in (rule.get("fields") or {}).items())


def s6_holds(rule, entry, verdict):
    """Whether S6's verdict on a planted candidate is the table's: its unit diagnosis at the current point, its
    admission, and both judges' marks on the requirements the rule names."""
    ok = True
    if "unit_diagnosis" in rule:
        of = rule["unit_diagnosis"]
        ok = (verdict["outcome"]["unit_diagnosis"].get("current") or {}).get(entry[of["of"]]) == of["is"]
    if "admission" in rule:
        ok = ok and verdict["outcome"]["admission"]["admission"] == rule["admission"]
    return ok and all(verdict["requirements"][w].get(name) == mark for w in ("A", "B")
                      for name, mark in (rule.get("requirements") or {}).items())


def planted_id(nonce, kind, n):
    return "k-" + hashlib.sha256(f"{nonce}\x00{kind}\x00{n}".encode("utf-8")).hexdigest()[:16]


def fabricated_session(nonce, host):
    """A session id of the host's shape that no census holds (a UUID drawn from the nonce)."""
    h = hashlib.sha256(f"{nonce}\x00session".encode("utf-8")).hexdigest()
    return f"{host}:{h[:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}"


def alter(text):
    """The altered quote: one character changed, the length kept, so only the bytes say it was altered."""
    if not text:
        return "x"
    return text[:-1] + ("y" if text[-1] == "x" else "x")


def paraphrase(text):
    """A unit's rule in other order: its clauses rotated, so the words stay the unit's and the sentence is not."""
    parts = [p.strip(" .;,:") for p in re.split(r"[;,:]|\.\s", text.strip()) if p.strip(" .;,:")]
    if len(parts) > 1:
        parts = parts[1:] + parts[:1]
    body = "; ".join(parts) if parts else text.strip()
    return body[:1].upper() + body[1:] + ("" if body.endswith(".") else ".")


def paraphrasable(unit_index):
    """The units a paraphrase control may name: operative, standing for their text in a layer the owner writes, with
    enough distinct words to be recognisable (PARAPHRASE_MIN_KEYS)."""
    out = []
    for rep, layer in sorted(unit_index.layer_of.items()):
        unit = unit_index.units[rep]
        if layer in PARAPHRASE_LAYERS and len(lifecycle_intake.keys_tf(unit["text"])[0]) >= PARAPHRASE_MIN_KEYS:
            out.append(rep)
    return out


def plant(natural, unit_index, cited_of, evidence_of, known_sessions, nonce=None):
    """`(planted candidates, their evidence records by id, controls.json's document)`.

    `natural` are S4's candidates; `cited_of(candidate)` the evidence ids it cites; `evidence_of(id)` the record of an
    id or None; `known_sessions` the census's session keys. A kind that cannot be planted from the run's material is
    listed `incomplete` with its reason, and S5 refuses the run CONTROLS_INCOMPLETE.

    A planted id is drawn from the nonce and a planted label follows S4's last, so on disk the two kinds differ in form,
    as S4's own candidates.json already tells them apart. What must not tell them apart is what a judge is sent, and no
    model is sent either: S6 hides the id and the label from every packet and names a candidate's calls by one digest of
    its id (stage_judge's CANDIDATE_HIDDEN and `item_of`), which S6's self-test holds on every packet its golden sends
    (Codex WP-10 X r1 #4)."""
    nonce = nonce or secrets.token_hex(8)
    rng = random.Random(nonce)
    formed = sorted((k for k in natural if k["source"] == "formed" and k.get("event_ids")), key=lambda k: k["candidate_id"])
    numbers = [int(k["label"][1:]) for k in natural if re.fullmatch(r"k[1-9][0-9]*", str(k.get("label")))]
    label = max(numbers, default=0)
    doc = {"nonce": nonce, "planted": [], "incomplete": [],
           "gate": [{"kind": row["kind"], "code": row["code"]} for row in table()["gate"]]}
    planted, evidence = [], {}
    units = paraphrasable(unit_index)
    wanted = next((spec["count"] for spec in table()["planted"] if spec["kind"] == "paraphrase_covered"), 0)
    chosen_units = rng.sample(units, min(len(units), wanted))   # the table's count (Codex WP-10 r1 #5), not §6.5's copy
    for spec in table()["planted"]:
        for n in range(spec["count"]):
            kind = spec["kind"]
            if not formed:
                doc["incomplete"].append({"kind": kind, "reason": "no formed candidate with events to borrow from"})
                continue
            base = rng.choice(formed)
            record = copy.deepcopy(base)
            label += 1
            record["candidate_id"], record["label"] = planted_id(nonce, kind, n), f"k{label}"
            entry = {"candidate_id": record["candidate_id"], "kind": kind, "borrowed_from": base["candidate_id"],
                     "checked_at": list(spec["checked_at"]), "expected": dict(spec["expected"])}
            if kind == "paraphrase_covered":
                if n >= len(chosen_units):
                    doc["incomplete"].append({"kind": kind, "reason": f"the library has {len(units)} paraphrasable units, "
                                                                      f"and {spec['count']} are needed"})
                    label -= 1
                    continue
                unit = unit_index.units[chosen_units[n]]
                text = paraphrase(unit["text"])
                record.update(lesson=text, situation=text, action=text)
                entry["unit_id"] = unit["unit_id"]
            elif kind == "temporal_order_cause":
                # only the stated reason changes: the claims it cites still show the event, and no cause beyond its order
                record["admission"]["causal_support"]["basis"] = TEMPORAL_BASIS
            elif kind == "task_specific_requirement":
                record.update(TASK_SPECIFIC)
            elif kind == "altered_quote":
                source = next((evidence_of(i) for i in cited_of(base) if evidence_of(i) is not None), None)
                if source is None:
                    doc["incomplete"].append({"kind": kind, "reason": "the borrowed candidate cites no quote a store holds"})
                    label -= 1
                    continue
                new_id = "e-" + hashlib.sha256(f"{nonce}\x00quote".encode("utf-8")).hexdigest()[:16]
                evidence[new_id] = {**copy.deepcopy(source), "evidence_id": new_id, "redacted_text": alter(source["redacted_text"])}
                record["admission"]["observed_event"]["evidence_ids"] = (
                    list(record["admission"]["observed_event"]["evidence_ids"]) + [new_id])
                entry["evidence_id"] = new_id
            elif kind == "fabricated_session":
                host = (base.get("sessions") or ["claude:"])[0].split(":", 1)[0]
                session = fabricated_session(nonce, host)
                if session in known_sessions:
                    doc["incomplete"].append({"kind": kind, "reason": "the drawn session id is a census row"})
                    label -= 1
                    continue
                record["sessions"] = [session]
                entry["session"] = session
            planted.append(record)
            doc["planted"].append(entry)
    return planted, evidence, doc


def check_s5(doc, rows_by_id):
    """`(problems)` of S5's checks against the S5 verdicts, each entry of `doc` given its `S5` observation."""
    problems = [f"CONTROLS_INCOMPLETE {i['kind']}: {i['reason']}" for i in doc["incomplete"]]
    for entry in doc["planted"]:
        if "S5" not in entry["checked_at"]:
            continue
        row = rows_by_id.get(entry["candidate_id"])
        if row is None:
            problems.append(f"CONTROLS_INCOMPLETE {entry['kind']} {entry['candidate_id']}: S5 checked no such candidate")
            continue
        kind = entry["kind"]
        # the rule the table gave this control when it was planted (Codex WP-10 r1 #5: each kind's verdict was
        # restated here, so a table that changed it was not obeyed)
        ok = s5_holds(entry["expected"]["S5"]["rule"], entry, row)
        entry["S5"] = {"ok": ok}
        if not ok:
            problems.append(f"CONTROL_FAILED {entry['candidate_id']} {kind}: S5 did not give it its verdict "
                            f"({entry['expected']['S5']['text']})")
    return problems


def evaluate(doc, verdicts, gate_verdicts, natural_ids, s5_rows):
    """The controls after S6, and the natural candidates apart from them.

    `verdicts`: `{candidate_id: {"outcome": derive.unit_outcome(...), "requirements": {"A": {...}, "B": {...}}}}`;
    `gate_verdicts`: `{gate kind: {"planted": gate.accept(...), "clean": gate.accept(...)}}`; `natural_ids` the natural
    candidates; `s5_rows` S5's rows by id. Returns `{controls, gate, natural, problems}`."""
    problems = [f"CONTROLS_INCOMPLETE {i['kind']}: {i['reason']}" for i in doc["incomplete"]]
    controls = []
    for entry in doc["planted"]:
        if "S6" not in entry["checked_at"]:
            continue
        v = verdicts.get(entry["candidate_id"])
        if v is None:
            problems.append(f"CONTROLS_INCOMPLETE {entry['kind']} {entry['candidate_id']}: no judgment of it")
            controls.append({"candidate_id": entry["candidate_id"], "kind": entry["kind"], "ok": False})
            continue
        admitted = v["outcome"]["admission"]["admission"]
        ok = s6_holds(entry["expected"]["S6"]["rule"], entry, v)
        controls.append({"candidate_id": entry["candidate_id"], "kind": entry["kind"], "ok": ok})
        if not ok:
            why = "accepted as natural" if admitted == "admitted" else "not given its verdict"
            problems.append(f"CONTROL_FAILED {entry['candidate_id']} {entry['kind']}: {why} "
                            f"({entry['expected']['S6']['text']})")
    gate = []
    for row in doc["gate"]:
        got = gate_verdicts.get(row["kind"])
        if got is None:
            problems.append(f"CONTROLS_INCOMPLETE gate {row['kind']}: no verdict of the gate over its planted call")
            gate.append({"kind": row["kind"], "ok": False})
            continue
        planted_ok = got["planted"]["ok"] is False and row["code"] in got["planted"]["codes"]
        clean_ok = got["clean"]["ok"] is True
        gate.append({"kind": row["kind"], "ok": planted_ok and clean_ok})
        if not planted_ok:
            problems.append(f"CONTROL_FAILED gate {row['kind']}: the planted call was not rejected {row['code']}")
        if not clean_ok:
            problems.append(f"CONTROL_FAILED gate {row['kind']}: its clean counterpart was not accepted")
    judged = [i for i in natural_ids if i in verdicts or i in s5_rows]
    rejected = [i for i in judged if (i in verdicts and verdicts[i]["outcome"]["admission"]["admission"] == "rejected")
                or (i in s5_rows and (s5_rows[i]["quote_ok"] is False or s5_rows[i]["session_problems"]))]
    limit = table()["rejection_share"]["natural_more_than"]
    if len(judged) > limit and not rejected:
        problems.append(f"REJECTION_SHARE_ZERO: {len(judged)} natural candidates and none rejected; more than {limit} "
                        "with no rejection fails O4 (the controls are counted apart)")
    return {"controls": controls, "gate": gate, "natural": {"candidates": len(judged), "rejected": len(rejected)},
            "problems": problems}


def require(evaluation):
    """Refuse by name when the controls or the natural share fail: the run stops before S7."""
    if evaluation["problems"]:
        raise Refused("\n".join(evaluation["problems"]))


# ---- F27: no judge-visible byte marks a control --------------------------------------------------------------------

def kind_of(value):
    return "object" if isinstance(value, dict) else "array" if isinstance(value, list) else "null" if value is None \
        else "boolean" if isinstance(value, bool) else "number" if isinstance(value, (int, float)) else "string"


def marker_problems(control, natural, path=""):
    """What a field marker would change between a control's record and a natural one of the same shape: MARKER_FIELD for
    a key one object holds and the other does not, MARKER_TYPE for a value of another kind (a null is any kind's value;
    the items of an array are held to the other array's first item, and an empty array to nothing)."""
    if isinstance(control, dict) and isinstance(natural, dict):
        out = [f"MARKER_FIELD {path}/{k}" for k in sorted(set(control) ^ set(natural))]
        for k in sorted(set(control) & set(natural)):
            out += marker_problems(control[k], natural[k], f"{path}/{k}")
        return out
    if isinstance(control, list) and isinstance(natural, list):
        if not control or not natural:
            return []
        out = []
        for item in control:
            out += [p for p in marker_problems(item, natural[0], f"{path}/[]") if p not in out]
        return out
    a, b = kind_of(control), kind_of(natural)
    return [] if "null" in (a, b) or a == b else [f"MARKER_TYPE {path}: {a}, where a natural record holds {b}"]


# where the expected verdicts may be named, each with its reason; any other site of non-test code is a reader S6 could be
READERS = {
    ("runlib/stage_retrieve.py", "<module>"): "OUTPUTS declares controls.json as one of S5's outputs",
    ("runlib/stage_retrieve.py", "run"): "S5 writes the expected verdicts it planted, outside every packet",
    ("runlib/stage_render.py", "<module>"): "INPUTS declares controls.json as one of S9's S5 input artifacts",
    ("runlib/stage_render.py", "load"): "S9 reads which candidates S5 planted, so a proposal for one is accounted as a "
                                        "control and never rendered as a review row; S9 runs after S6 and S7, and the "
                                        "review is the owner's, read by no judge",
}
TEST_CODE = ("self_test", "fx_")


def reader_sites(texts):
    """`(module, top-level function)` of every non-test site in `texts` (`{relative path: source}`) that names the
    expected verdicts' file (the literal or CONTROLS_FILE), this module aside."""
    sites = set()
    for rel, source in sorted(texts.items()):
        if rel == "runlib/controls.py":
            continue
        tree = ast.parse(source)
        for top in tree.body:
            name = getattr(top, "name", "<module>")
            if name.startswith(TEST_CODE):
                continue
            for node in ast.walk(top):
                if (isinstance(node, ast.Constant) and node.value == CONTROLS_FILE) or \
                        (isinstance(node, (ast.Name, ast.Attribute)) and getattr(node, "id", getattr(node, "attr", None)) == "CONTROLS_FILE"):
                    sites.add((rel, name))
    return sites


def reader_problems(texts):
    sites = reader_sites(texts)
    return ([f"CONTROLS_READ {rel} ({name}): names the expected verdicts' file, and no reason in READERS says why"
             for rel, name in sorted(sites - set(READERS))]
            + [f"CONTROLS_READ_STALE {rel} ({name}): listed in READERS, and it no longer names the file"
               for rel, name in sorted(set(READERS) - sites)])


def module_texts(root=HERE):
    root = pathlib.Path(root)
    texts = {f"runlib/{p.name}": p.read_text(encoding="utf-8") for p in sorted((root / "runlib").glob("*.py"))}
    texts["distill.py"] = (root / "distill.py").read_text(encoding="utf-8")
    return texts


# ---- self-test -------------------------------------------------------------------------------------------------------

def self_test():
    import shutil
    import tempfile
    from runlib import records, stage_retrieve
    failures, ran = [], []

    def control(name, condition, detail=""):
        ran.append(name)
        if not condition:
            failures.append(f"{name}: {detail}")

    def guarded(action, default):
        try:
            return action()
        except Exception as exc:  # noqa: BLE001 - reported by the control that reads the default
            return default if not callable(default) else default(exc)

    def refusal(action):
        try:
            action()
        except Refused as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001 - a control whose subject raises anything else fails by its own name
            return f"RAISED {exc!r}"
        return ""

    # ---- the table against the design ---------------------------------------------------------------------------
    control("contract fidelity: the planted kinds and counts are §6.5's, the gate controls §3.2's, the share bar 20",
            table_problems() == [], f"{table_problems()}")
    drifted = copy.deepcopy(table())
    drifted["planted"][0]["count"] = 1
    control("control: one paraphrase planted where §6.5 says two is CONTRACT_DRIFT",
            any(p.startswith("CONTRACT_DRIFT planted") for p in table_problems(drifted)), f"{table_problems(drifted)}")
    dropped = copy.deepcopy(table())
    dropped["gate"] = dropped["gate"][:-1]
    control("control: a gate control dropped from the table is CONTRACT_DRIFT",
            any(p.startswith("CONTRACT_DRIFT gate") for p in table_problems(dropped)), f"{table_problems(dropped)}")

    # ---- planting over a golden run's material ------------------------------------------------------------------
    root = pathlib.Path(tempfile.mkdtemp(prefix="controls-"))
    try:
        run_dir = guarded(lambda: stage_retrieve.fx_gold(root / "base"), lambda exc: exc)
        if isinstance(run_dir, Exception):
            failures.append(f"the golden run through S4 could not be made: {run_dir!r}")
            run_dir = None
        if run_dir is not None:
            from runlib import census, evidence as evidences, stage_form
            cands = records.read_json(run_dir / "candidates.json")
            natural = cands["candidates"]
            current = records.read_json(run_dir / "inventory" / "current.json")
            index = stage_retrieve.UnitIndex(current["units"])
            subject_of = stage_form.subject(run_dir)
            names = [t["name"] for t in records.read_json(run_dir / "views.json")["transcripts"]]
            stored = stage_retrieve.stored_evidence(run_dir, names)
            extra = cands.get("origin_evidence") or {}
            known = {census.key_of(r) for r in census.rows(census.load(run_dir))}

            def cited_of(k):
                return stage_retrieve.cited(k, subject_of)[0]

            def evidence_of(i):
                return stored.get(i) or extra.get(i)
            planted, planted_ev, doc = plant(natural, index, cited_of, evidence_of, known, nonce="0123456789abcdef")
            kinds = [e["kind"] for e in doc["planted"]]
            control("done-when 4: the full §6.5 population is planted: two paraphrases, two admission failures, one "
                    "altered quote, one fabricated session id, and the §3.2 gate controls declared beside them",
                    sorted(kinds) == sorted(k for k, n in DESIGN_6_5_COUNTS.items() for _ in range(n))
                    and not doc["incomplete"] and len(doc["gate"]) == len(DESIGN_3_2), f"{kinds} {doc['incomplete']}")
            natural_ids = {k["candidate_id"] for k in natural}
            control("F27: every control has an ordinary id - k- and sixteen hex digits, as a formed candidate's - none of "
                    "them a natural candidate's", all(ID.fullmatch(k["candidate_id"]) for k in planted)
                    and not natural_ids & {k["candidate_id"] for k in planted}
                    and all(ID.fullmatch(k["candidate_id"]) for k in natural if k["source"] == "formed"),
                    f"{[k['candidate_id'] for k in planted]}")
            by_id = {k["candidate_id"]: k for k in natural}
            marks = {e["candidate_id"]: marker_problems(k, by_id[e["borrowed_from"]])
                     for k, e in zip(planted, doc["planted"])}
            control("F27 (structural): a control's record against the natural candidate it borrowed shows no marker field "
                    "- the same paths and types", all(not m for m in marks.values()), f"{marks}")
            control("control: a planted field would show as MARKER_FIELD",
                    marker_problems({**planted[0], "planted": True}, by_id[doc["planted"][0]["borrowed_from"]])
                    == ["MARKER_FIELD /planted"], "unmarked")
            control("control: a field holding another kind of value would show as MARKER_TYPE",
                    marker_problems({**planted[0], "lesson": ["x"]}, by_id[doc["planted"][0]["borrowed_from"]])
                    == ["MARKER_TYPE /lesson: array, where a natural record holds string"], "unmarked")
            raw = json.dumps(planted, sort_keys=True)
            words = [e["kind"] for e in doc["planted"]] + [CONTROLS_FILE, doc["nonce"], "borrowed_from", "expected"]
            control("F27: no planted record holds its kind, the nonce, or the expected-verdicts file's words",
                    not [w for w in words if w in raw], f"{[w for w in words if w in raw]}")
            control("the same nonce plants the same controls; another draws other ids",
                    plant(natural, index, cited_of, evidence_of, known, nonce="0123456789abcdef")[0] == planted
                    and {k["candidate_id"] for k in plant(natural, index, cited_of, evidence_of, known, nonce="fedcba9876543210")[0]}
                    .isdisjoint({k["candidate_id"] for k in planted}), "differs")
            altered = next(e for e in doc["planted"] if e["kind"] == "altered_quote")
            rec = planted_ev[altered["evidence_id"]]
            control("the altered quote's record differs from its source by one character of its text and keeps every field",
                    len(rec["redacted_text"]) == len(next(evidence_of(i) for i in cited_of(by_id[altered["borrowed_from"]])
                                                          if evidence_of(i))["redacted_text"])
                    and evidences.verify(run_dir, rec) and evidences.verify(run_dir, rec)[0].startswith("QUOTE_MISMATCH"),
                    f"{evidences.verify(run_dir, rec)[:1]}")
            fab = next(e for e in doc["planted"] if e["kind"] == "fabricated_session")
            control("the fabricated session id has its host's shape and is no census row",
                    fab["session"] not in known and fab["session"].startswith("claude:"), f"{fab['session']}")
            para = [e for e in doc["planted"] if e["kind"] == "paraphrase_covered"]
            control("the two paraphrases name two distinct operative units the library holds",
                    len({e["unit_id"] for e in para}) == 2 and all(e["unit_id"] in index.units for e in para), f"{para}")
            # incomplete populations
            _p, _e, none_doc = plant([k for k in natural if k["source"] != "formed"], index, cited_of, evidence_of, known, "aa")
            control("CONTROLS_INCOMPLETE: a run with no formed candidate to borrow from plants none, and says why per kind",
                    len(none_doc["incomplete"]) == sum(DESIGN_6_5_COUNTS.values())
                    and check_s5(none_doc, {})[0].startswith("CONTROLS_INCOMPLETE"), f"{none_doc['incomplete'][:1]}")
            small = stage_retrieve.UnitIndex([u for u in current["units"] if u["unit_id"] == "u-tests"])
            _p, _e, small_doc = plant(natural, small, cited_of, evidence_of, known, "bb")
            control("CONTROLS_INCOMPLETE: a library with one paraphrasable unit plants one paraphrase, and names the second",
                    [i["kind"] for i in small_doc["incomplete"]] == ["paraphrase_covered"]
                    and sum(1 for e in small_doc["planted"] if e["kind"] == "paraphrase_covered") == 1, f"{small_doc['incomplete']}")
            fewer = copy.deepcopy(table())
            fewer["planted"] = [r for r in fewer["planted"] if r["kind"] != "fabricated_session"]
            _TABLES["t"] = fewer
            try:
                _p, _e, fewer_doc = plant(natural, index, cited_of, evidence_of, known, "cc")
            finally:
                _TABLES.pop("t", None)
            control("CONTROLS_INCOMPLETE: a population with fewer than the six listed is refused against §6.5 by the table "
                    "check", table_problems(fewer) and len(fewer_doc["planted"]) == 5, f"{table_problems(fewer)}")

            # ---- S5's verdicts --------------------------------------------------------------------------------------
            def row(k, **over):
                base = {"retrieved_units": [], "quote_ok": True, "quote_problems": [], "session_problems": []}
                return {**base, **over}
            good = {}
            for e in doc["planted"]:
                if e["kind"] == "paraphrase_covered":
                    good[e["candidate_id"]] = row(e, retrieved_units=[{"unit_id": e["unit_id"]}])
                elif e["kind"] == "altered_quote":
                    good[e["candidate_id"]] = row(e, quote_ok=False, quote_problems=[f"QUOTE_MISMATCH {e['evidence_id']}"])
                elif e["kind"] == "fabricated_session":
                    good[e["candidate_id"]] = row(e, session_problems=[f"SESSION_UNKNOWN {e['session']}"])
            control("S5: each S5 control given its verdict passes", check_s5(copy.deepcopy(doc), good) == [],
                    f"{check_s5(copy.deepcopy(doc), good)}")
            for kind, change in (("altered_quote", dict(quote_ok=True, quote_problems=[])),
                                 ("fabricated_session", dict(session_problems=[])),
                                 ("paraphrase_covered", dict(retrieved_units=[]))):
                bent = copy.deepcopy(good)
                target = next(e["candidate_id"] for e in doc["planted"] if e["kind"] == kind)
                bent[target] = {**bent[target], **change}
                control(f"CONTROL_FAILED: {kind} accepted by S5 as a natural candidate would be is named",
                        any(p.startswith(f"CONTROL_FAILED {target} {kind}") for p in check_s5(copy.deepcopy(doc), bent)),
                        f"{check_s5(copy.deepcopy(doc), bent)}")

            # Codex WP-10 r1 #5: the verdict a control is held to is the table's rule, read where it was planted
            swapped = copy.deepcopy(doc)
            for e in swapped["planted"]:
                if e["kind"] == "altered_quote":
                    e["expected"]["S5"]["rule"] = {"problem": "SESSION_UNKNOWN", "of": "evidence_id",
                                                   "in": "quote_problems"}
            aq = next(e["candidate_id"] for e in doc["planted"] if e["kind"] == "altered_quote")
            control("Codex WP-10 r1 #5: S5's verdict on a control follows its rule: the altered quote's row passes its "
                    "own rule and fails one that names another problem",
                    check_s5(copy.deepcopy(doc), good) == []
                    and any(p.startswith(f"CONTROL_FAILED {aq} altered_quote") for p in check_s5(swapped, good)),
                    f"{check_s5(swapped, good)}")
            # one more than §6.5's two, from a library that holds that many: a count read from §6.5's copy samples two
            # units and names the third incomplete
            more = DESIGN_6_5_COUNTS["paraphrase_covered"] + 1
            ruled = copy.deepcopy(table())
            for r in ruled["planted"]:
                if r["kind"] == "paraphrase_covered":
                    r["count"] = more
            _TABLES["t"] = ruled
            try:
                _p, _e, ruled_doc = plant(natural, index, cited_of, evidence_of, known, "dd")
            finally:
                _TABLES.pop("t", None)
            control("Codex WP-10 r1 #5: the paraphrases planted are the table's count, not §6.5's copy of it",
                    len(paraphrasable(index)) >= more
                    and sum(1 for e in ruled_doc["planted"] if e["kind"] == "paraphrase_covered") == more
                    and not [i for i in ruled_doc["incomplete"] if i["kind"] == "paraphrase_covered"],
                    f"{len(paraphrasable(index))} paraphrasable {[e['kind'] for e in ruled_doc['planted']]} "
                    f"{ruled_doc['incomplete']}")
            invalid = copy.deepcopy(table())
            invalid["planted"][0]["expected"]["S5"]["rule"] = {"judged": "unit_id"}
            control("Codex WP-10 r1 #5: a rule no evaluator applies is TABLE_INVALID",
                    any(p.startswith("TABLE_INVALID planted paraphrase_covered S5") for p in table_problems(invalid)),
                    f"{table_problems(invalid)}")

            # ---- after S6: the judge controls, the gate controls, the natural share -----------------------------------
            def outcome(admission, covers=None):
                return {"outcome": {"admission": {"admission": admission}, "unit_diagnosis": {"current": covers or {}}},
                        "requirements": {"A": {"causal_support": "unmet"}, "B": {"causal_support": "unmet"}}}
            verdicts = {}
            for e in doc["planted"]:
                if e["kind"] == "paraphrase_covered":
                    verdicts[e["candidate_id"]] = outcome("disputed", {e["unit_id"]: "covers"})
                elif "S6" in e["checked_at"]:
                    verdicts[e["candidate_id"]] = outcome("rejected")
            gates = {r["kind"]: {"planted": {"ok": False, "codes": [r["code"]]}, "clean": {"ok": True, "codes": []}}
                     for r in doc["gate"]}
            nat = sorted(natural_ids)
            some = {i: outcome("admitted") for i in nat}
            some[nat[0]] = outcome("rejected")
            clean = evaluate(doc, {**verdicts, **some}, gates, nat, {})
            control("after S6: every control given its verdict, every gate control rejected by name with its clean "
                    "counterpart accepted, passes", clean["problems"] == [], f"{clean['problems']}")
            temporal = next(e["candidate_id"] for e in doc["planted"] if e["kind"] == "temporal_order_cause")
            accepted = evaluate(doc, {**verdicts, **some, temporal: outcome("admitted")}, gates, nat, {})
            control("CONTROL_FAILED: a planted control accepted as natural is named, and require() stops the run",
                    any(p.startswith(f"CONTROL_FAILED {temporal} temporal_order_cause: accepted as natural") for p in accepted["problems"])
                    and refusal(lambda: require(accepted)).startswith("CONTROL_FAILED"), f"{accepted['problems']}")
            other = {**verdicts[temporal], "requirements": {"A": {"causal_support": "met"}, "B": {"causal_support": "unmet"}}}
            loose = copy.deepcopy(doc)
            for e in loose["planted"]:
                if e["kind"] == "temporal_order_cause":
                    e["expected"]["S6"]["rule"] = {"admission": "rejected"}
            control("Codex WP-10 r1 #5: S6's verdict on a control follows its rule: the temporal-order control rejected "
                    "for another requirement fails its own rule and passes one that asks only for the rejection",
                    any(p.startswith(f"CONTROL_FAILED {temporal}") for p in
                        evaluate(doc, {**verdicts, **some, temporal: other}, gates, nat, {})["problems"])
                    and not any(p.startswith(f"CONTROL_FAILED {temporal}") for p in
                                evaluate(loose, {**verdicts, **some, temporal: other}, gates, nat, {})["problems"]),
                    "the rule was not followed")
            control("CONTROL_FAILED: a temporal-order control rejected for another requirement is not its verdict",
                    any(p.startswith(f"CONTROL_FAILED {temporal}") for p in
                        evaluate(doc, {**verdicts, **some, temporal: other}, gates, nat, {})["problems"]), "passed")
            p0 = para[0]["candidate_id"]
            control("CONTROL_FAILED: a paraphrase whose unit the judges do not find covering is named",
                    any(p.startswith(f"CONTROL_FAILED {p0} paraphrase_covered") for p in
                        evaluate(doc, {**verdicts, **some, p0: outcome("disputed", {})}, gates, nat, {})["problems"]), "passed")
            missing = {k: v for k, v in verdicts.items() if k != temporal}
            control("CONTROLS_INCOMPLETE: a control with no judgment is named",
                    any(p.startswith("CONTROLS_INCOMPLETE temporal_order_cause") for p in
                        evaluate(doc, {**missing, **some}, gates, nat, {})["problems"]), "passed")
            no_gate = {k: v for k, v in gates.items() if k != "stale_receipt"}
            control("CONTROLS_INCOMPLETE: a gate control with no verdict of the gate is named",
                    any(p.startswith("CONTROLS_INCOMPLETE gate stale_receipt") for p in
                        evaluate(doc, {**verdicts, **some}, no_gate, nat, {})["problems"]), "passed")
            slipped = {**gates, "refusal": {"planted": {"ok": True, "codes": []}, "clean": {"ok": True, "codes": []}}}
            wrong = {**gates, "nonzero_exit": {"planted": {"ok": False, "codes": ["SCHEMA_INVALID"]}, "clean": {"ok": True, "codes": []}}}
            spoiled = {**gates, "inherited_profile": {"planted": {"ok": False, "codes": ["PROFILE_INHERITED"]},
                                                      "clean": {"ok": False, "codes": ["SCHEMA_INVALID"]}}}
            control("CONTROL_FAILED: a planted gate fault accepted, or rejected under another code, or a clean counterpart "
                    "rejected, is named",
                    any("gate refusal: the planted call was not rejected" in p for p in evaluate(doc, verdicts, slipped, [], {})["problems"])
                    and any("gate nonzero_exit: the planted call" in p for p in evaluate(doc, verdicts, wrong, [], {})["problems"])
                    and any("gate inherited_profile: its clean counterpart" in p for p in evaluate(doc, verdicts, spoiled, [], {})["problems"]),
                    "passed")

            def share(n, rejected=0, s5=None):
                ids = [f"k-{i:016x}" for i in range(n)]
                vs = {i: outcome("rejected" if j < rejected else "admitted") for j, i in enumerate(ids)}
                return evaluate(doc, {**verdicts, **vs}, gates, ids, s5 or {})
            control("done-when 4: 21 natural candidates all admitted fail O4 (REJECTION_SHARE_ZERO)",
                    any(p.startswith("REJECTION_SHARE_ZERO: 21 natural") for p in share(21)["problems"]), f"{share(21)['problems']}")
            control("control: 20 natural candidates all admitted pass", share(20)["problems"] == [], f"{share(20)['problems']}")
            control("control: 21 natural candidates with one rejected pass", share(21, 1)["problems"] == [], f"{share(21, 1)['problems']}")
            ids21 = [f"k-{i:016x}" for i in range(21)]
            control("a natural candidate S5 failed is a rejection of the natural share",
                    share(21, 0, {ids21[0]: {"quote_ok": False, "session_problems": []}})["problems"] == [], "failed")
            control("the controls are counted apart: their rejections do not lift a natural share of zero",
                    share(21)["natural"] == {"candidates": 21, "rejected": 0}
                    and any(p.startswith("REJECTION_SHARE_ZERO") for p in share(21)["problems"]), f"{share(21)['natural']}")

        # ---- the expected verdicts are read nowhere S6 could ---------------------------------------------------------
        texts = guarded(module_texts, {})
        control("F27: outside this module only S5's writer names the expected verdicts' file, each site with its reason",
                texts and reader_problems(texts) == [], f"{reader_problems(texts) if texts else 'no texts'}")
        planted_text = dict(texts)
        planted_text["runlib/stage_form.py"] = texts.get("runlib/stage_form.py", "") + (
            '\n\ndef sneak(run_dir):\n    return (run_dir / "controls.json").read_text()\n')
        held_readers = dict(READERS)
        READERS[("runlib/stage_form.py", "run")] = "a reason for a site that does not name the file"
        try:
            stale = reader_problems(texts)
        finally:
            READERS.clear()
            READERS.update(held_readers)
        control("control: a listed site that no longer names the file is CONTROLS_READ_STALE",
                "CONTROLS_READ_STALE runlib/stage_form.py (run): listed in READERS, and it no longer names the file" in stale,
                f"{stale}")
        control("control: a stage that reads the expected verdicts is CONTROLS_READ by site",
                "CONTROLS_READ runlib/stage_form.py (sneak): names the expected verdicts' file, and no reason in READERS "
                "says why" in reader_problems(planted_text), f"{reader_problems(planted_text)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    for failure in failures:
        print(f"controls --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"controls --self-test: OK ({len(ran)} controls: §6.5's population planted from a golden run's material under "
          "ordinary ids with no marker field (F27), CONTROLS_INCOMPLETE, S5's verdicts and CONTROL_FAILED, the judge and "
          "gate controls after S6, REJECTION_SHARE_ZERO at 21 and not at 20, the controls apart from the natural share, "
          "and the expected verdicts read nowhere else)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    print("usage: controls.py --self-test", file=sys.stderr)
    sys.exit(2)
