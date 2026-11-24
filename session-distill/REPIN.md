# Re-pinning distill's hosts and moving its seats

Distill dispatches each host only to the binary and version `session-distill/seats.json` pins
(`hosts.<host>.version`, `hosts.<host>.path`), and seats each stage on the model `stage_seats` names. Three
events oblige work here: Claude Code updates, the Codex CLI updates, or a seat moves to another model (with the
launch profile's tiers, D-20261124-ebb701). When the pinned file is gone, dispatch refuses
`HOST_BINARY_UNPINNED`. `gate.seats_problems` refuses a path that does not name its version
(`PIN_PATH_VERSION`), a measurement that names another version than the pin (`PIN_STALE`), and a seated seat
with no capacity row (`CAPACITY_UNDECLARED`).

Steps marked **(model call)** make live calls: they need the owner's leave, and nothing here runs them for
you. Reading the owner's sessions needs its own approval for each read (D-20261103-c2f013). Everything else
here is offline.

What a pin still lacks is stated in `seats.json` itself; list it rather than trusting a note:

```bash
python3 -I - <<'PY'
import json
d = json.load(open("session-distill/seats.json"))
seated = {s for k, row in d["stage_seats"].items() if not k.startswith("$") for s in row}
for host, h in d["hosts"].items():
    if not isinstance(h, dict):
        continue
    for prof, slot in h.get("host_allowance", {}).items():
        if not slot.get("measured"):
            print(f"unmeasured  hosts.{host}.host_allowance.{prof}")
        elif slot.get("measured_version") != h["version"]:
            print(f"stale       hosts.{host}.host_allowance.{prof} ({slot.get('measured_version')}, pinned {h['version']})")
    for prof, ctx in h.get("context", {}).items():
        if ctx.get("carried"):
            print(f"carried     hosts.{host}.context.{prof} (observed {ctx.get('observed_version')}, pinned {h['version']})")
for seat in sorted(seated):
    row = d["seat_capacity"].get(seat)
    host = seat.split(":", 1)[0]
    if row is None:
        print(f"no capacity {seat}")
    elif row["host_version"] != d["hosts"][host]["version"]:
        print(f"stale       seat_capacity.{seat} ({row['host_version']}, pinned {d['hosts'][host]['version']})")
PY
```

## The Claude host

The hermetic evidence helper (`wrappers/claude_hermetic_evidence.py`) reads any version's transcript whose
record kinds stay inside the measured sets (`RECORD_KINDS`, D-20261102-29ca35) and refuses one holding a kind
outside them (`RECORD_KIND_UNKNOWN`, `ATTACHMENT_TYPE_UNKNOWN`). This procedure moves the pin to the installed
version and adds that version's measured set. Steps 3 and 6 make model calls.

### 1. Name the binary

```bash
claude --version                                   # e.g. 2.1.316 (Claude Code)
ls -l ~/.local/share/claude/versions/<version>     # the versioned file itself, never the `claude` symlink
```

The pin is the versioned file: an update moves the symlink, never this file (plan P2).

### 2. Re-read the flags the hermetic profiles send

`hosts.claude.profiles` in `seats.json` holds the `hermetic` and `hermetic-producing` flag sets, whose sha256 every
receipt and capture carries. Read each flag in `claude --help` (offline) and in the CLI reference
(code.claude.com/docs/en/cli-reference): `--safe-mode`, `--setting-sources`, `--strict-mcp-config`,
`--disable-slash-commands`, `--tools`, `--allowedTools`, `--permission-mode`. A flag that is gone or whose
meaning moved is a re-derivation of the profile and a decision record, not a re-pin; stop here. The empty
`--setting-sources ""` stays as long as D-20261102-6b6676 holds (moot in a fresh cell).

### 3. One hermetic call on the new version (model call)

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

### 4. Count the record kinds the call wrote

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

### 5. Add the version's set

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

### 6. Update the pins

- `seats.json`: `hosts.claude.version` and `hosts.claude.path`; re-measure `host_allowance.hermetic` (the basis
  text says how: observed main-request input tokens, the maximum over hermetic calls through dispatch) and the
  `seat_capacity` rows whose `host_version` names the old version. These are model calls too.
- `DEPENDENCIES.md`: the verified Claude version for the hermetic profile.
- `gates/check_parity.py` `claude_run_hermetic`: the one line that names the version the hermetic flag set was
  measured on. Its fake host, and every self-test that joins a fixture to the checkout's pin, read the pinned
  version and the S3 seat from `seats.json`, so nothing else names the version.
- Record the re-pin with `python3 decisions/record-decision.py --kind design`, naming the version left, any
  kind that changed, and each read kind the sample did not show.

### 7. Verify

`./gates/check-parity.sh` (the helper's self-test holds every read kind inside the union of the measured sets),
then one dispatch through distill on the new pin.

## The Codex host

Homebrew keeps each version in its own directory and removes the old one on upgrade, so an update leaves the
pin pointing at nothing. `wrappers/codex-run.sh --capture` reads a version-bound trace channel
(`wrappers/codex_frame_filter.py`) and refuses a codex whose version is not the one it is handed; dispatch
hands it the pinned version, so no code outside `seats.json` names the Codex pin. Steps 5 and 6 make model calls.

### 1. Name the binary

```bash
codex --version
ls -l /opt/homebrew/Caskroom/codex/<version>/bin/codex   # the versioned file itself, never the `codex` link
```

### 2. Re-read the flags the hermetic profile sends

`hosts.codex.profiles.hermetic` holds `--ignore-user-config`, `--ephemeral` and `-c project_doc_max_bytes=0`.
Read each in `codex exec --help` (offline). A flag that is gone or whose meaning moved is a re-derivation of
the profile and a decision record, not a re-pin; stop here.

### 3. Read each seat's window from the binary's catalogue (offline)

The binary bundles its model catalogue. A Codex capture reports no context size, so a Codex seat's
`seat_capacity` is that catalogue's `context_window` for the model; `max_context_window` is the entry's
ceiling and is not what is declared. No network, and `~/.codex` is not read:

```bash
python3 -I - /opt/homebrew/Caskroom/codex/<version>/bin/codex <<'PY'
import json, re, sys
data = open(sys.argv[1], "rb").read()
for start in (m.start() for m in re.finditer(rb'\{\s*"models"\s*:\s*\[', data)):
    try:
        doc, _ = json.JSONDecoder().raw_decode(data[start:start + 4_000_000].decode("utf-8", "replace"))
    except ValueError:
        continue
    for m in doc["models"]:
        print(m["slug"], m.get("visibility"), m.get("context_window"), m.get("default_reasoning_level"),
              [e.get("effort") for e in m.get("supported_reasoning_levels", [])])
PY
```

Write one row per Codex seat with `host_version` set to the new version and a basis naming where it was read.
An effort the catalogue does not list for the model is not a seat.

### 4. Mark what the new version has not measured

- `host_allowance.hermetic`: until step 6 runs, `measured: false` and `allowance_tokens: null` (an unmeasured
  slot carries no number; dispatch's self-test refuses one that does), with the last measurement and its
  version in the basis. A run declares its own allowance, measured on its host (`HOST_ALLOWANCE_STALE`).
  Only the stage that reads view windows, S3, needs an allowance: a run declares one for its S3 seat
  (`ALLOWANCE_UNDECLARED`), and dispatch refuses a view-window call on a host with none measured
  (`ALLOWANCE_UNMEASURED`). While S3 sits on a Claude seat, an unmeasured Codex allowance holds no stage back.
- `context.hermetic`, the built-in skills the host loads: until step 5 observes them, `carried: true` and a
  basis saying since when. A capture that loads a skill the manifest does not declare is refused by name
  (`CONTEXT_UNDECLARED`).

### 5. The first capture on the new version (model call)

Dispatch a hermetic Codex call through distill on the new pin. Its capture is what shows that the trace frames
still have the shape the filter reads, and it names the built-in skills the host loaded: when they equal
`context.hermetic.skills`, set `observed_version` to the new version and drop `carried`. When the capture is
refused for its shape, the filter is re-derived before anything is pinned. Record the version in the capture
paragraph of `DEPENDENCIES.md`.

### 6. Measure the host allowance (model calls)

The allowance is the largest observed main-request input of a call (input + cache read + cache creation),
over hermetic calls dispatched through distill on the new pin; it is needed before a Codex seat takes S3. It includes the
packet and the schema the call was handed, so it is an upper bound on the host's own share. Set `measured:
true`, the count, `measured_version`, and a basis naming the calls, their seats and the commit.

### 7. Update the pins and verify

`seats.json` `hosts.codex.version` and `hosts.codex.path`; a decision record with
`python3 decisions/record-decision.py --kind design` naming the version left and whatever step 4 left
unmeasured; then `git grep -n '<old version>'` for any other site, the outstanding list above, and
`./gates/check-parity.sh`.

## When a seat's model changes

The tiers and distill's seats move together, in this order, because `launch/check-prompting-targets.sh`
refuses a binding that no prompting guide names.

1. **Currency (offline).** `python3 gates/check-model-currency.py` reads the catalogues both CLIs already cache
   and names every binding the vendor now calls older, with the current successor for its role. `npm publish`
   runs it as `--publish-guard`.
2. **The prompting guide (network, no model call).** Re-derive the family's section of
   `claude/guides/claude-prompting.md` or `claude/guides/gpt-prompting.md` from the vendor's documents as
   served today, and its Korean reference: read the documents, revise what they no longer say, add the ids to
   `targets:`, move `derived_at` and every `source_pins` entry to the bytes read, map any new document in
   `gates/prompting-sources.json`, regenerate the mirrors with `python3 gates/emit-mirrors.py`, and run
   `python3 gates/check-prompting-sources.py --online`. A pin records the bytes; only the reading re-derives.
3. **The launch profile (offline).** `launch/agent-launch.toml` (tiers, presets, the model list),
   `codex/agents/*.toml`, `wrappers/codex-helm.sh`, `claude/guides/cli-multi-model-workflow.md` and its Korean
   reference (then the mirrors), `docs/advanced-launch.md`, the expectations in `gates/check_parity.py` and
   `launch/test-tier-effort.py`, and `gates/goldens/review-matrix.json` recaptured with
   `python3 gates/capture-review-goldens.py`. Record the binding with `decisions/record-decision.py`.
4. **Distill's seats (offline).** `stage_seats` in `seats.json`; the owner's departures from design §4 in
   `runlib/dispatch.py`'s self-test (`owner_departures`), which holds the pinned seats against the design; and a
   `seat_capacity` row for every newly seated seat — for Codex from the catalogue (Codex step 3), for Claude the
   host-reported window, which takes a call (Claude step 6).
5. **The measurements (model calls, the owner's go).**
   - Distill's host allowance for the host of S3's seat, when S3's model changes (Codex step 6, Claude step 6):
     the counts are in the serving model's tokens, so a new model re-measures it even on an unchanged host
     version. No other stage reads view windows, so no other seat needs one.
   - The first capture through each newly seated model (Codex step 5): it shows the model answers through the
     strict structured-output projection the stage hands it.
   - The instruction-behavior benchmark (`benchmarks/README.md`, "Run this whenever a tier binding moves to a
     new model"): the regression run on the new model and the divergence hunt against the incumbent, then a
     new-class probe (`benchmarks/EXTENDING.md`, per-new-model cycle). Pin the model and the effort.
   - The tier experiments (`benchmarks/tier/`), when the move changes which tier a role should hold: they
     answer which tier a role needs, which the instruction-behavior benchmark does not ask.
6. **Release.** The release notes name the bindings moved and each measurement step 5 has not yet run.
