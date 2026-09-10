---
created_at: 2026-08-05T11:39:24+09:00
head: fcea430
branch: spurious-captain
kind: handoff
supersedes: HANDOFF.md (2026-07-18) for current state only; that record stands as written
---

# Session-distill current state, re-derived

`HANDOFF.md` is July's. It was edited in place on 2026-08-04 to carry August
figures and corrected paths, which produced a document that was neither July nor
August — the ambiguity the dated-record rule exists to remove, and the finding
the PR's own automated reviewer raised against that commit. The July text is
restored; what that edit added lives here instead, re-derived at `fcea430`
rather than copied forward.

## Ledger

```bash
python3 -c "import json,collections;e=json.load(open('design/session-distill/ledger.json'))['entries'];print(len(e),collections.Counter(x['status'] for x in e))"
```

**83 entries** on 2026-08-05: placed 51, incubating 27, incubating-G 2,
adopted-no-text 2, absorbed 1.

July's counts are not wrong, they are earlier: 74 at the 2026-07-18 seeding,
78 after the 2026-07-19 decisions, 49 selected and placed in §P8. Read them as
what each decision was made against.

## Paths that moved since July

| July text | Now |
| --- | --- |
| `scripts/session-distill/` | `session-distill/` |
| `scripts/session-distill/out/BUNDLE.md` | `session-distill/out/BUNDLE.md` |
| `scripts/gates/check-parity.sh` | `gates/check-parity.sh` |

The July record names the first column throughout. That was true when written.

## Environment, verified 2026-08-05

| Tool | Version | How |
| --- | --- | --- |
| Codex CLI | 0.145.0 | `codex --version` |
| Claude CLI | 2.1.222 | `claude --version` |
| ultracode-for-codex | 0.7.1 | `ultracode-for-codex --version` |

The 2026-08-04 edit recorded Claude CLI 2.1.221. It moved within the day, which
is the argument for the command over the number.

## What is open

Unchanged from July: the incubating candidates await a promote/retire judgment.
Nothing in this re-derivation changes the initiative's next step; it only makes
the current numbers quotable without reading a mixed-age document.
