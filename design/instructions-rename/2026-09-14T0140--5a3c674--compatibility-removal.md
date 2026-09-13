---
created_at: 2026-09-14T01:40:00+09:00
head: 5a3c674
kind: backlog
---

# Remove the Instructions compatibility layer after consumer migration

The user requested keeping compatibility in 0.19.2 as an explicit future removal
item. It is not a permanent second interface or implementation.

Scope and owner: the current inventory and removal conditions are in
`docs/instructions-compatibility.md`; runtime owners are the installer, launcher,
private store, transaction module and app bridge. Remove the older command/option
aliases, environment aliases, import shims and old-release adapters together only
when their consumers have migrated and a breaking release has been announced.

Before removing support, demonstrate that stored user roots, concurrent writer
exclusion, historical snapshots, session pins and recovery records remain usable
or have an explicit migration. Do not rename stored bytes merely to remove a word.
The compatibility test suite supplies preservation cases to carry into the migration.

Revisit at the next breaking-release plan or when a consumer migration inventory
establishes that removal is safe. No removal version is assigned. The alternatives
are coordinated removal after migration, or continued support while consumers or
historical data still depend on it. Silent removal in 0.19.2 is excluded.
