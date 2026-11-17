---
created_at: 2026-10-23T13:36:54+09:00
head: 2a61d6b
kind: design
supersedes: null
---

# Plan amendment: the per-run native capture is its own package, before WP-10

This amends `2026-10-20T2119--cc0498f--implementation-plan.md` by adding one package and narrowing
WP-07. It is the owner's decision of 2026-10-23, taken after WP-07's review round 2 raised five
findings (GB#0–GB#4) that were all inside the capture WP-07 had grown.

## What changed in WP-07

WP-07 no longer captures anything. Its run mode reports every native layer `unknown`, with a reason
naming the capture it has no record of, which makes the reference point incomplete — the state
design §6.1 and §6.4 already define. It never reads the owner's live homes in run mode.

Reading a live home is an **inspection** (`--native-root`, `--native-live`): every artifact carries
`mode: inspection` and `not_a_pipeline_result: true`, the CLI says so, and an inspection is refused
inside a run directory, so its output can never be mistaken for a stage result.

Two things from GB#0–GB#4 stay in WP-07 because they are about paths WP-07 still has:

- **The write-free destination preflight** (GB#0). The destination is judged before anything is
  locked, captured or recorded: a stage record is a write, so a run directory under a protected root
  is refused before the stage is entered. Its control asserts no `stages/` directory appears.
- **The host homes stay protected** whether or not a run reads them, so replacing them as an input
  cannot quietly stop protecting them.

The rest — GB#1 (project identities escaping the frozen destination, project files never captured),
GB#2 (run mode neither requiring nor reusing its capture), GB#3 (verification not binding the
consumed bytes to the declaration), GB#4 (skipped sources becoming complete-and-empty layers) — move
to the new package, which is where that code now lives.

## The new package: S0 native capture

**Scope.** One per-run, immutable, declared copy of the native layers, written by S0 and consumed by
S2's inventory. Host homes and project roots in scope; the host adapters' own enumeration of native
sources; nothing else under a home is walked, and a host's transcripts never are.

**The contract WP-07 consumes.** `<run>/capture/native/manifest.json`:

```
{"scope": {"hosts": {host: {"home": <masked>, "present": bool}},
           "projects": [{"path": <masked>, "slug_sha256": str, "present": bool}],
           "layers": [...]},
 "files": [{"host", "relative", "layer", "source": <masked>, "sha256", "bytes"}],
 "skipped": [{"host", "relative"|"pattern", "layer", "reason"}],
 "layer_digests": {layer: sha256},
 "sha256": <aggregate over (host, relative, sha256)>}
```

Every path in it is masked with the projection's own home mask, because the manifest is a document
the run writes. The refusals WP-07's run mode expects from a capture reader: `CAPTURE_ABSENT`,
`CAPTURE_CHANGED`, `CAPTURE_DRIFT`, `CAPTURE_EXISTS`.

**Done-when, from GB#0–GB#4.**

1. Nothing is written — capture, lock or stage record — before a shared, write-free destination
   preflight; every capture destination is confined, symlinked parents included; the default run
   location does not sit inside the default protected project checkout. Controls observe every
   attempted write.
2. A confined relative storage identifier, distinct from the canonical project identity, so an
   absolute project key cannot address the original project's own files. Project instruction files
   are captured at acquisition, and project inputs are reconstructed only from the verified
   manifest. The control uses the identity mapping the CLI really produces.
3. Run mode requires and reuses the run's existing declared capture: a first run creates it, a rerun
   opens it, an absent capture is refused. Acquisition is separate from inventory execution.
4. Verification binds the bytes actually consumed: manifest paths validated and confined, symlinks
   and undeclared files rejected, aggregate and per-layer digests recomputed from the verified bytes,
   exactly the manifest's file set consumed, the capture published atomically under a capture lock,
   and the verified manifest bound to the declaration's `starting_hashes.layers`.
5. Expected sources and outcomes are enumerated together: missing, skipped and unreadable states
   survive into each layer's completeness decision, so a symlinked global file or an unreadable
   settings file beside a captured file cannot leave the layer `complete, empty`. One isolated
   control per outcome.
6. One source walker decides what is read, hashed, omitted and copied (WP-07's `walk_source` is the
   shape to reuse), and a link is rejected before it is read, leaf and ancestor alike.

**Dependencies.** After WP-01, whose S0 declaration and stage-record contract it writes under
(`records.STAGE_PARTS` already gives S2 one part per producer, so the capture's own stage record
follows the same rule). Before WP-10, which cannot judge a delivery state or an absence claim about
the native layers while the inventory reports them `unknown`.

**Starting point.** The capture code WP-07 had, with these findings unfixed, is saved outside the
tree on the day of the split; it is a starting point, not a design.

## What this closes

**"Build the capture inside WP-07."** Rejected. Round 2's five capture findings were all of a kind
WP-07 cannot settle: the capture is an S0 acquisition with its own lock, its own atomic publish, its
own declaration binding and its own scope enumeration, and growing it inside the inventory produced a
capture that was written before the destination was judged, trusted its own aggregate digests, and
let a skipped source read as an empty layer. The plan put the capture at S0; WP-07 having built one
was the plan's boundary being crossed, not a smaller version of the same work.

WP-07's own completeness answer makes the split safe to take: a reference point whose native layers
are `unknown` is incomplete, and §6.4 already turns the derivations that need them into `unknown`
rather than into a wrong answer.
