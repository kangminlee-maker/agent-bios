#!/usr/bin/env bash
# Prompting guides are model-version-bound: unlike the rest of the guide set,
# their rules change when the model changes (the current generation inverted the
# previous one's advice). So they name concrete models, and this gate keeps that
# naming honest — it fails when the launch config binds a model no prompting
# guide covers, which is exactly when the guidance needs re-deriving from the
# vendor's current docs.
set -u
cd "$(dirname "$0")/.." || exit 2

python3 - "$@" <<'PY'
import pathlib, re, sys, tomllib

config = pathlib.Path("launch/agent-launch.toml")
hosts = tomllib.loads(config.read_text())["hosts"]

# host -> the guide that owns prompting guidance for that host's model family
OWNERS = {"codex": "gpt-prompting", "claude": "claude-prompting"}

def targets(guide_id):
    path = pathlib.Path(f"codex/guides/{guide_id}.md")
    if not path.is_file():
        sys.exit(f"FAIL: missing prompting guide: {path}")
    front = re.match(r"---\n(.*?)\n---\n", path.read_text(), re.S)
    if not front:
        sys.exit(f"FAIL: missing YAML frontmatter: {path}")
    block = re.search(r"^targets:\n((?:\s+-\s+\S+\n)+)", front.group(1), re.M)
    if not block:
        sys.exit(f"FAIL: {path} declares no targets:")
    return {line.strip().lstrip("- ").strip() for line in block.group(1).splitlines()}

fail = 0
for host, guide_id in OWNERS.items():
    configured = set(hosts.get(host, {}).get("models", []))
    for tier in hosts.get(host, {}).get("tiers", {}).values():
        if tier.get("model"):
            configured.add(tier["model"])
    if not configured:
        print(f"FAIL: no models configured for host {host}; nothing to check")
        fail = 1
        continue
    declared = targets(guide_id)
    stale = sorted(configured - declared)
    if stale:
        print(
            f"FAIL: {guide_id}.md does not cover configured {host} model(s): "
            f"{', '.join(stale)} — re-derive it from current vendor guidance and "
            f"update its targets:"
        )
        fail = 1
    else:
        print(f"  {guide_id}: covers all {len(configured)} configured {host} model(s)")
    unused = sorted(declared - configured)
    if unused:
        print(f"  note: {guide_id} also targets unbound model(s): {', '.join(unused)}")

sys.exit(fail)
PY
status=$?
[ $status -eq 0 ] && echo "PROMPTING TARGETS OK: every configured model is covered" \
                  || echo "PROMPTING TARGETS FAILED"
exit $status
