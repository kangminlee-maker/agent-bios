---
created_at: 2026-09-27T14:08:43+09:00
head: 365a6f2
kind: design
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260927-f6c55a, D-20260927-ff5fb9, D-20260927-6c5b6a, D-20260927-d1cb86, D-20260927-9153a9
---

# V1, fourth slice, second increment: probing delivery routes on the installed hosts

The [first increment](2026-09-27T1022--0715475--v1-slice4-owner-record.md) made a route supported
only where a real probe of that recipient's delivery on the host's name and version worked, and
had nothing that probed. This increment is `capability.probe` for the four delivery capabilities,
run for real on Claude Code 2.1.283 and Codex 0.156.1 on this machine. A real delivery through
the hook is a third increment (`D-20260927-9153a9`). V1 is not complete and no node is accepted
by it.

## What was written

- `workenv/hosts/probes.py`: `capability.probe` for `new_delivery`, `current_delivery`,
  `child_delivery` and `rehydrated_delivery`. It refuses a target other than the requester's
  profile (`request_mismatch`) and a wire other than `command_hook` 1
  (`wire_version_unsupported`), then runs the host before the unit of work and commits the probe
  with the host configuration it ran under. Probing any other capability is declined by name.
- `workenv/hosts/hook.py`: the command a host runs on its events. It reads the recipient and
  text from the job file `AGENT_BIOS_HOOK_JOB` names, prints the adapter's output only for that
  recipient, writes nothing and never fails its host. Its command is the same bytes on every run
  (`D-20260927-f6c55a`).
- Each adapter says how its host is driven: its executable, the environment that marks a
  process as inside one of its sessions (dropped before a probe), and a drive.
  - Claude Code: `claude -p` with the hook in a plugin of the probe's own and no setting
    sources. A new, current or child session is one run that keeps no session. A rehydrated one
    is a kept session: a prompt, `/compact`, then the question.
  - Codex: `codex exec --ephemeral -s read-only` with the hook as a per-run `-c hooks.<event>`
    value, after listing every hook Codex would run through its app server
    (`D-20260927-ff5fb9`). A rehydrated session is unsupported: `codex exec` does not compact
    (`D-20260927-6c5b6a`).
- `workenv.hosts:capability_probe`, the entry the serving table already named, with its
  `prepare` step; `hook.py`'s entrance disposition (`session_start`, no reach, holds no write);
  both files in `package.json`.

## How a probe decides

The probe hands the recipient a line carrying a random nonce and asks it to repeat any such
line. The recorded outcome:

| Outcome | Offered | When |
| --- | --- | --- |
| `worked` | yes | the reply carries the nonce |
| `refused` | yes | the host answered without it, as when it did not run the hook |
| `no_response` | yes | no reply, a failure, a timeout, a compaction that failed, or Codex listing no hooks |
| `unreachable` | no | the host is not installed, or the installed version is not the one named |
| `unsupported` | no | no adapter names the host, no route to that recipient is declared, or the adapter cannot drive it there |

## How it was checked

**Units.** `test_probes.py` (29) runs the real probe, drives and hook against `fakehost.py`, a
stand-in installed as `claude` and `codex` on a PATH of the test's own. It covers every outcome
above, a marker the hook did not hand over, the route configured as declared, no setting sources
and no kept session, the nested-session variables dropped, and Codex's untrusted, managed and
repeated hooks. It also checks that the host runs before the unit of work holds the store, that a
replay does not run the host again, and that the hook never fails its host. `test_hosts.py` (19)
holds every adapter to naming its executable and a drive.

**Reverts.** 56 rules reverted one at a time in a copy, 56 caught. Code whose revert no test
could see was removed rather than kept: an exit-code check on `--version`, an exit-code check on
`codex exec`, and a second `prepare` attribute the journal never reads.

**The V1 cases on the real driver.** 13 pass, 7 fail and 2 block. Before this increment 13
passed, 2 failed and 7 blocked. Five cases that blocked on "no `capability_probe` yet"
(N16-ENTRANCES-POS and four TUI-ENTRY cases) now fail by name at "probing read is not served
yet", which slice five serves. CMP-QUALIFIED and DEL-PERSONAL fail as before.

**Every scenario.** With every other step given, 47 of 162 pass, 81 block and 34 fail, the same
as before.

**Gates.** `check-workenv`, `check-ontology` after re-deriving `payload_files` (121) and
re-emitting the map, `check-lexicon`, `check-package`.

## Used on this machine

With the real code, a state root of its own, this repository's files read in place and every
request through the journal:

| Host | new | current | child | rehydrated |
| --- | --- | --- | --- | --- |
| Claude Code 2.1.283 | worked | worked | worked | worked |
| Codex 0.156.1 | refused | refused | unsupported | unsupported |

- Each Claude Code probe recorded one hook, the probe's own, enabled. The whole run, eight
  probes and the deliveries after them, took 47 seconds.
- Each Codex probe recorded seven hooks: the six the person configured, enabled, and the probe's,
  not enabled, because Codex runs a hook given per session only once the person has trusted it in
  `/hooks` (`D-20260927-d1cb86`). The reason is in each probe's `observed`.
- After probing, every Claude Code route was supported and every Codex route was not. The same
  deliveries as the first increment were then attempted:
  - to this Claude Code session and to a child of it: received;
  - on the Codex link: `route_unsupported` and `child_route_unsupported`;
  - observing the Claude Code preparation named the session and the child `delivered`;
  - activating the session returned the two guides' bytes, identical to the files, and
    observing again named the session `activated`.
- These attempts were submitted by the script, standing in for the hook; the hook has not yet
  answered a host event with bodies. That is the third increment.

Opening Codex with both of the probe's hooks lists them under the same keys and hashes as the
probes give them one at a time, so one review in `/hooks` covers later probes. The person has not
reviewed them yet.

## Next

The person's review of the probe's hooks in Codex, then Codex probed again. Then the third
increment: the hook answering a host event with the bodies an activation returns, and a real
delivery to a Claude Code and a Codex session. Then slice five, the P01 re-freeze and V1's
acceptance.
