---
created_at: 2026-09-05T00:48:46+09:00
head: f7f74cc
kind: review
supersedes: null
---

# User-managed corpus design — cross-validation round 1

Target:
`2026-09-04T2321--17862b3--proposed-design.md` at SHA-256
`a84293da85e584752dd0845f32dc5c4fcce3dadf3d8977f3734c61a55cd2718b`.

Criterion and full 12-row scenario set:
`2026-09-05T0035--f7f74cc--cross-validation-packet.md`.

## Verdict

**REVISE — seven material design failures in the union.** Five came from an
isolated GPT FRONTIER contract review; two additional implementation-reality
failures came from an isolated reviewer. Each reviewer covered all twelve
declared scenarios. Findings were counted by union, not agreement.

A Claude Fable 5 OAuth seat was authenticated and launched with only read tools,
but the sandboxed run reached no provider (`ENOTFOUND`, `input_tokens: 0`). An
unsandboxed retry was refused because it would send an internal repository
design packet to an external provider without explicit user approval of that
payload and destination. It is not a participating reviewer and this round is
not cross-provider-validated.

## Confirmed findings and dispositions

### 1. No complete identity for fresh personal creation

Severity: high.

The design requires `CorpusRef = (package_id, item_id)`, lets runtime create an
`item_id`, but defines neither a reserved personal package nor package
create/select input. A fresh create request therefore has no complete identity
or canonical source home. Personal learnings similarly carry `learning_id` but
no package identity.

Correction: reserve and auto-create `@local/personal` for V1 personal creation.
Represent the existing host-local learning stores explicitly rather than
pretending one store exists; see finding 3.

### 2. Learning capture and corpus apply can overwrite each other's Codex region

Severity: high.

`learn/collect-learning.py::apply_codex` reads and rewrites the whole
`AGENTS.md`, while `compose/assemble.py::merge_codex` independently reads and
rewrites the same file. A learning-only lock does not serialize that shared
carrier with corpus publication.

Correction: every operation that reads or writes a shared host reader file takes
the deployment lock first, then the relevant learning lock. Factor one
region-aware merge primitive that re-reads the live file inside that boundary;
capture, migration, reset, and corpus apply must not publish stale whole-file
snapshots. The fixed lock order is deployment → Claude learning → Codex
learning, with unused locks omitted.

### 3. Personal learning authority is host-local, not singular

Severity: medium.

Current capture resolves one of two homes and writes separate Claude and Codex
JSONL/prose stores. Install migrates them independently. The proposed single
learning lock/generation makes reset, edit, recover, and identity ambiguous.

Correction: preserve V1 behavior and expose the two current stores as explicit
adapter-backed local sources, `@local/learnings-claude` and
`@local/learnings-codex`, with `item_id = learning_id`. Each has its own source
revision and lock; combined operations acquire them in the fixed order above.
The wiki may present one Personal Learnings collection while every action and
receipt remains host-qualified. A future shared store is a separate migration
decision, not an implicit V1 rewrite.

### 4. Mutable effective learning conflicts with ID-only upload/promotion

Severity: high.

The current upload watermark and server dedup settle by `learning_id`, and
promotion/migration also select by that id. Editing content while retaining the
id can leave the server on the old payload and later remove the edited local
content as though the same revision was promoted.

Correction: treat JSONL capture rows as immutable source events. Corpus edits
create local overlay revisions and change only the effective local projection;
they do not mutate an already-uploaded event. Promotion metadata must carry the
exact source/content digest. Migration may deactivate only that exact revision;
an edited overlay remains personal or enters an explicit rebase conflict. The UI
states that a local edit does not update an already-uploaded remote record.

### 5. Reset defaults are not paired with their baseline

Severity: high.

One mutable `install-defaults.json` cannot describe both a current and an older
baseline when their packages/domains differ. Rollback followed by reset would
have to guess whether to reject, drop, or translate the newer selection.

Correction: each immutable baseline snapshot owns its validated package/domain
selection and packaged settings. The active baseline pointer selects the
baseline-plus-defaults tuple. Reset replays that tuple; rollback validates and
switches the tuple atomically.

### 6. Shared router prose lacks edge-level ownership

Severity: medium.

One current global router can point to several guides. Making it a member of one
guide removes the others; keeping it independent can strand a link; an
unspecified dependency closure cannot restore one edge without rewriting the
shared carrier.

Correction: model a guide's route as a stable edge, not ownership of a physical
router bullet. The resolver groups active edges and deterministically regenerates
shared router prose. Removing/restoring a guide removes/restores only its edge;
negative controls prove sibling targets remain reachable. Any meaningful common
router prose is its own item, separate from the edge set.

### 7. “Permanent purge” overclaims remote deletion

Severity: medium.

The operating endpoint contract has POST ingest only. A learning already
uploaded remains on the server after every local deletion path, and no deletion
receipt can prove otherwise.

Correction: name the V1 operation **Permanent local purge**. Preview and result
state when an uploaded remote copy may remain. Global purge requires a future
authenticated delete contract and receipt; it is outside V1.

## Premises that held

- Immutable installed baseline plus exact-target personal overlay remains the
  best default; direct deployed-file edit and full fork remain inferior.
- Stable item identity is required by edit/move/remove/restore.
- The management skill's bootstrap exception is sound and preserves recovery.
- Ordered publication, a startup barrier, journaled undo, and fail-loud status
  make the absence of a universal host generation pointer a verification gap,
  not a current design contradiction.
- The design correctly gates hook/agent CRUD on live consumer evidence.
- Feature-off byte equality, npm-only E2E, and no Git-history runtime dependency
  are appropriate implementation gates.

## Verification gaps, not present defects

- Real crash injection is still required around every publication boundary.
- Claude agent-body consumption and Codex derived agent-template behavior need
  live probes before advanced CRUD is admitted.
- The ordered startup barrier must be exercised against real host launches.
- Cross-provider review remains absent until explicit external-egress approval is
  given.

## Review disposition

`FRONTIER disposition: the baseline/overlay and stable-id skeleton survives, but
the proposed design is not approval-ready until all seven findings are folded
into a superseding design and that revision is re-reviewed. The findings change
identity, learning authority, lock ownership, baseline coupling, router
granularity, and purge semantics; they are design corrections, not implementation
notes.`

