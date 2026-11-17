---
created_at: 2026-10-22T21:04:23+09:00
head: 6d351b5
kind: design
supersedes: null
---

# The JSONL splitter sits beside the one reader that travels alone

This records where the one JSONL splitter lives and why. The 2046 record states what reads through it.
The lead approved the choice on 2026-10-22 (option A of the F-21 round-1 escalation).

## The constraint

`wrappers/claude_hermetic_evidence.py` reads two kinds of Claude stream rows: the init row
(`stream_mcp_servers`) and the result row (`result_object`). The compatibility install
(`install.sh` `cmd_install`) copies it on its own into `$CLAUDE_DIR/bin`, beside the deployed
`claude-run`. `claude-run.sh` resolves the helper beside itself and never looks it up anywhere else.
So a splitter that lived anywhere but beside the helper would be missing from that one layout, or
the helper would need a second place to look.

Every other consumer runs inside a package root that holds the whole payload. These are the
checkout, the npm package, the private release (`instructions_install._copy_release` copies every
`files[]` path at its relative path), and the Windows bundle (the whole tree staged as
`release/package`). No other installer deploys the helper outside a package root. Nothing under
`packages/windows/` and nothing in `compose/windows_deploy.py`, `runtime_entry.py` or
`native_cli.py` names the helper or deploys `wrappers/` files on their own.

## Decided

**A: the owner is `wrappers/jsonl_lines.py`.** The helper loads it beside itself and fails naming
the path when it is not there. `install.sh` deploys it beside the helper, `install.sh verify`
checks it, and the uninstall path removes it with the helper. `compose/` (through
`host_platform.py`), `learn/migrate-learnings.py` and `session-distill/runlib/records.py` load
`../wrappers/jsonl_lines.py` inside their own package root. None of them falls back anywhere.

`gates/check-package.sh` finds each of these loads. A `/`-joined chain of string segments
(`… / "wrappers" / "jsonl_lines.py"`) resolves from the repo root. A single segment after
`.parent` (`Path(__file__).resolve().parent / "jsonl_lines.py"`) resolves in the loader's own
directory. Each has a negative control naming `wrappers/jsonl_lines.py`. The sibling control
removes the other two loads and the installer's deploy line, so the helper's own load is the
only one left to find it. `gates/check_parity.py` `claude_run` copies the adapter to a directory
alone. With the helper but without the splitter, the copy fails naming `jsonl_lines.py`. With
both, it runs.

## Closed

- **B: keep the owner in `learn/` and also deploy it into the compatibility bin.** In a checkout the
  helper would find it at `../learn`, and in that install beside itself. Two locations for one
  file is a fallback, and a fallback lets a missing file go unnoticed in whichever layout was not
  checked.
- **C: leave the helper on `str.splitlines()` and record an open finding.** The defect is real.
  A U+2028 or U+2029 in any string of the init row hides the MCP servers the gate judges. One in
  the result text loses the closing result. Both were reproduced.
- **D: stop deploying the helper outside the package root, so the compatibility `claude-run` runs
  from the package.** This would change how the compatibility install lays out its adapters, which
  is a decision about that install and outside this finding.
  **Revisit when** the compatibility install is retired or reworked. Then the splitter could
  live anywhere in the package.
