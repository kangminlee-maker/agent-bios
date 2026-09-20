"""B03 the storage binding: the gaps a durable write or a restore answers with.

Record kind: `storage_binding`.

One declarative connection profile, read back on every connection and refused on mismatch,
because a pragma that did not take looks exactly like one that did until a machine loses power.
WAL is chosen with its price named: a fault point during checkpoint, backup only through the
backup API, and a refusal when the journal mode read back is not `wal`.
"""
CONTRACT = "B03"
RECORD_KINDS = ("storage_binding",)
IN_RESULTS = True

CONNECTION_PROFILE_MISMATCH = "connection_profile_mismatch"
JOURNAL_MODE_UNEXPECTED = "journal_mode_unexpected"
BACKUP_SET_INCOMPLETE = "backup_set_incomplete"
BACKUP_SET_DAMAGED = "backup_set_damaged"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    CONNECTION_PROFILE_MISMATCH: "a connection whose settings read back differently from the "
                                 "profile this binding states",
    JOURNAL_MODE_UNEXPECTED: "a database whose journal mode is not the one this binding requires",
    BACKUP_SET_INCOMPLETE: "a backup missing a member its own manifest names",
    BACKUP_SET_DAMAGED: "a backup whose members do not hash to what its manifest says",
}
