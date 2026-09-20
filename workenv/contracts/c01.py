"""C01 Identity and reference: the gaps its operations answer with.

Record kinds: `principal_binding`, `repository_binding`, `source_ref`.

An id is an opaque string this installation made; it proves nothing about who holds it. A
display name, an e-mail address, a locator and a key are labels or credentials that change,
so no C01 record has a field for one in the place of an id, and the closed schemas refuse the
attempt as an unknown field. What is left for an operation to answer is below.
"""
CONTRACT = "C01"
RECORD_KINDS = ("principal_binding", "repository_binding", "source_ref")
IN_RESULTS = True

ID_BOUND_TO_OTHER_BYTES = "id_bound_to_other_bytes"
BINDING_UNVERIFIED = "binding_unverified"
BINDING_CONFLICT = "binding_conflict"
REPOSITORY_BINDING_REQUIRED = "repository_binding_required"
REF_UNAVAILABLE = "ref_unavailable"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    ID_BOUND_TO_OTHER_BYTES: "an id or digest already bound here to bytes that differ",
    BINDING_UNVERIFIED: "a binding whose evidence is absent or does not verify",
    BINDING_CONFLICT: "a credential already bound to another principal; kept, never merged",
    REPOSITORY_BINDING_REQUIRED: "a fork used as its original without an explicit binding",
    REF_UNAVAILABLE: "an exact reference whose bytes this installation does not hold",
}
