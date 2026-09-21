"""C01 Identity and reference: the gaps its operations answer with.

Record kinds: `principal_binding`, `repository_binding`, `source_ref`, `source_home`,
`source_manifest`, `source_request`, `behaviour_capture`, `knowledge_capture`,
`memory_capture`, `source_provenance`.

An id is an opaque string this installation made; it proves nothing about who holds it. A
display name, an e-mail address, a locator and a key are labels or credentials that change,
so no C01 record has a field for one in the place of an id, and the closed schemas refuse the
attempt as an unknown field. What is left for an operation to answer is below.

A source is held apart from its bytes the same way. Where it is authored and which authority
accepts its revisions are two fields, not one; what one revision holds is a manifest of members
and hashes; where the bytes came from, when this installation acquired them and whether anything
here accepted them are three facts in a provenance record, none of which confers priority.
A capture is three record kinds because it carries the material itself, and material of
different roles is different in kind: a knowledge or memory capture has no property for a
behavioural unit, so promoting either into behavioural text cannot be written down. The
operation that admits any of these is C03's; what they are is C01's.
"""
CONTRACT = "C01"
RECORD_KINDS = ("principal_binding", "repository_binding", "source_ref", "source_home",
                "source_manifest", "source_request", "behaviour_capture", "knowledge_capture",
                "memory_capture", "source_provenance")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request.
# The union across the contract modules is the closed list a request may name.
OPERATIONS = (
    "identity.binding.add",
    "identity.binding.revoke",
    "reference.resolve",
    "source.home.register",
    "source.capture.record",
    "source.revision.admit",
    "source.revision.commit",
    "source.revision.publish",
)

ID_BOUND_TO_OTHER_BYTES = "id_bound_to_other_bytes"
BINDING_UNVERIFIED = "binding_unverified"
BINDING_CONFLICT = "binding_conflict"
REPOSITORY_BINDING_REQUIRED = "repository_binding_required"
REF_UNAVAILABLE = "ref_unavailable"
SOURCE_HOME_CONFLICT = "source_home_conflict"
PUBLISHER_BYTES_MODIFIED = "publisher_bytes_modified"
MANIFEST_MEMBER_UNLISTED = "manifest_member_unlisted"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    ID_BOUND_TO_OTHER_BYTES: "an id or digest already bound here to bytes that differ",
    BINDING_UNVERIFIED: "a binding whose evidence is absent or does not verify",
    BINDING_CONFLICT: "a credential already bound to another principal; kept, never merged",
    REPOSITORY_BINDING_REQUIRED: "a fork used as its original without an explicit binding",
    REF_UNAVAILABLE: "an exact reference whose bytes this installation does not hold",
    SOURCE_HOME_CONFLICT: "a second home claiming the accepted state of one source; a "
                          "repository document and a managed twin cannot both own it",
    PUBLISHER_BYTES_MODIFIED: "installed publisher bytes changed in place, where an addition "
                              "is a derived source with a home of its own",
    MANIFEST_MEMBER_UNLISTED: "a revision holding a member its manifest does not list",
}
