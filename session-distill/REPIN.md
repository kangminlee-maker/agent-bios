# Re-pinning the Claude host for distill

Distill dispatches Claude only to the binary and version `session-distill/seats.json` pins
(`hosts.claude.version`, `hosts.claude.path`); when Claude Code updates, dispatch refuses
`HOST_BINARY_UNPINNED` (the pinned file is gone). The hermetic evidence helper
(`wrappers/claude_hermetic_evidence.py`) reads any version's transcript whose record kinds stay inside the
measured sets (`RECORD_KINDS`, D-20261102-29ca35) and refuses one holding a kind outside them
(`RECORD_KIND_UNKNOWN`, `ATTACHMENT_TYPE_UNKNOWN`). This procedure moves the pin to the installed version
and adds that version's measured set. Steps 3 and 6 make model calls: they need the owner's
leave, and nothing here runs them for you.

## 1. Name the binary

```bash
claude --version                                   # e.g. 2.1.316 (Claude Code)
ls -l ~/.local/share/claude/versions/<version>     # the versioned file itself, never the `claude` symlink
```

The pin is the versioned file: an update moves the symlink, never this file (plan P2).

## 2. Re-read the flags the hermetic profiles send

`hosts.claude.profiles` in `seats.json` holds the `hermetic` and `hermetic-producing` flag sets, whose sha256 every
receipt and capture carries. Read each flag in `claude --help` (offline) and in the CLI reference
(code.claude.com/docs/en/cli-reference): `--safe-mode`, `--setting-sources`, `--strict-mcp-config`,
`--disable-slash-commands`, `--tools`, `--allowedTools`, `--permission-mode`. A flag that is gone or whose
meaning moved is a re-derivation of the profile and a decision record, not a re-pin; stop here. The empty
`--setting-sources ""` stays as long as D-20261102-6b6676 holds (moot in a fresh cell).

## 3. One hermetic call on the new version (model call)

From the checkout, with a cell root that is yours, mode 700, outside your home, and with no instruction surface
in its ancestry (`claude-run.sh --help`, `--cell-root`):

```bash
root=$(mktemp -d /private/tmp/repin.XXXXXX); chmod 700 "$root"; mkdir "$root/capture"
printf 'CALL-ID: repin-<version>\nAnswer OK.\n' |
  REVIEW_CAPTURE_DIR="$root/capture" bash wrappers/claude-run.sh --profile hermetic \
    --model claude-sonnet-5-5 --effort medium --cell-root "$root" --call-id repin-<version> \
    --claude-bin ~/.local/share/claude/versions/<version> --host-version <version> --max-output-tokens 4096
```

If the new version writes a kind outside the measured sets, the call completes and its evidence is refused
by that kind's name; that refusal is what this step is for. The cell's transcripts are kept in
`$root/capture/transcripts/` before the cell is deleted.

## 4. Count the record kinds the call wrote

Kinds and counts only; never print a record's content:

```bash
python3 - "$root/capture/transcripts" <<'PY'
import collections, json, pathlib, sys
types, attachments, versions = collections.Counter(), collections.Counter(), set()
for path in pathlib.Path(sys.argv[1]).rglob("*.jsonl"):
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        types[record.get("type")] += 1
        if isinstance(record.get("version"), str):
            versions.add(record["version"])
        if record.get("type") == "attachment":
            attachments[(record.get("attachment") or {}).get("type")] += 1
print("versions", sorted(versions)); print("types", dict(types)); print("attachments", dict(attachments))
PY
```

## 5. Add the version's set

In `wrappers/claude_hermetic_evidence.py`, add `RECORD_KINDS["<version>"]` with the counted `types` and
`attachments`, beside the earlier versions' sets. The set records what this sample showed, not every kind the
version writes. Compare with the previous set first:

- A kind in `READ_TYPES` or `READ_ATTACHMENTS` that the sample does not show is unobserved, not gone: one empty
  hermetic call loads no instruction file, skill or agent, so `instructions` or `skill_listing` need not appear.
  Name each unobserved read kind in the re-pin's decision record (step 6). It is gone or renamed only when a call
  that must write it shows another kind in its place (for `instructions`, a call whose working directory holds a
  `CLAUDE.md`); then the helper reads the format wrongly on this version: re-derive `requests_of` and
  `summarise` before pinning. Until such a call is measured, a renamed read kind is refused by name on the first
  transcript that holds it, since its new name is outside every measured set.
- A new kind or attachment type is added to the set as known and unread, unless it carries context the evidence
  must see (an instruction, skill, agent, hook or MCP server), in which case the helper must read it first.
- One hermetic call shows the kinds one call writes. Kinds that appear only under other uses (compaction, a
  producing call with tools) are added when a call that produces them is measured; until then a transcript
  holding one is refused by name, which is the intended outcome.

## 6. Update the pins

- `seats.json`: `hosts.claude.version` and `hosts.claude.path`; re-measure `host_allowance.hermetic` (the basis
  text says how: observed main-request input tokens, the maximum over hermetic calls through dispatch) and the
  `seat_capacity` rows whose `host_version` names the old version. These are model calls too.
- `DEPENDENCIES.md`: the verified Claude version for the hermetic profile.
- Record the re-pin with `python3 decisions/record-decision.py --kind design`, naming the version left, any
  kind that changed, and each read kind the sample did not show.

## 7. Verify

`./gates/check-parity.sh` (the helper's self-test holds every read kind inside the union of the measured sets),
then one dispatch through distill on the new pin.
