---
name: repo-charter
description: Write or overhaul a repository's AGENTS.md (with CLAUDE.md as a one-line shim) for the agents that will work in it. Use when a repo has no agent instructions, when its AGENTS.md is a preamble that names nothing, or when the user asks to set a repo up for coding agents. Reads invariants and traps out of the code rather than pasting a template.
---

# Repo charter

A repository's AGENTS.md is the repo's own layer of agent instruction — what global
instructions cannot supply because it is true only here. This skill produces that layer for a real
repository, and it produces it *from the repository*: the substantive half is reading the
invariants, the gates and the traps out of the code, and no template can do that part.

The output belongs to the repository — its team, its contributors, its git history. Nothing
this skill writes carries a marker, a version stamp, or copyable boilerplate, because nothing
outside that repo will ever update it.

## 0. First decide whether the file is warranted

Many repositories correctly have no instruction file. Content and documentation repos need
at most a few lines of orientation; a personal repo rarely needs governance; and a one-line
fix in someone else's project is not the moment to charter it — the file is theirs to create.
Write one when agents will do repeated, non-trivial work here and the repo carries rules a
newcomer would otherwise learn by breaking something. If the answer is no, say so and stop;
an empty file with a heading is worse than none.

Read enough to answer honestly before deciding: the top-level tree, the package or build
manifest, hook and CI configuration, and the last fifty commit subjects. Steps 0 and 1 are
provisional; step 3 may revise them. **Draft from the code first** — if the repo already has
an instruction file, open it only at step 8, because reading it earlier anchors your
structure to it and the comparison stops being evidence.

## 1. Purpose type, then category mix

Decide what the repo is *for* before writing a line. The type fixes which categories must be
thick; everything else stays thin or absent.

| Purpose type | Categories that must be thick |
| --- | --- |
| Library / framework that accepts outside contribution | contribution protocol, completion gates, hard boundaries |
| Application / product | project invariants, pitfall warnings, co-change duties |
| CLI / single-author tool | repo orientation, project invariants, task procedure |
| Monorepo / platform | context routing, task procedure |
| Instructions / payload the repo publishes elsewhere (the code is delivery, the content is the product) | hard boundaries, co-change duties, completion gates |
| Content / docs | repo orientation only, minimal |

A repo may take two rows; take the union and note which row explains each thick category.

The category vocabulary, in one line each: **repo orientation** (what lives where, so nobody
has to search), **command recipes** (the exact commands), **house form** (the shape of
outputs), **project invariants** (semantic contracts the code must keep), **context routing**
(when to open which document, skill or tool), **task procedure** (the order for a kind of
work), **pitfall warnings** (traps and environment quirks that cause misdiagnosis),
**contribution protocol** (how a change gets accepted), **completion gates** (what must pass
before "done"), **co-change duties** (change X, then also Y), **hard boundaries** (never),
**human authority** (where to stop and hand over), **agent conduct** (how the agent itself
operates). Across thousands of real files, human authority is the rarest of these — people
write prohibitions but not escalation paths — so it is asked for explicitly in step 5.

## 2. AGENTS.md is the body; CLAUDE.md is a shim

Write one file: `AGENTS.md`, which Codex reads natively. Where Claude Code is used, add a
`CLAUDE.md` whose only content is an import of `AGENTS.md` (`@AGENTS.md`), plus at most a
sentence saying why the shim exists — and if that sentence claims something about a tool's
behaviour, date it or drop it, because such claims rot into lies. Two bodies drift; one body
and one pointer cannot. A file's name does not tell an agent which tool it is for — content
that opens "guidance for tool X" is copied between tools verbatim, so leave the tool's name
out of the body; the shim sentence is the one exception.

## 3. Read the invariants and traps out of the code

This is the work, and it is done by reading, not by asking the repo's owner to dictate.
For an existing repo, collect at least these before drafting:

- **What runs before a commit and what it enforces.** Hooks, CI configuration, gate scripts,
  lint and test entrypoints. For each rule you state, name the file that enforces it, and
  mark the rules nothing enforces as convention — a reader must be able to tell a gate from
  a wish.
- **What a green check does and does not prove.** A test suite that skips a leg, a check that
  runs against a fixture rather than the real path, a scan whose subject set can be empty.
  These belong in the file because they are exactly what a newcomer misreads.
- **Generated paths.** Anything produced from another file must be named as such, with the
  generator and the command that regenerates it; hand-editing a projection is the most
  common silent defect.
- **Where authority lives.** For each value that appears in more than one place, which copy
  is the source and how the others follow it.
- **What the history paid for.** Read the recent log and any postmortems or dated design
  notes for mistakes that cost a real attempt — the deploy that took the wrong tree, the
  command whose exit status lied, the flag that was rejected rather than implemented. Each
  becomes a present-tense warning that names the symptom.
- **Runtime shape that a reader cannot infer.** Which entrypoint is real, which directory
  is payload versus tooling, which environment the tests assume.

State each finding as a rule about the present, in one or two sentences, and cite the code
by **file and identifier** — function, constant, leg name — never by line number: a symbol
survives an edit and is greppable, a line number is wrong within a day. A rule that cannot
cite its enforcer or its evidence is a candidate for deletion. Stop collecting when a new
source stops producing rules you would keep — usually after the hooks, the gate entrypoints,
the packaging manifest, the installer, and the recent commit subjects.

## 4. Choose the sections from the findings, not from a template

Group what step 3 produced under headings that match the repo's thick categories from
step 1. Order by what an agent hits first: orientation and the pre-commit contract before
style; traps near the commands that trigger them. The file is re-sent to every session, so it
is a token budget: if the draft exceeds roughly 2,000 words, the excess is a guide — move the
longest section behind a pointer and keep the one rule that says when to read it.

## 5. Ask for human authority explicitly

Ask the user, in outcome terms, which decisions an agent must bring to a person rather than
settle: releases and publishes, schema or data migrations, anything touching credentials or
production, deleting or rewriting history, spending money, changing a public contract.
Write the answer as a short list of *stop points* with what to bring (evidence, options),
not as a prohibition. If the user has no answer yet, record the question as open in the
file rather than inventing a policy; if the run is unattended, draft the stop points as a
proposal marked as requiring confirmation, and never infer one the code does not evidence
as irreversible or outward-facing.

## 6. Refuse the zero-content preamble

Delete any sentence that could open any repository's file: "this file provides guidance to
agents working in this repository", "follow best practices", "write clean code", restated
general engineering rules the agent already carries. Read the draft once more asking of each
line, "what would an agent do differently after reading this?" — a line with no answer goes.

## 7. Directory-scoped files only for the monorepo or platform type

A `CLAUDE.md` or `AGENTS.md` placed inside a subdirectory is loaded when a file beside it is
touched, which makes it survive the loss of early session context. That is valuable when
subtrees have genuinely different rules — the monorepo case — and noise everywhere else,
where it splits one file's authority in two. Default to one root file.

## 8. Before handing it over

Self-review against three constraints, and fix rather than annotate:

- Nothing in the output is boilerplate meant to be pasted elsewhere, and nothing points back
  to this skill, to a version, or to any tool that would "update it later" — no such
  mechanism exists, and a stamp that promises one is a lie the repo will carry.
- Every rule names the code that enforces it, or is marked as convention.
- The file states current behaviour only. Change narratives, rejected alternatives and
  handoff logs are pointed to where they live (design notes, the log), not repeated here. A
  live process that is followed but not enforced is current, not history — it belongs in the
  file or behind a pointer, and length decides which.

Now read the repo's existing instruction file, if any, and verify each of its claims against
the code — a stale sentence beside current code reads as fact. Show the user your skeleton
beside it and name the divergences: a large gap means either the draft or the existing file
is wrong, and finding out which is the point of the exercise.
