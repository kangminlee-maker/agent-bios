---
created_at: 2026-09-05T06:10:00+09:00
head: f7f74cc          # the pin both stages ran at; the instrument that reads them is main after fa1d960 (rules 5–13)
kind: review
supersedes: 2026-09-04T2050--9c38e38--stage1-codex-screen.md (as the Stage-1 result; that record stays as the account of the first run)
---

# Stage 1 re-run, both hosts: the Codex screen is clean on the isolated instrument; on Claude the helm seat rewrites a long brief when relaying it, and control 4 voids the run

What ran: `live.py stage1 --host codex|claude --sizes 10,40,160 --R 3`, both hosts in
parallel, pinned at `f7f74cc` (the isolated instrument, `D-20260904-4ccdf9` — oracle
regenerated only when scoring begins, run tree `~/.agent-bios/tier`, every stub stating its
spec). Launched 2026-09-04 23:22. Codex finished 01:35 (45 runs, Σ modelled $20.13,
dispatch 7,524 s). Claude finished 05:40 (36 runs — four arms, fork-same is not an arm on
Claude, `D-20260904-fd86f1` — Σ measured $40.83 over the 36 runs; the aggregator's cost
total is $39.45 over the 35 whose cost it reads, M40-b1-delegated-same's child artifact
being cut — dispatch 6,500 s) after two stops: at
00:22 a usage-limit failure followed by a fork-same dispatch refusal tripped the breaker,
and at 01:30 two usage-limit failures did; each time the stage resumed at the same pin
with the same command, skipping the runs that had a record. The Claude manifest had
declared fork-same (the `stage_arms` filter did not exist at the pin); after six
refusals (three at M=10, three at M=40, before any M=160 dispatch) it was amended to the
four Claude arms — the amendment is on the manifest
(`amended`), the original beside it. Every run reached its visible done-when at the solve
pass, no plant fired, every level that was scored is zero.

The two hosts shared their block fixtures (seed `stage1:<block>`), so while one host
scored a block its key sat under that run's dir for seconds while the other host's seat
on the same block ran; every read of another run's tree or of a key name is voided, and
a seat that constructs a path the scan cannot name is the instrument's stated limit
(`D-20260905-8a5d2f`). Future stages seed per host and seal a finished run's solution
until the stage ends (`D-20260905-1635fa`, `D-20260905-8a5d2f`).

## How the records are read

The live scan on both stages was rule 4, which discarded the measured level on a hit. The
records are read by the aggregator on main under **rule 13** (`level.RULE`): every receipt is re-scanned from the artifacts, the earlier rule's void
leaves, and a run the earlier rule voided while discarding its level is scored again
from its preserved workdir with the oracle regenerated from the seed (`--rescore`; the
generator is byte-identical to `f7f74cc`, checked by `same_generator`). 14 Codex and 22
Claude records were rescored; none needed the key on disk while a seat ran.

    python3 benchmarks/tier/stage.py ~/.agent-bios/tier/stage1-rerun-codex/runs --sizes 10,40,160 --R 3 --rescore
    python3 benchmarks/tier/stage.py ~/.agent-bios/tier/stage1-rerun-claude/runs --sizes 10,40,160 --R 3 --rescore --arms inline,delegated-same,delegated-workhorse,delegated-sweep
    python3 benchmarks/tier/stage.py … --census --rescore

Rules 5 through 10 came from four cross-family review rounds of the instrument while the
stages ran (rounds 4–7: sessions `01a06cb2-c002-7130-940f-b896e0793bc3`,
`01a06ce2-d55b-7181-b9f9-be4d8c6687a7`, `01a06d14-3069-7902-9b56-ddb672524334`,
`01a06d2a-f722-70f3-b98b-ce61a798c574`; 7, 4, 2, 3 findings, all applied with a control
each) and from the re-run's own false voids. Under rule 4 the live scan had voided 16
Codex and 23 Claude runs, nearly all for a scratch directory under `/tmp`, a JS literal's
escaped quote, a shell default, the home's root, the word `oracle` in a seat's own
script, an awk program, the run's own fixture dir, or a path that does not exist — each
now excused, each with a control. Rules 11 and 12 came from review round 8 (session
`01a06e38-1698-7292-8d5b-67e9d2342e21`, three highs): a root is a name only after a verb
that prints, tests, or lists it, and a search root, a working directory, or an unknown
command there reaches everything beneath; a path absent at scan time is excused only
inside a tree whose layout is known (the stage tree, an allowed home) or when its first
segment is no directory on this machine; key names match in any case; a shell variable
set in the call is substituted where it is used, and a host home variable's `${VAR:-…}`
default is dead text because the stage sets the variable (rule 10 read the default —
the machine's home, where the store may not exist — and excused the read as absent).
Rule 11 as first written voided four more Codex runs, each a read the scan could vouch
for: two sweep seats ran absolute-path reads of the guides with the stage home as their
working directory, one printed the home root inside a JS template, one listed file names
with `rg --files` over `~/.codex`. Rule 12 judges a root working directory on the
command's relative reads, a name listing (`rg --files`, a `find` without an action) as a
name, and a JS command literal on its own text. Rule 13 came from review round 9
(session `01a06e70-a88f-7243-8f76-1a15d09097a2`, gpt-5.6-sol at ultra; five over-voids, six under-voids): a
relative operand at a root working directory is resolved against it and judged like any
path (`cat guides/x.md` at the home is a surface read, `cat sessions/x` a store read, a
search pattern a name that does not exist); a working directory pairs with its own
command, not with every command in the unit; JS keys in either quote; a verb by its
basename (`/bin/ls`); `${VAR:+alt}` is the alternative; a name listing piped, directly or
through name filters, into `xargs`, a shell loop, or an interpreter is a read; an input
redirection and a path-shaped token inside a quoted program are operands; a glob is
what it expands to and is never excused as absent; a variable holds the value it had at
the use, not its final value; `$PWD` and its modifiers (`${PWD:h:h:h}`, `${PWD%/runs/*}`,
nested `dirname`) are expanded against the run's known workdir and the result judged; a
bare `cd` climbs; `\u002f` in a JS literal is a slash. The aggregate under rule 13 is
identical to rule 10's on all three stages, every figure below included. Under rule 13:

| host | runs | sound | voided | Σ cost | rescored |
| --- | --- | --- | --- | --- | --- |
| codex | 45 | 43 | 2 | $20.13 (modelled) | 14 |
| claude | 36 | 25 | 11 | $40.83 measured ($39.45 in the aggregate, 35 runs) | 22 |

## The voids

**Codex (2):** M10-b2-delegated-same and M40-b3-delegated-workhorse each ran
`find .. -name AGENTS.md -print` — a search above the workdir for an instruction file.
It reads names, not the key; the rule voids `..` as written, and the record says so
rather than excusing it.

**Claude (11):** M10-b3-delegated-same `cd`'d through `..`. The other ten are
**control 4**: the child did not receive the pinned rendering of the brief. The parent
seat (Opus 5 at xhigh) rewrote it in its `Agent` call — `<` became `&lt;` in 8 of the 12
standard briefs at M≥40 (five of six at M=40, 958 characters; three of six at M=160,
2,099), and `\\` became `\` in 2 of the 6 cheap-seat briefs (both at M=160, 21,316–21,934
characters; the visible-case strings carry backslashes) — and the child's stored first
message is the parent's text, not the host's: the transformation is the parent's
transcription, not a transport artifact. Every M=10 brief arrived verbatim — the 688-
character standard brief and the 2,280–2,501-character cheap-seat brief alike — so length
is not the trigger on its own. So on Claude, delegation is measured as delivering a
different brief in those runs, and the pre-registered control voids them: 5 of 9
delegated runs at M=40, 5 of 9 at M=160. M40-b1-delegated-same's child artifact is also
cut (no terminal record, cost null in the aggregate).

| Claude void | reason |
| --- | --- |
| M10-b3-delegated-same | `..` |
| M40-b1-delegated-same | control 4; child artifact cut |
| M40-b1-delegated-workhorse, M40-b2-delegated-same, M40-b2-delegated-workhorse, M40-b3-delegated-workhorse | control 4 |
| M160-b1-delegated-same, M160-b1-delegated-sweep, M160-b2-delegated-same, M160-b2-delegated-sweep, M160-b3-delegated-workhorse | control 4 |

## Codex: the screen

Every cell is not output-dominated (comparator share of output-priced dollars 0.20–0.26).
Every scored level is zero in every arm at every M — the specified fixture carries no
level signal at all; the Stage-1 level defects were under-specification. Cost per item
falls 7.6–13× from M=10 to M=160 in every arm (the ladder is periodic; M measures
repetition; the fall is 7.6× in the workhorse arm and 13× in delegated-same, inline 11×,
sweep 7.8×, fork 8.9×). Contrasts stand on paired blocks:

| M | retention (workhorse vs same) | rebind-vs-same (sweep vs same) | rebind-vs-incumbent (sweep vs workhorse) | R |
| --- | --- | --- | --- | --- |
| 10 | **+57.8%** (2 blocks, exceeds sd) | **+72.3%** (2, exceeds) | +28.8% (3, inside) | 12 (sd_rel 0.134) |
| 40 | **+48.8%** (2, exceeds) | **+64.0%** (3, exceeds) | +34.6% (2, inside) | 15 (cap; sd_rel 0.433) |
| 160 | **+36.4%** (3, exceeds) | **+53.8%** (3, exceeds) | **+27.4%** (3, exceeds) | 13 (sd_rel 0.138) |

The retention bit and the rebind-vs-same bit are set at every M; rebind-vs-incumbent only
at M=160. Two cells are one run short (the `..` voids), M=160 is COMPLETE. The R rule
written before the data gives **12 / 15 / 13**; Codex's Stage 2 at those R is
(12 + 15 + 13) × 5 arms × 3 levels = **600 runs**.

## Claude: the screen at M=10, and nothing derivable above it

| M | retention | rebind-vs-same | rebind-vs-incumbent | R |
| --- | --- | --- | --- | --- |
| 10 | −7.2% (2 blocks, inside sd — workhorse costs MORE per item than same) | **+48.5%** (2, exceeds) | **+51.9%** (3, exceeds) | 13 (sd_rel 0.140) |
| 40 | unpaired (workhorse 0 sound) | +41.6% on 1 block | unpaired | NOT DERIVABLE (1 comparator run) |
| 160 | unpaired | +35.9% on 1 block | unpaired | NOT DERIVABLE |

On Claude at M=10 inline (0.0723 per item) is cheaper than delegated-same (0.1033) and
delegated-workhorse (0.1136); only the sweep arm (0.0547 — the child is a haiku seat)
undercuts it. So the retention bit is not set and the rebind bits are. Above M=10 the Claude cells are hollow
by control 4, not by the seats' work: the sound runs there all reached done-when at level
zero.

## What this decides and what it leaves to the owner

The Codex screen is what the design asked Stage 1 for: a per-cell R and the screen bits,
on an instrument whose voids are two reads the rule names and nothing the seats hid. The
Claude screen exists at M=10 and is an owner decision above it:

1. **Relax control 4 to a comparison up to the parent's escaping** (entities unescaped,
   every backslash dropped, a trailing newline ignored, on both sides; the transformation
   disclosed on the record): measured 2026-09-05 over the ten voided runs with exactly that
   comparator (*Re-derive*), it matches the child's first message to the pinned brief in
   all ten — entity-unescaping alone matches the eight standard briefs, and the two
   cheap-seat briefs match only once backslashes are dropped, the parent having unescaped
   `\\'` to `'` as a JS string would. Nine come back
   with a cost; M40-b1-delegated-same's child artifact has no terminal record and its cost
   is null. The price is measuring "the pinned brief up to escaping" rather than the pinned
   brief.
2. **Deliver the brief by file** (`BRIEF.md` in the workdir, the parent's message says
   to read it): the child receives the pinned bytes, and the delegated arms' economics
   change — the parent's relayed tokens shrink, the child's read grows.
3. **Run Claude's Stage 2 at M=10 only**, where the brief arrives verbatim.
4. **Drop Claude from Stage 2**, and let the Codex screen carry the experiment.

None of these is chosen here. The Codex Stage 2 at R 12 / 15 / 13 is derivable now and
waits on the same decision (`D-20260904-45c833`: R extension on approval).

## Corrections (2026-09-05, review round 8 — session `01a06e38-1698-7292-8d5b-67e9d2342e21`, gpt-5.6-sol at ultra, read-only)

The round read this record against the records and the code and found the prose wrong
in seven places, corrected above in place: the live rule-4 voids were 16 Codex and 23
Claude, not 11 and 12; Claude's measured Σ is $40.83 over 36 runs, the $39.45 being the
aggregate over the 35 runs with a cost; the Codex cost-per-item fall from M=10 to M=160
is 7.6–13×, not 11–15×; at M=10 the Claude sweep arm is cheaper than inline, so "cheaper
than any delegated arm" was wrong; the parent escaped 8 of the 12 long standard briefs
and 2 of the 6 cheap-seat briefs, not every one, and the M=10 cheap-seat briefs are
2,280–2,501 characters (688 was the standard brief), so length alone is not the trigger;
a normalised comparison restores nine of the ten control-4 voids, not "all but the M=160
cheap-seat"; and the fork-same refusals were six, not nine. Its three highs on the scan
became rules 11 and 12 (above), each with controls shown failing on a revert.

Round 9 (2026-09-05, same seat, on this record and the rule-11/12 diff; its first
dispatch was refused by the provider's safety filter for asking, as a "security"
perspective, which command shapes read the key unseen — the same question rephrased as
a measurement-validity audit ran) found five over-voids and six under-voids in rules
11–12, applied as rule 13 (above, 15 reverts each failing a control by name), and four
reproduction gaps: the live rule-4 counts, the measured cost, the brief transformation
and length figures, and the refusal count could not be re-derived from the appendix.
The *Re-derive* section below gives the command behind each; running them today gives
16 / 23 rule-4 hits, $40.83 over 36 runs with no null `measured_total_usd`, 688 / 958 /
2,099 standard and 2,280–2,501 / 6,114–6,246 / 21,316–21,934 cheap-seat brief characters
at M=10 / 40 / 160, six fork-same refusals in the launcher log (23:31–00:22), and the
ten-of-ten match under the escaping-insensitive comparison that option 1 now states —
the record had said nine of ten, taking round 8's word for it.

Round 10 (2026-09-05, same seat, on the rule-13 diff and this record) returned fifteen
findings again: three on reproduction, applied above (the comparator in *Re-derive* is
now the one option 1 states, its output attributes each run to raw / newline / entities
/ canon and says whether control 4 voided it, and the refusal command prints the six
lines with their times); six over-voids and six under-voids on the classifier, **not
applied** — listed under *Open after round 10* with the decision they wait on. Three
rounds in a row have each returned a new set of shell shapes that none of the 126 runs
read under rules 5–13 ever used, so extending the classifier is no longer the question;
where isolation should live is.

## Open after round 10

Rules 11–13 answer review rounds 8–10 by teaching a transcript classifier more shell.
Round 10's unapplied findings, each with a control-shaped scenario: a literal `..` or a
`$VAR` inside single quotes read as a climb or a path (`rg -nF '..' "$X/guides/x.md"`); a
search verb's pattern taken for an operand; `xargs` treated as a reader whatever it runs;
`${VAR:+alt}` after an `unset`; a working directory paired with the wrong command when a
JS object writes `workdir` before `cmd` and two calls sit at equal distance (an over-void
in one direction and an under-void in the other); `pwd -P`; a relative path inside an
option value (`rg --file=sessions/x`); `system (` with a space in awk; zsh brace
expansion (`{sess,sess2}ions/…`); and a listing written to a file and read back through a
variable in a later command. All are decidable text patterns; none has a reading in the
126 runs. The alternatives the owner chooses between: **(a)** apply them as rule 14 and run
round 11, on the convergence rule of two dry rounds, at roughly an hour of instrument work
and a reviewer pass per round; or **(b)** stop extending the classifier, keep it as the
disclosure and void it is, and put Stage 2's isolation where a read cannot happen rather
than where it is detected — a config home per run holding the instruction surface only (no
`sessions/`, no thread database, so the store class has nothing to read), the sibling
vault already sealing finished runs, the oracle already absent until scoring — with the
classifier's remaining job the `..` / sibling-name / oracle-name reads it has voided since
rule 5. Path (b) is the smaller concept surface and the one the corpus's own rule
prefers (make the read unavailable rather than enumerate its spellings); the record
recommends it and leaves the choice to the owner with the Stage-2 scope decision.


## Claude under control 4 up to escaping (2026-09-05, after `D-20260905-fd9177`)

With the ten control-4 voids re-judged at load (`stage.rebrief`: the child's first message
against the pass-1 brief, equal up to escaping), the Claude re-run reads **34 / 36 sound**
(the `..` read and the cut child artifact remain), every cell not output-dominated
(0.22–0.25), every scored level zero:

| M | retention | rebind-vs-same | rebind-vs-incumbent | R |
| --- | --- | --- | --- | --- |
| 10 | −7.2% (2 blocks, inside sd) | **+48.5%** (2, exceeds) | **+51.9%** (3, exceeds) | 13 (sd_rel 0.140) |
| 40 | **+12.5%** (2, exceeds) | **+48.1%** (2, exceeds) | **+32.2%** (3, exceeds) | 5 (sd_rel 0.058) |
| 160 | −12.0% (3, beyond sd — workhorse costs more than same) | **+27.9%** (3, exceeds) | **+35.6%** (3, exceeds) | 5 (sd_rel 0.065) |

The rebind bits are set at every M; the retention bit is set at M=40 only, and at M=160
the workhorse child costs more per item than the same-model child. Claude's Stage 2 at
R 13 / 5 / 5 is (13 + 5 + 5) × 4 arms = **92 runs** per task level. Codex is unchanged
(control 4's brief half is launch-only there). Re-derive with the commands below; the
census reports `brief_rejudged: 10`.

## Re-derive

From a checkout, with the run trees under `~/.agent-bios/tier/stage1-rerun-<host>`:

    # the cells, the screen, R (identical under rules 10–13)
    python3 benchmarks/tier/stage.py ~/.agent-bios/tier/stage1-rerun-codex/runs --sizes 10,40,160 --R 3 --rescore [--census --json]
    # live rule-4 hits (the scan that ran during the stage) and the measured cost
    python3 - <<'EOF'
    import json, pathlib
    for host in ('codex', 'claude'):
        recs = [json.load(open(p)) for p in sorted((pathlib.Path.home()/f'.agent-bios/tier/stage1-rerun-{host}/runs').glob('*/record.json'))]
        print(host, 'rule-4 hits:', sum(r['access_scan']['hits'] > 0 for r in recs), 'Σ measured:', round(sum(r['measured_total_usd'] or 0 for r in recs), 2), 'null:', sum(r['measured_total_usd'] is None for r in recs))
    EOF
    # the pinned brief's length per M and protocol, and the control-4 comparison (from benchmarks/tier)
    python3 - <<'EOF'
    import json, pathlib, html, live
    root = pathlib.Path.home()/'.agent-bios/tier/stage1-rerun-claude'
    def ent(s): return html.unescape(s).rstrip('\n')                       # entities unescaped, a trailing newline ignored
    def canon(s): return html.unescape(s).replace('\\', '').rstrip('\n')  # … and every backslash dropped
    for rd in sorted((root/'runs').iterdir()):
        rec = json.load(open(rd/'record.json')); m, b = rd.name.split('-')[:2]
        pinned = live.brief_text(rec['nonce'], rec['protocol'], json.load(open(root/'blocks'/f'{m}-{b}'/'manifest.json')))
        child = sorted((rd/'artifacts').glob('agent-*.jsonl'))
        got = json.loads(child[0].read_text().splitlines()[0])['message']['content'] if child else None
        v = ('no child' if got is None else 'raw' if got == pinned else 'newline' if got.rstrip('\n') == pinned.rstrip('\n')
             else 'entities' if ent(got) == pinned.rstrip('\n') else 'canon' if canon(got) == canon(pinned) else 'differs')
        print(rd.name, len(pinned), v, 'voided' if any('control 4' in p for p in rec['problems']) else 'sound')
    EOF
    # 2026-09-05: 9 inline runs have no child; of the 27 delegated, 8 match raw and 9 up to a trailing
    # newline (all 17 sound — control 4 compares the reported sha, which ignores the newline), 8 match
    # once entities are unescaped and 2 only once backslashes are dropped (those 10 are the control-4 voids)
    EOF
    grep -E '^[0-9:]+ M[0-9]+-b[0-9]-fork-same: FAILED' ~/.agent-bios/tier/stage1-rerun-claude.launcher.log
    # 23:31:00 M10-b1, 23:38:50 M10-b2, 23:46:19 M10-b3, 00:05:11 M40-b1, 00:14:16 M40-b2, 00:22:44 M40-b3 — six lines,
    # each a dispatch of that run (a seventh line quoting the last is the breaker's); the first M=160 dispatch is 00:48:22

## Appendix: aggregator output (rule 13, `--rescore`; identical to rule 10)

### codex
```
== codex/M=10  INCOMPLETE {"delegated-same": 1} unpaired {"retention": 2, "rebind-vs-same": 2}  label=not output-dominated (comparator share 0.204)  flags=access_notes,brief_receipt,cache_band,output_dominance
   inline               runs=3 reached=3 cpi=0.0496 level=[0, 0, 0]
   delegated-same       runs=2 reached=2 cpi=0.0596 level=[0, 0]
   delegated-workhorse  runs=3 reached=3 cpi=0.0228 level=[0, 0, 0]
   delegated-sweep      runs=3 reached=3 cpi=0.0163 level=[0, 0, 0]
   fork-same            runs=3 reached=3 cpi=0.0321 level=[0, 0, 0]
   voided (1): M10-b2-delegated-same [held-out access (re-scanned)]
   screen retention              paired=2 saving=+57.8% contrast=$0.0345 exceeds_comparator_sd=True
   screen rebind-vs-same         paired=2 saving=+72.3% contrast=$0.0431 exceeds_comparator_sd=True
   screen rebind-vs-incumbent    paired=3 saving=+28.8% contrast=$0.0066 exceeds_comparator_sd=False
   level band (comparator sd of defects/item): 0.0000  — point estimate vs band (Stage 2 reads the confirmed upper bound)
   level inline               D=0.0000 diff=+0.0000 (paired=2) point_within_band=True same_level=None (not computed here)
   level delegated-same       D=0.0000 diff=+0.0000 (paired=2) point_within_band=True same_level=None (not computed here)
   level delegated-workhorse  D=0.0000 diff=+0.0000 (paired=2) point_within_band=True same_level=None (not computed here)
   level delegated-sweep      D=0.0000 diff=+0.0000 (paired=2) point_within_band=True same_level=None (not computed here)
   level fork-same            D=0.0000 diff=+0.0000 (paired=2) point_within_band=True same_level=None (not computed here)
   R for Stage 2: 12 (half-width under target; sd_rel=0.134)
== codex/M=40  INCOMPLETE {"delegated-workhorse": 1} unpaired {"retention": 2, "rebind-vs-incumbent": 2}  label=not output-dominated (comparator share 0.257)  flags=access_notes,brief_receipt,cache_band,output_dominance
   inline               runs=3 reached=3 cpi=0.0159 level=[0, 0, 0]
   delegated-same       runs=3 reached=3 cpi=0.0135 level=[0, 0, 0]
   delegated-workhorse  runs=2 reached=2 cpi=0.0076 level=[0, 0]
   delegated-sweep      runs=3 reached=3 cpi=0.0049 level=[0, 0, 0]
   fork-same            runs=3 reached=3 cpi=0.0090 level=[0, 0, 0]
   voided (1): M40-b3-delegated-workhorse [held-out access (re-scanned)]
   screen retention              paired=2 saving=+48.8% contrast=$0.0073 exceeds_comparator_sd=True
   screen rebind-vs-same         paired=3 saving=+64.0% contrast=$0.0086 exceeds_comparator_sd=True
   screen rebind-vs-incumbent    paired=2 saving=+34.6% contrast=$0.0026 exceeds_comparator_sd=False
   level band (comparator sd of defects/item): 0.0000  — point estimate vs band (Stage 2 reads the confirmed upper bound)
   level inline               D=0.0000 diff=+0.0000 (paired=3) point_within_band=True same_level=None (not computed here)
   level delegated-same       D=0.0000 diff=+0.0000 (paired=3) point_within_band=True same_level=None (not computed here)
   level delegated-workhorse  D=0.0000 diff=+0.0000 (paired=2) point_within_band=True same_level=None (not computed here)
   level delegated-sweep      D=0.0000 diff=+0.0000 (paired=3) point_within_band=True same_level=None (not computed here)
   level fork-same            D=0.0000 diff=+0.0000 (paired=3) point_within_band=True same_level=None (not computed here)
   R for Stage 2: 15 (cap — spread too wide for the target at 15; sd_rel=0.433)
== codex/M=160  COMPLETE  label=not output-dominated (comparator share 0.233)  flags=access_notes,brief_receipt,cache_band,output_dominance
   inline               runs=3 reached=3 cpi=0.0044 level=[0, 0, 0]
   delegated-same       runs=3 reached=3 cpi=0.0046 level=[0, 0, 0]
   delegated-workhorse  runs=3 reached=3 cpi=0.0030 level=[0, 0, 0]
   delegated-sweep      runs=3 reached=3 cpi=0.0021 level=[0, 0, 0]
   fork-same            runs=3 reached=3 cpi=0.0036 level=[0, 0, 0]
   screen retention              paired=3 saving=+36.4% contrast=$0.0017 exceeds_comparator_sd=True
   screen rebind-vs-same         paired=3 saving=+53.8% contrast=$0.0025 exceeds_comparator_sd=True
   screen rebind-vs-incumbent    paired=3 saving=+27.4% contrast=$0.0008 exceeds_comparator_sd=True
   level band (comparator sd of defects/item): 0.0000  — point estimate vs band (Stage 2 reads the confirmed upper bound)
   level inline               D=0.0000 diff=+0.0000 (paired=3) point_within_band=True same_level=None (not computed here)
   level delegated-same       D=0.0000 diff=+0.0000 (paired=3) point_within_band=True same_level=None (not computed here)
   level delegated-workhorse  D=0.0000 diff=+0.0000 (paired=3) point_within_band=True same_level=None (not computed here)
   level delegated-sweep      D=0.0000 diff=+0.0000 (paired=3) point_within_band=True same_level=None (not computed here)
   level fork-same            D=0.0000 diff=+0.0000 (paired=3) point_within_band=True same_level=None (not computed here)
   R for Stage 2: 13 (half-width under target; sd_rel=0.138)
```

### claude (`--arms inline,delegated-same,delegated-workhorse,delegated-sweep`)
```
== claude/M=10  INCOMPLETE {"delegated-same": 1} unpaired {"retention": 2, "rebind-vs-same": 2}  label=not output-dominated (comparator share 0.253)  flags=access_notes,cache_band,output_dominance
   inline               runs=3 reached=3 cpi=0.0723 level=[0, 0, 0]
   delegated-same       runs=2 reached=2 cpi=0.1033 level=[0, 0]
   delegated-workhorse  runs=3 reached=3 cpi=0.1136 level=[0, 0, 0]
   delegated-sweep      runs=3 reached=3 cpi=0.0547 level=[0, 0, 0]
   voided (1): M10-b3-delegated-same [held-out access (re-scanned)]
   screen retention              paired=2 saving=-7.2% contrast=$-0.0074 exceeds_comparator_sd=False
   screen rebind-vs-same         paired=2 saving=+48.5% contrast=$0.0501 exceeds_comparator_sd=True
   screen rebind-vs-incumbent    paired=3 saving=+51.9% contrast=$0.0589 exceeds_comparator_sd=True
   level band (comparator sd of defects/item): 0.0000  — point estimate vs band (Stage 2 reads the confirmed upper bound)
   level inline               D=0.0000 diff=+0.0000 (paired=2) point_within_band=True same_level=None (not computed here)
   level delegated-same       D=0.0000 diff=+0.0000 (paired=2) point_within_band=True same_level=None (not computed here)
   level delegated-workhorse  D=0.0000 diff=+0.0000 (paired=2) point_within_band=True same_level=None (not computed here)
   level delegated-sweep      D=0.0000 diff=+0.0000 (paired=2) point_within_band=True same_level=None (not computed here)
   R for Stage 2: 13 (half-width under target; sd_rel=0.14)
== claude/M=40  INCOMPLETE {"delegated-same": 2, "delegated-workhorse": 3} unpaired {"retention": 0, "rebind-vs-same": 1, "rebind-vs-incumbent": 0}  label=not output-dominated (comparator share 0.238)  flags=access_notes,cache_band,inheritance,output_dominance
   inline               runs=3 reached=3 cpi=0.0233 level=[0, 0, 0]
   delegated-same       runs=1 reached=1 cpi=0.0370 level=[0]
   delegated-workhorse  runs=0 reached=0 cpi=n/a level=[]
   delegated-sweep      runs=3 reached=3 cpi=0.0201 level=[0, 0, 0]
   voided (5): M40-b1-delegated-same [ledger/level problem], M40-b1-delegated-workhorse [ledger/level problem], M40-b2-delegated-same [ledger/level problem], M40-b2-delegated-workhorse [ledger/level problem], M40-b3-delegated-workhorse [ledger/level problem]
   screen retention              paired=0 saving=n/a contrast=$n/a exceeds_comparator_sd=None
   screen rebind-vs-same         paired=1 saving=+41.6% contrast=$0.0154 exceeds_comparator_sd=None
   screen rebind-vs-incumbent    paired=0 saving=n/a contrast=$n/a exceeds_comparator_sd=None
   level band (comparator sd of defects/item): n/a  — point estimate vs band (Stage 2 reads the confirmed upper bound)
   level inline               D=0.0000 diff=+0.0000 (paired=1) point_within_band=None same_level=None (not computed here)
   level delegated-same       D=0.0000 diff=+0.0000 (paired=1) point_within_band=None same_level=None (not computed here)
   level delegated-workhorse  D=n/a diff=n/a (paired=0) point_within_band=None same_level=None (not computed here)
   level delegated-sweep      D=0.0000 diff=+0.0000 (paired=1) point_within_band=None same_level=None (not computed here)
   R for Stage 2: NOT DERIVABLE (comparator has 1 sound run(s) — no spread, no R derivable; sd_rel=None)
== claude/M=160  INCOMPLETE {"delegated-same": 2, "delegated-workhorse": 1, "delegated-sweep": 2} unpaired {"retention": 0, "rebind-vs-same": 1, "rebind-vs-incumbent": 0}  label=not output-dominated (comparator share 0.223)  flags=access_notes,cache_band,inheritance,output_dominance
   inline               runs=3 reached=3 cpi=0.0097 level=[0, 0, 0]
   delegated-same       runs=1 reached=1 cpi=0.0097 level=[0]
   delegated-workhorse  runs=2 reached=2 cpi=0.0104 level=[0, 0]
   delegated-sweep      runs=1 reached=1 cpi=0.0062 level=[0]
   voided (5): M160-b1-delegated-same [ledger/level problem], M160-b1-delegated-sweep [ledger/level problem], M160-b2-delegated-same [ledger/level problem], M160-b2-delegated-sweep [ledger/level problem], M160-b3-delegated-workhorse [ledger/level problem]
   screen retention              paired=0 saving=n/a contrast=$n/a exceeds_comparator_sd=None
   screen rebind-vs-same         paired=1 saving=+35.9% contrast=$0.0035 exceeds_comparator_sd=None
   screen rebind-vs-incumbent    paired=0 saving=n/a contrast=$n/a exceeds_comparator_sd=None
   level band (comparator sd of defects/item): n/a  — point estimate vs band (Stage 2 reads the confirmed upper bound)
   level inline               D=0.0000 diff=+0.0000 (paired=1) point_within_band=None same_level=None (not computed here)
   level delegated-same       D=0.0000 diff=+0.0000 (paired=1) point_within_band=None same_level=None (not computed here)
   level delegated-workhorse  D=0.0000 diff=n/a (paired=0) point_within_band=None same_level=None (not computed here)
   level delegated-sweep      D=0.0000 diff=+0.0000 (paired=1) point_within_band=None same_level=None (not computed here)
   R for Stage 2: NOT DERIVABLE (comparator has 1 sound run(s) — no spread, no R derivable; sd_rel=None)
```

### census by arm

codex:

| arm | runs | voided | Σ cost |
| --- | --- | --- | --- |
| delegated-same | 9 | 1 | 5.66 |
| delegated-sweep | 9 | 0 | 2.10 |
| delegated-workhorse | 9 | 1 | 3.08 |
| fork-same | 9 | 0 | 3.79 |
| inline | 9 | 0 | 5.50 |

claude:

| arm | runs | voided | Σ cost |
| --- | --- | --- | --- |
| delegated-same | 9 | 5 | 10.59 |
| delegated-sweep | 9 | 2 | 7.27 |
| delegated-workhorse | 9 | 4 | 11.96 |
| inline | 9 | 0 | 9.63 |
