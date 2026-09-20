"""C09 Exchange and trust: the gaps its operations answer with.

Record kinds: `transfer_envelope`, `transfer_stage_record`, `contribution_return`.

Exported, received, verified, accepted and committed are five outcomes, each recorded when it
happens. A package that arrived has not verified, and one that verified has not been accepted by
the authority that owns what it carries.

Trust is enrolment or verified authority continuity, named by digest. A package's own key proves
nothing about the package, so no field carries one. Signing is not encryption either, which is
why confidentiality is stated separately from the evidence that the bytes are what they claim.

A delta names the acknowledged inventory and checkpoint it applies to. "Everything since
Tuesday" has no field, and a missing or damaged baseline is answered by a permitted complete
transfer rather than by an endless chain of deltas nobody holds.
"""
CONTRACT = "C09"
RECORD_KINDS = ("transfer_envelope", "transfer_stage_record", "contribution_return")
IN_RESULTS = True

TRUST_CONTINUITY_UNVERIFIED = "trust_continuity_unverified"
AUDIENCE_MISMATCH = "audience_mismatch"
CONTROL_SUPERSEDED = "control_superseded"
BASELINE_MISSING = "baseline_missing"
BODY_MISSING = "body_missing"
EXECUTABLE_IMPORT_REFUSED = "executable_import_refused"
SEMANTICS_UNSUPPORTED = "semantics_unsupported"
FORK_EVIDENCE = "fork_evidence"
IMPORT_CONFLICTING_BYTES = "import_conflicting_bytes"

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
}
