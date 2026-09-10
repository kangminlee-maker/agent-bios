---
created_at: 2026-08-05T17:38:11+09:00
head: 9427be6
branch: spurious-captain
kind: review
supersedes: none — first record of this review
---

# Four-lens cross-family review of `9427be6`, and what it cost me to skip it

The PR's automated reviewer stopped after `cb03ee9` (2026-08-04 22:04 KST). Three
commits went unreviewed for ~18 hours while every prior review had landed within
5–16 minutes. Waiting was not the answer, so the replacement named in the standing
constraint was used: four `codex exec` subprocesses, `gpt-5.6-sol` at `max`, read-only
sandbox, fresh process each, same packet with one lens apiece — correctness,
verification quality, payload boundary, concept economy and active docs.

The packet let each reviewer read the real repository rather than a diff, and
demanded a reproducible failure path per finding. It injected this repo's design
principles, because an external model does not load the corpus.

## The finding that mattered

**`packaged_mode()` has nothing to do with npm versus clone.**

```
packaged_mode() { [ "${DOMAINS_SET:-0}" = 1 ] || [ -f "$STATE_DIR/selection.json" ]; }
```

It is true only when `--domains` was passed or a prior selection exists. A default
`agent-bios install` — the command `package.json` advertises — takes the *other*
branch, which never reaches the assembler. So the `audience: author` withholding
that `9427be6` added covered the minority of installs and missed the default one.

Three of the four lenses reached this independently. I had reasoned "plain mode
means a clone, so it is safe" and never read `packaged_mode`. This machine is
packaged mode because a `selection.json` exists here, which is exactly the sample
size of one that made the wrong generalisation feel verified.

## What each lens bought

Convergence on the same defect from three lenses is confidence. Divergence is the
point of running four — each of these was found by exactly one:

| Lens | Found alone |
| --- | --- |
| correctness | sub-second gaps truncated per-gap: **947 seconds lost across the real ledger's 32 spans, 216 in one**, measured by replaying the actual transcripts |
| boundary | `./gates/` in `files[]` satisfies neither `shipped()` nor `author_side()` while npm packs it — proven with npm's own packlist |
| concepts | `--check` validates `str(value)`, a stringified copy, so a numeric `summary` passed and then crashed `render` |
| verification | the transcript-damage control exercised the helper and not the CLI wiring — dropping one keyword argument left every row reliable and the suite green |

The last one is worth naming twice: it is the same defect class I had found and
fixed myself for `check_artifact` one hour earlier, in the same file, and did not
generalise.

## Dispositions

Every finding was re-derived against real code before being acted on; none was
taken on the reviewer's word.

**Fixed** — withholding on both install paths plus removal of a stale deployed
copy, and `verify` taught to require the absence rather than the presence;
`files[]` entries normalised through `rel_key`; a runtime `$REPO/...` reference to
a nonexistent path now fails; `check_ledger` validates types rather than
stringified copies; `intervals` distrusts a pair with no session; `split_span`
accumulates exact microseconds; explicit-null and offset-naive transcript
timestamps counted as damage instead of skipped or raised; `session_id` prefers
the inner Codex thread, measured — a Claude session running `codex exec` passes
`CLAUDE_CODE_SESSION_ID` straight through, so preferring Claude stamped the outer
session onto the inner one's work; the read projections get the artifact check and
`--render` names the file it read.

**Stated as bounds, not fixed** — `RUNTIME_GUARDED` finds its guard in the
referring file rather than around each reference, so a second unguarded call to an
already-guarded path passes; `repo_path` cannot judge a typo in a path's first
segment. Neither is decidable from a substring, and this repo blocks only on
decidable violations.

**Deferred, recorded as D-0034** — the launcher has no reader for a preset's
`audience = "author"`, so a packaged user is still offered Session distill.

## What this changed about the branch's own claims

`gates/test-install-guides.sh` is new because no existing suite touched the full
install path. It takes the pre-commit hook from ~15s to ~135s. That is the price
of covering the branch a default install actually takes, and it is stated in
`AGENTS.md` rather than discovered by whoever waits for the next commit.

Two sentences in `AGENTS.md` written at `9427be6` were false and are corrected:
that every gate ships a `--self-test` (`gates/check_parity.py` and
`launch/check-prompting-targets.sh` do not), and the hook's duration.
