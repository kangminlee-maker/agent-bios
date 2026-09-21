"""The cutover's dispositions: one `entrance_disposition` per existing route, in entrances.jsonl.

Both sides are derived rather than listed here: the routes from `install.sh`'s command dispatch
and the shipped entry scripts, the dispositions from the file. A route added without a
disposition, or a disposition left behind by a route that is gone, fails by name. Run by
gates/workenv/check-workenv.py, one process per file.
"""
import json
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from workenv.contracts import examples, records  # noqa: E402

DATA = pathlib.Path(__file__).with_name("entrances.jsonl")
ENTRY_SUFFIXES = (".py", ".sh", ".zsh")


def commands(text):
    """Every command name install.sh dispatches: its `"$CMD" = "x"` tests and `case` arms."""
    found = set(re.findall(r'"\$CMD" = "([a-z][a-z-]*)"', text))
    for block in re.findall(r'case "\$CMD" in\n(.*?)\n\s*esac', text, re.S):
        for arm in re.findall(r"^\s*([a-z][a-z|-]*)\)", block, re.M):
            found |= {name for name in arm.split("|") if re.match(r"^[a-z]", name)}
    return found


def shipped_entry_scripts(root):
    """Tracked, shipped files a caller can start: a `__main__` guard or a shebang."""
    entries = [e.strip("./").rstrip("/") for e in
               json.loads((root / "package.json").read_bytes())["files"]]
    tracked = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True,
                             text=True, check=True).stdout.split()
    found = set()
    for rel in tracked:
        if rel == "install.sh" or not rel.endswith(ENTRY_SUFFIXES):
            continue
        if not any(rel == e or rel.startswith(e + "/") for e in entries):
            continue
        body = (root / rel).read_text(errors="replace")
        if body.startswith("#!") or re.search(r"__name__ == ['\"]__main__['\"]", body):
            found.add(rel)
    return found


def dispositions():
    schemas = examples.load_schemas()
    rows = []
    for number, line in enumerate(DATA.read_bytes().splitlines(), 1):
        value, identifier, found = records.load(line, schemas, "stored")
        rows.append((number, value, identifier, found))
    return rows


class Dispositions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = dispositions()
        cls.routes = [(row[1]["route"]["path"], row[1]["route"].get("command"))
                      for row in cls.rows]

    def test_every_line_is_a_disposition_the_reader_accepts(self):
        self.assertGreater(len(self.rows), 50)
        for number, _, identifier, found in self.rows:
            self.assertEqual((identifier, found), ("c03_entrance_disposition", []),
                             f"line {number}")

    def test_one_disposition_per_route(self):
        self.assertEqual(len(self.routes), len(set(self.routes)))

    def test_every_install_command_has_a_disposition_and_no_other_does(self):
        tree = commands((ROOT / "install.sh").read_text())
        self.assertGreater(len(tree), 10)
        recorded = {command for path, command in self.routes if path == "install.sh"}
        self.assertEqual(recorded, tree)

    def test_every_entry_script_has_a_disposition_and_no_other_path_does(self):
        tree = shipped_entry_scripts(ROOT)
        self.assertGreater(len(tree), 40)
        recorded = {path for path, _ in self.routes if path != "install.sh"}
        self.assertEqual(recorded, tree)

    def test_a_script_is_disposed_of_whole_or_command_by_command(self):
        split = {}
        for path, command in self.routes:
            split.setdefault(path, set()).add(command)
        mixed = {path for path, names in split.items() if None in names and len(names) > 1}
        self.assertEqual(mixed, set())

    def test_a_retirement_forwards_to_something_that_stays(self):
        # A compatibility shim may forward to a library module rather than a route, so the
        # successor is held to what it can be: a path in the tree that is not itself retired, and
        # when it names a command, a recorded route that stays.
        retired = {(row[1]["route"]["path"], row[1]["route"].get("command")) for row in self.rows
                   if row[1]["disposition"]["state"] == "retired_at_cutover"}
        stays = set(self.routes) - retired
        for _, value, _, _ in self.rows:
            if value["disposition"]["state"] != "retired_at_cutover":
                continue
            successor = value["disposition"]["successor"]
            path, command = successor["path"], successor.get("command")
            with self.subTest(route=value["route"]):
                self.assertTrue((ROOT / path).is_file(), path)
                self.assertNotIn((path, None), retired)   # a file retired whole
                if command:
                    self.assertIn((path, command), stays)

    def test_each_owner_is_held_by_at_most_one_route(self):
        owns = [row[1]["disposition"]["owns"] for row in self.rows
                if row[1]["disposition"]["state"] == "choke_point"]
        self.assertEqual(len(owns), len(set(owns)), owns)


class Derivation(unittest.TestCase):
    """The two derivations, against inputs built here, so an empty or blind scan is seen."""

    def test_commands_read_both_dispatch_shapes(self):
        text = ('if [ "$CMD" = "one" ]; then\nfi\n'
                'case "$CMD" in\n  two|three) x ;;\n  help|-h|--help) usage ;;\n'
                '  *) no ;;\nesac\n')
        self.assertEqual(commands(text), {"one", "two", "three", "help"})


if __name__ == "__main__":
    unittest.main()
