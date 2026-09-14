#!/usr/bin/env python3
"""Is the child's behaviour really absent from this variant?

An ablated arm is only an ablated arm if the instructions no longer instructs the
behaviour. Deleting the sentence is not the same thing: a guide can carry the
same instruction in other words, and then the "ablated" arm still teaches it and
the experiment measures nothing.

Two layers, because each misses what the other catches:

  lexical   the ledger's phrases for the child must appear nowhere in the variant.
            Cheap, decidable, and blind to paraphrase.
  semantic  a seat reads each carrier section the child lived in and answers one
            question: does this section instruct the behaviour? It is given the
            behaviour and the section, never the phrases, so it cannot pattern-match
            the thing we just deleted.

The semantic layer carries its own **positive control**: a section known to carry
the behaviour under other words. A seat that does not flag that section is not
reading for meaning, and its "absent" verdicts are worth nothing. This is not
hypothetical — the phrase probe that produced this design missed S3-22's passage
in tooling-gotchas ("confirm the running process's actual version/behaviour or
force a restart"), which carried the behaviour with none of the phrases.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re

import dispatch

ABSENT, PRESENT, UNCLEAR = "ABSENT", "PRESENT", "UNCLEAR"

SEMANTIC_PROMPT = """You are checking whether a section of an agent instruction library
instructs a specific behaviour. You are NOT checking whether it uses particular words.

THE BEHAVIOUR:
{behaviour}

THE SECTION:
<<<
{section}
>>>

Answer PRESENT if an agent following this section would perform the behaviour, even if
the section never uses the words above — a paraphrase, a worked example, or a rule that
entails it all count as PRESENT. Answer ABSENT if nothing here would produce it. Answer
UNCLEAR only if the section is too fragmentary to tell.

Reply with exactly one JSON object and nothing else:
{{"verdict": "PRESENT" | "ABSENT" | "UNCLEAR", "why": "<one sentence quoting what decided it>"}}
"""


class AbsenceError(RuntimeError):
    """An absence check that cannot be trusted to detect presence."""


def lexical(phrases: list[str], home: pathlib.Path, instructions_paths: tuple) -> dict:
    """Every ledger phrase for the child, searched across the variant's instructions."""
    if not phrases:
        raise AbsenceError("no phrases to search — a lexical check over nothing is vacuous")
    files = []
    for rel in instructions_paths:
        p = home / rel
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files += [q for q in p.rglob("*.md") if q.is_file()]
    if not files:
        raise AbsenceError(f"no instructions files under {home} — nothing was searched")
    hits = {}
    for phrase in phrases:
        found = [str(f.relative_to(home)) for f in files
                 if phrase.lower() in f.read_text(encoding="utf-8", errors="replace").lower()]
        if found:
            hits[phrase] = found
    return {"searched_files": len(files), "phrases": len(phrases), "hits": hits,
            "verdict": PRESENT if hits else ABSENT}


def sections_of(path: pathlib.Path) -> list[tuple[str, str]]:
    """(heading, body) pairs — the unit a reader can judge without the whole file.

    The text BEFORE the first heading is a section too. It was emitted only when the
    file had no H2-H4 at all, so in any file with sections the H1 and the introduction
    under it were dropped — and an instruction file's opening paragraph is exactly where a
    standing instruction tends to live. A file whose only statement of the behaviour
    sat there was judged ABSENT with the answer visible in the input."""
    text = path.read_text(encoding="utf-8", errors="replace")
    parts = re.split(r"^(#{2,4} .+)$", text, flags=re.M)
    out = []
    if parts[0].strip():
        h1 = next((line.strip().lstrip("#").strip()
                   for line in parts[0].splitlines() if line.startswith("# ")), "")
        out.append((f"{path.name} preamble" + (f" — {h1}" if h1 else ""), parts[0]))
    for i in range(1, len(parts), 2):
        out.append((parts[i].strip(), parts[i + 1]))
    return out or [(path.name, text)]


def parse_verdict(text: str) -> str:
    """One of the three labels. Anything else — unparseable, or a fourth word the model
    invented — is UNCLEAR, never a label the aggregate can read as absence."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return UNCLEAR
    try:
        got = json.loads(text[start:end + 1]).get("verdict", UNCLEAR)
    except json.JSONDecodeError:
        return UNCLEAR
    return got if got in (PRESENT, ABSENT, UNCLEAR) else UNCLEAR


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dispatch_problem(label: str, receipt, seat: dict) -> str | None:
    """Why this call is not evidence of anything, or None.

    `ask` used to return model text alone, so a stub could answer ABSENT for every
    carrier without a model ever running and the result still read `valid: true`. An
    absence verdict is a claim about what a seat could not find, which is worthless
    unless that seat is known to have been asked."""
    if not isinstance(receipt, dict):
        return f"{label}: no dispatch receipt — model text alone evidences nothing"
    if receipt.get("status") != "ok":
        return f"{label}: dispatch status {receipt.get('status')!r}, not ok"
    if not receipt.get("session_id"):
        return f"{label}: no session id, so the call cannot be located afterwards"
    problem = dispatch.seat_problem(seat.get("host"), seat.get("model"),
                                    receipt.get("models_reported") or [])
    return f"{label}: {problem}" if problem else None


def semantic(behaviour: str, sections: list[tuple[str, str]], ask, seat: dict) -> dict:
    """`ask(prompt) -> (text, receipt)`. Kept injectable so the positive control and the
    real run go through the identical path — a control that takes a different route
    proves something about that route.

    Records are a LIST. Keying them by heading meant a repeated heading — legal within a
    file and common across files — overwrote the earlier record, so a carrier judged
    PRESENT vanished behind a later ABSENT and the aggregate reported absence.

    The aggregate is not a two-way split. ABSENT is asserted only when every carrier
    said ABSENT; one PRESENT makes it PRESENT; anything unjudged makes it UNCLEAR,
    including no carriers at all. Folding UNCLEAR into ABSENT let 'we could not tell'
    be reported as 'it is not there'."""
    records, problems = [], []
    for index, (heading, body) in enumerate(sections):
        prompt = SEMANTIC_PROMPT.format(behaviour=behaviour, section=body)
        text, receipt = ask(prompt)
        problem = dispatch_problem(f"carrier {index} ({heading})", receipt, seat)
        if problem:
            problems.append(problem)
        records.append({
            "index": index, "heading": heading, "verdict": parse_verdict(text),
            "prompt_sha256": _sha(prompt), "result_sha256": _sha(text),
            "session_id": (receipt or {}).get("session_id") if isinstance(receipt, dict) else None,
            "models_reported": (receipt or {}).get("models_reported") if isinstance(receipt, dict) else None,
        })
    labels = [r["verdict"] for r in records]
    if PRESENT in labels:
        aggregate = PRESENT
    elif labels and all(label == ABSENT for label in labels):
        aggregate = ABSENT
    else:
        aggregate = UNCLEAR
    return {"records": records, "verdict": aggregate, "problems": problems}


def check(behaviour: str, phrases: list[str], home: pathlib.Path, instructions_paths: tuple,
          carrier_sections: list[tuple[str, str]], control_section: tuple[str, str],
          ask, seat: dict) -> dict:
    """The full check, positive control first.

    The control runs BEFORE the real sections and its failure aborts: a seat that
    cannot see the behaviour where it is known to be present has already told you
    what its ABSENT verdicts are worth. Every call must ALSO carry a dispatch receipt
    for `seat`; a verdict with no evidence that a model produced it is withheld rather
    than reported, and so is one where any carrier could not be judged."""
    control_text, control_receipt = ask(SEMANTIC_PROMPT.format(
        behaviour=behaviour, section=control_section[1]))
    control_verdict = parse_verdict(control_text)
    problem = dispatch_problem(f"positive control ({control_section[0]})",
                               control_receipt, seat)
    if problem:
        return {"valid": False, "control": control_verdict, "why": problem}
    if control_verdict != PRESENT:
        return {"valid": False, "control": control_verdict,
                "why": (f"the paraphrase positive control ({control_section[0]}) was judged "
                        f"{control_verdict}; a seat that misses a known paraphrase cannot "
                        f"evidence absence")}
    lex = lexical(phrases, home, instructions_paths)
    sem = semantic(behaviour, carrier_sections, ask, seat)
    common = {"control": control_verdict, "control_session_id": control_receipt.get("session_id"),
              "control_prompt_sha256": _sha(SEMANTIC_PROMPT.format(
                  behaviour=behaviour, section=control_section[1])),
              "lexical": lex, "semantic": sem, "seat": dict(seat)}
    if sem["problems"]:
        return {**common, "valid": False, "why": "; ".join(sem["problems"])}
    if sem["verdict"] == UNCLEAR:
        return {**common, "valid": False,
                "why": ("a carrier could not be judged, so absence is not established — "
                        "'we could not tell' is not 'it is not there'")}
    absent = lex["verdict"] == ABSENT and sem["verdict"] == ABSENT
    return {**common, "valid": True, "verdict": ABSENT if absent else PRESENT}
