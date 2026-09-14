#!/usr/bin/env python3
"""Bijection/coverage gate: compose/domains.json vs the canonical instructions.

The manifest is the sole classification authority (tagged-monolith layout);
claude/CLAUDE.md stays the sole text authority. This gate closes the
silent-drop window: a bullet reworded without a manifest update, or a
manifest entry whose anchor no longer matches, fails HERE, before landing.

Blocking checks (any violation exits 1, all violations listed):
  1. schema shape + registry legality (tiers/domains from the manifest's own
     registry; domains list non-empty iff tier == "domain")
  2. bullet bijection: every manifest anchor matches exactly ONE `- ` bullet
     in claude/CLAUDE.md, and every bullet is claimed by exactly ONE entry
  3. file coverage: every file in claude/guides|hooks|agents and every skill
     directory in claude/skills claimed exactly once; every claimed one exists
     on disk (a skill is a directory carrying SKILL.md — a directory there
     without one is malformed, not unclaimed)
  4. router-guide co-package, both directions: a bullet or guide referencing a
     guide must have an audience covered by that guide's audience, and the target
     must be one an install actually receives; every guide must be pointed at by
     something — a bullet, a parent guide, or a launch preset — or it ships and is
     read by nobody. This gate assumes references take PATH form; the rule that
     makes that true is author-side, in gates/check-lexicon.py — it needs LEXICON
     and the ko/ tree, neither of which a packaged install has
  5. hook source_guide: a hook naming its source guide must carry the same
     tier + domain set as that guide
  6. non-vacuity: every subject set this gate judges is non-empty, so a green
     run cannot be vacuous

Informational (non-blocking until budgets are set in the manifest): estimated
token size per package.

--self-test: runs negative controls (mutated manifests that MUST fail) and
exits 0 only if every mutation is caught. Proves the gate can fail.
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pkgid  # noqa: E402  (sibling module in compose/)
from assemble import (  # noqa: E402  the shipped structural/audience/ownership readers
    GuideMemberError,
    author_only,
    guide_member_map,
    hook_command_matches,
)

REPO = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = REPO / "compose" / "domains.json"
MONOLITH = REPO / "claude" / "CLAUDE.md"
FILE_SECTIONS = {  # manifest key -> instructions dir, glob
    "guides": ("claude/guides", "*.md"),
    "hooks": ("claude/hooks", "*"),
    "agents": ("claude/agents", "*.md"),
    # A skill's unit is its DIRECTORY (SKILL.md + free subdirectories), deployed as a
    # tree by install.sh and asked of the assembler by name (`--selected-skills`), so the
    # manifest classifies the directory name, not the files inside it.
    "skills": ("claude/skills", "*"),
}
SKILL_MARKER = "SKILL.md"


def units_on_disk(root, glob, key):
    """The names the manifest section `key` must claim: files, or for skills the
    directories that carry SKILL.md. Returns (names, malformed) — a skills subdirectory
    without the marker is neither claimable nor ignorable."""
    names, malformed = set(), []
    if key == "guides":
        try:
            return set(guide_member_map(root)), malformed
        except GuideMemberError as exc:
            return names, [str(exc)]
    for p in root.glob(glob):
        if key == "skills":
            if p.is_dir():
                if (p / SKILL_MARKER).is_file():
                    names.add(p.name)
                else:
                    malformed.append(p.name)
        elif p.is_file():
            names.add(p.name)
    return names, malformed


def load_manifest(path=MANIFEST):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def instructions_bullets(path=MONOLITH):
    text = path.read_text(encoding="utf-8")
    return [ln for ln in text.splitlines() if ln.startswith("- ")]


def audience(entry, errors, ctx):
    """Universal set marker, or the frozen domain set; records legality errors."""
    tier = entry.get("tier")
    domains = entry.get("domains", [])
    if tier in ("core", "infra"):
        if domains:
            errors.append(f"{ctx}: tier {tier} must not list domains, got {domains}")
        return "UNIVERSAL"
    if tier == "env-personal":
        if domains:
            errors.append(f"{ctx}: env-personal must not list domains")
        return "NEVER"
    if tier == "domain":
        if not domains:
            errors.append(f"{ctx}: tier domain requires >=1 domain")
        return frozenset(domains)
    errors.append(f"{ctx}: illegal tier {tier!r}")
    return "NEVER"


def delivered(name, repo=None):
    """Does an install actually receive this guide?

    Manifest audience says who NEEDS it; `audience: author` says who can act on it, and
    compose/assemble.py withholds the second from every packaged install. A reference whose
    target is withheld is unresolvable for every installed reader no matter how universal its
    tier looks, so audience coverage alone is the wrong question to ask about it."""
    base = (repo or REPO) / "claude" / "guides" / name
    try:
        return not author_only(base)
    except Exception:
        return True   # unreadable frontmatter is check-package's call, not this one


def covers(guide_aud, bullet_aud):
    if guide_aud == "UNIVERSAL":
        return True
    if bullet_aud in ("UNIVERSAL", "NEVER"):
        return False  # universal bullet needs universal guide; NEVER refs nothing
    return isinstance(guide_aud, frozenset) and guide_aud >= bullet_aud


def prose_handles(name):
    """Prose forms of a guide name, DERIVED from the filename rather than declared.

    Multi-token runs of the stem only — `coding-staged-workflow` yields "staged-workflow"
    and "coding-staged", never the bare "workflow" or "coding", because a single generic
    token matches unrelated sentences and a gate that cries wolf gets routed around. The
    hyphen is what makes a run distinctive enough to mean the guide.

    Derivation rather than declaration because declaring is a step someone forgets: two
    prose references were already caught this way after their instances were patched, and
    a third and fourth were found by the derivation itself. `handles` stays for a phrasing
    that shares no token run with the filename."""
    toks = name[:-3].split("-")
    return sorted({"-".join(toks[i:j]) for i in range(len(toks))
                   for j in range(i + 2, len(toks) + 1)}, key=len, reverse=True)


# The words that make a prose mention a REFERENCE ("read the X guide/doc/..."). One list,
# owned here because this file ships and gates/ may import shipped, never the reverse.
# refs_from hard-coded "guide" while check-lexicon knew four words, so "read the
# staged-workflow document" resolved for the author-side gate and not for this one — a
# universal bullet could carry that pointer past rule 4 undetected.
REFERRING_WORDS = ("guide", "guidance", "document", "doc")


def referring_alternation():
    """The regex alternation for referring words, plurals included — "read the concept
    economy guideS" was a reference the singular-only pattern let through. One builder,
    because two gates consume this and a plural added in one drifted from the other."""
    return "|".join(w if w == "guidance" else w + "s?" for w in REFERRING_WORDS)


def refs_from(text, guides):
    """Which guides this text sends the reader to — by path, by declared handle, or by a
    derived prose form. Stable order, so one guide named twice is judged once.

    A derived run counts only when it identifies ONE guide — or is a guide's entire stem,
    since naming the whole filename is not ambiguous even where it prefixes a sibling's.
    Without that, "the llm-capability-boundary guide" marked the base AND both of its
    children as consumed, so an unrelated mention of the parent kept an unreachable child
    out of the orphan report."""
    found = list(dict.fromkeys(re.findall(r"guides/([a-z0-9-]+\.md)", text)))
    lowered = text.lower()

    def loose(run):
        # Prose renders filenames as plain words: a bullet saying "the concept economy
        # guide" is a promise refs_from could not see while it required the hyphen, so a
        # universal bullet could point at a domain guide undetected. Safe to relax here
        # because this branch already requires the word "guide" after the run — a bare
        # dehyphenated mention never reaches it.
        return r"[-\s]+".join(re.escape(tok) for tok in run.split("-"))

    owner = {}
    for name in guides:
        for r in prose_handles(name):
            owner.setdefault(r, set()).add(name)
    for name, entry in guides.items():
        if name in found:
            continue
        stem = name[:-3]
        runs = [h for h in prose_handles(name) if owner.get(h) == {name} or h == stem]
        if any(re.search(rf"(?<![0-9A-Za-z_]){re.escape(h.lower())}(?![0-9A-Za-z_])",
                         lowered) for h in entry.get("handles", [])) or \
           any(re.search(rf"\b{loose(h)}\s+(?:{referring_alternation()})\b", lowered)
               for h in runs):
            found.append(name)
    return found


def run_gate(manifest, bullets, repo=REPO):
    errors = []

    def name_set(value, key):
        """The registry's names, or an error and an empty set.

        This gate's contract is that shape violations exit 1 with every violation LISTED.
        `set(None)` raises instead, so a `"domains": null` — parse-valid JSON, and exactly
        the shape a bad hand-edit leaves — came out of the gate as a TypeError traceback
        before it could name anything at all."""
        if isinstance(value, (list, dict, tuple, set)):
            return set(value)
        errors.append(f"registry: {key} must be a list or object, got {type(value).__name__}")
        return set()

    tiers = name_set(manifest.get("tiers", []), "tiers")
    domains_reg = name_set(manifest.get("domains", {}), "domains")
    if not tiers or not domains_reg:
        errors.append("registry: tiers/domains registry empty")

    errors += check_settings_template(manifest, repo)

    # -- 0. package identity ------------------------------------------------
    # Absent means core (the reservation that keeps pre-v2 artifacts valid), but
    # a PRESENT malformed id must fail rather than fall back — silently treating
    # a typo as core would hand it the engine's unconditional-injection audience.
    pid = pkgid.resolve(manifest)
    if not pkgid.is_valid(pid):
        errors.append(f"package_id: {pid!r} is not @scope/name (lowercase, hyphen-separated)")

    # A registered domain with nothing in it. The gate asserts its subject sets are
    # non-empty so a green run cannot be vacuous, and the DOMAIN registry was the one set it
    # never asked that of: a name could be selectable, appear in the picker, be written into
    # selection.json — and deliver only the universal tier, which every other selection
    # delivers too. A domain that changes nothing about what you receive is a promise the
    # assembler cannot keep, and nothing downstream can notice.
    claimed = set()
    for entry in manifest.get("bullets", []):
        if isinstance(entry, dict):
            claimed.update(d for d in entry.get("domains", []) if isinstance(d, str))
    for kind in FILE_SECTIONS:
        for entry in (manifest.get(kind) or {}).values():
            if isinstance(entry, dict):
                claimed.update(d for d in entry.get("domains", []) if isinstance(d, str))
    for name in sorted(domains_reg - claimed):
        errors.append(
            f"domain {name!r} is registered but no bullet, guide, hook, agent or skill is in "
            f"it — selecting it would deliver exactly what selecting nothing delivers")

    def check_registry(entry, ctx):
        if entry.get("tier") not in tiers:
            errors.append(f"{ctx}: tier {entry.get('tier')!r} not in registry")
        for d in entry.get("domains", []):
            if d not in domains_reg:
                errors.append(f"{ctx}: domain {d!r} not in registry")

    # -- 2. bullet bijection ------------------------------------------------
    mb = manifest.get("bullets", [])
    if not bullets:
        errors.append("non-vacuity: no bullets found in monolith")
    if not mb:
        errors.append("non-vacuity: manifest has no bullet entries")
    if len(mb) != len(bullets):
        errors.append(f"bijection: manifest has {len(mb)} bullet entries, monolith has {len(bullets)} bullets")
    claimed = [0] * len(bullets)
    seen_anchors = set()
    for i, entry in enumerate(mb):
        ctx = f"bullets[{i}] anchor={entry.get('anchor', '')!r:.60}"
        check_registry(entry, ctx)
        anchor = entry.get("anchor", "")
        if not anchor:
            errors.append(f"{ctx}: empty anchor")
            continue
        if anchor in seen_anchors:
            errors.append(f"{ctx}: duplicate anchor")
        seen_anchors.add(anchor)
        hits = [j for j, b in enumerate(bullets) if anchor in b]
        if len(hits) != 1:
            errors.append(f"{ctx}: anchor matches {len(hits)} bullets (need exactly 1)")
        for j in hits:
            claimed[j] += 1
    for j, n in enumerate(claimed):
        if n != 1:
            errors.append(f"bijection: bullet line {bullets[j][:70]!r} claimed {n} times (need exactly 1)")

    # -- 3. file coverage ---------------------------------------------------
    entries = {}
    for key, (rel, glob) in FILE_SECTIONS.items():
        section = manifest.get(key, {})
        entries[key] = section
        if not section:
            errors.append(f"non-vacuity: manifest section {key!r} empty")
        on_disk, malformed = units_on_disk(repo / rel, glob, key)
        if not on_disk:
            errors.append(f"non-vacuity: no files on disk under {rel}")
        for name in malformed:
            if key == "skills":
                errors.append(f"{key}: directory {name} in {rel} carries no {SKILL_MARKER} — "
                              f"not a skill the hosts can load, and not a name the manifest can claim")
            else:
                errors.append(f"{key}: invalid bundle source shape — {name}")
        for name, entry in section.items():
            check_registry(entry, f"{key}/{name}")
            if name not in on_disk:
                errors.append(f"{key}: claimed file {name} does not exist in {rel}")
        for name in sorted(on_disk - set(section)):
            errors.append(f"{key}: file {name} in {rel} not claimed by the manifest")

    # -- 4. router-guide co-package ----------------------------------------
    # Path form AND declared prose handles. Naming a guide in prose is still a router — the
    # reader is sent somewhere — and a path-only scan reports clean on it, so a rule can ship to
    # an audience that cannot hold what it names. Prose is decidable once the mapping exists, so
    # the mapping is DATA on the guide entry (`handles`) and the check stays structural. A
    # handle is only as good as its declaration: this catches phrasings someone wrote down, not
    # every paraphrase.
    guide_aud = {n: audience(e, errors, f"guides/{n}") for n, e in entries["guides"].items()}
    guide_dir = repo / "claude" / "guides"
    try:
        guide_sources = guide_member_map(guide_dir)
    except GuideMemberError:
        # Rule 3 already reports the concrete shape error.  Keep the router checks from
        # raising so one malformed companion cannot hide the rest of the manifest errors.
        guide_sources = {}
    for name, members in guide_sources.items():
        primary_is_author_only = author_only(guide_dir / name)
        for member in members[1:]:
            path = guide_dir / member
            if path.suffix == ".md" and author_only(path) and not primary_is_author_only:
                errors.append(
                    f"guides/{name}: companion {member} declares audience: author but its "
                    f"primary is delivered — author-only content cannot ride a public guide bundle"
                )
    # A declared handle is a NAME, and a name resolving to two guides routes the reader
    # nowhere: refs_from() would credit both targets from one prose router, falsely
    # rooting and co-packaging a guide the sentence never meant. Duplicates fail here
    # so resolution below can trust that a declared handle has one owner.
    hdl_owner = {}
    for n, e in entries["guides"].items():
        for h in e.get("handles", []):
            # Indexed by the SAME normalized form resolution uses — refs_from
            # lowercases before matching, so "Case Alias" and "case alias" are one
            # name, and indexing raw text passed the pair as distinct.
            hdl_owner.setdefault(h.lower(), []).append(n)
    for h, owners in sorted(hdl_owner.items()):
        if len(owners) > 1:
            errors.append(f"guides: handle {h!r} is declared by {', '.join(sorted(owners))}"
                          f" — one name, one target; make the handle unique")
    # Declared×derived is the remaining collision pair (declared×declared above,
    # derived×derived resolves to nobody inside refs_from): a handle like "concept
    # economy guide" declared on another guide double-resolves with concept-economy.md's
    # DERIVED form, one prose pointer rooting and co-packaging two targets. Normalized —
    # lowercased, one trailing referring word stripped, spaces to hyphens — a declared
    # handle may not carry a different guide's run or stem at a hyphen boundary.
    ref_tail = re.compile(rf"[-\s]+(?:{referring_alternation()})$")
    for n, e in entries["guides"].items():
        for h in e.get("handles", []):
            norm = re.sub(r"\s+", "-", ref_tail.sub("", h.lower()).strip())
            for other in entries["guides"]:
                if other == n:
                    continue
                runs = set(prose_handles(other)) | {other[:-3]}
                if any(re.search(rf"(?:^|-){re.escape(r)}(?:-|$)", norm) for r in runs):
                    errors.append(
                        f"guides: handle {h!r} on {n} collides with {other}'s derived "
                        f"name — one prose pointer would resolve both; reword the handle")
                    break
    anchor_of = {id(e): e.get("anchor", "?") for e in mb}
    ref_checks = 0
    undelivered = set()
    for entry in mb:
        hits = [b for b in bullets if entry.get("anchor", "\0") in b]
        if len(hits) != 1:
            continue  # already reported by bijection
        b_aud = audience(entry, errors, f"bullet {entry.get('anchor', '')!r:.40}")
        if b_aud == "NEVER":
            # env-personal is never assembled (assemble.py maps the tier to NEVER),
            # so this bullet's references reach no reader — remembered here so the
            # orphan check below does not let it root a guide.
            undelivered.add(hits[0])
        for g in refs_from(hits[0], entries["guides"]):
            ref_checks += 1
            if g not in guide_aud:
                errors.append(f"router: bullet {entry['anchor']!r:.40} references unclaimed guide {g}")
            elif not delivered(g, repo):
                errors.append(
                    f"router: bullet {entry['anchor']!r:.40} references {g}, which declares "
                    f"audience: author and is withheld from every install — no reader can open it"
                )
            elif not covers(guide_aud[g], b_aud):
                errors.append(
                    f"router: bullet {entry['anchor']!r:.40} (audience {b_aud}) references guide {g} "
                    f"(audience {guide_aud[g]}) — user can hold the router without the guide"
                )
    if ref_checks == 0:
        errors.append("non-vacuity: no router->guide references were checked")

    # The same relation, read the other way. Rule 4 asks whether the reader of a pointer has
    # the guide; this asks whether a guide has a pointer at all. Without it a guide can be
    # written, packaged, and delivered while nothing reaches it, and every other check is green.
    #
    # Three consumer kinds exist and each is a real delivery path, so none of them is an
    # exemption: an instruction bullet (by path or declared handle), a parent guide citing a child
    # as a depth chain, and a launch preset's mission. An exemption list would be the fourth,
    # and it is the one that lets a genuinely orphaned guide through.
    launch = repo / "launch" / "agent-launch.toml"
    launch_text, launch_missions = "", []
    if launch.is_file():
        # PARSED string values, not the raw file: a guide named in a TOML comment reaches
        # no agent, but refs_from over raw text credited it as a consumer and an orphan
        # slipped past. The parser drops comments and keys; what remains is exactly the
        # text a mission can put in front of a model. A config that does not parse is a
        # loud error — silently falling back to raw text would re-open the comment hole.
        import tomllib
        # Instruction-bearing fields ONLY — `mission` is what the launcher appends to the
        # system prompt, so it is the one field whose text reaches a model. Walking every
        # string value credited a guide named in an unused key as consumed, hiding an
        # orphan; and classified-or-loud closes the other direction too: a guides/
        # reference in any NON-instruction field fails outright, because text no agent
        # reads is either a mistake or belongs in a mission.
        def _fields(v, path=()):
            if isinstance(v, str):
                yield path, v
            elif isinstance(v, dict):
                for k, x in v.items():
                    yield from _fields(x, path + (k,))
            elif isinstance(v, list):
                for x in v:
                    yield from _fields(x, path)

        def _is_mission(path):
            # presets.*.mission ONLY — the launcher reads mission from presets alone
            # (launch/agent-launch.py, load_config -> presets), so a `mission` key under
            # any other table is inert text no model receives. Filtering by leaf key
            # credited exactly such a value as a consumer.
            return len(path) == 3 and path[0] == "presets" and path[2] == "mission"
        try:
            pairs = list(_fields(tomllib.loads(launch.read_text(encoding="utf-8"))))
            launch_missions = [v for k, v in pairs if _is_mission(k)]
            launch_text = "\n".join(launch_missions)
            for k, v in pairs:
                # Path form OR prose form — refs_from covers both (its path regex is
                # this test's old one): a `mission` under the wrong table saying
                # "read the concept economy guide first" is the same inert text as a
                # guides/ path there, and the path-only test let the prose form
                # masquerade as instructions no launcher delivers.
                if not _is_mission(k) and refs_from(v, entries["guides"]):
                    errors.append(
                        f"launch: field {'.'.join(k)!r} names a guide but is not "
                        f"instruction-bearing — no agent reads it there; move it into a "
                        f"preset mission or drop it")
        except tomllib.TOMLDecodeError as exc:
            errors.append(f"launch: agent-launch.toml does not parse ({exc}) — mission "
                          f"consumers cannot be judged")
    # install.sh deploys the launch config regardless of domain selection, so a mission's
    # DEPLOYED-form reference (a CLAUDE_CONFIG_DIR / ~/.claude path) must resolve for every
    # user: universal tier and delivered. A CHECKOUT-form reference (bare claude/guides/...,
    # as the distill mission uses on purpose) names the author's repo; its guard is
    # check-package's RUNTIME_GUARDED leg, not audience math — but it still counts as a
    # consumer below, or the guide it points at reads as an orphan.
    # Judged PER MISSION, never over the concatenated text: one preset's guarded
    # checkout reference must not exempt another preset's prose reference to the same
    # guide — collapsing by name did exactly that, and review reproduced it with both
    # forms of concept-economy in one config.
    launch_flagged = set()
    for mtext in launch_missions:
        # Occurrences are classified separately even inside ONE mission: refs_from
        # collapses a checkout path and a prose pointer to the same guide, and the
        # mission-wide checkout match exempted the prose — review reproduced both forms
        # in a single mission. Stripping every path first leaves exactly the prose
        # occurrences, so what still resolves afterwards was said in words.
        pathless_m = re.sub(r"\S*guides/[a-z0-9-]+\.md\S*", "", mtext)
        prose_refs = set(refs_from(pathless_m, entries["guides"]))
        for lg in refs_from(mtext, entries["guides"]):
            if lg in launch_flagged:
                continue
            # The EXEMPTION is the narrow case: a checkout-form path (bare
            # claude/guides/..., the distill mission's deliberate shape, guarded by
            # check-package's RUNTIME_GUARDED) names the author's repo. A deployed-home
            # path or a PROSE occurrence reaches every selection, because presets deploy
            # unconditionally.
            checkout_form = re.search(
                r"(?<![\w$}])claude/guides/" + re.escape(lg), mtext)
            deployed_form = re.search(
                r"(?:CLAUDE_CONFIG_DIR|CODEX_HOME|\.claude|\.codex)[^\n\"']*guides/"
                + re.escape(lg), mtext)
            if (deployed_form or lg in prose_refs or not checkout_form) and (
                    not delivered(lg, repo) or guide_aud.get(lg) != "UNIVERSAL"):
                launch_flagged.add(lg)
                errors.append(
                    f"launch: a mission references {lg}, the launch config deploys to "
                    f"every selection, and {lg} is "
                    f"{'withheld (audience: author)' if not delivered(lg, repo) else 'domain-scoped'}"
                    f" — a non-matching selection receives the mission without the guide")
    def _defenced(text):
        # Fenced code blocks are EXAMPLES: a fenced `guides/x.md` shows the reader what a
        # reference looks like without sending anyone anywhere, and counting it as a
        # consumer let a fenced sample conceal an orphan after its real router was
        # removed. ALL Markdown fence forms — ``` and ~~~ at any length >= 3, closed by
        # the same character at >= the opening length — because the first version knew
        # only triple backticks and review moved the sample to ~~~. Inline code spans
        # stay: real references are written as backticked deploy paths.
        out, fence = [], None
        prev_blank, last_nonblank, in_indent = True, "", False
        for line in text.splitlines():
            # Blockquote markers are containers, not content: `> ```` opens a fence as
            # surely as ``` does, and the prefixed form escaped the opener match. The
            # marker is normalized off for the whole pipeline — blockquoted PROSE still
            # renders and its real references still count.
            # A list marker is a container the same way when a blockquote rides it:
            # `- > ```` renders as code inside a list-carried blockquote, and the
            # leading marker hid the `>` from the normalization — the fence never
            # opened and the quoted example read as prose. Stripped only when a
            # blockquote follows; a plain list item is content, not a wrapper.
            line = re.sub(r"^\s*(?:[-*+]|\d+\.)\s+(?=>)", "", line)
            line = re.sub(r"^(\s*>)+ ?", "", line)
            s = line.strip()
            m = re.match(r"(`{3,}|~{3,})", s)
            if fence is not None:
                if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                        and not s[len(m.group(1)):].strip():
                    # A CLOSING fence carries nothing but whitespace — ```python inside
                    # an open block is a nested opener in real Markdown, and treating it
                    # as the close exposed the rest of the example as prose.
                    fence = None
                continue
            if m:
                fence = (m.group(1)[0], len(m.group(1)))
                continue
            # Markdown's INDENTED code form: four spaces (or a tab) after a blank line
            # opens a code block unless the preceding block is a list item, whose
            # continuation lines are legitimately indented prose. The fenced repairs
            # left this fourth example syntax crediting consumers.
            # The code threshold is RELATIVE to the enclosing block: four columns past
            # the text of a list item (whose continuations are legitimately indented
            # prose), four from the margin otherwise. A blanket list exemption kept an
            # eight-space sample nested under a list item as prose.
            lm = re.match(r"(\s*(?:[-*+]|\d+\.)\s+)", last_nonblank.expandtabs(4))
            base = len(lm.group(1)) if lm else 0
            # Tabs expand to columns (CommonMark: a tab advances to the next 4-column
            # stop); counting a tab as one character kept tab-indented code as prose.
            exp = line.expandtabs(4)
            ind = len(exp) - len(exp.lstrip())
            indented = bool(s) and ind >= base + 4
            if in_indent:
                if (bool(s) and ind >= base + 4) or not s:
                    continue
                in_indent = False
            elif indented and prev_blank:
                in_indent = True
                continue
            if s:
                last_nonblank = line
            prev_blank = not s
            out.append(line)
        prose = "\n".join(out)
        # HTML comments are stripped from RENDERED PROSE, after the fence pass: a literal
        # <!-- inside a fenced sample is code, and subbing comments first let it swallow
        # everything through EOF — including a real router after the fence, which then
        # read as an orphan. Closed comments first, then an unterminated one through EOF
        # (rendered Markdown hides the remainder either way).
        prose = re.sub(r"<!--.*?-->", "", prose, flags=re.S)
        return re.sub(r"<!--.*", "", prose, flags=re.S)

    bodies = {
        name: "\n".join(
            _defenced((guide_dir / member).read_text(encoding="utf-8"))
            for member in members if member.endswith(".md")
        )
        for name, members in guide_sources.items()
    }
    if not bodies:
        errors.append("non-vacuity: no guide bodies read, so consumers were not checked")
    # Reachability is TRANSITIVE FROM ROOTS (bullets and launch missions), not "any
    # incoming edge": two unrooted guides citing each other kept each other alive as an
    # inert island — the same lesson the pre-commit reach scan learned about seeding.
    # And a root must be DELIVERED: an undelivered (env-personal) bullet exists in the
    # monolith but ships to nobody, and routing a guide's only pointer through one
    # concealed the orphan behind a tier change.
    reachable, frontier = set(), [
        g for g in entries["guides"]
        if any(g in refs_from(b, entries["guides"])
               for b in bullets if b not in undelivered)
        or g in refs_from(launch_text, entries["guides"])]
    while frontier:
        g = frontier.pop()
        if g in reachable:
            continue
        reachable.add(g)
        frontier.extend(n for n in refs_from(bodies.get(g, ""), entries["guides"])
                        if n != g and n not in reachable)
    for name in entries["guides"]:
        if name not in reachable:
            errors.append(
                f"orphan: guide {name} is claimed by the manifest and delivered, but no bullet, "
                f"no other guide, and no launch preset points at it — it is inert"
            )

    # A guide citing another guide is a router with the same failure mode, so it needs the
    # same audience check. Miss it and an install can deliver the citing guide while withholding
    # the cited one, which reads to the gate as two independently legal packages.
    body_checks = 0
    for name, body in bodies.items():
        if name not in entries["guides"]:
            continue                                # unclaimed file: rule 3 owns that
        src_aud = audience(entries["guides"][name], errors, f"guides/{name}")
        for cited in refs_from(body, entries["guides"]):
            if cited == name:
                continue
            body_checks += 1
            if delivered(name, repo) and not delivered(cited, repo):
                errors.append(
                    f"router: guide {name} is delivered but points at {cited}, which declares "
                    f"audience: author and is withheld — the citation cannot resolve for a reader"
                )
            elif delivered(name, repo) and not covers(guide_aud.get(cited, "NEVER"), src_aud):
                # Coverage is asked only of citations a packaged reader can follow. An
                # audience:author guide never reaches an install, and a checkout has the whole
                # tree regardless of domains — so its citation of a narrow-domain child is a
                # gap for nobody, and failing it would force author docs to carry universal
                # audiences they do not have.
                errors.append(
                    f"router: guide {name} (audience {src_aud}) points at {cited} "
                    f"(audience {guide_aud.get(cited)}) — reader can hold {name} without it"
                )
    if body_checks == 0:
        errors.append("non-vacuity: no guide->guide references were checked")

    # -- 5. hook source_guide -----------------------------------------------
    for name, entry in entries["hooks"].items():
        src = entry.get("source_guide")
        if src:
            g = entries["guides"].get(src)
            if g is None:
                errors.append(f"hooks/{name}: source_guide {src} not in manifest guides")
            elif (entry.get("tier"), sorted(entry.get("domains", []))) != (g.get("tier"), sorted(g.get("domains", []))):
                errors.append(f"hooks/{name}: tier/domains differ from source guide {src}")

    # -- informational token report ------------------------------------------
    sizes = {}
    for entry in mb:
        key = entry.get("tier") if entry.get("tier") != "domain" else ",".join(entry.get("domains", ["?"])[:1])
        hit = next((b for b in bullets if entry.get("anchor", "\0") in b), "")
        sizes[key] = sizes.get(key, 0) + len(hit) // 4
    for name, entry in entries["guides"].items():
        key = entry.get("tier") if entry.get("tier") != "domain" else ",".join(entry.get("domains", ["?"])[:1])
        for member in guide_sources.get(name, []):
            p = repo / FILE_SECTIONS["guides"][0] / member
            if p.is_file():
                sizes[key] = sizes.get(key, 0) + p.stat().st_size // 4
    return errors, sizes


def check_settings_template(manifest, repo=REPO):
    """Every hook registered in the shipped settings template must be a hook the
    manifest declares.

    `merge_settings` only re-adds template entries whose command names a
    manifest-declared hook (assemble.py:167-169), so an entry for anything else
    is silently inert — it looks registered, ships to every user, and never runs.
    That is how a machine-local registration ends up committed in a
    deploy-managed file. Make it invalid instead of asking people to remember.
    """
    errors = []
    spath = repo / "claude" / "settings.template.json"
    if not spath.is_file():
        return ["settings: claude/settings.template.json missing"]
    names = set(manifest.get("hooks", {}))
    entries = [(ev, h.get("command", ""))
               for ev, evs in json.loads(spath.read_text(encoding="utf-8")).get("hooks", {}).items()
               for en in evs for h in en.get("hooks", [])]
    if not entries:
        errors.append("non-vacuity: settings template registers no hooks")
    for ev, cmd in entries:
        # The assembler's matcher, not a substring: `.disabled` after the name satisfied
        # `in` while merge_settings skipped the entry, so the gate blessed a template the
        # install silently dropped. One matcher, imported, so they cannot drift apart.
        if not any(hook_command_matches(cmd, n) for n in names):
            errors.append(f"settings: {ev} hook {cmd!r} names no manifest hook "
                          f"(known: {sorted(names)}) — it would never deploy")
    return errors


def self_test(manifest, bullets):
    """Negative controls: each mutation MUST make the gate fail."""
    import copy

    muts = []
    m1 = copy.deepcopy(manifest)
    m1["bullets"] = m1["bullets"][1:]
    muts.append(("dropped bullet entry", m1, bullets, "bijection"))
    m2 = copy.deepcopy(manifest)
    m2["bullets"][0]["anchor"] = "zz-no-such-phrase-zz"
    muts.append(("anchor matches nothing (reword drift)", m2, bullets, "anchor"))
    m3 = copy.deepcopy(manifest)
    m3["bullets"][1]["anchor"] = m3["bullets"][0]["anchor"]
    muts.append(("duplicate anchor claim", m3, bullets, "anchor"))
    m4 = copy.deepcopy(manifest)
    first_guide = next(iter(m4["guides"]))
    del m4["guides"][first_guide]
    muts.append((f"unclaimed guide {first_guide}", m4, bullets, "unclaimed"))
    b5 = bullets + ["- a brand new bullet the manifest never heard of"]
    muts.append(("bullet added without manifest entry", copy.deepcopy(manifest), b5, "bijection"))
    m6 = copy.deepcopy(manifest)
    m6["package_id"] = "@Acme/Builder"          # uppercase is not a legal segment
    muts.append(("malformed package_id", m6, bullets, "package_id"))
    # A registry name with nothing in it. It is selectable, it is written into
    # selection.json, and it delivers exactly the universal tier every other selection also
    # delivers — so nothing downstream can tell it apart from choosing nothing at all.
    m8 = copy.deepcopy(manifest)
    m8["domains"]["empty-domain-control"] = "registered with no subjects"
    muts.append(("a registered domain with no subjects", m8, bullets, "empty-domain-control"))
    m7 = copy.deepcopy(manifest)
    m7["hooks"] = {"renamed-hook.py": {"tier": "core", "domains": []}}
    muts.append(("settings registers a hook the manifest does not declare", m7, bullets, "settings"))
    # Skills are directory units. Both directions of coverage, and the subject asserted
    # first: a self-test that finds no shipped skill would "catch" its own absence.
    if not manifest.get("skills"):
        raise SystemExit("self-test: the manifest declares no skill, so the skill-coverage "
                         "controls have no subject and would pass vacuously")
    m9 = copy.deepcopy(manifest)
    first_skill = next(iter(m9["skills"]))
    del m9["skills"][first_skill]
    muts.append((f"unclaimed skill directory {first_skill}", m9, bullets, "not claimed"))
    m10 = copy.deepcopy(manifest)
    m10["skills"]["no-such-skill-control"] = {"tier": "domain", "domains": ["builder-base"]}
    muts.append(("a claimed skill with no directory on disk", m10, bullets, "does not exist"))

    # A bullet that names a cross-domain guide in PROSE. This shipped for real: the reader
    # held the rule and could not hold the guide, and a path-only scan reported clean. The
    # control plants the handle rather than a path, so it fails only while handle detection
    # is live — deleting `handles` or reverting refs_from() to the path regex brings it back.
    handled = [(n, e) for n, e in manifest["guides"].items()
               if e.get("handles") and e.get("tier") == "domain"]
    if not handled:
        raise SystemExit("self-test: no guide declares `handles` — the prose-router control "
                         "has no subject and would pass vacuously")
    gname, gentry = handled[0]
    victim = next(b for b in manifest["bullets"]
                  if b.get("tier") == "domain"
                  and not set(b.get("domains") or []) & set(gentry["domains"]))
    hits = [b for b in bullets if victim["anchor"] in b]
    assert len(hits) == 1, "self-test: prose-router control could not locate its bullet"
    b8 = [b + f" (see the {gentry['handles'][0]})" if b is hits[0] else b for b in bullets]
    muts.append((f"bullet names {gname} in prose across a domain boundary",
                 copy.deepcopy(manifest), b8, "router"))
    # The dehyphenated PLURAL of the same promise: "the concept economy guides" resolved
    # to nothing while the singular was caught — the referring pattern must own plurals.
    spoken8 = gname[:-3].replace("-", " ")
    b8p = [b + f" — read the {spoken8} guides first" if b is hits[0] else b for b in bullets]
    muts.append((f"bullet names {gname} as a dehyphenated PLURAL prose reference",
                 copy.deepcopy(manifest), b8p, "router"))

    # The orphan control removes a guide's ONLY pointer. It picks that guide by looking, not
    # from a name typed here: a typed name stops being the right subject the moment that guide
    # gains a second consumer, and the control would go quiet without saying so.
    only_bullet = []
    for name in manifest["guides"]:
        cited = f"guides/{name}"
        handles = manifest["guides"][name].get("handles", [])
        refs = [b for b in bullets
                if cited in b or any(h.lower() in b.lower() for h in handles)]
        elsewhere = any(cited in (REPO / "claude" / "guides" / o).read_text(encoding="utf-8")
                        for o in manifest["guides"] if o != name)
        if len(refs) == 1 and not elsewhere:
            only_bullet.append((name, refs[0]))
    if not only_bullet:
        raise SystemExit("self-test: no guide is reachable through exactly one bullet, so the "
                         "orphan control has no subject and would pass vacuously")
    o_name, o_line = only_bullet[0]
    if len(only_bullet) < 2:
        raise SystemExit("self-test: fewer than two single-pointer guides, so the island "
                         "control has no subject and would pass vacuously")
    i_name, i_line = only_bullet[1]
    # The manifest entry goes with the line. Dropping the line alone breaks the bijection in
    # rule 2, which fails first — the control would then pass without the orphan check being
    # consulted at all.
    m_orphan = copy.deepcopy(manifest)
    m_orphan["bullets"] = [e for e in m_orphan["bullets"] if e["anchor"] not in o_line]
    if len(m_orphan["bullets"]) != len(manifest["bullets"]) - 1:
        raise SystemExit("self-test: the orphan control could not drop exactly one manifest "
                         "entry with its bullet, so the mutation is not the one it claims")
    muts.append((f"guide {o_name} left with no pointer at all",
                 m_orphan, [b for b in bullets if b != o_line], "orphan"))

    # A bullet that exists but ships to NOBODY cannot root a guide: reclassify the
    # orphan guide's only router bullet as env-personal (assemble maps the tier to
    # NEVER) and the guide must be reported as an orphan. The monolith line survives,
    # so the bijection stays intact and the orphan leg itself is the one judged —
    # which is why this control requires the orphan error by name instead of joining
    # the generic any-error mutation list.
    m_never = copy.deepcopy(manifest)
    tgt = [e for e in m_never["bullets"] if e["anchor"] in o_line]
    if len(tgt) != 1:
        raise SystemExit("self-test: the never-delivered control could not target exactly "
                         "one manifest entry, so the mutation is not the one it claims")
    tgt[0]["tier"] = "env-personal"
    tgt[0].pop("domains", None)
    errs_nv, _ = run_gate(m_never, bullets)
    never_ok = any(o_name in e and "orphan" in e for e in errs_nv)
    print(f"self-test [{'CAUGHT' if never_ok else 'MISSED'}] an env-personal (never-"
          f"delivered) router bullet leaves {o_name} an orphan")

    # Bundle shape is structural, not a second manifest class.  These controls run against
    # copies because the source is the input being judged: an orphan resource tree and a
    # symlink must be named before router/coverage checks can pretend the guide is ordinary.
    bundle_sources = guide_member_map(REPO / "claude" / "guides")
    bundle_name = next((name for name, members in bundle_sources.items()
                        if len(members) > 1), None)
    if bundle_name is None:
        raise SystemExit("self-test: no guide bundle has a companion member, so bundle-shape "
                         "controls would pass vacuously")
    companion_markdown = next((member for member in bundle_sources[bundle_name][1:]
                               if member.endswith(".md")), None)
    if companion_markdown is None:
        raise SystemExit("self-test: the companion bundle has no Markdown resource, so the "
                         "companion-router control would pass vacuously")
    import shutil as _bundle_shutil, tempfile as _bundle_tempfile
    with _bundle_tempfile.TemporaryDirectory() as _td:
        _root = pathlib.Path(_td)
        for _sub in ("claude", "ko", "launch"):
            if (REPO / _sub).is_dir():
                _bundle_shutil.copytree(REPO / _sub, _root / _sub)
        _guide_root = _root / "claude" / "guides"
        (_guide_root / "orphan-companion-control").mkdir()
        _orphan_shape, _ = run_gate(manifest, bullets, repo=_root)
        orphan_companion_ok = any("orphan guide companion tree" in e for e in _orphan_shape)
        _bundle_shutil.rmtree(_guide_root / "orphan-companion-control")

        _symlink = _guide_root / pathlib.Path(bundle_name).stem / "symlink-control"
        _symlink.symlink_to(_guide_root / bundle_name)
        _symlink_shape, _ = run_gate(manifest, bullets, repo=_root)
        symlink_ok = any("must not contain symlinks" in e for e in _symlink_shape)
        _symlink.unlink()

        _companion = _guide_root / companion_markdown
        _body = _companion.read_text(encoding="utf-8")
        _companion.write_text(_body + f"\n\nSee `guides/{o_name}` for the control.\n",
                              encoding="utf-8")
        _companion_router, _ = run_gate(m_orphan, [b for b in bullets if b != o_line], repo=_root)
        companion_router_ok = not any(o_name in e and "orphan" in e for e in _companion_router)
        _companion.write_text("---\naudience: author\n---\n" + _body, encoding="utf-8")
        _companion_author, _ = run_gate(manifest, bullets, repo=_root)
        companion_author_ok = any(bundle_name in e and companion_markdown in e
                                  and "audience: author" in e for e in _companion_author)
    print(f"self-test [{'CAUGHT' if orphan_companion_ok else 'MISSED'}] an orphan companion "
          "tree is rejected without requiring a manifest item")
    print(f"self-test [{'CAUGHT' if symlink_ok else 'MISSED'}] a symlink in a companion tree "
          "is rejected")
    print(f"self-test [{'CAUGHT' if companion_router_ok else 'MISSED'}] a Markdown companion "
          "is scanned as its primary guide's router")
    print(f"self-test [{'CAUGHT' if companion_author_ok else 'MISSED'}] an author-only companion "
          "cannot ride a delivered primary")

    # A registry of the wrong TYPE must be listed like any other violation. `set(None)` is
    # not a diagnostic — it is a TypeError out of the gate before it can name anything, and
    # `"domains": null` is exactly what a bad hand-edit of this file leaves behind. The
    # contrast is the shape it should have: both must come back as errors, never as a raise.
    for field, bad_value in (("domains", None), ("tiers", "core")):
        m_shape = copy.deepcopy(manifest)
        m_shape[field] = bad_value
        try:
            errs_shape, _ = run_gate(m_shape, bullets)
            shape_ok = any(f"registry: {field} must be" in e for e in errs_shape)
        except Exception as exc:
            errs_shape, shape_ok = [], False
            print(f"self-test [MISSED] {field}={bad_value!r} RAISED {type(exc).__name__}")
        print(f"self-test [{'CAUGHT' if shape_ok else 'MISSED'}] a {field} registry of the "
              f"wrong type is listed rather than raised")

    # One handle, one guide: copying a declared handle onto a second guide must fail as
    # a duplicate declaration, not silently resolve one prose router to both targets.
    m_dup = copy.deepcopy(manifest)
    donor = next((n for n in m_dup["guides"] if m_dup["guides"][n].get("handles")), None)
    if donor is None:
        raise SystemExit("self-test: no guide declares a handle, so the duplicate-handle "
                         "control has no subject and would pass vacuously")
    other = next(n for n in m_dup["guides"] if n != donor)
    m_dup["guides"][other].setdefault("handles", []).append(
        m_dup["guides"][donor]["handles"][0])
    errs_dup, _ = run_gate(m_dup, bullets)
    dup_ok = any("handle" in e and "declared by" in e for e in errs_dup)
    print(f"self-test [{'CAUGHT' if dup_ok else 'MISSED'}] a handle declared by two "
          f"guides fails as a duplicate declaration")

    # Case is not identity: resolution lowercases, so the uniqueness index must too —
    # a case variant of a declared handle is the same name and must fail the same way.
    m_case = copy.deepcopy(manifest)
    variant = m_case["guides"][donor]["handles"][0].upper()
    if variant == m_case["guides"][donor]["handles"][0]:
        raise SystemExit("self-test: the case-variant control is vacuous — the donor "
                         "handle has no case to vary")
    other2 = next(n for n in m_case["guides"] if n != donor)
    m_case["guides"][other2].setdefault("handles", []).append(variant)
    errs_case, _ = run_gate(m_case, bullets)
    case_ok = any("handle" in e and "declared by" in e for e in errs_case)
    print(f"self-test [{'CAUGHT' if case_ok else 'MISSED'}] a case-variant duplicate "
          f"handle fails as the same name")

    # Declared×derived: a handle spelling ANOTHER guide's spoken name (plus a referring
    # word) must fail as a collision — refs_from would resolve both targets from one
    # prose pointer, the declared branch for the handle's owner and the derived branch
    # for the guide the words actually name.
    m_xd = copy.deepcopy(manifest)
    target_g = next((n for n in m_xd["guides"] if "-" in n[:-3]), None)
    if target_g is None:
        raise SystemExit("self-test: no guide has a hyphenated stem, so the declared× "
                         "derived collision control has no subject and would pass vacuously")
    victim_g = next(n for n in m_xd["guides"] if n != target_g)
    m_xd["guides"][victim_g].setdefault("handles", []).append(
        target_g[:-3].replace("-", " ") + " guide")
    errs_xd, _ = run_gate(m_xd, bullets)
    xd_ok = any("collides with" in e and target_g in e for e in errs_xd)
    print(f"self-test [{'CAUGHT' if xd_ok else 'MISSED'}] a declared handle spelling "
          f"another guide's derived name fails as a collision")

    # Guide-to-guide audience. The mutation is a manifest narrowing, not an instruction edit, so it
    # cannot trip the bijection the way the orphan control first did: take a guide that some
    # OTHER guide cites and shrink its domain set to one the citing guide does not hold.
    # The cited guide must be one NO bullet points at — a depth-chain child. Pick one a bullet
    # also names and the forward leg fails on the same mutation, so the control would pass
    # without this leg being consulted.
    citers = []
    for name in manifest["guides"]:
        body = (REPO / "claude" / "guides" / name).read_text(encoding="utf-8")
        for cited in re.findall(r"guides/([a-z0-9-]+\.md)", body):
            if cited == name or cited not in manifest["guides"]:
                continue
            handles = manifest["guides"][cited].get("handles", [])
            if any(f"guides/{cited}" in b or any(h.lower() in b.lower() for h in handles)
                   for b in bullets):
                continue                       # a bullet names it too; forward leg would fire
            citers.append((name, cited))
    if not citers:
        raise SystemExit("self-test: no guide cites another that no bullet names, so the "
                         "guide->guide control cannot be isolated from the forward leg")
    c_from, c_to = citers[0]
    m_cross = copy.deepcopy(manifest)
    m_cross["guides"][c_to] = {"tier": "domain", "domains": ["office-work"]}
    muts.append((f"guide {c_from} cites {c_to} after {c_to} moves to a domain it does not hold",
                 m_cross, bullets, "router"))

    # Targeted: the settings leg must use the assembler's TOKEN rule, not a substring.
    # `.disabled` appended after the hook name is the reviewer-verified shape: substring
    # said deployed, merge_settings skipped it, the install carried no hook. Planted in a
    # copy because the leg reads the template from disk.
    import shutil as _sh, tempfile as _tf, json as _json
    with _tf.TemporaryDirectory() as _td:
        tmpl_tmp = pathlib.Path(_td)
        _sh.copytree(REPO / "claude", tmpl_tmp / "claude")
        sp = tmpl_tmp / "claude" / "settings.template.json"
        data = _json.loads(sp.read_text(encoding="utf-8"))
        for evs in data.get("hooks", {}).values():
            for en in evs:
                for h in en.get("hooks", []):
                    h["command"] = h.get("command", "") + ".disabled"
        sp.write_text(_json.dumps(data), encoding="utf-8")
        dis_errs = [e for e in check_settings_template(manifest, tmpl_tmp)
                    if e.startswith("settings:")]
    print(f"self-test [{'CAUGHT' if dis_errs else 'MISSED'}] a '.disabled'-suffixed hook "
          f"command fails the settings leg instead of passing as a substring")

    # Targeted: the settings rule itself must speak, not just some neighbouring
    # check tripping on the same mutation.
    import copy as _c
    m_off = _c.deepcopy(manifest)
    m_off["hooks"] = {"renamed-hook.py": {"tier": "core", "domains": []}}
    settings_errs = [e for e in check_settings_template(m_off) if e.startswith("settings:")]
    print(f"self-test [{'CAUGHT' if settings_errs else 'MISSED'}] settings rule fires on its own")

    # Targeted: an ambiguous derived run must resolve to nothing, and a full stem to exactly
    # its own guide. Without the restriction, "the llm-capability-boundary guide" marked the
    # base and both children consumed, so an unrelated mention of a parent could keep an
    # unreachable child out of the orphan report.
    owner_st = {}
    for n in manifest["guides"]:
        for r in prose_handles(n):
            owner_st.setdefault(r, set()).add(n)
    shared = next((r for r, o in sorted(owner_st.items())
                   if len(o) > 1 and all(r != g[:-3] for g in o)), None)
    if shared is None:
        raise SystemExit("self-test: no derived run is shared between guides, so the "
                         "ambiguity control has no subject and would pass vacuously")
    amb = refs_from(f"see the {shared} guide", manifest["guides"])
    print(f"self-test [{'CAUGHT' if not amb else 'MISSED'}] shared run {shared!r} "
          f"resolves to no guide (got {amb})")
    stem_owner = next((g for r, o in owner_st.items() if len(o) > 1
                       for g in o if r == g[:-3]), None)
    stem_ok = True
    if stem_owner is not None:
        got = refs_from(f"see the {stem_owner[:-3]} guide", manifest["guides"])
        stem_ok = got == [stem_owner]
        print(f"self-test [{'CAUGHT' if stem_ok else 'MISSED'}] full stem resolves to "
              f"{stem_owner} alone (got {got})")

    # Targeted: a withheld guide's citation of a narrower child is a gap for nobody — the
    # packaged reader never holds the citing guide, and a checkout has the whole tree. The
    # firing side of this leg is the m_cross mutation above; this is the exemption side,
    # planted in a throwaway copy because the leg reads bodies from disk.
    import shutil, tempfile
    withheld = next((n for n in manifest["guides"] if not delivered(n)), None)
    narrow = next((n for n, e in manifest["guides"].items() if e.get("tier") == "domain"), None)
    if withheld is None or narrow is None:
        raise SystemExit("self-test: no withheld guide or no domain guide, so the "
                         "author-citation exemption has no subject and would pass vacuously")
    with tempfile.TemporaryDirectory() as td:
        tmp2 = pathlib.Path(td)
        for sub in ("claude", "ko", "launch"):
            if (REPO / sub).is_dir():
                shutil.copytree(REPO / sub, tmp2 / sub)
        gf = tmp2 / "claude" / "guides" / withheld
        gf.write_text(gf.read_text(encoding="utf-8")
                      + f"\n\nSee `guides/{narrow}` for the workflow.\n", encoding="utf-8")
        errs2, _ = run_gate(manifest, bullets, repo=tmp2)
        false_hits = [e for e in errs2 if withheld in e and narrow in e]
    print(f"self-test [{'CAUGHT' if not false_hits else 'MISSED'}] withheld {withheld} citing "
          f"{narrow} is exempt from audience coverage")

    # A directory under claude/skills that carries no SKILL.md is malformed — the hosts
    # cannot load it and the manifest cannot claim it — and must be named, not skipped
    # the way a stray file under guides/ is. Planted in a throwaway copy of the tree.
    with tempfile.TemporaryDirectory() as td:
        tmp_sk = pathlib.Path(td)
        for sub in ("claude", "ko", "launch"):
            if (REPO / sub).is_dir():
                shutil.copytree(REPO / sub, tmp_sk / sub)
        (tmp_sk / "claude" / "skills" / "half-a-skill-control" / "notes").mkdir(parents=True)
        errs_sk, _ = run_gate(manifest, bullets, repo=tmp_sk)
        sk_ok = any("half-a-skill-control" in e and "no SKILL.md" in e for e in errs_sk)
    print(f"self-test [{'CAUGHT' if sk_ok else 'MISSED'}] a skills/ directory without "
          f"SKILL.md is reported as malformed")
    if not sk_ok:
        return ["a skills/ directory without SKILL.md was not reported"]

    # Launch missions: a deployed-form reference to a non-universal or withheld guide must
    # fail; the real checkout-form reference must stay clean (it is the distill mission's
    # deliberate shape, guarded by check-package instead).
    with tempfile.TemporaryDirectory() as td:
        tmp3 = pathlib.Path(td)
        for sub in ("claude", "ko", "launch"):
            if (REPO / sub).is_dir():
                shutil.copytree(REPO / sub, tmp3 / sub)
        lt = tmp3 / "launch" / "agent-launch.toml"
        lt.write_text(lt.read_text(encoding="utf-8")
                      + f'\n[presets.zz-probe]\nmission = "read '
                        f'${{CLAUDE_CONFIG_DIR:-$HOME/.claude}}/guides/{narrow} first"\n',
                      encoding="utf-8")
        errs3, _ = run_gate(manifest, bullets, repo=tmp3)
        launch_hits = [e for e in errs3 if e.startswith("launch:") and narrow in e]
        # The same plant in Codex-home form: the config drives both hosts, and the regex
        # knowing only Claude homes was review's next find.
        lt.write_text(lt.read_text(encoding="utf-8")
                      + f'\n[presets.zz-probe-cx]\nmission = "read '
                        f'${{CODEX_HOME}}/guides/{narrow} first"\n',
                      encoding="utf-8")
        errs3c, _ = run_gate(manifest, bullets, repo=tmp3)
        launch_hits_cx = [e for e in errs3c if e.startswith("launch:") and narrow in e]
    print(f"self-test [{'CAUGHT' if launch_hits else 'MISSED'}] a deployed-form mission "
          f"reference to domain-scoped {narrow} fails the launch leg")
    print(f"self-test [{'CAUGHT' if launch_hits_cx else 'MISSED'}] the CODEX_HOME form "
          f"of the same reference fails too")

    # A TOML comment naming a guide reaches no agent: planting the orphaned guide's ONLY
    # pointer as a comment must leave the orphan error standing.
    with tempfile.TemporaryDirectory() as td:
        tmp4 = pathlib.Path(td)
        for sub in ("claude", "ko", "launch"):
            if (REPO / sub).is_dir():
                shutil.copytree(REPO / sub, tmp4 / sub)
        lt4 = tmp4 / "launch" / "agent-launch.toml"
        lt4.write_text(lt4.read_text(encoding="utf-8")
                       + f'\n# a comment mentioning guides/{o_name} reaches nobody\n',
                       encoding="utf-8")
        errs4, _ = run_gate(m_orphan, [b for b in bullets if b != o_line], repo=tmp4)
        still_orphan = any(o_name in e for e in errs4)
    print(f"self-test [{'CAUGHT' if still_orphan else 'MISSED'}] a TOML comment naming "
          f"{o_name} does not resurrect it as consumed")

    # A fenced code sample in another guide is an example, not a router: with the real
    # pointer dropped, the sample alone must leave the orphan error standing.
    with tempfile.TemporaryDirectory() as td:
        tmp7 = pathlib.Path(td)
        for sub in ("claude", "ko", "launch"):
            if (REPO / sub).is_dir():
                shutil.copytree(REPO / sub, tmp7 / sub)
        host7 = next(n for n in manifest["guides"] if n != o_name)
        g7 = tmp7 / "claude" / "guides" / host7
        fenced_orphan = True
        for fence_open, fence_close, label in (
                ("```", "```", "triple backtick"),
                ("~~~", "~~~", "tilde"),
                ("````", "````", "four backtick"),
                ("```", "```python\nstill inside\n```", "info-string non-close"),
                ("<!--", "-->", "HTML comment"),
                ("<!--", "", "unclosed HTML comment"),
                ("", "", "four-space indented"),
                ("", "", "list-nested indented"),
                ("", "", "tab indented"),
                ("> ```", "> ```", "blockquoted fence"),
                ("- > ```", "  > ```", "list-blockquoted fence")):
            base7 = g7.read_text(encoding="utf-8")
            if label == "four-space indented":
                sample7 = f"\n\n    read guides/{o_name} for the flow\n"
            elif label == "list-nested indented":
                sample7 = (f"\n\n- a list item\n\n"
                           f"        read guides/{o_name} for the flow\n")
            elif label == "tab indented":
                sample7 = f"\n\n\tread guides/{o_name} for the flow\n"
            elif label == "blockquoted fence":
                sample7 = (f"\n\n> ```\n> read guides/{o_name} for the flow\n> ```\n")
            elif label == "list-blockquoted fence":
                sample7 = (f"\n\n- > ```\n  > read guides/{o_name} for the "
                           f"flow\n  > ```\n")
            else:
                sample7 = (f"\n\n{fence_open}\nread guides/{o_name} for the "
                           f"flow\n{fence_close}\n")
            g7.write_text(base7 + sample7, encoding="utf-8")
            errs7, _ = run_gate(m_orphan, [b for b in bullets if b != o_line], repo=tmp7)
            ok7 = any(o_name in e for e in errs7)
            fenced_orphan = fenced_orphan and ok7
            print(f"self-test [{'CAUGHT' if ok7 else 'MISSED'}] a {label} fenced sample "
                  f"naming {o_name} does not resurrect it as consumed")
            g7.write_text(base7, encoding="utf-8")

        # Two unrooted guides citing each other must BOTH stay orphans: reciprocal
        # references are edges, not roots.
        m_isl = copy.deepcopy(manifest)
        m_isl["bullets"] = [e for e in m_isl["bullets"]
                            if e["anchor"] not in o_line and e["anchor"] not in i_line]
        b_isl = [b for b in bullets if b not in (o_line, i_line)]
        ga = tmp7 / "claude" / "guides" / o_name
        gb = tmp7 / "claude" / "guides" / i_name
        base_a, base_b = ga.read_text(encoding="utf-8"), gb.read_text(encoding="utf-8")
        ga.write_text(base_a + f"\n\nSee `guides/{i_name}` too.\n", encoding="utf-8")
        gb.write_text(base_b + f"\n\nSee `guides/{o_name}` too.\n", encoding="utf-8")
        errs_isl, _ = run_gate(m_isl, b_isl, repo=tmp7)
        island_ok = (any(o_name in e and "orphan" in e for e in errs_isl)
                     and any(i_name in e and "orphan" in e for e in errs_isl))
        print(f"self-test [{'CAUGHT' if island_ok else 'MISSED'}] a reciprocal island "
              f"({o_name} <-> {i_name}) is still orphaned — edges are not roots")
        ga.write_text(base_a, encoding="utf-8")
        gb.write_text(base_b, encoding="utf-8")

        # The other direction: a REAL router placed after a fence whose sample contains
        # a literal <!-- must still count — comments-before-fences deleted it through
        # EOF and reported a false orphan.
        g7.write_text(base7 + f"\n\n```\n<!-- a literal in an example\n```\n\n"
                      f"See `guides/{o_name}` for the flow.\n", encoding="utf-8")
        errs7b, _ = run_gate(m_orphan, [b for b in bullets if b != o_line], repo=tmp7)
        post_fence_ok = not any(o_name in e for e in errs7b)
        print(f"self-test [{'CAUGHT' if post_fence_ok else 'MISSED'}] a real router after "
              f"a fence containing a literal <!-- still counts as a consumer")

        # And blockquoted prose riding a list marker still RENDERS: stripping the
        # combined container must not delete a real router written as `- > see ...`.
        g7.write_text(base7 + f"\n\n- > See `guides/{o_name}` for the flow.\n",
                      encoding="utf-8")
        errs7c, _ = run_gate(m_orphan, [b for b in bullets if b != o_line], repo=tmp7)
        listquote_prose_ok = not any(o_name in e for e in errs7c)
        print(f"self-test [{'CAUGHT' if listquote_prose_ok else 'MISSED'}] a real router "
              f"in list-blockquoted prose still counts as a consumer")
        g7.write_text(base7, encoding="utf-8")

    # A guides/ reference in a non-instruction field must fail loudly, not quietly count.
    with tempfile.TemporaryDirectory() as td:
        tmp5 = pathlib.Path(td)
        for sub in ("claude", "ko", "launch"):
            if (REPO / sub).is_dir():
                shutil.copytree(REPO / sub, tmp5 / sub)
        lt5 = tmp5 / "launch" / "agent-launch.toml"
        lt5.write_text(lt5.read_text(encoding="utf-8")
                       + f'\nzz_inert = "see guides/{narrow} for details"\n',
                       encoding="utf-8")
        # And the reviewer's sharper shape: a `mission` key OUTSIDE presets is equally
        # inert — the leaf name does not make it instruction-bearing.
        lt5.write_text(lt5.read_text(encoding="utf-8")
                       + f'\n[capabilities.zz-cap]\nmission = "read guides/{narrow}"\n',
                       encoding="utf-8")
        # And the PROSE form of that shape: an inert field needs no guides/ path to
        # send the reader somewhere — the spoken name is the same masquerade.
        spoken5 = narrow[:-3].replace("-", " ")
        lt5.write_text(lt5.read_text(encoding="utf-8")
                       + f'\n[capabilities.zz-cap2]\nmission = "Read the {spoken5} guide '
                       f'first."\n',
                       encoding="utf-8")
        errs5, _ = run_gate(manifest, bullets, repo=tmp5)
        inert_hits = [e for e in errs5 if "not instruction-bearing" in e]
        cap_hits = [e for e in errs5 if "capabilities.zz-cap.mission" in e]
        cap2_hits = [e for e in errs5 if "capabilities.zz-cap2.mission" in e]
    print(f"self-test [{'CAUGHT' if inert_hits else 'MISSED'}] a guide named in a "
          f"non-instruction TOML field fails loudly")
    print(f"self-test [{'CAUGHT' if cap_hits else 'MISSED'}] a mission key outside "
          f"presets is inert and fails loudly too")
    print(f"self-test [{'CAUGHT' if cap2_hits else 'MISSED'}] a PROSE reference in an "
          f"inert field fails loudly without a path form")

    # PROSE form of the same promise: "Read the <spoken> guide" in a mission must fail
    # for a domain guide exactly as the deployed path does — form must not be a bypass.
    with tempfile.TemporaryDirectory() as td:
        tmp6 = pathlib.Path(td)
        for sub in ("claude", "ko", "launch"):
            if (REPO / sub).is_dir():
                shutil.copytree(REPO / sub, tmp6 / sub)
        lt6 = tmp6 / "launch" / "agent-launch.toml"
        spoken6 = narrow[:-3].replace("-", " ")
        lt6.write_text(lt6.read_text(encoding="utf-8")
                       + f'\n[presets.zz-prose]\nmission = "Read the {spoken6} guide first."\n',
                       encoding="utf-8")
        errs6, _ = run_gate(manifest, bullets, repo=tmp6)
        prose_hits = [e for e in errs6 if e.startswith("launch:") and narrow in e]
    print(f"self-test [{'CAUGHT' if prose_hits else 'MISSED'}] a PROSE mission reference "
          f"to domain-scoped {narrow} fails without needing a path form")

    # One preset's guarded checkout reference must not launder another preset's prose
    # reference to the same guide.
    with tempfile.TemporaryDirectory() as td:
        tmp8 = pathlib.Path(td)
        for sub in ("claude", "ko", "launch"):
            if (REPO / sub).is_dir():
                shutil.copytree(REPO / sub, tmp8 / sub)
        lt8 = tmp8 / "launch" / "agent-launch.toml"
        spoken8b = narrow[:-3].replace("-", " ")
        lt8.write_text(lt8.read_text(encoding="utf-8")
                       + f'\n[presets.zz-ck]\nmission = "read claude/guides/{narrow} in '
                         f'the agent-bios checkout"\n'
                         f'[presets.zz-pr]\nmission = "Read the {spoken8b} guide first."\n',
                       encoding="utf-8")
        errs8, _ = run_gate(manifest, bullets, repo=tmp8)
        mixed_hits = [e for e in errs8 if e.startswith("launch:") and narrow in e]
    print(f"self-test [{'CAUGHT' if mixed_hits else 'MISSED'}] a checkout reference in one "
          f"preset does not exempt a prose reference in another")

    # Both forms in ONE mission: the checkout path must not exempt the prose pointer
    # standing beside it.
    with tempfile.TemporaryDirectory() as td:
        tmp9 = pathlib.Path(td)
        for sub in ("claude", "ko", "launch"):
            if (REPO / sub).is_dir():
                shutil.copytree(REPO / sub, tmp9 / sub)
        lt9 = tmp9 / "launch" / "agent-launch.toml"
        spoken9 = narrow[:-3].replace("-", " ")
        lt9.write_text(lt9.read_text(encoding="utf-8")
                       + f'\n[presets.zz-both]\nmission = "read claude/guides/{narrow} in '
                         f'the agent-bios checkout, or just read the {spoken9} guide."\n',
                       encoding="utf-8")
        errs9, _ = run_gate(manifest, bullets, repo=tmp9)
        same_hits = [e for e in errs9 if e.startswith("launch:") and narrow in e]
    print(f"self-test [{'CAUGHT' if same_hits else 'MISSED'}] a checkout path does not "
          f"exempt a prose pointer in the SAME mission")

    # Targeted: the consumer legs resolve handles, not only paths. All three call refs_from,
    # so proving the resolver sees a handle-only mention proves the legs do. Without it a child
    # cited only in prose reads as inert while rule 4 validates that same reference.
    handled = next((n for n, e in manifest["guides"].items() if e.get("handles")), None)
    if handled is None:
        raise SystemExit("self-test: no guide declares handles, so the handle-resolution "
                         "assertion has no subject and would pass vacuously")
    probe = f"see the {manifest['guides'][handled]['handles'][0]} for the rest"
    handle_ok = handled in refs_from(probe, manifest["guides"])
    # A handle must match as a complete phrase: "multi-model guidelines" contains the
    # handle "multi-model guide" and is ordinary prose, not a router.
    hprefix = f"note the {manifest['guides'][handled]['handles'][0]}lines here"
    handle_bounded = handled not in refs_from(hprefix, manifest["guides"])
    print(f"self-test [{'CAUGHT' if handle_bounded else 'MISSED'}] a handle embedded in a "
          f"longer word does not resolve")
    dehy = next((n for n in manifest["guides"] if "-" in n[:-3]
                 and prose_handles(n) and n[:-3] in
                 [r for r in prose_handles(n)]), None)
    dehy_ok = True
    if dehy is not None:
        spoken = dehy[:-3].replace("-", " ")
        dehy_ok = (dehy in refs_from(f"read the {spoken} guide", manifest["guides"])
                   and dehy in refs_from(f"read the {spoken} document", manifest["guides"]))
        print(f"self-test [{'CAUGHT' if dehy_ok else 'MISSED'}] a dehyphenated reference "
              f"('the {spoken} guide') resolves to {dehy}")
    print(f"self-test [{'CAUGHT' if handle_ok else 'MISSED'}] a handle-only reference "
          f"resolves to {handled}")

    failed = [] if settings_errs else ["settings rule fires on its own"]
    if amb:
        failed.append("shared run resolves to no guide")
    if not stem_ok:
        failed.append("full stem resolves uniquely")
    if false_hits:
        failed.append("withheld-guide citation exempt from coverage")
    if not dehy_ok:
        failed.append("dehyphenated reference resolves")
    if not dis_errs:
        failed.append("disabled-suffixed hook command fails the settings leg")
    if not launch_hits:
        failed.append("deployed-form launch reference to a domain guide fails")
    if not launch_hits_cx:
        failed.append("CODEX_HOME-form launch reference fails")
    if not still_orphan:
        failed.append("comment mention does not count as a consumer")
    if not fenced_orphan:
        failed.append("fenced sample does not count as a consumer")
    if not post_fence_ok:
        failed.append("real router after a <!--bearing fence still counts")
    if not listquote_prose_ok:
        failed.append("real router in list-blockquoted prose still counts")
    if not never_ok:
        failed.append("never-delivered bullet does not root a guide")
    if not orphan_companion_ok:
        failed.append("orphan companion tree is rejected")
    if not symlink_ok:
        failed.append("companion-tree symlink is rejected")
    if not companion_router_ok:
        failed.append("Markdown companion prose is scanned as a router")
    if not companion_author_ok:
        failed.append("author-only companion cannot ride a delivered primary")
    if not island_ok:
        failed.append("reciprocal island stays orphaned")
    if not inert_hits:
        failed.append("non-instruction field naming a guide fails loudly")
    if not cap_hits:
        failed.append("mission outside presets is inert")
    if not cap2_hits:
        failed.append("prose reference in an inert field fails loudly")
    if not dup_ok:
        failed.append("duplicate declared handle fails as a duplicate declaration")
    if not xd_ok:
        failed.append("declared handle colliding with a derived name fails")
    if not case_ok:
        failed.append("case-variant duplicate handle fails as the same name")
    if not prose_hits:
        failed.append("prose mission reference validated like a path")
    if not mixed_hits:
        failed.append("checkout occurrence does not launder a prose occurrence")
    if not same_hits:
        failed.append("checkout path does not exempt prose in the same mission")
    if not handle_ok:
        failed.append("handle-only reference resolves")
    if not handle_bounded:
        failed.append("handle embedded in a longer word must not resolve")
    # A clean baseline first. Every row below reads "this mutation makes the gate complain",
    # and that sentence is only true if the unmutated manifest does NOT — otherwise each row
    # is reporting a pre-existing error as its own catch.
    baseline, _ = run_gate(manifest, bullets)
    if baseline:
        failed.append("baseline: the unmutated manifest already fails, so every mutation "
                      f"below is judged against noise ({baseline[:1]})")
        print(f"self-test [MISSED] baseline is clean before mutating ({len(baseline)} errors)")

    for name, mm, bb, expect in muts:
        errs, _ = run_gate(mm, bb)
        # The mutation's OWN diagnostic, not merely some error. Asking only whether the list
        # is non-empty let an unrelated complaint stand in for the one the row exists to
        # provoke — suppress the bijection checks entirely and this loop still reported
        # CAUGHT, because a malformed package id elsewhere in the same manifest kept the
        # list non-empty. A negative control that any failure satisfies tests nothing.
        hit = any(expect in e for e in errs)
        if not hit:
            failed.append(f"{name} (wanted a diagnostic naming {expect!r}, got {errs[:2]})")
        print(f"self-test [{'CAUGHT' if hit else 'MISSED'}] {name}")
    return failed


def main():
    manifest = load_manifest()
    bullets = instructions_bullets()
    extra = [a for a in sys.argv[1:] if a != "--self-test"]
    if extra:
        sys.exit(f"check-domains: refusing unknown argument(s) {extra!r}. This gate "
                 f"validates the core manifest only; a package manifest path would be "
                 f"silently ignored, reporting a check that never ran. Parameterizing "
                 f"it is contract v2 §3.")
    if "--self-test" in sys.argv:
        missed = self_test(manifest, bullets)
        if missed:
            print(f"SELF-TEST FAIL: gate missed: {missed}")
            return 1
        print("SELF-TEST OK: every negative control was caught")
        return 0
    errors, sizes = run_gate(manifest, bullets)
    for e in errors:
        print(f"FAIL: {e}")
    print("-- package token estimate (informational) --")
    for k in sorted(sizes):
        print(f"  {k}: ~{sizes[k]} tokens")
    if errors:
        print(f"DOMAINS GATE FAIL: {len(errors)} violation(s)")
        return 1
    print(f"DOMAINS GATE OK: {len(bullets)} bullets bijective, all files claimed, routers co-packaged and delivered, no orphan guides")
    return 0


if __name__ == "__main__":
    sys.exit(main())
