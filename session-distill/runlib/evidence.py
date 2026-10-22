#!/usr/bin/env python3
"""The evidence store (design §5.5): a quote that can be walked back to bytes nobody has touched.

An evidence record's fields are declared in `schemas/evidence.schema.json` and checked against design §5.5 by
`claims.py`, which is the one place that list is written down; restating it here would make this a second
authority for it. What the fields MEAN: the locator is the immutable copy S2 made, a 1-based line in it and the
content block of that record; the span is over the block's **redacted projection** (`projection.project` of the
block's value), never over the raw bytes, and the stored text is that span. Nothing here lets a model type a locator or a quote: `make` takes the span
and reads the text from the projection, `from_view` finds a quote in what a window showed and maps it to the block's
characters through the entry's segments, and a quote that is not exactly there (a character changed, or the raw
bytes where the projection holds a mask) is `QUOTE_MISMATCH`.

`verify` re-derives everything from the immutable copy and does not trust the projection file or the record:

  1. the record conforms to its schema (EVIDENCE_INVALID);
  2. the copy exists and hashes to `version_sha` (SOURCE_MISSING, SOURCE_TAMPERED);
  3. `redaction_version` is the current one (REDACTION_VERSION_MISMATCH) - an old quote is made again from the
     same source, it is not patched;
  4. the line and pointer resolve to a content block (LOCATOR_UNRESOLVED);
  5. `redacted_text` equals the span of the block's projection (QUOTE_MISMATCH).

The review shows the quote with `openable`: the copy's path and the line. A hash of a copy is remembered for the
process by the file's size, mtime and inode, so a copy that is edited in place is hashed again.

  evidence.py --self-test
"""
import hashlib
import json
import os
import pathlib
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import claims, projection, records, stagelock
from runlib.records import Refused

_HASHES = {}


def copy_sha(path):
    stat = os.stat(path)
    key = (str(path), stat.st_mtime_ns, stat.st_size, stat.st_ino)
    if key not in _HASHES:
        _HASHES[key] = records.sha256_file(path)
    return _HASHES[key]


def resolve_pointer(value, pointer):
    for token in pointer.split("/")[1:]:
        token = token.replace("~1", "/").replace("~0", "~")
        try:
            value = value[int(token)] if isinstance(value, list) else value[token]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise KeyError(pointer) from exc
    return value


ABSENT = object()   # distinct from a block whose value is JSON null


def read_block(copy_path, line, pointer):
    """The value of the content block at `line` and `pointer` of a copy, or `ABSENT` when it is not there.
    The value, not its characters: the projection walks a structure before serialising it, so handing it text
    is what let a serialised secret through. A last line without its newline is a record the host was still
    writing, not a record."""
    with open(copy_path, "rb") as handle:
        for number, raw in enumerate(handle, 1):
            if number == line:
                if not raw.endswith(b"\n"):
                    return ABSENT
                try:
                    return resolve_pointer(json.loads(raw), pointer)
                except (ValueError, KeyError):
                    return ABSENT
    return ABSENT


def projection_of(copy_path, line, pointer, version):
    block = read_block(copy_path, line, pointer)
    return None if block is ABSENT else projection.project(block, version)


def evidence_id(version_sha, line, pointer, span, version):
    return "e-" + hashlib.sha256(f"{version_sha}|{line}|{pointer}|{span[0]}-{span[1]}|{version}".encode()).hexdigest()[:16]


def copy_rel(version_sha):
    """The one locator an evidence record may carry for its source. A record names the copy the owner opens;
    verification hashes the copy the version names. When the two are allowed to differ, the bytes that were
    checked and the file the owner is sent to are not the same file, and the record still verifies."""
    return f"sources/{version_sha}.jsonl"


def copy_problem(run_dir, version_sha):
    """`(path, None)` for an intact copy, else `(path, the named problem)`."""
    path = pathlib.Path(run_dir) / copy_rel(version_sha)
    if not path.is_file():
        return path, f"SOURCE_MISSING {path}: the immutable copy of version {version_sha[:12]} is not in the run"
    if copy_sha(path) != version_sha:
        return path, f"SOURCE_TAMPERED {path}: the copy hashes {copy_sha(path)[:12]}, the evidence names {version_sha[:12]}"
    return path, None


def make(run_dir, version_sha, line, pointer, span, window_role, version=projection.CURRENT):
    """The evidence record for `span` of one content block; the quote is read from the projection, never supplied."""
    path, problem = copy_problem(run_dir, version_sha)
    if problem:
        raise Refused(problem)
    text = projection_of(path, line, pointer, version)
    if text is None:
        raise Refused(f"LOCATOR_UNRESOLVED line {line} {pointer}: no content block there in {path.name}")
    a, b = span
    if not 0 <= a < b <= len(text):
        raise Refused(f"LOCATOR_UNRESOLVED line {line} {pointer}: span {a}-{b} is not within the block's {len(text)} characters")
    # The STRICT rule, and it is the owner's: a quote is persisted and shared, so the context that makes a
    # secret-named key with a masked value safe to READ in a window does not travel with it. A quote that
    # names a secret in any spelling cannot be stored at all - not masked, not partly accepted. Owner
    # decision of 2026-10-21; `design/session-distill/2026-10-21T2223--1bfd4c7--strict-rule-uses-the-floors-own-matching.md`.
    admissible, why = projection.evidence_quote_admissible(text[a:b])
    if not admissible:
        raise Refused(f"EVIDENCE_QUOTE_SENSITIVE line {line} {pointer}: {why}; a quote that names a secret "
                      "cannot be stored, so quote a span that does not")
    record = {"evidence_id": evidence_id(version_sha, line, pointer, span, version), "source_copy": copy_rel(version_sha),
              "version_sha": version_sha, "line": line, "json_pointer": pointer, "char_span": [a, b],
              "redaction_version": version, "redacted_text": text[a:b], "window_role": window_role}
    problems = claims.validate_record("evidence", record)
    if problems:
        raise Refused("EVIDENCE_INVALID " + "; ".join(problems))
    return record


def quote_spans(text, quote):
    """Every span of `text` that is exactly `quote`."""
    spans, start = [], text.find(quote) if quote else -1
    while start >= 0:
        spans.append([start, start + len(quote)])
        start = text.find(quote, start + 1)
    return spans


def from_quote(run_dir, version_sha, line, pointer, quote, window_role, version=projection.CURRENT, occurrence=None):
    """The evidence record for `quote` in a block's projection: unique, or named by `occurrence`."""
    path, problem = copy_problem(run_dir, version_sha)
    if problem:
        raise Refused(problem)
    text = projection_of(path, line, pointer, version)
    spans = quote_spans(text or "", quote)
    if not spans:
        raise Refused(f"QUOTE_MISMATCH line {line} {pointer}: the quote is not in the block's projection at {version}")
    if len(spans) > 1 and occurrence is None:
        raise Refused(f"QUOTE_AMBIGUOUS line {line} {pointer}: the quote occurs {len(spans)} times; name the occurrence")
    return make(run_dir, version_sha, line, pointer, spans[0 if occurrence is None else occurrence], window_role, version)


def view_spans(entry, quote):
    """Where `quote` sits in the block, for each place the entry's view text shows it inside one shown stretch."""
    found = []
    for seg in entry["segments"]:
        piece = entry["text"][seg["view"][0]:seg["view"][1]]
        for a, b in quote_spans(piece, quote):
            found.append([seg["block"][0] + a, seg["block"][0] + b])
    return found


def from_view(run_dir, version_sha, entry, quote, version=projection.CURRENT, occurrence=None):
    """The evidence record for a quote read out of a window's entry: the span is found in what the window showed and
    mapped to the block's characters, then `make` reads the text from the projection."""
    spans = view_spans(entry, quote)
    if not spans:
        raise Refused(f"QUOTE_MISMATCH {entry['record_id']}: the quote is not in any stretch the window showed")
    if len(spans) > 1 and occurrence is None:
        raise Refused(f"QUOTE_AMBIGUOUS {entry['record_id']}: the quote occurs {len(spans)} times; name the occurrence")
    return make(run_dir, version_sha, entry["line"], entry["json_pointer"], spans[0 if occurrence is None else occurrence],
                entry["window_role"], version)


def verify(run_dir, record, current=projection.CURRENT):
    """Violations of one evidence record against the immutable copy; empty when the quote walks back to untouched bytes."""
    problems = claims.validate_record("evidence", record)
    if problems:
        return ["EVIDENCE_INVALID " + "; ".join(problems)]
    if record["source_copy"] != copy_rel(record["version_sha"]):
        return [f"SOURCE_LOCATOR_MISMATCH {record['evidence_id']}: the record points at {record['source_copy']}, but the "
                f"version it names is copied at {copy_rel(record['version_sha'])}; the bytes verified and the file the "
                f"owner opens must be one file"]
    path, problem = copy_problem(run_dir, record["version_sha"])
    if problem:
        return [problem]
    if record["redaction_version"] != current:
        return [f"REDACTION_VERSION_MISMATCH {record['evidence_id']}: made under {record['redaction_version']}, the projection is "
                f"{current}; make it again from {record['source_copy']}"]
    text = projection_of(path, record["line"], record["json_pointer"], current)
    if text is None:
        return [f"LOCATOR_UNRESOLVED {record['evidence_id']}: line {record['line']} {record['json_pointer']} is not a content block of the copy"]
    a, b = record["char_span"]
    if not 0 <= a < b <= len(text) or text[a:b] != record["redacted_text"]:
        return [f"QUOTE_MISMATCH {record['evidence_id']}: the quote is not the span {a}-{b} of the block's projection"]
    return []


def openable(run_dir, record):
    """The path and line the owner opens to see the quote's source."""
    return f"{pathlib.Path(run_dir) / record['source_copy']}:{record['line']}"


def append(run_dir, name, record):
    """Store a verified record under `evidence/<name>.jsonl`; storing the same record again changes nothing.

    The admission rule is asked again here, not only where the record was made: a record can arrive from
    anywhere - another tool, an older file, a hand-written line - and this is the boundary where text
    becomes persisted and shareable."""
    admissible, why = projection.evidence_quote_admissible(record.get("redacted_text", ""))
    if not admissible:
        raise Refused(f"EVIDENCE_QUOTE_SENSITIVE {record.get('evidence_id')}: {why}; a quote that names a "
                      "secret cannot be stored")
    problems = verify(run_dir, record)
    if problems:
        raise Refused("\n".join(problems))
    path = stagelock.confine(run_dir, pathlib.Path(run_dir) / "evidence" / f"{name}.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    if record["evidence_id"] in {r["evidence_id"] for r in load(run_dir, name)}:
        return False
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return True


def load(run_dir, name, current=None):
    """The stored records of one file. `current` is the projection they must have been made under, and
    `False` reads them without the check - which only a tool migrating a store may ask for.

    The check belongs in the READER, not only in `verify`: a caller that lists or resolves a record and
    hands its `redacted_text` on has published a quote made under a projection that masked less, and
    nothing in the path it took would have said so."""
    path = pathlib.Path(run_dir) / "evidence" / f"{name}.jsonl"
    if not path.is_file():
        return []
    records_read = [json.loads(line) for line in records.jsonl_lines(path.read_text(encoding="utf-8")) if line.strip()]
    if current is False:
        return records_read
    want = projection.CURRENT if current is None else current
    stale = [r["evidence_id"] for r in records_read if r.get("redaction_version") != want]
    if stale:
        raise Refused(f"REDACTION_VERSION_MISMATCH {path}: {len(stale)} record(s) were made under another "
                      f"projection ({stale[:3]}); the projection is {want} - make the quotes again from the source")
    return records_read


def resolve(run_dir, evidence_id, current=None):
    """The stored record with this id, or None. Refused by name when the store holds a record of another
    projection, for the same reason `load` is."""
    for path in sorted((pathlib.Path(run_dir) / "evidence").glob("*.jsonl")):
        for record in load(run_dir, path.stem, current):
            if record["evidence_id"] == evidence_id:
                return record
    return None


def self_test():
    import tempfile
    from runlib import views

    failures = []
    with tempfile.TemporaryDirectory() as td:
        golden = views.golden(pathlib.Path(td), "ev")
        run_dir, manifest = golden["run_dir"], golden["manifest"]
        main = golden["main"]
        sha = main["version_sha"]
        copy = pathlib.Path(run_dir) / main["source_copy"]
        entries = {r["record_id"]: r for w in golden["windows"] for r in w["records"]}
        human = entries[f"{golden['lines']['human']}/message/content"]
        quote = "show me the plain version"

        # a stored record ends at "\n" only; the writer keeps U+2028 and U+2029 raw (ensure_ascii=False)
        held = {"evidence_id": "f21", "redacted_text": "before\u2028between\u2029after"}
        (pathlib.Path(run_dir) / "evidence").mkdir(exist_ok=True)
        (pathlib.Path(run_dir) / "evidence" / "f21.jsonl").write_text(json.dumps(held, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            got = load(run_dir, "f21", current=False)
        except ValueError as exc:
            got = str(exc)
        finally:
            (pathlib.Path(run_dir) / "evidence" / "f21.jsonl").unlink()  # the store the controls below read is the golden run's
        if got != [held]:
            failures.append(f"jsonl-line-separators-inside-a-string-read-whole (load): {got!r}")

        # positive controls: a quote read out of a window verifies, stores, resolves, and opens at its source
        record = from_view(run_dir, sha, human, quote)
        if verify(run_dir, record):
            failures.append(f"positive control: a quote read out of a window did not verify: {verify(run_dir, record)}")
        if record["redacted_text"] != quote or record["window_role"] != "in_window" or record["source_copy"] != copy_rel(sha):
            failures.append(f"positive control: the record is not the quote at its source: {record}")
        if not append(run_dir, "t1", record) or append(run_dir, "t1", record) or resolve(run_dir, record["evidence_id"]) != record:
            failures.append("a record was not stored once and resolved by its id")
        if openable(run_dir, record) != f"{run_dir}/sources/{sha}.jsonl:{golden['lines']['human']}":
            failures.append(f"the openable locator is {openable(run_dir, record)}")


        # ---- Y#0 and Y#1: the strict rule through the REAL paths, from source fixtures ----------------
        #
        # Not the predicate loop: these names stand in a transcript, are projected, and the projected quote
        # still carries them - which is the only way to show that `make` refuses and that an independently
        # built record is refused at `append`, into a new file and into a populated one, with every stored
        # byte unchanged.
        def surrogate_pair_escape(text):
            """`text` with every non-BMP character written as the two escapes a serialiser writes."""
            out = []
            for character in text:
                code = ord(character)
                if code > 0xFFFF:
                    high = ((code - 0x10000) >> 10) + 0xD800
                    low = ((code - 0x10000) & 0x3FF) + 0xDC00
                    out.append(f"\\\\u{high:04x}\\\\u{low:04x}")
                else:
                    out.append(character)
            return "".join(out)

        def wide_text(text):
            """`text` with each ASCII lowercase letter as its fullwidth form, which NFKC folds back."""
            return "".join(chr(ord(character) - 0x61 + 0xFF41) if "a" <= character <= "z" else character
                           for character in text)

        maths_name = "".join(chr(0x1D5BA + (ord(c) - ord("a"))) for c in "password")
        turkish_name = "AP" + chr(0x0130) + "_KEY"       # AA#1: the CHARACTER, not its escape
        korean_words = chr(0xC554) + chr(0xD638) + " " + chr(0xD544) + chr(0xB4DC)
        backslash = chr(0x5C)
        # Each row declares the spelling its source text actually has, asserted below before any boundary
        # is asked: a row written as `"AP\\u0130_KEY"` in this file holds the ESCAPE, and reading it as the
        # character is how Y#1's plain case went missing twice.
        #     (label, source text, spelling, outcome)
        # spelling: "plain" - no backslash in the source text; "escaped" - at least one
        # outcome:   False - the projected quote is refused; True - admitted;
        #            "blanked" - the projection blanks the block, and the raw text is refused as undecodable
        strict_rows = [
            ("a compatibility name in mathematical letters", maths_name, "plain", False),
            ("... written as surrogate pair escapes", surrogate_pair_escape(maths_name), "escaped", False),
            ("a secret-named token with U+0130", turkish_name, "plain", False),
            ("... written as an escape", "AP" + backslash + "u0130_KEY", "escaped", False),
            # a lone surrogate is an encoding the verifier cannot finish, so the PROJECTION already blanks
            # the block: there is no sensitive quote left to refuse, which is the stronger outcome. The
            # predicate is still asked about the raw text below.
            ("a lone high surrogate escape", "a field " + backslash + "ud83d here", "escaped", "blanked"),
            ("a lone low surrogate escape", "a field " + backslash + "ude00 here", "escaped", "blanked"),
            # AA#0: a backslash sequence the JSON escape table does not define. The lenient reading drops
            # the backslash and reads `x41`, which is why the strict traversal tracks this itself. Only the
            # short `\u` run is blanked in the view: the view side is best-effort by the owner's split, and
            # these rows are about the STRICT boundary refusing what the view still carries.
            ("an \\x escape", "a " + backslash + "x41 field", "escaped", False),
            ("a \\q escape", "a " + backslash + "q field", "escaped", False),
            ("a short \\u escape", "a " + backslash + "u12 field", "escaped", "blanked"),
            ("a \\U escape", "a " + backslash + "U0001D5C9 field", "escaped", False),
            ("a trailing lone backslash", "a field ends here " + backslash, "escaped", False),
            # AB#0: an invisible character inside a secret name. Each renders nothing of its own or only
            # modifies its neighbour, so `pass<it>word` reads as `password` to a person and tokenised as
            # two ordinary names before the skeleton dropped them. One row per category, plain and
            # JSON-escaped.
            ("an Mc mark inside the name", "the pass" + chr(0x093E) + "word field", "plain", False),
            ("an Me mark inside the name", "the pass" + chr(0x0488) + "word field", "plain", False),
            ("a zero-width space inside the name", "the pass" + chr(0x200B) + "word field", "plain", False),
            ("a zero-width joiner inside the name", "the pass" + chr(0x200D) + "word field", "plain", False),
            ("a soft hyphen inside the name", "the pass" + chr(0x00AD) + "word field", "plain", False),
            ("a variation selector inside the name",
             "the pass" + chr(0xFE0F) + "word field", "plain", False),
            ("a tag character inside the name", "the pass" + chr(0xE0041) + "word field", "plain", False),
            ("... the zero-width space, JSON-escaped",
             "the pass" + backslash + "u200bword field", "escaped", False),
            ("... the soft hyphen, JSON-escaped",
             "the pass" + backslash + "u00adword field", "escaped", False),
            ("... the variation selector, JSON-escaped",
             "the pass" + backslash + "ufe0fword field", "escaped", False),
            # AC#0: a Unicode variant of an OWNER PATH and of a FLOOR VALUE. These are the two detectors
            # that saw only the decoded spelling while the name detector normalised; each goes through
            # the real writers here, not the predicate. Two of the path rows are masked in the view
            # already - the projection's own home rule reaches them - so those assert the masking and
            # the raw refusal, and the three the view still carries assert the boundary refusing them.
            ("an owner path with a fullwidth letter",
             "the file /U" + wide_text("sers") + "/fixtureowner/Documents/notes.md was read",
             "plain", False),
            ("an owner path with a zero-width space",
             "the file /Users/fixture" + chr(0x200B) + "owner/Documents/notes.md was read",
             "plain", "masked"),
            ("an owner path with a combining mark",
             "the file /Users/fixtureowne" + chr(0x0301) + "r/Documents/notes.md was read",
             "plain", "masked"),
            ("a floor value in fullwidth",
             "the key sk-" + wide_text("abcdefghijklmnopqrst") + " was used", "plain", False),
            ("a floor value with a zero-width space",
             "the key sk-abcdefghij" + chr(0x200B) + "klmnopqrst was used", "plain", False),
            # AD#0 / AD#1: one row per ORDER the pipeline could not reach. The invisible character sits
            # inside a CASE-SENSITIVE owner path and credential, which the casefolded skeleton could
            # never have matched; the escapes are revealed by NFKC and by casefolding, after the decoding
            # step had already run.
            ("an invisible character inside a case-sensitive owner path",
             "the file /Us" + chr(0x200B) + "ers/fixtureowner/Documents/notes.md was read",
             "plain", False),
            ("an invisible character inside a case-sensitive credential",
             "the key sk-abcdefghij" + chr(0x200B) + "klmnopqrst was used", "plain", False),
            # AE#0: a credential whose REQUIRED PREFIX is case-sensitive. The `sk-` row above is matched
            # by the casefolded skeleton too, so it passes with or without case preservation and tests
            # nothing about the order. `AKIA[0-9A-Z]{12,}` does not survive casefolding, so only a
            # spelling that is invisible-stripped AND case-preserved reaches the floor with it. The
            # property is asserted directly below, before the boundary is asked.
            ("an invisible character inside a case-SENSITIVE credential",
             "the key AKI" + chr(0x200B) + "A0123456789ABCDEF was used", "plain", False),
            ("an escape revealed by NFKC",
             "the " + chr(0xFF3C) + "u0070assword field was empty", "plain", False),
            ("an escape revealed by casefolding",
             "the A " + backslash + "U0070ASSWORD FIELD was empty", "escaped", False),
            ("an ordinary escaped e-acute", "the caf" + backslash + "u00e9 menu was read", "escaped", True),
            # ... and the admitted side for the same two detectors
            ("an ordinary non-owner path with Unicode letters",
             "the file /opt/caf" + chr(0xE9) + "/bin/tool was run", "plain", True),
            # ... and the invisible characters where they name nothing
            ("an emoji with a zero-width joiner sequence",
             "a family " + chr(0x1F468) + chr(0x200D) + chr(0x1F469) + chr(0x200D) + chr(0x1F467)
             + " stands here", "plain", True),
            ("a variation selector in a non-secret word",
             "the caf" + chr(0xE9) + chr(0xFE0F) + " menu", "plain", True),
            # ... and the admitted controls: the table's own escapes, and characters that need none
            ("an ordinary non-ASCII word", korean_words, "plain", True),
            ("... written as escapes",
             backslash + "uc554" + backslash + "ud638 " + backslash + "ud544" + backslash + "ub4dc",
             "escaped", True),
            ("only table escapes, and characters needing none",
             "a " + backslash + "n b " + backslash + '" c ' + chr(0xE9) + " " + chr(0x1F600),
             "escaped", True),
        ]

        def fx_strict_rows():
            records = [views.fx_human(views.fx_stamp(1), "a block a reader may see")]
            for index, (_label, text, _spelling, _state) in enumerate(strict_rows, start=2):
                records.append(views.fx_assistant(views.fx_stamp(index), f"the {text} field was empty"))
            return records

        strict_run = views.golden(pathlib.Path(td), "strict-rows", main_records=fx_strict_rows,
                                  owned=[[0, len(strict_rows) + 2]])
        strict_dir, strict_main = strict_run["run_dir"], strict_run["main"]
        strict_texts = views.projection_texts(strict_dir, strict_main["redacted"])
        # a clean record of this run is stored first, so there is a populated file to protect
        clean_strict = make(strict_dir, strict_main["version_sha"], 1, "/message/content",
                            [0, len("a block a reader")], "in_window")
        if not append(strict_dir, "populated", clean_strict):
            failures.append("the clean record of the strict-rows run was not stored")
        populated_strict = pathlib.Path(strict_dir) / "evidence" / "populated.jsonl"
        if not populated_strict.read_bytes():
            failures.append("the strict-rows populated file is empty, so byte-identity proves nothing")
        # AE#0: the fixture only tests the case-preserving step if the floor pattern behind it really is
        # case-sensitive. Asserted here, of the floor itself, rather than assumed of a pattern that could
        # gain an IGNORECASE flag later.
        case_clean = "AKIA0123456789ABCDEF"
        floor_rules = projection.floor_patterns()
        if not any(pattern.search(case_clean) for pattern in floor_rules):
            failures.append(f"the floor does not claim {case_clean!r}, so the case-sensitive credential "
                            f"fixture tests nothing")
        if any(pattern.search(case_clean.casefold()) for pattern in floor_rules):
            failures.append(f"the floor claims the casefold of {case_clean!r} too, so that fixture passes "
                            f"without case preservation and tests nothing")

        for index, (label, text, spelling, state) in enumerate(strict_rows, start=2):
            admissible = state is True
            # AA#1: the source spelling, asserted before any boundary is asked of the row
            if (backslash in text) != (spelling == "escaped"):
                failures.append(f"{label}: the source text is not {spelling}: {text!r}")
                continue
            record_id = f"{index}/message/content/0/text"
            projected = strict_texts.get(record_id)
            if projected is None:
                failures.append(f"{label}: the fixture wrote no block at {record_id}")
                continue
            if state == "masked":
                # the projection's own home-path masking already rewrote the span, so there is no
                # sensitive quote left to refuse. The predicate is still asked about the raw text.
                if text in projected or projection.HOME_MASK not in projected:
                    failures.append(f"{label}: the projection did not mask the path: {projected[:60]!r}")
                allowed, why = projection.evidence_quote_admissible(text, views.FX_HOME)
                if allowed or "home path" not in (why or ""):
                    failures.append(f"{label}: the strict rule does not refuse the raw text as the "
                                    f"owner's home path: {why!r}")
                continue
            if state == "blanked":
                if projected != projection.FLOOR.PLACEHOLDER:
                    failures.append(f"{label}: the projection did not blank the block: {projected[:40]!r}")
                allowed, why = projection.evidence_quote_admissible(text, views.FX_HOME)
                if allowed or "undecodable" not in (why or ""):
                    failures.append(f"{label}: the strict rule does not refuse the raw text as "
                                    f"undecodable: {why!r}")
                continue
            if text not in projected and not admissible:
                failures.append(f"{label}: the projected quote no longer carries the name, so refusing it "
                                f"proves nothing: {projected[:40]!r}")
            span = [0, len(projected)]
            before_bytes = {path: path.read_bytes() for path in
                            sorted((pathlib.Path(strict_dir) / "evidence").glob("*"))}
            # the MAKING path
            try:
                made_row = make(strict_dir, strict_main["version_sha"], index,
                                "/message/content/0/text", span, "in_window")
                if not admissible:
                    failures.append(f"{label}: make built a record for a quote that names a secret")
            except Refused as exc:
                made_row = None
                if admissible:
                    failures.append(f"{label}: make refused an admissible quote: {exc}")
                elif "EVIDENCE_QUOTE_SENSITIVE" not in str(exc):
                    failures.append(f"{label}: make refused it unnamed: {exc}")
            # the INDEPENDENT record, appended to a new file and to the populated one
            independent_row = {
                "evidence_id": evidence_id(strict_main["version_sha"], index,
                                           "/message/content/0/text", span, projection.CURRENT),
                "source_copy": copy_rel(strict_main["version_sha"]),
                "version_sha": strict_main["version_sha"], "line": index,
                "json_pointer": "/message/content/0/text", "char_span": span,
                "redaction_version": projection.CURRENT, "redacted_text": projected,
                "window_role": "in_window"}
            for name in (f"new{index}", "populated"):
                try:
                    append(strict_dir, name, independent_row)
                    if not admissible:
                        failures.append(f"{label}: an independently built record was stored into "
                                        f"{name}.jsonl")
                except Refused as exc:
                    if admissible:
                        failures.append(f"{label}: an admissible record was refused at append: {exc}")
                    elif "EVIDENCE_QUOTE_SENSITIVE" not in str(exc):
                        failures.append(f"{label}: an independently built record was refused unnamed: {exc}")
            if not admissible:
                if (pathlib.Path(strict_dir) / "evidence" / f"new{index}.jsonl").exists():
                    failures.append(f"{label}: the refused record created its own store file")
                after_bytes = {path: path.read_bytes() for path in
                               sorted((pathlib.Path(strict_dir) / "evidence").glob("*"))}
                if after_bytes != before_bytes:
                    failures.append(f"{label}: a refusal changed a stored evidence file")
            elif made_row is None:
                failures.append(f"{label}: an admissible row produced no record at all")

        # ---- the owner's strict quote rule, at the boundary where text becomes shareable ----------
        #
        # A quote is lifted out of its block and carried into a report, so the context that makes
        # `"password": "<REDACTED>"` a correct thing to READ in a window does not travel with it. The rule
        # refuses such a quote outright: not masked, not partly accepted. Clean counterpart first - the
        # ordinary quote above was stored and verified - and then each trigger, plain and encoded, through
        # the real admission path rather than through the predicate alone.
        strict_cases = [
            ("a secret-named token", 'the "password" field was empty'),
            # X#0: every spelling the FLOOR recognises, each one plain and then one encoding down. The
            # dotted capital I is the one that casefolding alone loses: `APİ_KEY` casefolds to `api` plus a
            # combining dot, which the floor's `api[_-]?key` no longer matches.
            ("a secret-named token with U+0130", "the AP\u0130_KEY field was empty"),
            ("... and the same name one encoding down", "the AP\\u0130_KEY field was empty"),
            ("a secret-named token spelled with U+017F", "the pa\u017f\u017fword field was empty"),
            ("... and the same name one encoding down", "the pa\\u017f\\u017fword field was empty"),
            # a fullwidth spelling, which NFKC folds to the floor's own name
            ("a secret-named token in a compatibility spelling",
             "the \uff53\uff45\uff43\uff52\uff45\uff54 field was empty"),
            ("... and the same name one encoding down",
             "the \\uff53\\uff45\\uff43\\uff52\\uff45\\uff54 field was empty"),
            ("a secret-named token carrying a combining mark", "the passwo\u0301rd field was empty"),
            ("... and the same name one encoding down", "the passwo\\u0301rd field was empty"),
            # X#1: a name the floor claims only because something was prefixed to it
            ("a prefixed secret name", "my_password was empty"),
            ("a prefixed secret name in a Unicode spelling", "my_pa\u017f\u017fword was empty"),
            ("a credential the floor claims", "use sk-" + "Ab1_" * 6 + " now"),
            ("a credential the floor claims, encoded",
             "use " + "".join(f"\\u{ord(c):04x}" for c in "sk-" + "Ab1_" * 6) + " now"),
            ("the owner's home path", f"{views.FX_HOME}/Documents/notes.md"),
            ("the owner's home path, encoded",
             views.FX_HOME.replace("/", "\\u002f") + "\\u002fDocuments"),
            # the reviewer's shapes of this round, as quotes
            ("V#0: a readable array under an encoded key", '"\\u0070assword":["v0canary"]'),
            ("V#1: a suffix after a masked scalar", '"\\u0070assword":"<REDACTED>"v1suffix'),
            ("V#2: a quoted key with a newline before its separator", '"password"\n: "v2canary"'),
        ]
        refused_quotes = 0
        for label, text in strict_cases:
            admissible, why = projection.evidence_quote_admissible(text, views.FX_HOME)
            if admissible:
                failures.append(f"the strict quote rule admits {label}: {text[:40]!r}")
                continue
            refused_quotes += 1
            if not why:
                failures.append(f"the strict quote rule refused {label} without naming a reason")
        if refused_quotes != len(strict_cases):
            failures.append(f"only {refused_quotes} of {len(strict_cases)} sensitive quotes were refused")
        # X#1: the POSITIVE controls - names the floor does not claim stay admissible, or the strict rule is
        # a rule against the word `token` rather than against a secret's name
        for label, text in (("an ordinary accounting field", "input_tokens were 412 this turn"),
                            ("an ordinary tool name", "the tokenizer ran twice"),
                            ("an ordinary sentence with no name at all", "three files changed"),
                            ("the mask by itself", projection.FLOOR.PLACEHOLDER)):
            allowed, why = projection.evidence_quote_admissible(text, views.FX_HOME)
            if not allowed:
                failures.append(f"the strict quote rule refuses {label}: {why}")
        # ... and on the MAKING path too, through a transcript whose projected block really holds a
        # secret-named key with a masked value - which a window may show and a quote may not carry
        def fx_keyed_block():
            return [views.fx_human(views.fx_stamp(1), "a block a reader may see"),
                    views.fx_assistant(views.fx_stamp(2), '{"password":"keyed-value-for-the-quote-rule"}')]

        keyed = views.golden(pathlib.Path(td), "keyed", main_records=fx_keyed_block, owned=[[0, 3]])
        keyed_dir, keyed_main = keyed["run_dir"], keyed["main"]
        keyed_text = next((text for record, text in
                           views.projection_texts(keyed_dir, keyed_main["redacted"]).items()
                           if "password" in text), None)
        if keyed_text is None:
            failures.append("the keyed fixture's projection holds no secret-named key, so the control below "
                            "is about nothing")
        else:
            try:
                from_quote(keyed_dir, keyed_main["version_sha"], 2, "/message/content/0/text",
                           keyed_text, "in_window")
                failures.append(f"a quote naming a secret-named key was made: {keyed_text[:40]!r}")
            except Refused as exc:
                if "EVIDENCE_QUOTE_SENSITIVE" not in str(exc):
                    failures.append(f"a quote naming a secret-named key was refused unnamed: {exc}")

        # ... and the refusal really happens on the WRITING path, by name
        sensitive = dict(record)
        sensitive["redacted_text"] = 'the "password" field was empty'
        try:
            append(run_dir, "strict", sensitive)
            failures.append("a sensitive quote was stored, so the admission rule is not on the write path")
        except Refused as exc:
            if "EVIDENCE_QUOTE_SENSITIVE" not in str(exc):
                failures.append(f"a sensitive quote was refused unnamed: {exc}")
        # W#1: a record built INDEPENDENTLY of make - as another tool, or an older file, would hand it in -
        # is refused by append all the same, and nothing is written. The clean storage case above ran first,
        # so this is a refusal and not a store that never worked.
        if keyed_text is not None:
            independent = {"evidence_id": evidence_id(keyed_main["version_sha"], 2,
                                                      "/message/content/0/text", [0, len(keyed_text)],
                                                      projection.CURRENT),
                           "source_copy": copy_rel(keyed_main["version_sha"]),
                           "version_sha": keyed_main["version_sha"], "line": 2,
                           "json_pointer": "/message/content/0/text",
                           "char_span": [0, len(keyed_text)], "redaction_version": projection.CURRENT,
                           "redacted_text": keyed_text, "window_role": "in_window"}
            if claims.validate_record("evidence", independent):
                failures.append("the independently built record is not a valid record, so refusing it "
                                "proves nothing about the admission rule")
            # X#2: a CLEAN record of this run is stored first, so there is a populated file to protect and
            # the refusals below are refusals rather than a store that never worked at all.
            clean_keyed = make(keyed_dir, keyed_main["version_sha"], 1, "/message/content",
                               [0, len("a block a reader")], "in_window")
            if not append(keyed_dir, "populated", clean_keyed):
                failures.append("the clean record of the keyed run was not stored, so the controls below "
                                "protect nothing")
            populated = pathlib.Path(keyed_dir) / "evidence" / "populated.jsonl"
            if not populated.exists() or not populated.read_bytes():
                failures.append("the populated evidence file is empty, so byte-identity proves nothing")
            # ... and `verify` is otherwise clean about the sensitive record: what refuses it is the
            # admission rule and not a locator or a version problem
            if verify(keyed_dir, independent):
                failures.append(f"the independently built record is not otherwise verifiable: "
                                f"{verify(keyed_dir, independent)}")
            before_files = {path: path.read_bytes() for path in
                            sorted((pathlib.Path(keyed_dir) / "evidence").glob("*"))}
            # to a NEW filename, and to the POPULATED one: both refused by name
            for name in ("independent", "populated"):
                try:
                    append(keyed_dir, name, independent)
                    failures.append(f"an independently built record naming a secret-named key was stored "
                                    f"into {name}.jsonl")
                except Refused as exc:
                    if "EVIDENCE_QUOTE_SENSITIVE" not in str(exc):
                        failures.append(f"an independently built record was refused unnamed: {exc}")
            if (pathlib.Path(keyed_dir) / "evidence" / "independent.jsonl").exists():
                failures.append("the refused independent record created its store file")
            after_files = {path: path.read_bytes() for path in
                           sorted((pathlib.Path(keyed_dir) / "evidence").glob("*"))}
            if after_files != before_files:
                failures.append("the refused independent record changed an existing evidence file")
            if not populated.read_bytes():
                failures.append("the populated evidence file was emptied by a refusal")

        # ... and NOTHING was written by that refusal: a refusal that leaves a line behind is a disclosure
        # with an error message in front of it
        store = pathlib.Path(run_dir) / "evidence" / "strict.jsonl"
        if store.exists():
            failures.append(f"the refused quote created {store.name}, so the refusal still wrote")
        before = (pathlib.Path(run_dir) / "evidence" / "t1.jsonl").read_bytes()
        try:
            append(run_dir, "t1", sensitive)
            failures.append("a sensitive quote was stored into an existing file")
        except Refused:
            pass
        if (pathlib.Path(run_dir) / "evidence" / "t1.jsonl").read_bytes() != before:
            failures.append("the refused quote changed an existing evidence file")
        if make(run_dir, sha, record["line"], record["json_pointer"], record["char_span"], "in_window") != record:
            failures.append("make and from_view disagree about the same span")
        if claims.validate_record("evidence", record):
            failures.append("the record does not conform to the evidence schema")

        # O2 altered quote: one character changed in the quote -> QUOTE_MISMATCH; the raw bytes where the projection holds a mask -> the same
        for label, edit in (("one character changed", lambda r: {**r, "redacted_text": r["redacted_text"].replace("plain", "plaim")}),
                            ("the span moved by one", lambda r: {**r, "char_span": [r["char_span"][0] + 1, r["char_span"][1] + 1]}),
                            ("the span past the block", lambda r: {**r, "char_span": [10_000, 10_005]})):
            found = verify(run_dir, edit(record))
            if not any(f.startswith("QUOTE_MISMATCH") for f in found):
                failures.append(f"{label}: not named QUOTE_MISMATCH: {found}")
        masked = entries[f"{golden['lines']['human']}/message/content"]["text"]
        if golden["raw_path"] in masked or "<HOME>" not in masked:
            failures.append("instrument control: the planted path is not masked in the window, so the raw/masked controls prove nothing")
        raw_quote, masked_quote = f"see {golden['raw_path']}", "see <HOME>/Documents/repo/notes.md"
        try:
            from_quote_raw = from_quote(run_dir, sha, golden["lines"]["human"], "/message/content", raw_quote, "in_window")
            failures.append(f"a quote carrying the raw bytes was accepted: {from_quote_raw['redacted_text']!r}")
        except Refused as exc:
            if "QUOTE_MISMATCH" not in str(exc):
                failures.append(f"a raw-bytes quote was refused unnamed: {exc}")
        masked_record = from_quote(run_dir, sha, golden["lines"]["human"], "/message/content", masked_quote, "in_window")
        if verify(run_dir, masked_record) or masked_record["redacted_text"] != masked_quote:
            failures.append("a quote carrying the masked form did not validate")
        if any(golden["secret"] in json.dumps(r) or golden["raw_path"] in json.dumps(r) for r in (record, masked_record)):
            failures.append("a planted secret or path reached an evidence record")
        try:
            from_view(run_dir, sha, human, quote + " and then some")
            failures.append("a quote that is not in the window was made into evidence")
        except Refused as exc:
            if "QUOTE_MISMATCH" not in str(exc):
                failures.append(f"a quote not in the window was refused unnamed: {exc}")
        try:
            from_quote(run_dir, sha, golden["lines"]["human"], "/message/content", "e", "in_window")
            failures.append("an ambiguous quote was resolved without naming the occurrence")
        except Refused as exc:
            if "QUOTE_AMBIGUOUS" not in str(exc):
                failures.append(f"an ambiguous quote was refused unnamed: {exc}")
        try:  # the same, read out of a window's entry rather than named by line and pointer
            from_view(run_dir, sha, human, "e")
            failures.append("an ambiguous quote in a window was resolved without naming the occurrence")
        except Refused as exc:
            if "QUOTE_AMBIGUOUS" not in str(exc):
                failures.append(f"an ambiguous quote in a window was refused unnamed: {exc}")
        # `make` is where a locator is first resolved: a pointer that names no block, and a span outside the block
        for label, line, pointer, span in (("a pointer that names no block", golden["lines"]["human"], "/message/nowhere", [0, 3]),
                                           ("a line past the end", 9999, "/message/content", [0, 3]),
                                           ("a span past the block", golden["lines"]["human"], "/message/content", [10_000, 10_005]),
                                           ("an empty span", golden["lines"]["human"], "/message/content", [3, 3])):
            try:
                make(run_dir, sha, line, pointer, span, "in_window")
                failures.append(f"evidence was made for {label}")
            except Refused as exc:
                if "LOCATOR_UNRESOLVED" not in str(exc):
                    failures.append(f"{label} was refused unnamed: {exc}")
        # a locator that is not a block, a role the schema does not know, a record that is not a record
        if "LOCATOR_UNRESOLVED" not in "\n".join(verify(run_dir, {**record, "json_pointer": "/message/nowhere"})):
            failures.append("a pointer that names no block was not LOCATOR_UNRESOLVED")
        if "LOCATOR_UNRESOLVED" not in "\n".join(verify(run_dir, {**record, "line": 9999})):
            failures.append("a line past the end was not LOCATOR_UNRESOLVED")
        if "EVIDENCE_INVALID" not in "\n".join(verify(run_dir, {**record, "window_role": "elsewhere"})):
            failures.append("a record with a role the schema does not know was not EVIDENCE_INVALID")
        if "EVIDENCE_INVALID" not in "\n".join(verify(run_dir, {k: v for k, v in record.items() if k != "window_role"})):
            failures.append("a record without window_role was not EVIDENCE_INVALID")
        # M#6: the locator the owner opens is the file whose bytes were verified. Positive control first -
        # `record` itself verifies above - then the same record with only its source_copy substituted. A
        # second intact copy is planted under another name, so the substituted path is a real, openable,
        # unmodified file and nothing but the locator rule can refuse it.
        other = pathlib.Path(run_dir) / "sources" / "another-copy.jsonl"
        other.write_bytes((pathlib.Path(run_dir) / copy_rel(sha)).read_bytes())
        moved = {**record, "source_copy": "sources/another-copy.jsonl"}
        found = verify(run_dir, moved)
        if not any(f.startswith("SOURCE_LOCATOR_MISMATCH") for f in found):
            failures.append(f"a record whose source_copy points elsewhere verified: {found}")
        if openable(run_dir, moved) == openable(run_dir, record):
            failures.append("the substituted locator opened the same file, so the control proves nothing")
        try:
            append(run_dir, "mismatched", moved)
            failures.append("a record whose source_copy points elsewhere was stored")
        except Refused as exc:
            if "SOURCE_LOCATOR_MISMATCH" not in str(exc):
                failures.append(f"storing it was refused unnamed: {exc}")
        other.unlink()
        # P#5: the READER refuses a store made under another projection. `verify` always did; `load` and
        # `resolve` handed the record - and its quote - straight back. Positive control first: the store
        # holds this run's own record and both readers return it.
        if not load(run_dir, "t1") or resolve(run_dir, record["evidence_id"]) is None:
            failures.append("the store's own record is not readable through load and resolve")
        store = pathlib.Path(run_dir) / "evidence" / "stale.jsonl"
        store.write_text(json.dumps({**record, "redaction_version": "r1"}, sort_keys=True) + "\n", encoding="utf-8")
        for label, call in (("load", lambda: load(run_dir, "stale")),
                            ("resolve", lambda: resolve(run_dir, record["evidence_id"]))):
            try:
                call()
                failures.append(f"{label} returned a record made under another projection version")
            except Refused as exc:
                if "REDACTION_VERSION_MISMATCH" not in str(exc):
                    failures.append(f"{label} refused a stale store unnamed: {exc}")
        if [r["evidence_id"] for r in load(run_dir, "stale", current=False)] != [record["evidence_id"]]:
            failures.append("an explicit unchecked load did not read the stale store it was asked for")
        store.unlink()

        # the projection's version moves: the old quote fails by name, the same quote made again passes
        projection.VERSIONS["rt"] = lambda value, home=None: projection.project_r22(value, home)  # a new version, the same text
        try:
            found = verify(run_dir, record, current="rt")
            if not any(f.startswith("REDACTION_VERSION_MISMATCH") for f in found):
                failures.append(f"an old quote under a new projection version was not REDACTION_VERSION_MISMATCH: {found}")
            again = make(run_dir, sha, record["line"], record["json_pointer"], record["char_span"], "in_window", "rt")
            if verify(run_dir, again, current="rt") or again["redaction_version"] != "rt" or again["evidence_id"] == record["evidence_id"]:
                failures.append("the re-projected quote did not pass under the new version as a new record")
            projection.VERSIONS["rt"] = lambda value, home=None: projection.project_r22(value, home).replace("plain", "simple")
            if not any(f.startswith("QUOTE_MISMATCH") for f in verify(run_dir, again, current="rt")):
                failures.append("a record whose version is current but whose text the projection no longer gives was not QUOTE_MISMATCH")
        finally:
            del projection.VERSIONS["rt"]

        # SOURCE_TAMPERED: the copy is edited in place (the O2 altered-source plant); a missing copy is named too
        os.chmod(copy, 0o644)
        original = copy.read_bytes()
        copy.write_bytes(original.replace(b"plain version", b"plain versiom", 1))
        found = verify(run_dir, record)
        if not any(f.startswith("SOURCE_TAMPERED") for f in found):
            failures.append(f"an edited source copy was not SOURCE_TAMPERED: {found}")
        try:
            make(run_dir, sha, record["line"], record["json_pointer"], record["char_span"], "in_window")
            failures.append("evidence was made over an edited copy")
        except Refused as exc:
            if "SOURCE_TAMPERED" not in str(exc):
                failures.append(f"making evidence over an edited copy was refused unnamed: {exc}")
        copy.write_bytes(original)
        os.chmod(copy, 0o444)
        if verify(run_dir, record):
            failures.append("restoring the copy's bytes did not restore the evidence")
        os.chmod(copy, 0o644)
        copy.rename(copy.with_name("moved"))
        if not any(f.startswith("SOURCE_MISSING") for f in verify(run_dir, record)):
            failures.append("a missing copy was not SOURCE_MISSING")
        copy.with_name("moved").rename(copy)
        os.chmod(copy, 0o444)
        # the projection file is not trusted: evidence is checked against the copy, so a doctored projection changes nothing
        projected = pathlib.Path(run_dir) / main["redacted"]
        text = projected.read_text(encoding="utf-8")
        projected.write_text(text.replace("plain version", "plain wersion"), encoding="utf-8")
        if verify(run_dir, record):
            failures.append("evidence depended on the projection file instead of the copy")
        projected.write_text(text, encoding="utf-8")
        # a lone surrogate in a block: the projection replaces it, the quote around it still verifies
        if projection.project(json.loads('"a\\ud83dz"')) != "a?z":
            failures.append("a lone surrogate was not replaced")

    for failure in failures:
        print(f"evidence --self-test [FAIL] {failure}")
    if failures:
        return 1
    print("evidence --self-test: OK (a quote read from a window verifies, stores once, resolves and opens at its source; a changed "
          "character, a moved span, the raw bytes where a mask stands and a quote not shown are QUOTE_MISMATCH; an ambiguous quote, "
          "an unknown pointer or line, an unknown role and a missing window_role are named; an old projection version fails "
          "REDACTION_VERSION_MISMATCH and the quote made again passes; an edited copy is SOURCE_TAMPERED, a missing one SOURCE_MISSING, "
          "and the projection file is never the authority)")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: evidence.py --self-test")
    sys.exit(self_test())
