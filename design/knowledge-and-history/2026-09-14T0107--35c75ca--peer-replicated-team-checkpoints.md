---
created_at: 2026-09-14T01:07:21+09:00
head: 35c75ca
kind: design
status: proposed-minimal-peer-replication
amends: 2026-09-14T0003--35c75ca--disconnected-storage-and-sync.md
governance: 2026-09-13T2336--35c75ca--studio-governance-design.md
---

# Peer repositories for accepted team environments

## Recommendation

Let authorized workers retain and exchange the team's accepted environment
checkpoints directly. Any peer that has the required permitted objects can
serve another peer; a central storage service is optional. This advances the
product purpose by preserving the shared environment when a worker, device or
hosting service becomes unavailable.

The minimum is **peer replication plus verifiable accepted checkpoints**. Reuse
the previous portable objects, signed requests/receipts, trust continuity,
offline policy and importer. Add peer discovery/configuration and explicit
retention acknowledgments. Do not introduce another business-content schema or
an additional universal ledger.

Separate three functions:

| Function | Question | Evidence |
| --- | --- | --- |
| Review | Is this exact change accepted under the source/Team policy? | Eligible independent approval statements |
| Finalization | Which accepted change advanced this shared head? | Exact predecessor-bound authoritative commit/checkpoint |
| Replication | Where is that checkpoint and its usable content retained? | Scoped, dated verification/retention acknowledgments |

Several stored copies are not several approvals. Several approvals are not,
by themselves, a unique ordering of competing shared-head changes.

## Smallest peer contract

1. **Store immutable identities.** Retain allowed source revisions, environment
   editions, decisions, approvals, authority controls and accepted checkpoints.
   A peer's editable local folder is not an authority credential. Changed bytes
   require another object identity and any applicable review.
2. **Exchange scoped inventories.** With a known authorized peer or permitted
   file carrier, disclose only the inventory that recipient may learn. Compare
   exact checkpoints/object IDs and ask for missing objects or a complete package.
   No continuous all-to-all connection, public peer directory or universal
   peer-discovery service is required.
3. **Verify locally.** Check the same trusted origin, permissions, predecessor
   continuity, control state and required content/event closure regardless of
   which peer supplied the bytes. A node serving a file need not be its publisher.
   Receiving from an unfamiliar peer cannot enroll that peer as a trusted signer.
4. **Acknowledge durable retention.** A storage acknowledgment identifies peer,
   storage generation, checkpoint, verified body set, scope and retention commitment/limit. A hash
   without the body is not a usable replica. A former acknowledgment is evidence
   of a past observation, not a guarantee that the peer is reachable or still
   has the data now.
5. **Keep local work separate.** Local drafts, observations and outboxes can
   propagate to permitted peers for transport or backup. They remain proposals
   or scoped local decisions until the required authority accepts them. Peer
   receipt never silently promotes a proposal into Team policy.

This can use direct local-network exchange, existing Git transports, or the
already-designed full/incremental file bundles. A GitHub/internal-server mirror
may help connect peers but holds no exclusive copy required to continue work.
No peer sharing service or automatic network exposure is enabled by this design.

## Retention and access

For a small common Team environment, all authorized members may retain its
complete current permitted package. For large or restricted sources, ordinary
workers retain their selected work scope and designated custodians retain the
complete authorized recovery set. Sharing a Team does not grant read access to
every other member's private material or personal environment.

A proposed small-team durability target is three verified copies on separate
devices when such authorized devices exist. This is a configurable storage
target, not a three-vote approval rule, a universal minimum or proof of three
independent failure domains. One or two available devices do not receive a
fictional third acknowledgment. Ordinary permitted use remains available while
the replication target is unmet, with reduced recovery coverage visible.

Retention rules name what may be discarded and when; there is no "everyone
keeps every past body forever" requirement. Restrictive source policy and
tombstones still apply. Do not silently prune the only acknowledged recovery
copy for a retained edition. Conversely, a replica-count target cannot override
a deletion requirement. Retained trust/control continuity may be needed even
when a historical body can no longer be kept.

Replicas do not replace independent backup: one user's malware, common account
compromise, building outage or simultaneous disk loss can affect several peers.
Keep unique outboxes backed up before they are acknowledged elsewhere. Never
replicate private signing keys, live databases, voting state as interchangeable
active instances, or native session secrets with the source packages.

Keep evictable caches distinct from accepted retention commitments. A peer
without enough space declines retention rather than silently evicting retained
bodies. On learning that a peer's storage was reset/replaced, its new generation
invalidates old custody assumptions. Periodic reconstruction from another peer
provides stronger recovery evidence than counting old acknowledgments alone.

## Finalization in the recommended minimum

Retain one logical finalization authority per shared head, under the already
designed Team/source permissions and review policy. That role can operate on a
member's computer and transfer through the governed ownership/recovery process;
it does not require a central always-on server or exclusive storage location.

Authorized reviewers and publication executors may be several people. Their
requests reach the one serialization boundary; granting `publish` does not
create another independent checkpoint issuer for the same head. Content review,
execution permission and head serialization remain separate responsibilities.

Accepted checkpoints and their required bodies are replicated to peers. After
the finalizer goes offline, another authorized peer can still deliver those
exact accepted objects, including the adoption and control evidence a worker
needs. Permitted work continues. New shared-head changes wait until the
finalization role is available or validly transferred; this write-availability
limit is explicit.

In a partition, workers may make different proposals. They keep the last
accepted checkpoint locally and name unshared additions. A checkpoint arriving
later must extend the accepted authority lineage or supply supported continuity.
Conflicting authoritative successors are retained as fork evidence and stop
automatic adoption for the affected scope. Arrival time, longest chain, highest
version or a majority of cached files cannot choose the correct Team decision.

## If finalization must also be decentralized

The design boundary supports another finalization mechanism returning the same
accepted checkpoint/receipt contract. Such a mode needs an explicit participant
configuration and fault model; durable rounds/locks and recovery; membership and
key transitions under the preceding configuration; safe handling of concurrent
proposals; and a proof/test basis for its safety and progress claims.

Threshold signatures alone do not provide that protocol. For example, with
three participants and a two-signature threshold, each participant can lock a
different successor, leaving no complete certificate. Allowing them to forget
those locks merely because no certificate is visible can combine delayed votes
into conflicting results. Approver identity checks cannot repair a missing
consensus protocol. Restoring a backup must not erase outstanding vote state.

Crash-fault majority consensus and protection against malicious double-signing
also have different assumptions. A replica-count target, a content-review count
and a finalization quorum cannot be substituted for each other.

The initial design does not promise automatic quorum finalization. If a concrete
requirement is to continue shared writes after loss of the finalizer, select and
verify an established protocol for the actual fault/connectivity model, or
explicitly accept pending/forked state until governed resolution. This is an
implementation/design-extension condition, not an incomplete claim that a
homemade signature threshold already supplies linear finality.

## Concrete three-peer example

- A, B and C retain the authorized environment E3 and accepted checkpoint P40.
- A's device is lost. B can supply E3/P40 and required bodies to a properly
  enrolled replacement; C is another retained copy. No central download is needed.
- B prepares E4, a qualified independent reviewer approves its exact request,
  and the designated authority commits P41 under current applicable policy.
- Any authorized peer can relay P41 and its required bodies afterward. Each
  recipient verifies it rather than trusting the relay computer's assertion.
- If the authority is unreachable, E4 remains pending. E3 work continues within
  its offline conditions. If no permitted communication path exists between
  peers, they cannot exchange updates until such a path becomes available.

## Studio and acceptance cases

Operations adds a peer view showing exact known checkpoints, requested/verified
objects, outboxes and dated retention acknowledgments. The environment view
separates accepted edition, locally available bodies, replication coverage and
pending proposals. A disconnected peer is not reported to have lost its data,
nor reported currently reachable from an old acknowledgment.

Required implementation checks are:

- recover from another peer after losing the usual serving device;
- reject altered bytes, invalid trust lineage, replayed controls and missing
  required bodies regardless of the sender;
- deduplicate a package received from multiple paths without double-applying
  decisions or a publication receipt;
- keep proposals unaccepted even if every storage peer has received them;
- enforce recipient restrictions on inventories, bodies and recovery;
- avoid resurrection after a tombstone arrives, even from an older retained copy;
- show pending shared writes during finalizer absence while permitted local work
  remains possible;
- detect contradictory accepted checkpoints and refuse automatic selection;
- retain source/authority restrictions learned from peers without claiming
  immediate knowledge of restrictions that have not reached the device.

This is a proposed design amendment, not an implemented peer service or a
verified consensus implementation. No ports, repositories, servers or schedules
were created by this design work.

## Research and review basis

Local ownership and offline collaboration have an established framing in
[Local-first software](https://www.inkandswitch.com/essay/local-first/). The peer
exchange and Team authority boundary above are project-specific choices.

The separation of replicated storage, ordering, elections and membership, and
the need for communicating majorities in the crash-fault model, are described
in [the Raft paper](https://raft.github.io/raft.pdf). This is a reference for the
scope of consensus, not a decision to deploy Raft on intermittently connected
worker laptops.

An independent delegated review identified the distinction between content
approval and finalization votes, plus the deadlock/delayed-vote trap in naive
signature thresholds. Those limitations are incorporated here. Real durable
storage, permission, recovery and finalization implementations still need the
acceptance checks above.
