"""B01 the signature binding: the gaps a signing or verifying operation answers with.

Record kinds: `signature_binding`, `signature_envelope`.

A binding record is not a contract record. A contract says what an operation's input and result
mean; a binding says which concrete platform mechanism was chosen, on what evidence, on which
platforms it was observed, and what was not observed. It is where the refusal names the spikes
saw get an owning module, and where the alternatives those spikes ruled out become unwritable.

A signature travels as a `signature_envelope` among a request's proofs: the digest of the bytes
signed, their record kind's namespace and the principal binding whose key signed, never the key.
"""
CONTRACT = "B01"
RECORD_KINDS = ("signature_binding", "signature_envelope")
IN_RESULTS = True

SIGNATURE_INVALID = "signature_invalid"
SIGNER_NOT_PERMITTED = "signer_not_permitted"
SIGNATURE_NAMESPACE_MISMATCH = "signature_namespace_mismatch"
TOOL_ABSENT = "tool_absent"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    SIGNATURE_INVALID: "bytes whose signature does not verify",
    SIGNER_NOT_PERMITTED: "a signature that verifies from a signer this record does not allow; "
                          "it shares an exit status with an invalid signature, which is why "
                          "telling them apart takes two calls",
    SIGNATURE_NAMESPACE_MISMATCH: "a signature made for another record kind's namespace",
    TOOL_ABSENT: "no signing tool on this system; signed operations are unsupported here, never "
                 "passed",
}
