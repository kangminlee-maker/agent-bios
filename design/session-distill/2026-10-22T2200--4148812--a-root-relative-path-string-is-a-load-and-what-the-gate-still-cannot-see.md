---
created_at: 2026-10-22T22:00:15+09:00
head: 4148812
kind: review
supersedes: null
---

# A root-relative path string is a load, and what the package gate still cannot see

Round 3 of the F-21 review accepted `4148812`. It named one minor, pre-existing gap in the package
gate's by-path discovery, FC#0, and listed two more under its coverage question (Q5). This record
says what changed for FC#0 and keeps the other two as known limits. The 2127 record stays true.

## FC#0: one constant root-relative string

`compose/instructions_app.py` builds the Desktop bundle's tool list by loading
`release / "compose/app_desktop/server.py"` with `spec_from_file_location` (`_tools`). The path is
one string holding `/`-separated components. `gates/check-package.sh` `path_loads` read only chains
of two or more segments, so dropping `compose/app_desktop/` from `files[]` left the gate green. This
was true before this branch too.

`path_loads` now reads an outermost `/` expression whose single string segment holds `/` as a
root-relative path, like a chain. The control "a module loaded by one root-relative path string that
files[] does not ship" drops `compose/app_desktop/` and requires a failure naming
`compose/app_desktop/server.py` as referenced by `compose/instructions_app.py`. Nothing else names
the Desktop server, so only this recognition can find it. With the recognition reverted, the
control fails ("the planted violation passed"). The gate's runtime paths went from 58 to 60.

The same rule also corrects one path the review saw misread. `instructions_install._shell_manager`
loads `Path(__file__).resolve().parent.parent / "launch/shell_integration.py"`. Its one segment
holds `/`, so it is now read root-relative, as `launch/shell_integration.py`. Before, it was read as
a sibling in `compose/` and dropped, since no such file exists there. Other references already
covered that dependency.

## Known limits

- **Loads whose path is computed.** The installer's `_private_module` loads
  `package_root / "compose" / f"{stem}.py"`, and its corpus fallback is another f-string. A
  formatted or computed segment is not a constant, so `path_loads` cannot name the file. Those
  modules are also reached by the import walk or the `$REPO/` scan today, so no shipped file goes
  unseen through this. Nothing proves that stays so.
- **More than one `.parent`.** A SIBLING is one constant segment, without `/`, after `.parent`, and
  is resolved in the loader's own directory. `….parent.parent / "x.py"` would be resolved one
  directory too low, so the file would not be found. No load in the shipped tree has that shape now.

**Revisit when** a shipped file is loaded by a computed path that no import or `$REPO/` reference
also reaches, or a `.parent.parent / "<name>.py"` load appears. Either is the point at which the
gate needs to evaluate the expression, not just read its constants.
