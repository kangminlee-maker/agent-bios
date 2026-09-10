---
created_at: 2026-09-09T21:06:00+09:00
head: f8eeb4ba1212ed95b98ed759639b2276b33b7c10
kind: design
supersedes: 2026-09-09T0857--f8eeb4b--review-ko.md
---

# Pre-promotion verification and a complete corpus alternative

The owner required verification **before promotion**: can the proposed wording
recognize sufficiently similar situations and support appropriate execution?
They also explicitly selected comparison with a separate reconstruction of the
entire incumbent corpus. The earlier 15/5/13 review is therefore a set of
hypotheses, not an approval-ready placement decision. No learning is approved or
promoted by this experiment.

## Alternatives and comparison basis

| Arm | Concrete prototype | Benefit hypothesis | Cost and risk | Done when |
| --- | --- | --- | --- | --- |
| A | Frozen canonical corpus, unchanged | Already sufficient; preserves current knowledge and behavior | Existing acquisition and instruction cost | Its natural decisions, reads, actions and outcomes are observed |
| B | A with the 15 narrowed English paragraphs added to four existing guides | The additions resolve missing distinctions | Extra reading cost, repetition, or over-application | Exact amendment diff and outcomes compared with A |
| C | A complete self-contained reassembly of B using the five existing domains | Smaller initial exposure with usable situation routes | More retrieval, missed routing, details becoming unreachable | All original items map to C, additions equal B, and controls and transfer tasks are compared |

The reversible default is to construct all three locally and keep deployment
unchanged. A–B measures the amendment bundle; B–C measures this reorganization.
Neither comparison alone attributes an effect to a single paragraph. C is an
initial complete alternative, not a claim to have exhausted all possible corpus
designs. A shorter entry alone is not a reason to choose it.

The source snapshot is the tracked English Claude payload and Codex projection,
including the concurrent goal clarification present when this phase began. The
actual catalog derives 100 items: 77 rules, 18 guides, one hook, three roles and
one skill. The frozen canonical Claude tree contains 25 files; a previous
live-tree count of 26 used a different file set. The experiment does not copy
untracked personal settings into source artifacts.

C keeps the original rule bodies, guide detail, exceptions, examples, rationale,
bindings and executable assets. It retains 25 core rules plus one personal
preference in the entry and relocates 51 domain rules into five domain entry
guides. It adds five situation routes using existing domain names. The 18
original guides remain inside C; C never imports A or B. This tests complete
reorganization with preserved knowledge before undertaking a riskier semantic
rewrite. A reverse mapping discloses the routes and amendments introduced.

The builder derived and checked 100/100 item mappings and 15/15 byte-equal B/C
amendments. Removing relocated `rule-024` from a temporary copy made the
preservation check fail by that ID. These checks establish textual preservation,
not that the content will be found or applied.

At construction: A 299,184 UTF-8 bytes/25 files; B 308,299/25; C 310,804/30.
The entry file is 20,309 bytes in A and B, 4,934 in C. These are byte counts,
not token or execution-cost measurements.

## What is measured

Keep three outcomes separate:

1. **Meaning:** the response explains the evidence, distinction, applicability,
   boundary and uncertainty correctly.
2. **Natural recognition and acquisition:** an ordinary request leads to the
   relevant investigation and instruction reads without being told the lesson
   ID or target rule. A missing read is an observation, not automatically a
   wrong decision. A broken path is a delivery defect.
3. **Execution:** actual tool calls and resulting artifacts satisfy the task.
   Saying what should be done does not count as having done it. Conversely,
   retaining already-correct behavior can be a successful outcome.

Natural complete-task trials are primary. Supplied-text companion trials can
diagnose failures and a preregistered success sample: successful handling after
exposure but failure naturally suggests an acquisition problem; failure in both
does not prove that wording alone caused it. Companion trials are not pooled
with natural trials.

Case authors did not read the frozen amendment paragraphs or arm designs.
The first case specification contains 15 families × three variants: a close
keyword-stripped analogue, farther transfer, and a lookalike control that must
finish ordinary work. Source-derived cases still disclose constructed fixture
details. Literal source scenarios are retained as evidence, not counted as new
independent situations. Further unseen siblings are reserved for confirming
decision-changing differences.

The incumbent 13 benchmark scenarios and additional preservation obligations
remain a separate regression set. Passing only the new learning tasks cannot
justify replacing the entire corpus. Host results, scenario families and
repetitions remain separate; repeated executions are not new situations.

## Delivery and apparatus

Inspection found an important discrepancy. The old benchmark redirects a
configuration home; current `compose/corpus_session.py::compose_argv` preserves
native instructions and appends a private snapshot. The latter path retains
incumbent global content, and Codex does not support selectively excluding that
global through the current adapter. An additive native run cannot establish
that C works as a standalone replacement.

Therefore the first experiment measures **controlled standalone corpus
exposure** in owned temporary homes with common per-host capabilities. It uses
the installed host CLIs and real model turns, preserves subscription
authentication through the existing benchmark mechanism, rebinds routes into
each arm, captures real tool events and completed project files, and records
observed model identity. It does not claim current native activation or resume
compatibility. Those require a separate fresh-session compatibility pass through
the current snapshot compiler/activation adapter before any placement decision.

Only the actor's temporary project is a write target. Cases contain local,
disposable data and no real service/account operations. A local browser fixture
can establish actual input/application/persistence behavior in that application;
historical GUI traces or a fake API alone cannot establish live GUI execution.

Runtime owns cell IDs, source hashes, fixture reset, arm order, session records,
serialization and aggregation. It submits a sliding bounded set of jobs and
stops further jobs for a host after three consecutive unsuccessful apparatus
outcomes; no automatic retries. A manifest declares cells before calls, receipts
record completion, and unrun/invalid cells remain visible. Mixed/fallback model
output is invalid for the pinned-seat comparison. Requested effort is separate
from observed effort; unavailable evidence stays unavailable.

Provider stdout is parsed before secret-redacted persisted projections are
created. Wire hashes and stored-byte hashes are distinct. Auth-bearing homes
are outside the repository and removed by their owning context. No live token
is written into durable experiment outputs. Synthetic credential markers, where
used to test output behavior, are recorded as fixture observations rather than
real credentials.

## Stages and interpretation

1. **Apparatus, six calls:** one simple read/write/result-check request in each
   host × arm. It establishes input exposure, real action capability, actual
   model, result capture and timing. It is not evidence of learning efficacy.
2. **Bounded pilot:** positive and negative cases for six mechanisms (detector
   interpretation, configuration scope, review scope, observation versus defect,
   shell no-op, item-level outcome). Freeze their fixtures and oracles before
   actors run, then run two fresh repetitions per host-arm-case with arm order
   rotated in each block. Use measured apparatus/pilot duration and variability
   to choose later work rather than launching an unbounded sweep.
3. **Breadth and preservation:** remaining families, transfer cases and incumbent
   regressions. Do not infer cross-host portability from one host or full-corpus
   preservation from the 15 new families.
4. **Confirmation and native compatibility:** additional unseen sibling cases
   and repetitions for differences that can change the recommendation, plus
   current activation-path checks. Record unresolved gaps and stop at the
   declared finite scope rather than rerunning until a desired answer appears.

Every deterministic outcome assertion needs a known-good and known-bad control.
Use calibrated blind semantic assessment for meaning, not keywords in the
response. Cases with correct vocabulary but wrong action and unexpected
vocabulary but correct behavior test that evaluator. Preserve disagreements.

Structural invalidity makes a trial unusable. An observed behavioral failure is
data, not an excuse to discard it. Candidate efficacy and corpus choice remain
human decisions informed by per-case evidence. Two repeats can expose obvious
instability; they do not support a universal reliability claim. Report tested
cases and uncertainty instead of a generic PASS for the corpus.

B is disfavored where A already performs equally well and the amendment adds
cost or over-application. C is disfavored if retrieval erases the initial saving,
relocated detail becomes unreachable, or existing correct behavior regresses.
Equivalent demonstrated behavior at lower full-task cost may favor C. Mixed
results can justify selective amendments or retaining the incumbent; the
experiment need not manufacture one winner.

## Independent design and current recovery anchors

Fresh GPT-6 Astra/xhigh and Claude Fable 5/max received the same blind design
packet. Both proposed preserved-detail reassembly, positive/transfer/negative
cases, actual-action evidence and staged workload. The GPT draft additionally
checked the current native activation path and separated standalone efficacy
from native additive compatibility. The Claude draft relied on the old
benchmark layout; that load-bearing assumption was corrected by source
inspection, not carried into a claim about current activation. The two designs
are proposals, not a final clean-verdict review.

Local artifacts are under `session-distill/out/2026-09-09/comparison/`, excluded
from this checkout's git inventory. They are local recovery evidence, not
portable proof available from every clone: `source.tar`, `source/`,
`design-packet.md`, `design-claude.jsonl`, `design-claude.md`, `design-receipts/`,
`amendments.md`, `case-specs.md`, `build_arms.py`, `arm-manifest.json`, `arms/`,
`trial_runner.py`, `apparatus-cases.json`, and `apparatus/manifest.json`.
The source snapshot contains no credential copies. No corpus promotion,
deployment, ledger merge, version registration or nudge-baseline update has
occurred in this comparison phase.
