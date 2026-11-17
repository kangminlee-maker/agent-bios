---
created_at: 2026-11-15T21:25:00+09:00
head: 7a7752e          # the commit the content was true at
kind: review
supersedes: none (it corrects one sentence of 2026-11-15T1411--03042a3--rr-1-ran-to-its-close-on-a-copy-and-what-that-authorizes.md, which stays as written)
---

# Release 1 can change a library file, and RR-1 changed none

`…T1411--03042a3--rr-1-ran-to-its-close-on-a-copy-and-what-that-authorizes.md`, under "What RR-1
does not establish", says of the write path: "In release 1 this is the expected outcome of every run
until a kind other than `unclassified` can be derived". That sentence is false. It described the data
of one window as a property of the code. The lead repeated it to the owner, and corrected it on
2026-11-15 (D-20261115-9311c2).

What the code derives in release 1, read from `session-distill/runlib/derive.py` and
`session-distill/tables/allowed_pairs.json` at 7a7752e:

- A lifecycle candidate both judges mark `no_longer_arises` is `obsolete`, whose allowed
  dispositions include `reduce`.
- A redundancy candidate with enough covering units has the diagnosis `redundant`, whose allowed
  dispositions include `reduce` by merge.
- A legacy incubating entry falls under `legacy_maintenance`, which allows `place` when the entry is
  admitted and eligible on the window's evidence.

Each of those reaches S7 with a disposition that carries operations, and so reaches S11's write path.
What release 1 does not derive is a unit outcome, so a formed candidate from a session's events is
mostly `unclassified`, whose only disposition is `none`. RR-1's sixteen formed candidates were all
`unclassified`, and the five S7 proposed for carried no operation. That is the outcome of that window,
not of every run.

What changes because of this:

- T1411's first point under "What RR-1 does not establish" stands: RR-1 did not exercise the write
  path with a real change. The reason it gives for expecting that of every run does not.
- The owner chose to keep library-changing proposals open in release 1 and to fix the write-path
  findings of the WP-12 round-2 review before the publish (D-20261115-9311c2). Those fixes are in
  7a7752e, verified by revert trials, not by a third review round and not by a real run.
- The guide's "What a release 1 run produces" paragraph now says which dispositions can change a
  file and that RR-1 changed none.

Re-derive the kinds from the two files above before relying on this list; the table is the authority,
and this record is a reading of it at one commit.
