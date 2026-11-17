---
created_at: 2026-10-21T06:34:00+09:00
head: 9b42df2
kind: design
supersedes: null
---

# The always-loaded global file has a ceiling, not a ratchet

Owner decision of 2026-10-21. This record amends `2026-10-20T1942--9684f05--mechanism-design.md`
(below: the design) — the §2 owner decision "the rule that the always-loaded global file only
shrinks is enforced by a commit gate" and the first sentence of §13.1 — and the verdict section of
`2026-10-21T0455--9410a1d--plan-addendum-wp14.md`. Everything else in them stands, including the
distill-side rule of §7 and §13.1 that S7 proposes, and S11 accepts, only deletions and merges for
the global file.

## The rule

`claude/CLAUDE.md` may not exceed **20,480 bytes (20 KiB)**, counted as UTF-8 bytes of the staged
file. Below the ceiling, any edit is accepted: a rule removed or merged frees room that a later
commit may use. The line count is not limited.

The gate (`gates/check-global-file.py`) blocks only a staged file above the ceiling. It keeps its
two disclosures, which never change the exit code: every staged line absent from `HEAD`, and the
before/after size of `ko/claude/CLAUDE.md`. The measurement rules of the WP-14 addendum keep their
meaning for the one side the verdict now reads: an absent staged file measures as empty; a staged
file git cannot read leaves the gate without a measurement and exits 2 by name. `HEAD` is read only
for the disclosure; if it cannot be read, the disclosure says so and the verdict stands.

## Why a ceiling replaced the ratchet

The ratchet began on 2026-09-03 (decision D-20260903-63d769) as an interim freeze while the
delivery design was open, and the 2026-10-20 design made it a commit gate. Compared with `HEAD`, it
spent every reduction permanently: room freed by a merge could never be used again, and the only
way to add a rule was to shorten others in the same commit.

The figure comes from evidence gathered on 2026-10-21:

- **Current size and history.** 117 lines, 20,195 bytes, 77 bullets; about 20.1 KB on 2026-07-18
  and 20,235 characters on 2026-08-31, flat for over three months.
- **Hard limits of the installed hosts.** Claude Code 2.1.304 warns above 40,000 characters per
  memory file (on a 200k window) and skips files above 4 MiB; it never truncates.
  codex-cli 0.163.0 truncates project `AGENTS.md` files at a combined 32,768 bytes
  (`project_doc_max_bytes`, measured with `codex debug prompt-input`), while the global
  `$CODEX_HOME/AGENTS.md` and the `developer_instructions` route agent-bios uses are not limited.
- **Vendor guidance.** Anthropic's Claude Code memory documentation: "target under 200 lines per
  CLAUDE.md file. Longer files consume more context and reduce adherence." Advice, without a
  stated measurement. At about 260 bytes per line the file is already larger in bytes than a
  typical 200-line file.
- **Research.** Instruction-count studies disagree by orders of magnitude (IFScale 2025: top
  models near-perfect through 150+ simple instructions; a 2026 extension reports thousands; a
  2026 compositional study reports breakdown beyond 5–6 simultaneous constraints). No measurement
  of adherence against instruction-file length was found for the Claude 5.x or GPT-6 families.

No source supports growing the file, and the vendor guidance points the other way, so the ceiling
is set at today's size. A 24 KiB ceiling — the largest that keeps the delivered Korean block
(about 1.09× the English bytes, about 1.2× after guide paths are expanded) under Codex's 32 KiB
project-file truncation — was considered and not chosen.

## What this closes

- The ratchet against `HEAD` as the gate's verdict.
- A 24 KiB ceiling.
- Distill proposing additions to the global file. The distill-side rule stays deletions and
  merges only; revisit after the first production distill run.

Revisit the ceiling when a measurement of adherence against instruction-file length exists for
the configured model families, or when the delivery route of the always surface changes.
