#!/usr/bin/env python3
"""Author-side integration gate for the slide-writing instructions member.

Fixture rendering is deliberately test-local.  It exercises production
registration and artifact validation, but proves no rendering or semantic
quality claim.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


# This is an author-side gate. The payload must never carry this test beneath
# the guide, because private package installation rejects test paths.
REPO = Path(__file__).resolve().parents[1]
GUIDES = REPO / "claude" / "guides"
WRITING = GUIDES / "slide-writing"
GUIDE_PATH = GUIDES / "slide-writing.md"
PAIR_PATH = WRITING / "scripts" / "pair.py"
RENDER_PATH = WRITING / "scripts" / "render.mjs"
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / "compose"))

from instructions_catalog import compile_items, load_catalog  # noqa: E402
from instructions_install import InstructionsInstaller  # noqa: E402
from instructions_store import InstructionsStore  # noqa: E402


def load_pair_module():
    spec = importlib.util.spec_from_file_location("slide_pair_under_test", PAIR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PAIR = load_pair_module()


class PairCliIntegrationTests(unittest.TestCase):
    """The 16 source-protocol contracts, run against isolated runtime copies."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="slide-pair-gate-")
        self.root = Path(self.temp.name)
        self.guides = self.root / "guides"
        self.base = self.guides / "slide-writing"
        self.guide = self.guides / "slide-writing.md"
        (self.base / "scripts").mkdir(parents=True)
        for source, target in ((GUIDE_PATH, self.guide),
                               (PAIR_PATH, self.base / "scripts" / "pair.py"),
                               (RENDER_PATH, self.base / "scripts" / "render.mjs")):
            shutil.copyfile(source, target)
        self.source = self.root / "source.md"
        self.source.write_text("# Fixture source\n\nA decision with supporting evidence.\n", encoding="utf-8")
        self.spec = self.root / "spec.json"
        self.write_json(self.spec, {"title": "Fixture deck", "audience": "test"})
        self.playwright, self.browser = self.root / "playwright.mjs", self.root / "browser"
        self.playwright.write_text("// fixture-only placeholder\n", encoding="utf-8")
        self.browser.write_text("fixture-only placeholder\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def write_json(path: Path, value: object) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")

    @staticmethod
    def read_json(path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))

    def cli(self, *args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run([sys.executable, "-B", str(PAIR_PATH), "--base", str(self.base), *args],
                                cwd=self.root, text=True, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, expected,
                         f"CLI {args!r} returned {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        return result

    def error(self, needle: str, *args: str) -> None:
        self.assertIn(needle.lower(), self.cli(*args, expected=2).stderr.lower())

    def criteria(self) -> list[dict[str, str]]:
        return PAIR.parse_criteria(self.guide.read_bytes().decode("utf-8"))

    def prepare(self, name="job") -> Path:
        job = self.root / name
        self.cli("prepare", "--source", str(self.source), "--spec", str(self.spec), "--job", str(job))
        self.assertTrue((job / "manifest.json").is_file())
        return job

    def render_fixture(self, job: Path, omit_png=False):
        """Fixture-only renderer; the production render registration remains live."""
        calls: list[list[str]] = []
        def fake(command: list[str], **kwargs: object):
            calls.append(command)
            self.assertFalse(kwargs["shell"])
            self.assertEqual(Path(command[1]).resolve(), (self.base / "scripts" / "render.mjs").resolve())
            self.assertEqual(Path(command[2]).resolve(), (job / "sealed" / "output" / "deck.html").resolve())
            output = Path(command[3]); output.joinpath("deck.pdf").write_bytes(b"fixture pdf")
            if not omit_png: output.joinpath("page-0001.png").write_bytes(b"fixture png")
            self.write_json(output / "measurements.json", {"pages": [{"id": "p0001", "source_page": "", "title": "Fixture", "width": 1400, "height": 1000, "text": [], "outside": []}]})
            return subprocess.CompletedProcess(command, 0, stdout="fixture renderer")
        stderr = io.StringIO()
        with mock.patch.object(PAIR.subprocess, "run", side_effect=fake), contextlib.redirect_stderr(stderr):
            code = PAIR.main(["--base", str(self.base), "render", "--job", str(job), "--node", sys.executable,
                              "--playwright", str(self.playwright), "--browser", str(self.browser)])
        return code, stderr.getvalue(), calls

    def rendered(self, name="job") -> Path:
        job = self.prepare(name)
        (job / "output" / "deck.html").write_text("<section class='slide'>fixture</section>\n", encoding="utf-8")
        code, stderr, calls = self.render_fixture(job)
        self.assertEqual(code, 0, stderr); self.assertEqual(len(calls), 1)
        return job

    def observation(self, contract: dict[str, object]) -> dict[str, object]:
        pages = []
        for page_id in contract["properties"]["pages"]["exact_members"]:
            row = {}
            for field, rule in contract["properties"]["pages"]["items"]["properties"].items():
                row[field] = page_id if field == "page_id" else ("fixture observation" if rule.get("nonempty") else "")
            pages.append(row)
        return {"pages": pages}

    def submission(self, contract: dict[str, object]) -> dict[str, object]:
        items, constraints = [], contract["dynamic_constraints"]
        for criterion_id in contract["properties"]["items"]["exact_members"]:
            row = {}
            for field, rule in contract["properties"]["items"]["items"]["properties"].items():
                if field == "criterion_id": row[field] = criterion_id
                elif field == "covered_pages": row[field] = list(constraints["covered_pages"]["exact_members"])
                elif field == "evidence_refs": row[field] = [constraints["evidence_refs"]["allowed_exact"][0]]
                elif "enum" in rule: row[field] = "uncertain" if "uncertain" in rule["enum"] else rule["enum"][0]
                elif rule["type"] == "array": row[field] = []
                elif rule["type"] == "string": row[field] = "fixture structural record" if rule.get("nonempty") else ""
                else: self.fail(f"unhandled response field {field}: {rule!r}")
            items.append(row)
        return {"items": items}

    def observe(self, job: Path) -> None:
        path = self.root / f"{job.name}-observations.json"
        self.write_json(path, self.observation(self.read_json(job / "reader-request.json")["response_contract"]))
        self.cli("observe", "--job", str(job), "--request", str(job / "reader-request.json"), "--payload", str(path))

    def observed(self, name="observed") -> Path:
        job = self.rendered(name); self.observe(job); return job

    def test_protocol_fingerprint_names_the_executing_engine(self):
        job = self.prepare("binding")
        copied = self.base / "scripts" / "pair.py"; copied.write_text(copied.read_text() + "\n# revision\n")
        oracle = self.read_json(job / "input" / "ORACLE.json")
        self.assertEqual(oracle["protocol_fingerprints"]["pair_py"], hashlib.sha256(PAIR_PATH.read_bytes()).hexdigest())
        changed = subprocess.run([sys.executable, "-B", str(copied), "--base", str(self.base), "verify", "--job", str(job)], text=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(changed.returncode, 2); self.assertIn("job protocol implementation has changed", changed.stderr)

    def test_prepare_freezes_job_only_oracle_and_shared_criteria_are_exact(self):
        self.guide.write_bytes(GUIDE_PATH.read_bytes().replace(b"\n", b"\r\n"))
        self.cli("check")
        job = self.prepare()
        oracle = self.read_json(job / "input" / "ORACLE.json")
        writer = self.read_json(job / "writer-request.json")
        self.assertEqual(writer["criteria"], PAIR.common_criteria(oracle["criteria"]))
        self.assertEqual((job / "input" / self.guide.name).read_bytes(), self.guide.read_bytes())
        self.assertEqual(oracle["source_document"], self.guide.read_bytes().decode("utf-8"))
        self.assertEqual(oracle["source_document_fingerprint"], hashlib.sha256(self.guide.read_bytes()).hexdigest())
        self.assertFalse((self.base / "ORACLE.json").exists())
        self.assertIn(writer["criteria"], (job / "writer.md").read_bytes().decode("utf-8"))
        self.cli("verify", "--job", str(job))
        self.error("already exists", "prepare", "--source", str(self.source), "--spec", str(self.spec), "--job", str(job))

    def test_check_rejects_invalid_primary_guide_at_the_parser(self):
        pristine = GUIDE_PATH.read_text(encoding="utf-8")
        cases = [(pristine + "\nsubstantive stray text\n", "substantive text outside"),
                 (pristine.replace("criterion:c0001", "criterion:c0000", 1), "nonempty, unique"),
                 (PAIR.CRITERION_RE.sub("<!-- criterion:c0000 -->\n<!-- /criterion -->", pristine, count=1), "criterion c0000 is empty")]
        for content, message in cases:
            self.guide.write_text(content, encoding="utf-8"); self.error(message, "check")
            shutil.copyfile(GUIDE_PATH, self.guide)

    def test_check_rejects_unbalanced_markers_before_criterion_count_can_shrink(self):
        pristine = GUIDE_PATH.read_text(encoding="utf-8")
        cases = [(pristine.replace("<!-- /criterion -->", "", 1), "nested or unbalanced criterion markers"),
                 (pristine.replace("<!-- criterion:c0000 -->", "<!-- criterion:c0000 -->\n<!-- criterion:nested -->", 1), "nested or unbalanced criterion markers"),
                 (pristine.replace("<!-- criterion:c0000 -->", "<!-- /criterion -->\n<!-- criterion:c0000 -->", 1), "closing criterion marker without an opening marker")]
        for content, message in cases:
            self.guide.write_text(content, encoding="utf-8"); self.error(message, "check")
            self.assertFalse((self.base / "ORACLE.json").exists()); shutil.copyfile(GUIDE_PATH, self.guide)
        self.assertEqual(len(self.criteria()), 12)

    def test_criteria_edit_regenerates_packets_and_invalidates_old_job(self):
        old = self.prepare("old"); old_writer = self.read_json(old / "writer-request.json")
        path = self.guide
        path.write_text(path.read_text(encoding="utf-8").replace(
            "<!-- criterion:c0000 -->", "<!-- criterion:c0000 -->\n변경된 핵심 판단", 1), encoding="utf-8")
        self.cli("check"); new = self.prepare("new")
        self.assertNotEqual(old_writer["criteria"], self.read_json(new / "writer-request.json")["criteria"])
        self.error("origin guide changed", "verify", "--job", str(old))

    def test_prepared_job_rejects_source_spec_and_writer_packet_edits(self):
        for kind, message in (("source", "origin source changed"), ("spec", "origin spec changed"),
                              ("guide", "origin guide changed"), ("frozen-guide", "frozen guide snapshot changed"),
                              ("oracle", "frozen ORACLE changed"), ("writer", "writer.md is stale or edited")):
            job = self.prepare(kind)
            if kind == "source": self.source.write_text("changed\n")
            elif kind == "spec": self.write_json(self.spec, {"title": "changed"})
            elif kind == "guide": self.guide.write_bytes(self.guide.read_bytes() + b"\n")
            elif kind == "frozen-guide": (job / "input" / self.guide.name).write_bytes(b"changed\n")
            elif kind == "oracle": (job / "input" / "ORACLE.json").write_bytes(b"{}")
            else: (job / "writer.md").write_text("manual edit\n")
            self.error(message, "verify", "--job", str(job))
            self.source.write_text("# Fixture source\n\nA decision with supporting evidence.\n")
            self.write_json(self.spec, {"title": "Fixture deck", "audience": "test"})
            shutil.copyfile(GUIDE_PATH, self.guide)

    def test_manifest_state_cannot_claim_unregistered_lifecycle_stages(self):
        for state, consume in (("rendered", "observe"), ("observed", "submit"), ("submitted", None)):
            job = self.prepare(state); manifest = self.read_json(job / "manifest.json"); manifest["state"] = state; self.write_json(job / "manifest.json", manifest)
            message = f"job state {state} does not match registered lifecycle records (prepared)"; self.error(message, "verify", "--job", str(job))
            if consume == "observe":
                payload = self.root / f"{state}.json"; self.write_json(payload, {"pages": []}); self.error(message, "observe", "--job", str(job), "--request", str(job / "reader-request.json"), "--payload", str(payload))
            elif consume == "submit": self.error(message, "submit", "--job", str(job), "--request", str(job / "judge-request.json"), "--payload", str(self.root / "missing.json"))

    def test_manifest_request_set_cannot_claim_unregistered_lifecycle_prerequisites(self):
        job = self.prepare("request-set"); manifest = self.read_json(job / "manifest.json"); manifest["requests"]["reader"] = "invented"; self.write_json(job / "manifest.json", manifest)
        self.error("manifest request stages do not match lifecycle state", "verify", "--job", str(job))
        (job / "output" / "deck.html").write_text("fixture\n"); code, stderr, calls = self.render_fixture(job)
        self.assertEqual(code, 2); self.assertIn("manifest request stages", stderr); self.assertEqual(calls, [])

    def test_actual_lifecycle_records_verify_at_each_normal_stage(self):
        prepared = self.prepare("prepared"); self.cli("verify", "--job", str(prepared))
        rendered = self.rendered("rendered"); self.cli("verify", "--job", str(rendered))
        observed = self.observed("observed"); self.cli("verify", "--job", str(observed))
        common = self.read_json(observed / "writer-request.json")["criteria"]
        for stage in ("writer", "reader", "judge"):
            request = self.read_json(observed / f"{stage}-request.json")
            self.assertEqual(request["criteria"], common)
            self.assertIn(common, (observed / f"{stage}.md").read_bytes().decode("utf-8"))
        payload = self.root / "submit.json"; self.write_json(payload, self.submission(self.read_json(observed / "judge-request.json")["response_contract"]))
        self.cli("submit", "--job", str(observed), "--request", str(observed / "judge-request.json"), "--payload", str(payload)); self.cli("verify", "--job", str(observed))

    def test_fixture_render_registers_reader_and_detects_missing_artifacts(self):
        job = self.prepare(); (job / "output" / "deck.html").write_text("fixture\n")
        code, stderr, calls = self.render_fixture(job, omit_png=True); self.assertEqual(code, 2); self.assertIn("page-0001.png", stderr); self.assertEqual(len(calls), 1)
        self.assertEqual(self.read_json(job / "manifest.json")["state"], "prepared")
        job = self.rendered("complete"); reader, writer = self.read_json(job / "reader-request.json"), self.read_json(job / "writer-request.json")
        self.assertEqual(reader["criteria"], writer["criteria"]); self.assertNotIn("source", reader); self.assertEqual(reader["rendered_pages"], ["p0001"])
        (job / "output" / "deck.html").write_text("tampered\n"); self.error("writer output differs from sealed", "verify", "--job", str(job))

    def test_render_record_requires_current_schema_zero_exit_and_derived_command_tail(self):
        job = self.rendered("renderer-record")
        manifest_path = job / "manifest.json"
        original = manifest_path.read_bytes()
        self.cli("verify", "--job", str(job))
        cases = [
            ("exit", lambda record: record.update({"exit_code": 99}), "integer exit code 0"),
            ("bool", lambda record: record.update({"exit_code": False}), "integer exit code 0"),
            ("executable", lambda record: record["command"].__setitem__(0, ""), "renderer executable"),
            ("keys", lambda record: record.update({"extra": "forbidden"}), "renderer record has unsupported"),
        ]
        for index, name in enumerate(("renderer", "sealed-output", "render-dir", "sealed-root"), 1):
            cases.append((name, lambda record, index=index: record["command"].__setitem__(index, "fake"), "does not match this job"))
        for _name, mutate, message in cases:
            manifest = self.read_json(manifest_path)
            mutate(manifest["render"]["renderer"])
            self.write_json(manifest_path, manifest)
            self.error(message, "verify", "--job", str(job))
            manifest_path.write_bytes(original)

    def test_render_rejects_changed_origin_and_frozen_source_before_starting_renderer(self):
        for kind, message in (("origin", "origin source changed after prepare"), ("frozen", "frozen source snapshot changed")):
            job = self.prepare(kind); (job / "output" / "deck.html").write_text("fixture\n")
            target = self.source if kind == "origin" else job / "input" / "source" / self.source.name; target.write_text("changed\n")
            code, stderr, calls = self.render_fixture(job); self.assertEqual(code, 2); self.assertIn(message, stderr); self.assertEqual(calls, [])
            self.source.write_text("# Fixture source\n\nA decision with supporting evidence.\n")

    def test_observe_rejects_tampered_png_and_measurements_before_payload_consumption(self):
        for kind, relative in (("png", "render/page-0001.png"), ("measurements", "render/measurements.json")):
            job = self.rendered(kind); target = job / relative
            if kind == "png": target.write_bytes(b"tampered")
            else: measurement = self.read_json(target); measurement["pages"][0]["title"] = "tampered"; self.write_json(target, measurement)
            payload = self.root / f"{kind}.json"; self.write_json(payload, self.observation(self.read_json(job / "reader-request.json")["response_contract"]))
            self.error(f"rendered artifact changed: {relative}", "observe", "--job", str(job), "--request", str(job / "reader-request.json"), "--payload", str(payload)); self.assertFalse((job / "observations.json").exists())

    def test_observe_requires_current_request_and_complete_schema_then_preserves_observations(self):
        job = self.rendered(); request = job / "reader-request.json"; valid = self.observation(self.read_json(request)["response_contract"]); payload = self.root / "observe.json"
        self.write_json(payload, {"pages": []}); self.error("every rendered page exactly once", "observe", "--job", str(job), "--request", str(request), "--payload", str(payload))
        self.write_json(payload, {**valid, "runtime": "forbidden"}); self.error("runtime-owned fields", "observe", "--job", str(job), "--request", str(request), "--payload", str(payload))
        copied = self.root / "copied-request.json"; shutil.copyfile(request, copied); self.write_json(payload, valid); self.error("this job's current request", "observe", "--job", str(job), "--request", str(copied), "--payload", str(payload))
        self.cli("observe", "--job", str(job), "--request", str(request), "--payload", str(payload)); judge = self.read_json(job / "judge-request.json")
        self.assertIn("source_lines", judge); self.assertEqual(judge["spec"], self.read_json(self.spec)); self.assertIn("fixture observation", (job / "judge.md").read_text())
        (job / "judge-request.json").write_text("manual edit\n"); self.error("judge-request.json is stale or edited", "verify", "--job", str(job))

    def test_observations_record_requires_canonical_path_and_exact_schema(self):
        job = self.observed("observations-record")
        manifest_path = job / "manifest.json"
        original = manifest_path.read_bytes()
        self.cli("verify", "--job", str(job))
        for mutate, message in (
            (lambda record: record.update({"path": "missing.json"}), "observations record path is not canonical"),
            (lambda record: record.update({"extra": "forbidden"}), "manifest observations has unsupported"),
        ):
            manifest = self.read_json(manifest_path)
            mutate(manifest["observations"])
            self.write_json(manifest_path, manifest)
            self.error(message, "verify", "--job", str(job))
            manifest_path.write_bytes(original)

    def test_generated_response_contracts_expose_typed_payloads_and_accept_fixture_shape(self):
        job = self.rendered("contract"); reader = self.read_json(job / "reader-request.json"); contract = reader["response_contract"]
        self.assertEqual(contract["required"], ["pages"]); self.assertEqual(contract["properties"]["pages"]["exact_members"], reader["rendered_pages"])
        self.assertEqual({key: rule["type"] for key, rule in contract["properties"]["pages"]["items"]["properties"].items()}, {"page_id": "string", "text_reading": "string", "visual_reading": "string", "uncertainties": "string"})
        observation = self.root / "observation.json"; self.write_json(observation, self.observation(contract)); self.cli("observe", "--job", str(job), "--request", str(job / "reader-request.json"), "--payload", str(observation))
        judge = self.read_json(job / "judge-request.json"); judge_contract = judge["response_contract"]; fields = judge_contract["properties"]["items"]["items"]["properties"]
        self.assertEqual(fields["covered_pages"]["type"], "array"); self.assertEqual(fields["evidence_refs"]["type"], "array"); self.assertEqual(fields["verdict"]["enum"], ["satisfied", "revise", "uncertain", "not_applicable"])
        invalid = self.submission(judge_contract); invalid["items"][0].update({"verdict": "pass", "covered_pages": reader["rendered_pages"][0], "evidence_refs": "page:p0001"})
        path = self.root / "invalid-submit.json"; self.write_json(path, invalid); self.error("judge item verdict is invalid", "submit", "--job", str(job), "--request", str(job / "judge-request.json"), "--payload", str(path))
        invalid["items"][0]["verdict"] = "satisfied"; self.write_json(path, invalid); self.error("covered_pages must be a nonempty array", "submit", "--job", str(job), "--request", str(job / "judge-request.json"), "--payload", str(path))

    def test_submit_rejects_changed_origin_spec_or_render_before_payload_consumption(self):
        for kind, message in (("source", "origin source changed after prepare"), ("spec", "origin spec changed after prepare"), ("render", "rendered artifact changed: render/page-0001.png")):
            job = self.observed(kind)
            if kind == "source": self.source.write_text("changed\n")
            elif kind == "spec": self.write_json(self.spec, {"title": "changed"})
            else: (job / "render" / "page-0001.png").write_bytes(b"tampered")
            payload = self.root / f"{kind}-submit.json"; self.write_json(payload, self.submission(self.read_json(job / "judge-request.json")["response_contract"]))
            self.error(message, "submit", "--job", str(job), "--request", str(job / "judge-request.json"), "--payload", str(payload)); self.assertFalse((job / "review.json").exists())
            self.source.write_text("# Fixture source\n\nA decision with supporting evidence.\n"); self.write_json(self.spec, {"title": "Fixture deck", "audience": "test"})

    def test_submit_rejects_schema_coverage_and_reference_errors_then_accepts_complete_record(self):
        job = self.observed("submit-contract"); request = job / "judge-request.json"; valid = self.submission(self.read_json(request)["response_contract"])
        cases = [("missing", {"items": valid["items"][:-1]}, "every canonical criterion"), ("duplicate", json.loads(json.dumps(valid)), "duplicate or unknown"), ("coverage", json.loads(json.dumps(valid)), "covered_pages"), ("refs", json.loads(json.dumps(valid)), "evidence_refs"), ("unknown", json.loads(json.dumps(valid)), "runtime-owned fields")]
        cases[1][1]["items"][-1]["criterion_id"] = cases[1][1]["items"][0]["criterion_id"]; cases[2][1]["items"][0]["covered_pages"] = []; cases[3][1]["items"][0]["evidence_refs"] = ["source:L9999"]; cases[4][1]["items"][0]["runtime"] = "forbidden"
        for name, payload, message in cases:
            path = self.root / f"{name}.json"; self.write_json(path, payload); self.error(message, "submit", "--job", str(job), "--request", str(request), "--payload", str(path))
        accepted = self.root / "accepted.json"; self.write_json(accepted, valid); self.cli("submit", "--job", str(job), "--request", str(request), "--payload", str(accepted))
        report = (job / "review.md").read_text(); self.assertIn("does not prove semantic quality", report); self.assertNotIn("global PASS", report)
        (job / "review.md").write_text("manual edit\n"); self.error("review output changed", "verify", "--job", str(job))


class InstructionsProjectionTests(unittest.TestCase):
    """Catalog and compiler checks for the package-facing guide runtime."""

    def setUp(self) -> None:
        self.catalog = load_catalog(REPO)
        self.item = next(item for item in self.catalog["items"] if item["item_id"] == "skill-slide-writing")

    def test_source_projection_is_fresh_and_complete(self):
        expected = {"guides/slide-writing.md": GUIDE_PATH.read_text(encoding="utf-8")}
        expected.update({f"guides/slide-writing/{path.relative_to(WRITING).as_posix()}": path.read_text(encoding="utf-8")
                         for path in sorted(WRITING.rglob("*")) if path.is_file()})
        self.assertEqual(self.item["members"], expected)
        self.assertEqual(set(expected), {"guides/slide-writing.md", "guides/slide-writing/RUNBOOK.md",
                                         "guides/slide-writing/scripts/pair.py", "guides/slide-writing/scripts/render.mjs"})
        self.assertEqual(self.item["primary_member"], "guides/slide-writing.md")
        self.assertEqual(self.item["body"], expected["guides/slide-writing.md"])
        self.assertFalse(any("ORACLE" in member or "PRINCIPLES" in member for member in expected))
        check = subprocess.run([sys.executable, "-B", str(PAIR_PATH), "--base", str(WRITING), "check"], text=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_catalog_selection_exposes_complete_members_once_for_each_domain(self):
        self.assertEqual(self.item["kind"], "guide")
        self.assertEqual(set(self.item["domains"]), {"office-work", "visualization-docs"})
        for domain in self.item["domains"]:
            selected = [item for item in self.catalog["items"] if item["tier"] in {"core", "infra"} or domain in item["domains"]]
            matches = [item for item in selected if item["ref"] == self.item["ref"]]
            self.assertEqual(len(matches), 1, domain)
            self.assertEqual(matches[0]["members"], self.item["members"])

    def test_compiled_snapshot_relocates_complete_runtime_and_check_prepare_are_read_only(self):
        with tempfile.TemporaryDirectory(prefix="slide-writing-snapshot-") as temp:
            root = Path(temp); snapshot = root / "snapshot"; result = compile_items([self.item], snapshot, "claude")
            emitted = snapshot / "items" / next(path.name for path in (snapshot / "items").iterdir())
            runtime = emitted / "guides" / "slide-writing"
            self.assertEqual({path.relative_to(emitted).as_posix() for path in emitted.rglob("*") if path.is_file()}, set(self.item["members"]))
            self.assertIn("slide-writing/RUNBOOK.md", (emitted / "guides" / "slide-writing.md").read_text(encoding="utf-8"))
            self.assertTrue((runtime / "RUNBOOK.md").is_file())
            self.assertTrue(all(path.startswith("items/") or path in {"launch-content/instructions.md", "router/relevant.md"}
                                for path in result["files"]))
            before = {path.relative_to(emitted).as_posix(): path.read_bytes() for path in emitted.rglob("*") if path.is_file()}
            job, source, spec = root / "job", root / "source.md", root / "spec.json"; source.write_text("# source\n"); spec.write_text('{"title":"fixture"}\n')
            for command in (("check",), ("prepare", "--source", str(source), "--spec", str(spec), "--job", str(job))):
                run = subprocess.run([sys.executable, "-B", str(runtime / "scripts" / "pair.py"), "--base", str(runtime), *command], text=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(before, {path.relative_to(emitted).as_posix(): path.read_bytes() for path in emitted.rglob("*") if path.is_file()})
            self.assertEqual((job / "input" / "slide-writing.md").read_bytes(), (emitted / "guides" / "slide-writing.md").read_bytes())
            self.assertTrue((job / "input" / "ORACLE.json").is_file())

    def test_primary_body_edit_changes_only_the_next_compiled_job_oracle(self):
        with tempfile.TemporaryDirectory(prefix="slide-writing-store-edit-") as temp:
            root = Path(temp)
            store = InstructionsStore(REPO, root / "state", root / "user")
            store.install(["office-work"])
            source, spec = root / "source.md", root / "spec.json"
            source.write_text("# source\n", encoding="utf-8")
            spec.write_text('{"title":"fixture"}\n', encoding="utf-8")

            def prepare_from(snapshot: dict[str, object], name: str) -> dict[str, object]:
                snapshot_root, job = Path(snapshot["path"]), root / f"job-{name}"
                runtimes = list(snapshot_root.glob("items/*/guides/slide-writing"))
                self.assertEqual(len(runtimes), 1)
                runtime = runtimes[0]
                result = subprocess.run([sys.executable, "-B", str(runtime / "scripts" / "pair.py"), "--base", str(runtime),
                                         "prepare", "--source", str(source), "--spec", str(spec), "--job", str(job)],
                                        text=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertEqual(result.returncode, 0, result.stderr)
                return {"runtime": runtime, "job": job,
                        "oracle": json.loads((job / "input" / "ORACLE.json").read_text(encoding="utf-8"))}

            original_snapshot = store.snapshot("claude")
            original = prepare_from(original_snapshot, "original")
            shown = store.show(self.item["ref"])
            edited = copy.deepcopy(shown["item"])
            primary = edited["primary_member"]
            changed_body = edited["body"].replace("<!-- criterion:c0000 -->", "<!-- criterion:c0000 -->\nPersonal criterion edit", 1)
            edited["body"] = changed_body
            edited["members"][primary] = changed_body
            plan = store.plan({"operation": "update", "ref": self.item["ref"], "item_digest": shown["digest"],
                               "patch": {"body": changed_body, "members": edited["members"]}})
            store.apply(plan["plan_id"], plan["expected_revision"])
            changed_snapshot = store.snapshot("claude")
            changed = prepare_from(changed_snapshot, "changed")
            self.assertNotEqual(changed["oracle"]["criteria"], original["oracle"]["criteria"])
            old_verify = subprocess.run([sys.executable, "-B", str(original["runtime"] / "scripts" / "pair.py"),
                                         "--base", str(original["runtime"]), "verify", "--job", str(original["job"])],
                                        text=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(old_verify.returncode, 0, old_verify.stderr)

            current = store.show(self.item["ref"])
            plan = store.plan({"operation": "update", "ref": self.item["ref"], "item_digest": current["digest"],
                               "patch": {"body": self.item["body"], "members": self.item["members"]}})
            store.apply(plan["plan_id"], plan["expected_revision"])
            restored = prepare_from(store.snapshot("claude"), "restored")
            self.assertEqual(restored["oracle"]["criteria"], original["oracle"]["criteria"])

    def test_default_compiled_bundle_has_no_private_path_binary_asset_or_test_payload(self):
        with tempfile.TemporaryDirectory(prefix="slide-writing-bundle-") as temp:
            destination = Path(temp) / "bundle"; compile_items(self.catalog["items"], destination, "codex")
            files = [path for path in destination.rglob("*") if path.is_file()]
            self.assertTrue(files)
            for path in files:
                relative, payload = path.relative_to(destination).as_posix(), path.read_bytes()
                self.assertNotIn(b"/Users/kangmin/Documents/workbench-TA", payload, relative)
                self.assertNotIn(b"\0", payload, relative)
                self.assertNotIn("test_", relative, relative)
                self.assertNotIn("/test/", f"/{relative}", relative)
                self.assertNotIn("/tests/", f"/{relative}", relative)
                self.assertNotIn(b"test_pair.py", payload, relative)

    def test_private_installer_accepts_the_runtime_payload_without_author_test_files(self):
        with tempfile.TemporaryDirectory(prefix="slide-writing-install-") as temp:
            root = Path(temp); home, state, user = root / "home", root / "state", root / "user"
            installer = InstructionsInstaller(REPO, {"HOME": str(home), "AGENT_BIOS_STATE_DIR": str(state),
                                               "AGENT_BIOS_INSTRUCTIONS_DIR": str(user), "CLAUDE_CONFIG_DIR": str(home / ".claude"),
                                               "CODEX_HOME": str(home / ".codex"), "ZDOTDIR": str(home)})
            result = installer.install("office-work")
            release = Path(result["record"]["package_root"])
            expected = {"slide-writing.md"}
            expected.update({f"slide-writing/{path.relative_to(WRITING).as_posix()}" for path in WRITING.rglob("*") if path.is_file()})
            guide_root = release / "claude" / "guides"
            actual = {path.relative_to(guide_root).as_posix() for path in [guide_root / "slide-writing.md", *(guide_root / "slide-writing").rglob("*")]
                      if path.is_file()}
            self.assertEqual(actual, expected)
            self.assertFalse(any(part == "tests" or part.startswith("test_")
                                 for path in actual for part in Path(path).parts))
            self.assertTrue(installer.verify()["stored"])


if __name__ == "__main__":
    unittest.main()
