"""Changed-path checks for the canonical corpus catalog and private compiler."""
from __future__ import annotations

import copy
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

from corpus_catalog import CatalogError, compile_items, load_catalog, normalize_content, update_content


REPO = pathlib.Path(__file__).resolve().parent.parent


class CorpusCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_catalog(REPO)

    def test_core_catalog_accounts_for_every_manifest_item(self) -> None:
        manifest = json.loads((REPO / "compose" / "domains.json").read_text(encoding="utf-8"))
        expected = (len(manifest["bullets"]) + len(manifest["guides"]) +
                    len(manifest["hooks"]) + len(manifest["agents"]) +
                    len(manifest["skills"]))
        self.assertEqual(self.catalog["schema_version"], 1)
        self.assertEqual(len(self.catalog["items"]), expected)
        refs = [item["ref"] for item in self.catalog["items"]]
        self.assertEqual(len(refs), len(set(refs)))
        self.assertTrue(all(item["members"] for item in self.catalog["items"]))
        self.assertTrue(all(item["members"][item["primary_member"]] == item["body"]
                            for item in self.catalog["items"]))
        self.assertFalse(any(item.get("content_conflict") for item in self.catalog["items"]))

    def test_ref_survives_body_and_surface_edit(self) -> None:
        original = next(item for item in self.catalog["items"] if item["kind"] == "guide")
        edited = copy.deepcopy(original)
        edited["body"] += "\nEdited for a future snapshot.\n"
        edited["members"] = {path: text + "\nEdited for a future snapshot.\n"
                             for path, text in edited["members"].items()}
        edited["surface"] = "requested"
        with tempfile.TemporaryDirectory() as temp:
            compiled = compile_items([edited], pathlib.Path(temp), "codex")
        self.assertEqual(compiled["item_refs"], [original["ref"]])

    def test_bundle_member_paths_are_rewritten_with_the_primary(self) -> None:
        item = next(copy.deepcopy(row) for row in self.catalog["items"] if row["item_id"] == "skill-slide-writing")
        primary = item["primary_member"]
        companion = "guides/slide-writing/RUNBOOK.md"
        item["members"][primary] += "\nclaude/guides/slide-writing/RUNBOOK.md\n"
        item["body"] = item["members"][primary]
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            compiled = compile_items([item], root, "codex")
            copied = next(root.glob("items/*/guides/slide-writing.md"))
            target = copied.parent / "slide-writing" / "RUNBOOK.md"
            self.assertTrue(target.is_file())
            self.assertIn(str(target), copied.read_text())
            router = (root / "router/relevant.md").read_text()
            self.assertIn(str(copied), router)
            self.assertIn("when creating, revising, or reviewing slides", router)
            self.assertEqual(compiled["item_refs"], [item["ref"]])
            self.assertIn(companion, item["members"])

    def test_relevant_router_does_not_promote_example_metadata_to_a_condition(self) -> None:
        item = next(copy.deepcopy(row) for row in self.catalog["items"] if row["kind"] == "guide")
        body = "# A guide\n\n```yaml\ndescription: Only an example, not a routing condition.\n```\n"
        item["body"] = body
        item["members"][item["primary_member"]] = body
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            compile_items([item], root, "codex")
            router = (root / "router/relevant.md").read_text()
            self.assertIn(item["ref"], router)
            self.assertNotIn("Only an example", router)

    def test_requested_compile_uses_explicit_primary_member_not_member_order(self) -> None:
        item = {
            "package_id": "@local/personal", "item_id": "ordered", "title": "Ordered",
            "body": "Primary procedure.\n", "primary_member": "guides/primary.md",
            "surface": "requested", "tier": "domain", "domains": ["personal"], "kind": "guide",
            # The auxiliary member deliberately comes first: its order is not authority.
            "members": {"references/aux.md": "Auxiliary.\n", "guides/primary.md": "Primary procedure.\n"},
            "origin": {"source_path": "personal/primary.md"},
        }
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            compiled = compile_items([item], root, "codex")
        requested = next(line for line in compiled["instruction_text"].splitlines() if "Ordered" in line)
        self.assertIn("/guides/primary.md", requested)
        self.assertNotIn("/references/aux.md", requested)

    def test_legacy_rule_newline_normalizes_to_the_rule_member(self) -> None:
        legacy = {
            "body": "A generated rule.",
            "members": {"reference.md": "Reference.\n", "rule.md": "A generated rule.\n"},
        }
        normalized = normalize_content(legacy, allow_legacy=True)
        self.assertEqual("rule.md", normalized["primary_member"])
        self.assertEqual("A generated rule.\n", normalized["body"])
        self.assertNotIn("content_conflict", normalized)
        self.assertEqual("A generated rule.", legacy["body"])

    def test_conflicting_body_and_primary_member_update_fails_by_name(self) -> None:
        item = {
            "body": "Before\n", "primary_member": "content.md",
            "members": {"content.md": "Before\n", "reference.md": "Reference\n"},
        }
        with self.assertRaisesRegex(CatalogError, "body conflicts with primary_member"):
            update_content(item, {"body": "Body edit\n", "members": {
                "content.md": "Member edit\n", "reference.md": "Reference\n",
            }})

    def test_body_and_member_only_updates_keep_primary_member_canonical(self) -> None:
        item = {
            "body": "Before\n", "primary_member": "content.md",
            "members": {"content.md": "Before\n", "reference.md": "Reference\n"},
        }
        body_edited = update_content(item, {"body": "Edited through body\n"})
        self.assertEqual("Edited through body\n", body_edited["members"]["content.md"])
        members_edited = update_content(item, {"members": {
            "content.md": "Edited through members\n", "reference.md": "Reference\n",
        }})
        self.assertEqual("Edited through members\n", members_edited["body"])
        self.assertEqual("content.md", members_edited["primary_member"])

    def test_divergent_sole_legacy_member_stays_conflicted_until_an_explicit_edit(self) -> None:
        legacy = {"body": "Old body\n", "members": {"content.md": "New member\n"}}
        conflicted = normalize_content(legacy, allow_legacy=True)
        self.assertIn("content_conflict", conflicted)
        self.assertNotIn("primary_member", conflicted)
        self.assertEqual("Old body\n", conflicted["body"])
        self.assertEqual("New member\n", conflicted["members"]["content.md"])
        titled = update_content(conflicted, {"title": "Metadata only"})
        self.assertIn("content_conflict", titled)
        resolved = update_content(conflicted, {"body": "Reconciled body\n"})
        self.assertEqual("content.md", resolved["primary_member"])
        self.assertEqual("Reconciled body\n", resolved["members"]["content.md"])

    def test_strict_primary_and_body_disagreement_is_rejected(self) -> None:
        with self.assertRaisesRegex(CatalogError, "body conflicts with primary_member"):
            normalize_content({
                "body": "Stale\n", "primary_member": "content.md",
                "members": {"content.md": "Canonical\n"},
            })

    def test_ambiguous_legacy_content_is_visible_but_cannot_compile(self) -> None:
        item = {
            "package_id": "@local/personal", "item_id": "ambiguous", "title": "Ambiguous",
            "body": "Stale body\n", "surface": "requested", "tier": "domain",
            "domains": ["personal"], "kind": "guide",
            "members": {"guides/one.md": "One\n", "guides/two.md": "Two\n"},
            "origin": {"source_path": "personal/ambiguous.md"},
        }
        normalized = normalize_content(item, allow_legacy=True)
        self.assertIn("content_conflict", normalized)
        self.assertNotIn("primary_member", normalized)
        self.assertEqual(item["members"], normalized["members"])
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(CatalogError, "content_conflict"):
                compile_items([normalized], pathlib.Path(temp), "codex")

    def test_native_agent_route_uses_edited_frontmatter_name(self) -> None:
        item = copy.deepcopy(next(item for item in self.catalog['items'] if item['item_id'] == 'agent-sweep'))
        item['body'] = item['body'].replace('name: sweep\n', 'name: verification-sweep\n', 1)
        item['members'] = {name: item['body'] for name in item['members']}
        with tempfile.TemporaryDirectory() as temp:
            compiled = compile_items([item], pathlib.Path(temp), 'claude', native=True)
            self.assertIn(':verification-sweep', compiled['instruction_text'])
            self.assertNotIn(':sweep`', compiled['instruction_text'])
            emitted = next((pathlib.Path(temp) / compiled['assets']['claude_plugins'][0] / 'agents').glob('*.md'))
            self.assertTrue(emitted.read_text().startswith(item['body']))

    def test_invalid_hook_code_stays_unavailable_without_plugin_artifacts(self) -> None:
        item = copy.deepcopy(next(item for item in self.catalog['items'] if item['kind'] == 'hook'))
        item['body'] = 'def unfinished('
        item['members'] = {name: item['body'] for name in item['members']}
        with tempfile.TemporaryDirectory() as temp:
            compiled = compile_items([item], pathlib.Path(temp), 'claude', native=True)
            self.assertEqual(compiled['assets']['claude_plugins'], [])
            self.assertIn('not valid Python', compiled['unavailable'][0]['reason'])
            self.assertFalse(list(pathlib.Path(temp).rglob('plugin.json')))

    def test_private_compile_rewrites_known_guide_resources_for_both_hosts(self) -> None:
        # The complete canonical selection contains every guide target mentioned by
        # current rule/guide prose, making this an actual resource-reference probe.
        for host in ("claude", "codex"):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as temp:
                destination = pathlib.Path(temp) / "private-snapshot"
                compiled = compile_items(self.catalog["items"], destination, host)
                self.assertTrue(compiled["instruction_text"].startswith("# Activated private corpus"))
                self.assertTrue((destination / "launch-content" / "instructions.md").is_file())
                self.assertTrue((destination / "router" / "relevant.md").is_file())
                self.assertTrue(all(not pathlib.PurePosixPath(path).is_absolute()
                                    for path in compiled["files"]))
                emitted = "\n".join(
                    (destination / path).read_text(encoding="utf-8")
                    for path in compiled["files"]
                )
                self.assertNotIn("${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/", emitted)
                self.assertNotIn("${CODEX_HOME:-$HOME/.codex}/guides/", emitted)

    def test_shared_router_keeps_sibling_after_removal(self) -> None:
        def guide(item_id: str, title: str) -> dict:
            return {
                "package_id": "@local/personal", "item_id": item_id, "title": title,
                "body": f"# {title}\n", "surface": "relevant", "tier": "domain",
                "domains": ["personal"], "kind": "guide",
                "members": {f"guides/{item_id}.md": f"# {title}\n"},
                "origin": {"source_path": f"personal/{item_id}.md"},
            }
        first, sibling = guide("first-guide", "First guide"), guide("sibling-guide", "Sibling guide")
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            compile_items([first, sibling], root / "both", "claude")
            after = compile_items([sibling], root / "after", "claude")
            router = (root / "after" / "router" / "relevant.md").read_text(encoding="utf-8")
        self.assertIn(sibling["item_id"], router)
        self.assertNotIn(first["item_id"], router)
        self.assertIn("@local/personal:sibling-guide", after["item_refs"])

    def test_rejects_duplicate_and_traversal_members(self) -> None:
        item = copy.deepcopy(self.catalog["items"][0])
        duplicate = copy.deepcopy(item)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(CatalogError):
                compile_items([item, duplicate], pathlib.Path(temp), "claude")
        item["members"] = {"../escape.md": "no"}
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(CatalogError):
                compile_items([item], pathlib.Path(temp), "claude")

    def test_compiler_never_overwrites_an_existing_output(self) -> None:
        item = copy.deepcopy(self.catalog["items"][0])
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            first = compile_items([item], root, "claude")
            before = {name: (root / name).read_bytes() for name in first["files"]}
            item["body"] = "replacement"
            item["members"] = {name: "replacement" for name in item["members"]}
            with self.assertRaisesRegex(CatalogError, 'already exists'):
                compile_items([item], root, "claude")
            self.assertEqual(before, {name: (root / name).read_bytes() for name in first["files"]})

    def test_external_normalized_package_uses_the_same_validator(self) -> None:
        item = {
            "item_id": "welcome", "title": "Welcome", "body": "Hello.\n",
            "surface": "requested", "tier": "domain", "domains": ["personal"],
            "kind": "skill", "members": {"SKILL.md": "# Welcome\n"},
        }
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "manifest.json").write_text(json.dumps({
                "schema_version": 1, "package_id": "@local/example",
                "domains": {"personal": "Personal"}, "items": [item],
            }), encoding="utf-8")
            external = load_catalog(root)
        self.assertEqual(external["items"][0]["ref"], "@local/example:welcome")

    def test_native_false_keeps_event_and_delegated_items_unavailable(self) -> None:
        items = [item for item in self.catalog["items"] if item["kind"] in {"hook", "agent"}]
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            output = compile_items(items, root / "implicit", "claude")
            explicit = compile_items(items, root / "explicit", "claude", native=False)
        self.assertEqual({}, output["assets"])
        self.assertEqual({"event", "delegated"}, {row["surface"] for row in output["unavailable"]})
        self.assertFalse(any(".claude-plugin" in path for path in output["files"]))
        self.assertEqual(output["item_refs"], explicit["item_refs"])
        self.assertEqual(output["unavailable"], explicit["unavailable"])
        self.assertEqual(output["files"], explicit["files"])
        self.assertEqual(output["instruction_text"], explicit["instruction_text"])

    def test_core_hook_binding_comes_from_registered_template_and_can_be_edited(self) -> None:
        # This asserts a Bash matcher and reads tooling-gotchas-hook.py from the
        # plugin. Name that subject explicitly so catalog order cannot change it.
        hook = copy.deepcopy(next(item for item in self.catalog["items"]
                                  if item["ref"].endswith(":hook-tooling-gotchas-hook")))
        self.assertEqual({"event": "PreToolUse", "matcher": "Bash"}, hook["hook"])
        hook["hook"] = {"event": "PostToolUse", "matcher": "Write"}
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            output = compile_items([hook], root, "claude", native=True)
            plugin = root / output["assets"]["claude_plugins"][0]
            hooks = json.loads((plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual("Write", hooks["hooks"]["PostToolUse"][0]["matcher"])
        command = hooks["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        self.assertIn(sys.executable, command)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/hooks/tooling-gotchas-hook.py", command)

    def test_residual_guidance_is_retained_without_an_executable_read_advisory(self) -> None:
        refs = {item["ref"] for item in self.catalog["items"]}
        self.assertNotIn("@agent-bios/core:hook-residual-context", refs, "retired Read advisory is cataloged")
        self.assertIn("@agent-bios/core:hook-tooling-gotchas-hook", refs)
        self.assertFalse((REPO / "claude/hooks/residual-context-hook.py").exists(),
                         "retired Read advisory source is present")
        for host in ("claude", "codex"):
            guide = REPO / host / "guides/cli-multi-model-workflow.md"
            self.assertIn("Residual context", guide.read_text(encoding="utf-8"))
        settings = json.loads((REPO / "claude/settings.template.json").read_text())
        self.assertNotIn("residual-context-hook.py", json.dumps(settings), "retired Read advisory is registered")
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            output = compile_items(self.catalog["items"], root, "claude", native=True)
            self.assertTrue(output["files"])
            self.assertFalse(any("residual-context-hook" in path for path in output["files"]))
            self.assertTrue(any(path.endswith("hooks/tooling-gotchas-hook.py") for path in output["files"]))
            registrations = list(root.glob("items/*/hooks/hooks.json"))
            self.assertTrue(registrations)
            bodies = [json.loads(path.read_text()) for path in registrations]
            self.assertNotIn("residual-context-hook.py", json.dumps(bodies))
            self.assertTrue(any(row["matcher"] == "Bash" and
                                "tooling-gotchas-hook.py" in json.dumps(row["hooks"])
                                for body in bodies for row in body["hooks"].get("PreToolUse", [])))

    def test_native_claude_plugins_keep_agent_source_and_namespace_same_named_agents(self) -> None:
        source = copy.deepcopy(next(item for item in self.catalog["items"]
                                    if item["ref"].endswith(":agent-frontier")))
        second = copy.deepcopy(source)
        second["package_id"] = "@local/personal"
        second["item_id"] = "frontier-copy"
        second["ref"] = "@local/personal:frontier-copy"
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            output = compile_items([source, second], root, "claude", native=True)
            plugins = [root / relative for relative in output["assets"]["claude_plugins"]]
            namespaces = [json.loads((plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["name"]
                          for plugin in plugins]
            frontier = next(plugin for plugin in plugins if (plugin / "agents" / "frontier.md").is_file())
            emitted = (frontier / "agents" / "frontier.md").read_text(encoding="utf-8")
        self.assertEqual(2, len(set(namespaces)))
        self.assertTrue(all(f"{namespace}:frontier" in output["instruction_text"] for namespace in namespaces))
        self.assertTrue(emitted.startswith(source["members"]["agents/frontier.md"]))
        self.assertIn("disallowedTools: [Edit, Write, NotebookEdit]", emitted)
        self.assertIn("# Activated private corpus", emitted)

    @unittest.skipUnless(shutil.which("claude"), "Claude CLI required for offline plugin validation")
    def test_native_plugins_validate_and_sibling_removal_keeps_remaining_plugin(self) -> None:
        hook = copy.deepcopy(next(item for item in self.catalog["items"] if item["kind"] == "hook"))
        agent = copy.deepcopy(next(item for item in self.catalog["items"] if item["kind"] == "agent"))
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            both = compile_items([hook, agent], root / "both", "claude", native=True)
            self.assertEqual(2, len(both["assets"]["claude_plugins"]))
            for relative in both["assets"]["claude_plugins"]:
                plugin = root / "both" / relative
                components = list((plugin / "agents").glob("*.md")) + list((plugin / "hooks").glob("*.py"))
                self.assertTrue(components, f"plugin has no actual component subject: {plugin}")
                checked = subprocess.run(["claude", "plugin", "validate", "--json", str(plugin)],
                                         capture_output=True, text=True, timeout=30)
                self.assertEqual(0, checked.returncode, checked.stdout + checked.stderr)
                self.assertTrue(json.loads(checked.stdout)["success"])
            after = compile_items([agent], root / "after", "claude", native=True)
            restored = compile_items([hook, agent], root / "restored", "claude", native=True)
        self.assertEqual(1, len(after["assets"]["claude_plugins"]))
        self.assertEqual(2, len(restored["assets"]["claude_plugins"]))
        self.assertEqual([], after["unavailable"])

    def test_native_invalid_carrier_and_other_host_stay_unavailable(self) -> None:
        invalid = copy.deepcopy(next(item for item in self.catalog["items"] if item["kind"] == "guide"))
        invalid["surface"] = "event"
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            native = compile_items([invalid], root, "claude", native=True)
            self.assertFalse(any((root / path).exists() for path in native["files"] if ".claude-plugin" in path))
        self.assertEqual([], native["assets"]["claude_plugins"])
        self.assertIn("installed hook carrier", native["unavailable"][0]["reason"])
        hook_with_wrong_origin = copy.deepcopy(next(item for item in self.catalog["items"] if item["kind"] == "hook"))
        hook_with_wrong_origin["origin"]["source_path"] = "claude/hooks/not-a-python-carrier.txt"
        with tempfile.TemporaryDirectory() as temp:
            wrong_origin = compile_items([hook_with_wrong_origin], pathlib.Path(temp), "claude", native=True)
        self.assertIn("hooks/*.py carrier", wrong_origin["unavailable"][0]["reason"])

    def test_native_plugin_rejects_extra_auto_discovery_member_before_manifest_write(self) -> None:
        hook = copy.deepcopy(next(item for item in self.catalog["items"] if item["kind"] == "hook"))
        hook["members"]["agents/unselected.md"] = "---\nname: unselected\n---\nbody\n"
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            output = compile_items([hook], root, "claude", native=True)
            item_root = root / "items" / "item-_agent-bios_core_hook-tooling-gotchas-hook"
            self.assertFalse((item_root / ".claude-plugin" / "plugin.json").exists())
        self.assertEqual([], output["assets"]["claude_plugins"])
        self.assertIn("unselected agent carrier", output["unavailable"][0]["reason"])
        hook = copy.deepcopy(next(item for item in self.catalog["items"] if item["kind"] == "hook"))
        with tempfile.TemporaryDirectory() as temp:
            other = compile_items([hook], pathlib.Path(temp), "codex", native=True)
        self.assertTrue(other["assets"]["codex_hooks"]["PreToolUse"])
        self.assertEqual([], other["unavailable"])

    def test_native_rejects_invalid_typed_hook_binding(self) -> None:
        hook = copy.deepcopy(next(item for item in self.catalog["items"] if item["kind"] == "hook"))
        hook["hook"] = {"event": "NotAClaudeEvent", "matcher": "Bash"}
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(CatalogError, "unsupported hook event"):
                compile_items([hook], pathlib.Path(temp), "claude", native=True)

    def test_native_hook_rewrites_relative_guide_only_when_selected(self) -> None:
        # Paired with tooling-gotchas.md below and read back by that filename, so it names the
        # hook it means rather than taking whichever the manifest lists first.
        hook = copy.deepcopy(next(item for item in self.catalog["items"]
                                  if item["ref"].endswith(":hook-tooling-gotchas-hook")))
        guide = copy.deepcopy(next(item for item in self.catalog["items"]
                                   if item["origin"].get("source_path") == "claude/guides/tooling-gotchas.md"))
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            output = compile_items([hook, guide], root, "claude", native=True)
            plugin = root / output["assets"]["claude_plugins"][0]
            source = (plugin / "hooks" / "tooling-gotchas-hook.py").read_text(encoding="utf-8")
        self.assertIn("GUIDE = ", source)
        self.assertNotIn('GUIDE = "guides/tooling-gotchas.md"', source)
        self.assertIn(str(root / "items"), source)

    def test_hook_events_are_shared_with_explicit_host_differences(self) -> None:
        from corpus_catalog import HOOK_EVENTS_BY_HOST, validate_hook_binding
        hook = copy.deepcopy(next(item for item in self.catalog["items"] if item["kind"] == "hook"))
        for event, supported in (("PreToolUse", {"claude", "codex"}),
                                 ("PostCompact", {"claude", "codex"}),
                                 ("Interrupt", {"codex"}), ("PostToolUseFailure", {"claude"})):
            hook["hook"] = {"event": event, "matcher": "*"}
            validate_hook_binding(hook["hook"])
            for host in HOOK_EVENTS_BY_HOST:
                with self.subTest(host=host, event=event), tempfile.TemporaryDirectory() as temp:
                    output = compile_items([hook], pathlib.Path(temp), host, native=True)
                    self.assertEqual(bool(output["unavailable"]), host not in supported)
                    if host not in supported:
                        self.assertIn(f"unsupported {host} hook event", output["unavailable"][0]["reason"])
                        self.assertFalse(any(path.endswith('hooks/hooks.json') for path in output["files"]))

    def test_both_hook_adapters_execute_the_same_carrier_and_refuse_prose(self) -> None:
        import shlex
        hook = copy.deepcopy(next(item for item in self.catalog["items"] if item["item_id"] == "hook-tooling-gotchas-hook"))
        guide = copy.deepcopy(next(item for item in self.catalog["items"]
                                  if item["origin"].get("source_path") == "claude/guides/tooling-gotchas.md"))
        for host in ("claude", "codex"):
            with self.subTest(host=host), tempfile.TemporaryDirectory(prefix="hook path's ") as temp:
                root = pathlib.Path(temp)
                output = compile_items([hook, guide], root, host, native=True)
                config_file = next(root.glob('items/*/hooks/hooks.json'))
                config = json.loads(config_file.read_text())["hooks"]
                if host == "codex":
                    self.assertEqual(config, output["assets"]["codex_hooks"])
                command = config["PreToolUse"][0]["hooks"][0]["command"]
                carrier = shlex.split(command.replace('${CLAUDE_PLUGIN_ROOT}', str(config_file.parent.parent)))
                # The host expands the quoted plugin variable without re-parsing its value.
                if host == 'claude':
                    carrier = [sys.executable, str(config_file.parent / 'tooling-gotchas-hook.py')]
                for text, expected in (("git diff main..HEAD", "additionalContext"), ("echo hello", "")):
                    payload = {"session_id": "fixture", "hook_event_name": "PreToolUse",
                               "tool_name": "Bash", "tool_input": {"command": text}}
                    ran = subprocess.run(carrier, input=json.dumps(payload), text=True, capture_output=True)
                    self.assertEqual(0, ran.returncode, ran.stderr)
                    if expected:
                        self.assertIn(expected, ran.stdout)
                        self.assertIn(str(root), ran.stdout)
                    else:
                        self.assertEqual('', ran.stdout)
            prose = copy.deepcopy(guide)
            prose["surface"] = "event"
            with tempfile.TemporaryDirectory() as temp:
                output = compile_items([prose], pathlib.Path(temp), host, native=True)
                self.assertIn("installed hook carrier", output["unavailable"][0]["reason"])

    def test_native_hooks_refuse_discovery_payloads_on_both_hosts(self) -> None:
        source = next(item for item in self.catalog["items"] if item["kind"] == "hook")
        for host in ("claude", "codex"):
            for extra in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json",
                          ".mcp.json", "config.toml", "hooks.json", "agents/extra.md"):
                with self.subTest(host=host, extra=extra), tempfile.TemporaryDirectory() as temp:
                    hook = copy.deepcopy(source)
                    hook["members"][extra] = '{}'
                    if extra.startswith('.'):
                        with self.assertRaisesRegex(CatalogError, 'unsafe member path'):
                            compile_items([hook], pathlib.Path(temp), host, native=True)
                        continue
                    output = compile_items([hook], pathlib.Path(temp), host, native=True)
                    self.assertTrue(output["unavailable"])
                    self.assertFalse(any(output["assets"].values()))


if __name__ == "__main__":
    unittest.main()
