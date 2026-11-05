---
created_at: 2026-11-05T20:47:00+09:00
head: e54cfe8
kind: design
supersedes: null
---

# DW5's readings cite what they judge by, and the expansion gap is narrower than recorded

WP-08b, a fix to commit 2 (`e54cfe8`). Review W round 1 on `6ee4a22..e54cfe8` accepted with four minor findings, all
on DW5. This commit answers them before the live pair runs. Sections 1 to 3 change the fixture's golden answers and
the self-test's controls, not code. Section 4 clarifies the record
`2026-11-05T2017--4f34ae3--dw5-reads-two-expected-observations-from-a-seeded-ledger-and-an-occasion-only-the-search-finds-stays-pending.md`.
It does not replace that record.

## 1. The golden readings cite what they judge by

**What was wrong.** read.md asks each observation instance for evidence that shows both the exposure and the
behaviour. In DW5's golden run, each P-1 instance cited only its own ask: lines 3, 9, 13 and 20. The instance control
checked only that each instance cited something.

**The fix.** `FX_DW5_CITES` says what each P-1 reading cites, and `fx_dw5_answers` writes it. A record that two
readings cite is quoted once.

| Occasion | Cited records (lines) |
| --- | --- |
| ask 1 | the ask, and the answer after it (3, 4) |
| ask 2 | the plain guide's read, the ask, and the answer after it (5, 9, 10) |
| ask 3 | the plain guide's read, the ask, the answer after it, and the person asking again (5, 13, 14, 15) |
| ask 4 | the ask, and the answer after it (20, 21) |
| the test run | the line that did not pass (26), as before |

**The control.** The instance control now derives the expected lines from a rule. It does not read `FX_DW5_CITES`, so
changing the table cannot satisfy it. The rule:
- every P-1 instance cites its ask and the next assistant record;
- an eligible instance also cites the plain guide's read;
- a not-observed instance also cites the next human record;
- T-1's instance cites the test run's record.

It compares those lines with the lines of the evidence S3 stored for each instance.

## 2. The order the exposures rest on

**What was wrong.** The placement control held which window each record is in, but not their order. Moving the plain
guide's read past the second ask and its answer kept every DW5 control passing, before this commit. Yet that order is
what makes the second ask eligible.

**The fix.** A new control holds the order by line:
- the first ask, then the plain guide's read, then the second ask, then the third;
- the test guide's read, then the test run, then its report.

## 3. Every field of the due observations

**What was wrong.** The packet control checked each observation's label and occasion criteria, and that no retrieval
term was shown. It did not check the exposure rule or the expected behaviour. Before this commit, a packet with either
line deleted still passed it. Only the older general control (`4b`) failed.

**The fix.** The control now requires each packet's due list to equal, line by line, both observations with all three
fields: occasion criteria, exposure rule and expected behaviour.

## 4. The scope of the expansion gap (clarifies the 2017 record)

The 2017 record says that an occasion only the search finds stays pending unless another eligible occasion decides the
observation. That is too broad. Being found in an expansion does not by itself make an occasion exposure_unknown:
- An expansion can show its own exposure evidence within the text it expands.
- When no window judgement conflicts with it, `settle_occasions` keeps eligible, and the occasion can decide the
  observation.
- The reviewer probed this: with T-1's exposure alone changed to eligible, code derived T-1 not observed.

The gap is limited to two kinds of occasion:
- **Context outside the expansion.** The exposure can only be judged from records outside the expansion, which shows
  only the omitted middle (`overlap=False`). DW5's T-1 is one: the guide's read comes before the test run.
- **Conflicting readings.** The window and the expansion judge the same occasion's exposure differently, so
  `settle_occasions` makes it exposure_unknown (D-20261104-a9e2d2).

**How resolutions treat exposure_unknown (§11).**
- One eligible occasion that is not observed decides not observed, even beside exposure_unknown occasions. DW5's P-1
  is decided this way.
- Eligible occasions that are all observed do not decide observed while an exposure_unknown occasion stands. The
  observation stays pending.

The fix candidates in the 2017 record stand unchanged:
1. give an expansion the original window's surrounding records as overlap;
2. combine the expansion's occasion with the original window's exposure judgement.

Both apply only to the two kinds of occasion above.

## The live packets do not change

The golden answers and the controls changed; the packets did not. Measured on this commit with the live legs' run
names, each call's driver bytes equal those at `e54cfe8`:
- dw2: 14,273, 17,962 and 9,243;
- dw5: 27,845, 18,772 and 19,700.

## Pretrial

Each row bends one control's subject alone and must fail that control by name:
- `dw5_guide_moved`: the plain guide's read is moved past the second ask (§2).
- `dw5_rule_dropped`, `dw5_behaviour_dropped`, `dw5_occasion_dropped`: one field is dropped from the due list (§3).
- `dw5_cites_ask_only`: the readings cite their asks alone again (§1).

Before the fix, the first three rows failed no DW5 control.
