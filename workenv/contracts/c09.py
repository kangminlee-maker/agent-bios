"""C09 Exchange and trust: the gaps its operations answer with.

Record kinds: `transfer_envelope`, `transfer_stage_record`, `contribution_return`,
`authority_continuity`, `carrier_binding`, `carrier_request`, `carrier_state`.

Exported, received, verified, accepted and committed are five outcomes, each recorded when it
happens. A package that arrived has not verified, and one that verified has not been accepted by
the authority that owns what it carries.

Trust is enrolment or verified authority continuity, named by digest: a package's continuity
evidence is the `authority_continuity` epochs of the authority it comes from, from the founding
epoch to the current one, or the `principal_binding` that enrolled the sending device. Each is a
record its owner wrote, and each travels as a member of the package unless the recipient already
holds it. A package's own key proves nothing about the package, so no field carries one. Signing
is not encryption either, which is why confidentiality is stated separately from the evidence
that the bytes are what they claim.

A delta names the checkpoint it applies to and the acknowledged inventory it was built against:
the `custody_acknowledgment` (C10) in which a holder reported, object by object, what it keeps.
"Everything since Tuesday" has no field, and a missing or damaged baseline is answered by a
permitted complete transfer rather than by an endless chain of deltas nobody holds.

Staging a package writes its outbox or its bounded input and a stage record, moves no head and
names no receipt; accepting it commits, and only the owning authority's receipt makes what it
carries accepted.

Controls come before bodies. `controls_verified` names the control records it put in force — a
`control_evidence` permit or revocation its Team's issuing authority issued through
`access.control.record` (C02), or an authority's continuity epoch — and they stay in force when
the bodies then fail; `verified` names the controls record it follows. A holder comes to hold
control evidence only through a package that carries it as a `control_evidence` member. An
authority's continuity is one `authority_continuity` record per epoch: a successor names its
predecessor and the finalizer it fences, and two successors of one predecessor are fork
evidence. A package names each member by a relative path, digest, size and kind, where a kind is
a declared record kind or `source_member`, so a member that climbs out of the package has no
spelling.

A carrier is bound before it is used. `carrier_binding` names one Team's account, repository,
namespace and permitted effects, and nothing reaches the network for a carrier that was only
selected. A provisioning is recorded provisioned only against the repository the binding names:
a provider reporting another one leaves the binding `mismatched`, with nothing provisioned and
nothing moving through it. Provisioning in doubt is queried by its own request and never
repeated, part-way provisioning keeps what exists, and a disconnect ends one Team's exchange
through the binding without deleting the repository or revoking the credential. Repository rights
grant nothing in the Team; a peer, a bound carrier and a package are routes with the same
semantics.
"""
CONTRACT = "C09"
RECORD_KINDS = ("transfer_envelope", "transfer_stage_record", "contribution_return",
                "authority_continuity", "carrier_binding", "carrier_request", "carrier_state")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. The union across the
# contract modules is the closed list a request may name. A request for an operation states
# its `effect` class and grant `action`, and targets a resource whose id carries one of its
# `targets` prefixes: an exchange targets the authority its envelope names, and a carrier the
# Team that bound it.
OPERATIONS = {
    "transfer.stage": {"takes": ("transfer_envelope",), "returns": ("transfer_stage_record",),
                       "effect": "durable_candidate", "action": "transfer",
                       "targets": ("tem", "prn", "rep")},
    "transfer.accept": {"takes": ("transfer_envelope",), "returns": ("transfer_stage_record",),
                        "effect": "owner_commit", "action": "transfer",
                        "targets": ("tem", "prn", "rep")},
    "contribution.return": {"takes": ("transfer_envelope",), "returns": ("contribution_return",),
                            "effect": "owner_commit", "action": "contribute",
                            "targets": ("tem", "prn", "rep")},
    "carrier.bind": {"takes": ("carrier_binding",),
                     "returns": ("carrier_binding", "carrier_state"),
                     "effect": "owner_commit", "action": "policy", "targets": ("tem",)},
    "carrier.provision": {"takes": ("carrier_request",), "returns": ("carrier_state",),
                          "effect": "owner_commit", "action": "policy", "targets": ("tem",)},
    "carrier.disconnect": {"takes": ("carrier_request",), "returns": ("carrier_state",),
                           "effect": "owner_commit", "action": "policy", "targets": ("tem",)},
}

# Rules that relate one element of a record to another, which a schema cannot state. The
# runtime owner keeps each; a case in the registry (gates/workenv/case-index.json) checks it.
RUNTIME_RULES = {
    "provisioned_against_its_binding": "a carrier state that is provisioned or partial names the "
                                       "repository its binding names, and a mismatched one "
                                       "names a repository its binding does not",
}

TRUST_CONTINUITY_UNVERIFIED = "trust_continuity_unverified"
AUDIENCE_MISMATCH = "audience_mismatch"
CONTROL_SUPERSEDED = "control_superseded"
BASELINE_MISSING = "baseline_missing"
BODY_MISSING = "body_missing"
EXECUTABLE_IMPORT_REFUSED = "executable_import_refused"
SEMANTICS_UNSUPPORTED = "semantics_unsupported"
FORK_EVIDENCE = "fork_evidence"
IMPORT_CONFLICTING_BYTES = "import_conflicting_bytes"
PROVISIONING_IN_DOUBT = "provisioning_in_doubt"
CARRIER_REPOSITORY_MISMATCH = "carrier_repository_mismatch"
REPOSITORY_RIGHTS_NOT_A_GRANT = "repository_rights_not_a_grant"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    TRUST_CONTINUITY_UNVERIFIED: "authority continuity this installation cannot verify; the "
                                 "package's own key is not that evidence",
    AUDIENCE_MISMATCH: "a package addressed to another recipient or another permitted scope",
    CONTROL_SUPERSEDED: "a control or checkpoint a newer accepted one has displaced",
    BASELINE_MISSING: "an incremental transfer whose baseline this installation does not hold",
    BODY_MISSING: "an inventory entry whose bytes did not arrive",
    EXECUTABLE_IMPORT_REFUSED: "a package carrying something that would be executed on import",
    SEMANTICS_UNSUPPORTED: "required policy or event semantics this version does not implement; "
                           "they stay unsupported rather than being dropped quietly",
    FORK_EVIDENCE: "two authoritative successors in one scope; no version number, arrival order "
                   "or file count resolves them",
    IMPORT_CONFLICTING_BYTES: "an offered object whose bytes differ from the one already held; "
                              "both candidates are kept",
    PROVISIONING_IN_DOUBT: "a provisioning of a carrier binding whose earlier provisioning has "
                           "an unknown outcome; that request is queried, not repeated",
    CARRIER_REPOSITORY_MISMATCH: "a carrier binding whose provider reports a repository other "
                                 "than the one the binding names; nothing is provisioned and no "
                                 "object moves through the binding",
    REPOSITORY_RIGHTS_NOT_A_GRANT: "an action whose only authority is rights on a carrier's "
                                   "repository; those rights grant nothing in the Team",
}
