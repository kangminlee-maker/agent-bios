---
created_at: 2026-09-07T17:37:00+09:00
head: ed5b00f
kind: review
---

# Launcher help: operator understanding

The audience can use a CLI but does not independently build an advanced AI working
environment. The decision to support is: what changes in their work when they choose
a mode, preset, or corpus package? Human-facing translations need semantic clarity;
they do not need content-hash parity with instructions injected into a model.

## Changes verified in this session

- Mode and preset help explains the currently installed corpus and makes clear that
  choosing a mode does not install packages. Built-in preset help explains suitable
  work and time/usage tradeoffs in the selected UI language. User-local preset
  descriptions remain authored text.
- Each optional package has a readable localized name beside its stable id, a purpose
  summary, and one-line explanations of its topics. The package checklist explains
  installation scope across projects, checked versus unchecked packages, and when
  choices take effect. Its shared help also makes sense in numbered prompts.
- The detail panel grows within the available viewport. `j/k` and
  `Shift+PgUp/PgDn` scroll details, and `PgUp/PgDn` scrolls setup/status. Highlighting
  another option resets detail scrolling. A queued resize callback only acts on the
  active mounted screen.
- Unreadable corpus state is reported as unavailable rather than as a known empty
  selection. Unknown packages retain their manifest description.

Correction, 2026-09-07: the old `setup.bare` text claimed that only repository
instructions apply in Vanilla. `project_args` adds no launch flags for this path;
it does not disable the backend's normal global-instruction loading. The corrected
help describes normal global and project instruction loading.

The content owners are `launch/i18n/*.toml`. The consumers are
`pick_mode_and_preset`, `corpus_checklist`, `_domain_description`, and
`MenuScreen._describe` in `launch/agent-launch.py`. Package identities and assembly
still come from the existing manifest/status path; launch contracts remain separate
from UI translations.

## Remaining operator-facing gaps

| Priority | Evidence in `launch/agent-launch.py` | Decision the user still has difficulty making |
| --- | --- | --- |
| Next | `review_editor`, `review_description`, and the review branch of `customize` expose English and terms such as composable, provider, binding, and PROPOSED | Which review choice gives another opinion, how much extra work it requests, and what happens when a reviewer is unavailable |
| Next | `setup_summary_lines` displays raw permission values such as bypass and raw on/off values | Whether the selected setup can execute commands or change files without further confirmation; the policy editor explains more, but the summary itself does not |
| Later | `_corpus_summary_lines` shows author-registry mechanisms, placed/incubating counts, and versions on the main choice screen | Which status information matters to choosing a work mode, and which is maintainer bookkeeping |

These are observed UI gaps, not authorization to change permission defaults or
redesign review routing. A useful next increment would translate the existing
review choices into outcomes and make permission consequences readable in the
summary while retaining the machine values for correlation with configuration.

## Verification and limits

- Real Textual flow passed for en/ko/ja at 80x24, 110x38, and 160x52: mode to
  preset to corpus, localized help, on-screen navigation, full detail scrolling
  with both key forms, reset on highlight, cancellation, and a queued callback
  after dismissal. Korean rendered screens were visually inspected.
- The existing `tui_picker`, `launcher_renders_each_language`, `numbered_fallback`,
  and `distill_hub` checks passed under the installed TUI interpreter. Navigation
  markers now come from the UI catalog and model movements/defaults from the live
  fixture config rather than old prose or model positions.
- Catalog/placeholder consistency, contract-language isolation, corpus sizing and
  checklist behavior, malformed status handling, manifest coverage, package
  boundaries, terminology, Python compilation, and `git diff --check` passed.
- Three isolated read-only Claude Fable 5/max passes reviewed correctness, security,
  and reproduction. Their receipts matched the submitted packet and returned bytes,
  and provider results recorded the requested model. All three reported no material
  decision defect in the reviewed snapshot. Their smaller observations informed the
  portable scroll keys, numbered-prompt wording, and unknown-state correction.
  The later real navigation test found the resize callback lifetime defect, which
  was fixed and re-tested; the earlier review is not claimed as proof of that fix.
- The full parity umbrella ran and failed on twelve existing binding/projection/
  preset-save assertions. A controlled baseline retained the current config and
  restored the launcher and catalogs from `ed5b00f`; the same twelve failures
  reproduced through `environment_bindings`, `profile_errors`,
  `agent_materialization`, `cross_family`, `same_family`, and `preset_save`.
  The related config/guide changes were already in flight when this task started
  and were left untouched. The full repository is therefore not reported green.
- No backend work session was launched by the UI checks. The modified working tree
  was not deployed over the installed launcher, and no commit or publication was made.

Review dispatches: `03d7c2272c274abe8f86f0ff38ed011b`,
`0d1d653a8f37486d9fecce54d54ada71`, `4dbab2a8c2534eaeaf640e8fc17fa139`.
Their persisted Claude sessions are respectively
`11df81c7-b6a1-4fe2-bb2f-b7a577ad8c08`,
`d9191cb6-6f0f-4583-bb25-41fd04da5f0f`, and
`f1950150-3f15-47af-b8cb-860a8c2c47a1`.
