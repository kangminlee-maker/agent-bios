"""C09 Exchange and trust: the gaps its operations answer with.

Record kinds: `transfer_envelope`, `transfer_stage_record`, `contribution_return`,
`authority_continuity`, `carrier_binding`, `carrier_request`, `carrier_state`.

Exported, received, verified, accepted and committed are five outcomes, each recorded when it
happens. A package that arrived has not verified, and one that verified has not been accepted by
the authority that owns what it carries.

Trust is enrolment or verified authority continuity, named by digest. A package's own key proves
nothing about the package, so no field carries one. Signing is not encryption either, which is
why confidentiality is stated separately from the evidence that the bytes are what they claim.

A delta names the acknowledged inventory and checkpoint it applies to. "Everything since
Tuesday" has no field, and a missing or damaged baseline is answered by a permitted complete
transfer rather than by an endless chain of deltas nobody holds.

Controls come before bodies. `controls_verified` names the control records it put in force, and
they stay in force when the bodies then fail; `verified` names the controls record it follows. An
authority's continuity is one `authority_continuity` record per epoch: a successor names its
predecessor and the finalizer it fences, and two successors of one predecessor are fork evidence.
A package names each member by a relative path, digest, size and kind, where a kind is a declared
record kind or `source_member`, so a member that climbs out of the package has no spelling.

A carrier is bound before it is used. `carrier_binding` names one Team's account, repository,
namespace and permitted effects, and nothing reaches the network for a carrier that was only
selected. Provisioning in doubt is queried by its own request and never repeated, part-way
provisioning keeps what exists, and a disconnect ends one Team's exchange through the binding
without deleting the repository or revoking the credential. Repository rights grant nothing in
the Team; a peer, a bound carrier and a package are routes with the same semantics.
"""
CONTRACT = "C09"
RECORD_KINDS = ("transfer_envelope", "transfer_stage_record", "contribution_return",
                "authority_continuity", "carrier_binding", "carrier_request", "carrier_state")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. The union across the
# contract modules is the closed list a request may name.
OPERATIONS = {
    "transfer.stage": {"takes": ("transfer_envelope",), "returns": ("transfer_stage_record",)},
    "transfer.accept": {"takes": ("transfer_envelope",), "returns": ("transfer_stage_record",)},
    "contribution.return": {"takes": ("transfer_envelope",), "returns": ("contribution_return",)},
    "carrier.bind": {"takes": ("carrier_binding",),
                     "returns": ("carrier_binding", "carrier_state")},
    "carrier.provision": {"takes": ("carrier_request",), "returns": ("carrier_state",)},
    "carrier.disconnect": {"takes": ("carrier_request",), "returns": ("carrier_state",)},
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
    REPOSITORY_RIGHTS_NOT_A_GRANT: "an action whose only authority is rights on a carrier's "
                                   "repository; those rights grant nothing in the Team",
}
