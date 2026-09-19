# Findings — open implementation defects

Live queue, kept current. **Only open items live here.** Closing one means deleting its entry,
not annotating it — the reasoning belongs in that round's dated record, where it stops needing
maintenance.

A per-entry status field is the thing that goes stale, because closure often arrives as a side
effect of a decision taken under another name and nobody walks back to mark it. A file with no
status field cannot drift that way, so `gates/check-lexicon.py` fails if resolution markers
appear here.

These are defects in the **product**, not in the ontology. Judgements about the ontology's own
claims live in `ontology/instances/graph.json` (`verdicts`, `decisions`), which is a deliberate
split: a decision about a golden relationship and a decision about the CLI surface answer to
different authorities.

Every entry names its alternatives. An item with one path is not a finding, it is a task.

---

## F-17 — conditional prohibitions in the selected startup instructions need evaluation

`claude/CLAUDE.md` embeds prohibitions inside longer conditional bullets, including
runtime enforcement, lifecycle ownership, destructive operations, and spawn policy.
The private compiler preserves the selected rule text in startup snapshots. Moving
its delivery out of native global files does not establish that a model recognizes
and follows those clauses under context pressure; child reach is a separate question.

The structural observation is supported by the current canonical text. A comparative
behavior result for the current private delivery path is not established here. Review
must preserve each prohibition's intended scope and use a relevant activated snapshot;
a count of clauses or a shorter rewrite alone does not demonstrate better behavior.

Alternatives:

1. **Extract standalone boundaries within a reduction.** Remove the clauses being
   replaced and show their scoped meaning at the new location. Risk: a standalone
   prohibition may lose the condition that made it correct.
2. **Keep the current wording.** Accept the unresolved recognition risk if an
   appropriately scoped comparison does not justify the change.
3. **Enforce decidable boundaries in the owning tool.** Use capability, validation,
   or ownership checks where the action can be controlled; retain prose for judgments
   and surfaces without that authority. Each change needs its own negative control.
4. **Evaluate another current delivery surface.** Compare guide, requested procedure,
   or session-specific delivery against startup placement using `SURFACES.md`.
   Keep the canonical always surface reductions-only and test main/child reach
   separately before adopting a placement.

These alternatives remain open; enforcement and prose placement can be combined
for different clauses. Any behavior experiment needs a bounded question and scope.

---

## F-18 — a setup TUI test sends its keystrokes before focus has settled, and fails intermittently under load

`compose/test_instructions_setup.py`
`SetupCliTests.test_tty_apply_installs_chosen_policy_and_prints_compact_completion` waits
for the review page's text, then writes Tab, Tab, Enter to the PTY as one burst. The text
appearing is not the same event as the button row being focusable, so under load the burst can
land with focus on Cancel: the installer prints "Setup cancelled. No installation changes
were applied." and the test reports that the installer exited early.

Observed once on 2026-09-20 inside the pre-commit umbrella (523 tests, 1 failure, the captured
frame shows Cancel in reverse video) on a commit that staged only records; the same test then
passed 6 of 6 in isolation under the same environment, and had passed in the two umbrella runs
before it. One occurrence does not establish a rate. The cost is a refused commit about ten
minutes in, for a reason unrelated to the change. Sibling tests share `press_next` and the
same burst pattern and have not been examined.

1. **Wait for the focused control, not for page text.** Have the test read until the frame
   shows the intended button focused before sending Enter, one key at a time. Risk: couples
   the test to rendering details of the focus style.
2. **Give the review page a key that does not depend on focus order.** A bound shortcut for
   Apply removes the race for users as well as tests. Risk: a new user-visible binding that
   needs its own wording, i18n and accidental-apply consideration.
3. **Retry the keystroke burst inside the helper.** Cheapest, and it hides the same race from
   a person typing quickly; the wrong fix if the race is reachable by hand.
4. **Leave it and re-run the commit.** Acceptable only while the rate stays unmeasured and low;
   measure with a loop of the full suite before choosing.
