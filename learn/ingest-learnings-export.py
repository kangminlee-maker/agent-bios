#!/usr/bin/env python3
"""Curation intake — map a dashboard learnings export to ledger candidates.

Phase 3 of the collection loop (design/collection-loop/PHASE3-CURATION-DESIGN.md).
The curator exports RECEIVED learnings from the dashboard as ledger-compatible
JSON (GET /api/exports/learnings — verbatim payloads + provenance); THIS script
does the DETERMINISTIC half of intake:

  * validates each exported record against learn/learning.schema.json — the
    single validation source, reused from learn/check-learning.py (no second
    schema), so an invalid/verbatim-but-nonconforming payload is caught here;
  * buckets each row: VALID → a ledger-candidate entry; REJECTED → schema or
    domain-membership failure (with the reasons); DEFERRED → schema_version != 1
    (Phase 2 stores v2+ verbatim for forward-compat; the v1 intake cannot map it
    yet — it is NOT a reject, it is re-exportable once a v2-aware intake lands);
  * flags candidates whose learning_id already appears in ledger.json (a
    deterministic dedup warning — string membership, not a semantic judgment);
  * emits a curation WORKLIST the curator then works through by hand.

It does NOT do the SEMANTIC half — triage the domain, classify type/layer/
mechanism, or judge novelty vs the full canon. Those stay with the curator
(capability boundary); see design/collection-loop/CURATION-INTAKE.md.

PII boundary: the worklist carries `_provenance.user_email` (D3.3 — visibility
into who contributes what). The worklist is a LOCAL artifact — never commit it;
when merging a candidate into the git-tracked ledger.json, keep `learning_id`
(non-PII dedup key) and DROP `_provenance` (see the procedure doc).

Input:  a learnings-export JSON file (positional arg; '-' or omitted = stdin).
Output: the worklist JSON to stdout, or to --out FILE.
"""
import argparse
import importlib.util
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
LEDGER = REPO / "design" / "session-distill" / "ledger.json"
FIXTURE = REPO / "design" / "collection-loop" / "fixtures" / "export-sample.json"
SUPPORTED_SCHEMA_VERSION = 1


def die(msg, code=1):
    print(f"ingest-learnings-export: {msg}", file=sys.stderr)
    sys.exit(code)


def load_checker():
    """Reuse learn/check-learning.py as the single validation source."""
    path = REPO / "learn" / "check-learning.py"
    spec = importlib.util.spec_from_file_location("check_learning", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_ledger_learning_ids(path=LEDGER):
    """learning_ids already present in the ledger (dedup key). Entries sourced
    from earlier learnings carry a top-level `learning_id`; the historical
    session-distill entries do not, so they simply contribute nothing here.
    A missing/unreadable ledger is not fatal — dedup just finds nothing."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    out = set()
    for e in data.get("entries", []):
        lid = e.get("learning_id") if isinstance(e, dict) else None
        if isinstance(lid, str) and lid:
            out.add(lid.lower())
    return out


def map_candidate(payload, row):
    """A validated export row -> a ledger-candidate entry (ledger.json shape).
    Deterministic fields the record carries are copied; curator-only fields are
    null for the curator to fill. `_provenance` is worklist-only (strip before
    the ledger merge)."""
    cls = payload.get("classification") or {}
    return {
        "id": None,                                   # curator assigns (e.g. S4-02)
        "learning_id": payload.get("learning_id"),    # kept in ledger = dedup key
        "lesson": payload.get("lesson"),
        "strength": None,                             # curator: recurrence
        "verdict": None,                              # curator: novel|partial|principle
        "criteria": payload.get("criteria", []),
        "supporting_sessions": payload.get("supporting_sessions", []),
        "domain": payload.get("domain"),
        "proposed_domain": payload.get("proposed_domain"),
        "context": payload.get("context"),            # curator-facing evidence note
        "classification": {
            "type": cls.get("type"),
            "underlying_value": None,
            "reformulation": None,
            "meets_promotion_bar": cls.get("meets_bar"),
            "layer": cls.get("layer"),
            "mechanism": None,
            "token_est": None,
            "consumer_note": None,
            "split": None,
            "verification": None,
            "proposed": False,                        # ledger convention: boolean
        },
        "status": "candidate",
        "_provenance": {
            "user_email": row.get("user_email"),      # PII — worklist only, strip on merge
            "received_at": row.get("received_at"),    # server receipt time
            "created": payload.get("created"),        # user capture time (distinct)
            "schema_version": payload.get("schema_version"),
        },
    }


def process_export(export, checker, ledger_ids):
    """Bucket every export row. Deterministic: input order preserved, no
    timestamps, so the same input yields byte-identical output."""
    if not isinstance(export, dict) or not isinstance(export.get("learnings"), list):
        die("not a learnings-export (expected an object with a `learnings` array)")

    validator = checker.build_validator()
    domain_values = checker.valid_domain_values()

    entries, rejected, deferred, duplicates, warnings = [], [], [], [], []
    for i, row in enumerate(export["learnings"]):
        if not isinstance(row, dict) or not isinstance(row.get("payload"), dict):
            rejected.append({"index": i, "learning_id": None,
                             "reasons": ["export row has no payload object"]})
            continue
        payload = row["payload"]
        lid = payload.get("learning_id")

        sv = payload.get("schema_version")
        if sv != SUPPORTED_SCHEMA_VERSION:
            deferred.append({"index": i, "learning_id": lid, "schema_version": sv,
                             "note": "re-export once a v%s-aware intake exists "
                                     "(row stays available via includeExported)" % sv})
            continue

        errors = checker.validate_record(payload, validator, domain_values)
        if errors:
            rejected.append({"index": i, "learning_id": lid, "reasons": errors})
            continue

        # server-bug detector: the export's domain column should mirror payload.domain.
        if row.get("domain") != payload.get("domain"):
            warnings.append({"index": i, "learning_id": lid,
                             "detail": "export domain column %r != payload.domain %r"
                                       % (row.get("domain"), payload.get("domain"))})

        cand = map_candidate(payload, row)
        if isinstance(lid, str) and lid.lower() in ledger_ids:
            cand["duplicate_in_ledger"] = True
            duplicates.append({"index": i, "learning_id": lid})
        entries.append(cand)

    return {
        "source": "curation-intake",
        "generated_from": export.get("source", "learnings-export"),
        "counts": {"valid": len(entries), "rejected": len(rejected),
                   "deferred": len(deferred), "duplicates": len(duplicates),
                   "warnings": len(warnings)},
        "warnings": warnings,
        "rejected": rejected,
        "deferred": deferred,
        "entries": entries,
    }


def run(export, out_path=None):
    worklist = process_export(export, load_checker(), load_ledger_learning_ids())
    text = json.dumps(worklist, ensure_ascii=False, indent=2) + "\n"
    if out_path and out_path != "-":
        pathlib.Path(out_path).write_text(text, encoding="utf-8")
        c = worklist["counts"]
        print(f"ingest-learnings-export: wrote {out_path} "
              f"(valid={c['valid']} rejected={c['rejected']} deferred={c['deferred']} "
              f"duplicates={c['duplicates']})", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return worklist


def _self_test():
    """Verify bucketing against the committed export fixture (the cross-repo
    contract artifact): valid rows map (cardinality > 0), a bad-domain row is
    rejected with a domain reason (negative control), a v2 row is deferred not
    rejected, mapping preserves context + meets_bar rename, and output is
    deterministic. Exits non-zero on any failure."""
    export = json.loads(FIXTURE.read_text(encoding="utf-8"))
    checker = load_checker()
    w1 = process_export(export, checker, {"0f8c1c2a-4d1e-4abc-9def-000000000001"})
    w2 = process_export(export, checker, {"0f8c1c2a-4d1e-4abc-9def-000000000001"})

    valid_ids = {e["learning_id"] for e in w1["entries"]}
    rej_reasons = " ".join(r for row in w1["rejected"] for r in row["reasons"])
    deferred_svs = {d["schema_version"] for d in w1["deferred"]}
    full = next((e for e in w1["entries"]
                 if e["learning_id"] == "0f8c1c2a-4d1e-4abc-9def-000000000002"), None)

    checks = [
        ("valid rows mapped (cardinality > 0)", w1["counts"]["valid"] >= 3),
        ("bad-domain row rejected", w1["counts"]["rejected"] >= 1),
        ("reject reason names the domain (negative control)", "domain" in rej_reasons),
        ("v2 row deferred, not rejected", deferred_svs == {2}),
        ("deferred row absent from entries",
         "0f8c1c2a-4d1e-4abc-9def-00000000000a" not in valid_ids),
        ("context preserved verbatim", full is not None and full["context"]
         and "4분짜리" in full["context"]),
        ("meets_bar -> meets_promotion_bar",
         full is not None and full["classification"]["meets_promotion_bar"] is True),
        ("classification.proposed is boolean false",
         full is not None and full["classification"]["proposed"] is False),
        ("provenance carries user_email (worklist-only PII)",
         full is not None and full["_provenance"]["user_email"] == "alice@day1company.co.kr"),
        ("provenance keeps both created and received_at",
         full is not None and full["_provenance"]["created"] != full["_provenance"]["received_at"]),
        ("ledger dedup flags a known learning_id", w1["counts"]["duplicates"] == 1),
        ("deterministic (same input -> identical output)",
         json.dumps(w1, ensure_ascii=False) == json.dumps(w2, ensure_ascii=False)),
    ]
    failed = [name for name, ok in checks if not ok]
    if failed:
        for name in failed:
            print(f"ingest-learnings-export --self-test: FAIL: {name}", file=sys.stderr)
        sys.exit(1)
    print(f"ingest-learnings-export --self-test: OK ({len(checks)} intake checks)")


def main():
    ap = argparse.ArgumentParser(description="Map a learnings export to ledger candidates.")
    ap.add_argument("export", nargs="?", default="-",
                    help="learnings-export JSON file ('-' or omitted = stdin)")
    ap.add_argument("--out", default=None, help="write the worklist here (default: stdout)")
    ap.add_argument("--self-test", action="store_true",
                    help="run the intake self-test against the fixture and exit")
    args = ap.parse_args()

    if args.self_test:
        _self_test()
        return

    if args.export == "-":
        raw = sys.stdin.read()
    else:
        try:
            raw = pathlib.Path(args.export).read_text(encoding="utf-8")
        except OSError as e:
            die(f"cannot read export {args.export!r}: {e}")
    try:
        export = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"export is not valid JSON: {e}")
    run(export, args.out)


if __name__ == "__main__":
    main()
