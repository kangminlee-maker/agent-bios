"""B05 the host binding: the gaps a host interaction answers with.

Record kind: `host_binding`.

One record per installed host: what it offered, what it declared, and which route a person's
answer could arrive on. A host is qualified only when something has shown that its own automation
cannot produce that answer. Nothing observed so far has shown it — a configured hook answered an
elicitation with nobody present — so these records are `pending`, and a declared capability is
what the host says about itself rather than the qualification.
"""
CONTRACT = "B05"
RECORD_KINDS = ("host_binding",)
IN_RESULTS = True

HOST_NOT_QUALIFIED = "host_not_qualified"
PROTOCOL_VERSION_NOT_OFFERED = "protocol_version_not_offered"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    HOST_NOT_QUALIFIED: "a host no probe has shown can separate a person from its own "
                        "automation; a use needing an answer waits rather than accepting one",
    PROTOCOL_VERSION_NOT_OFFERED: "a wire version this installed host did not offer",
}
