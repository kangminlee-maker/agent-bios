# Paired static HTML/PDF authoring and review

This companion is an opt-in execution procedure for a requested static HTML/PDF
job. The sibling [slide-writing guide](../slide-writing.md) owns the semantic
criteria and is the default for every slide or presentation task. All role
requests in this path receive its same criterion text.

Use this runbook only when the requested output and review can actually use its
static `section.slide` HTML/PDF path. Preserve a requested native presentation
format; if this renderer cannot bind that format, apply the primary guide with
the appropriate authoring tool and disclose which runtime checks were not run.
Do not substitute an HTML deliverable or claim that unrelated screenshots passed
this paired runtime.

Use `<runbook-root>` for the directory containing this file and its `scripts/`
directory, and `<job>` for a new directory outside the immutable instructions bundle.
The runtime refuses an existing job directory; revised inputs or output use a
new job revision. In every command, `--base` names the companion directory. The
criteria source is its sibling, `<runbook-root>/../slide-writing.md`.

## Prepare

Provide the source text, a JSON work specification, and any local assets. Record
format and presentation values in that specification according to the criteria.
The HTML runtime requires static `section.slide` elements, equal page dimensions,
and print page breaks. An explicit positive integer `pages` in the specification
is checked against the actual render.

```bash
python3 -B "<runbook-root>/scripts/pair.py" --base "<runbook-root>" check
python3 -B "<runbook-root>/scripts/pair.py" --base "<runbook-root>" prepare \
  --source "<source.md>" \
  --spec "<work-spec.json>" \
  --asset "<optional-local-asset>" \
  --job "<job>"
```

Omit `--asset` when no assets are needed; repeat it for additional files. Asset
basenames must be unique. They are copied to `<job>/input/assets/<name>`, so URLs from
`<job>/output/deck.html` use `../input/assets/<name>`.

`check` parses and validates the primary criteria source without writing to the
guide bundle. `prepare` derives `<job>/input/slide-writing.md` and the job-only
`<job>/input/ORACLE.json`, then freezes them with the source, specification,
assets, and runtime version. The guide bundle has no source `ORACLE.json` and no
build command. Give the actual writer `writer.md` and the frozen inputs it names,
and save its result to `<job>/output/deck.html`. Keep the actual invocation
record. Request files alone do not establish that a writer consumed them.

## Render the submitted HTML

Resolve the Node executable, the Playwright module file, and the browser executable
in the current environment, then pass those paths explicitly.

```bash
python3 -B "<runbook-root>/scripts/pair.py" --base "<runbook-root>" render \
  --job "<job>" \
  --node "<node-executable>" \
  --playwright "<playwright-module-file>" \
  --browser "<chromium-browser-executable>"
```

The runtime seals the HTML and assets and invokes its renderer on that copy.
The renderer blocks network requests and file requests outside the sealed root.
It injects no slide styles. It creates the PDF, page images, and measurements and
checks PDF/HTML page counts and dimensions before registration. Arbitrary supplied
images are not a substitute for this renderer invocation.

`font_px` records computed CSS size. Glyph bounds, transforms, font loading, and
the actual image remain separate evidence. A render error leaves no completed
render; keep its diagnostics and use a new job for a corrected attempt.

## Freeze a screen reading

Give a separate review context `reader.md` and its listed rendered artifacts.
Do not supply source/specification contents or the writer's explanation during
this first observation stage. The generated request provides the response
contract and typed template.

```bash
python3 -B "<runbook-root>/scripts/pair.py" --base "<runbook-root>" observe \
  --job "<job>" \
  --request "<job>/reader-request.json" \
  --payload "<observations-proposal.json>"
```

The accepted observation is stored in `observations.json` with its request binding.
Only then does the runtime generate `judge.md` and `judge-request.json`, containing
the frozen source, specification, observations, and the same common criteria.
Packet separation does not create an operating-system read jail. Record the
actual review context and visual inspection performed.

## Compare and submit

Give the judge the generated judge request and the artifacts it names. Return the
semantic fields in that request's emitted contract; do not invent a parallel
response schema or translate rejected values into accepted ones.

```bash
python3 -B "<runbook-root>/scripts/pair.py" --base "<runbook-root>" submit \
  --job "<job>" \
  --request "<job>/judge-request.json" \
  --payload "<judgment-proposal.json>"
```

The runtime rejects missing/duplicate criteria, mismatched page coverage,
unsupported evidence references, stale inputs, and the wrong request. It writes
`review.json` and derives `review.md` from the accepted record. Do not edit either
result independently. Apply the semantic criteria when interpreting those
results; structural acceptance is not a quality verdict.

## Verify or revise

```bash
python3 -B "<runbook-root>/scripts/pair.py" --base "<runbook-root>" verify --job "<job>"
```

Every consuming command also performs its own preflight checks. An edit becomes
available to the next activated instructions snapshot and the next prepared job. An
existing job verifies against its original immutable instructions snapshot, frozen
criterion source, derived oracle, and runtime version. Mutating the guide or code
path recorded by that job instead of using its original snapshot invalidates the
binding, as do changes to its source document, specification, assets, HTML,
requests, or registered render/results. Preserve the old job as evidence of that
revision; prepare a new job rather than modifying its state or hashes to make it
current.

The immutable guide bundle is read-only input. Keep all job data outside it. Do
not repair an installed snapshot in place. A local experiment with different
criteria is a separate explicitly identified authoring copy, not an update to the
shared guide.

The protocol has no provider dispatcher or automatic publishing step. Use the
available authorized authoring/review tools, preserve their actual invocation
evidence, and disclose any unexecuted or uncertain checks. It verifies shared
criteria and bindings; model interpretation and visual-detection accuracy require
their own evidence.
