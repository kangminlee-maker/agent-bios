#!/usr/bin/env python3
"""The full-source search of design §5.4: BM25 over the redacted text of every viewed version, clipped spans included.

An index holds, for every content block it was given, the keys the block contains: its lowercase
word tokens, and for a run of Hangul or CJK characters the overlapping character bigrams (a
Korean word carries its particles, so the word itself rarely equals the word a term names). A
term (a retrieval term of an expected observation, §7.3) is a word or a phrase. A block is a
**match** for a term when it holds every key of the term and the term, normalized, occurs in the
block's normalized text; the second test needs the text, so `search` is given `text_of`, a
function from a document reference to its projected text. The index narrows, the text decides.

A hit is scored with BM25 (k1 1.2, b 0.75), the phrase being the unit: tf is the number of
occurrences in the block, df the number of blocks that matched the phrase, document length the
block's token count. The score ranks and is reported; whether a block is a hit does not depend on it.
Search only adds reading, it never closes a claim (§5.4): a term that matches nothing is not
evidence that nothing was said, and the caller keeps it as such.

The index is JSON (`dump`/`load`), never compressed: the run directory is swept as text for what
must not be in it.

  search.py --self-test
"""
import json
import math
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import projection   # noqa: E402  - the one owner of the projection's current version

WORD = re.compile(r"\w+", re.UNICODE)
CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힣]+")
MAX_KEY = 40       # a longer token is an encoded blob, not a word anyone searches for
K1, B = 1.2, 0.75


class SearchError(Exception):
    """A refusal; the message starts with its named code."""


def keys_of(text):
    """The set of keys a text holds, and its token count."""
    words = [w.lower() for w in WORD.findall(text)]
    keys = {w for w in words if len(w) <= MAX_KEY}
    for run in CJK.findall(text):
        keys.update(run[i:i + 2] for i in range(len(run) - 1))
    return keys, len(words)


def normalize(text):
    return " ".join(w.lower() for w in WORD.findall(text))


def term_keys(term):
    """The keys every matching block holds: a word is itself, and CJK characters stand as their bigrams
    (so a term of one CJK character has no key; `search` refuses it by name)."""
    keys = set()
    for word in WORD.findall(term):
        word = word.lower()
        if CJK.search(word):
            for run in CJK.findall(word):
                keys.update(run[i:i + 2] for i in range(len(run) - 1))
        elif len(word) <= MAX_KEY:
            keys.add(word)
    return keys


def occurrences(term, text):
    """How many times `term` occurs in `text`, by the normalization both go through."""
    want, have = normalize(term), normalize(text)
    if not want:
        return 0
    if CJK.search(term):
        return have.replace(" ", "").count(want.replace(" ", ""))
    return f" {have} ".count(f" {want} ")


class Index:
    def __init__(self, version_sha="", redaction_version=""):
        self.version_sha, self.redaction_version = version_sha, redaction_version
        self.docs, self.postings = [], {}

    def add(self, ref, text):
        """Add one block under `ref` (a JSON-able reference such as `[line, json_pointer]`)."""
        keys, length = keys_of(text)
        number = len(self.docs)
        self.docs.append({"ref": ref, "length": length})
        for key in keys:
            self.postings.setdefault(key, []).append(number)
        return number

    def to_json(self):
        return {"version_sha": self.version_sha, "redaction_version": self.redaction_version,
                "docs": self.docs, "postings": {k: self.postings[k] for k in sorted(self.postings)}}

    @classmethod
    def from_json(cls, data):
        index = cls(data["version_sha"], data["redaction_version"])
        index.docs, index.postings = data["docs"], data["postings"]
        return index


def dump(index, path):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(index.to_json(), handle, ensure_ascii=False, separators=(",", ":"))


def load(path, version=None):
    """The index at `path`, refused by name when it was built under another projection.

    The version is checked where the index is CONSUMED, not only where a quote is verified: an index built
    under a projection that masked less lists the words of text the current one would have masked, so a
    search over it can name a block by a term that should not have survived.  `version=False` reads it
    without the check, which only a tool that is migrating one may ask for."""
    with open(path, encoding="utf-8") as handle:
        index = Index.from_json(json.load(handle))
    if version is not False:
        want = projection.CURRENT if version is None else version
        if index.redaction_version != want:
            raise SearchError(f"REDACTION_VERSION_MISMATCH {path}: the index was built under "
                              f"{index.redaction_version!r}, the projection is {want!r}; build it again")
    return index


def search(index, terms, text_of):
    """Hits for `terms`: `[{ref, score, terms}]`, best first, ties in document order.

    A block is a hit when it matches at least one term; `terms` lists the ones it matched."""
    if not terms:
        raise SearchError("SEARCH_NO_TERMS: a search needs at least one retrieval term")
    for term in terms:
        if not isinstance(term, str) or not term_keys(term):
            raise SearchError(f"SEARCH_TERM_UNUSABLE {term!r}: a term needs a word, or two CJK characters; one that names nothing "
                              "would be skipped silently and read as 'searched, nothing found'")
    count = len(index.docs)
    average = (sum(d["length"] for d in index.docs) / count) if count else 0.0
    found = {}
    for term in terms:
        lists = [index.postings.get(k) for k in term_keys(term)]
        if any(l is None for l in lists):
            continue
        candidates = set(lists[0]).intersection(*map(set, lists[1:]))
        matched = {n: occurrences(term, text_of(index.docs[n]["ref"])) for n in sorted(candidates)}
        matched = {n: tf for n, tf in matched.items() if tf}
        df = len(matched)
        if not df:
            continue
        idf = math.log(1 + (count - df + 0.5) / (df + 0.5))
        for n, tf in matched.items():
            length = index.docs[n]["length"]
            weight = idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * length / average)) if average else 0.0
            hit = found.setdefault(n, {"ref": index.docs[n]["ref"], "score": 0.0, "terms": []})
            hit["score"] += weight
            hit["terms"].append(term)
    return [found[n] for n in sorted(found, key=lambda n: (-found[n]["score"], n))]


def self_test():
    failures = []
    blocks = {
        0: "Could you show me the plain version of that?",
        1: "the plain text of the version control log",              # both words, not the phrase
        2: "PLAIN VERSION please, the plain version again",           # case, two occurrences
        3: "database migration finished without errors",
        4: "쉽게 설명해줘, 처음 보는 사람도 이해할 수 있게",
        5: "설명이 너무 어렵다",
        6: "version 2.1.304 (build a1b2c3)",
    }
    index = Index("ab" * 32, projection.CURRENT)
    for n, text in blocks.items():
        index.add([n, "/message/content"], text)
    text_of = lambda ref: blocks[ref[0]]  # noqa: E731

    def refs(terms):
        return [h["ref"][0] for h in search(index, terms, text_of)]

    if refs(["plain version"]) != [2, 0]:  # positive control: the phrase, the block with two occurrences ranks first
        failures.append(f"the phrase 'plain version' hit {refs(['plain version'])}, expected [2, 0]")
    if set(refs(["version"])) != {0, 1, 2, 6}:
        failures.append(f"'version' hit {sorted(refs(['version']))}, expected the four blocks that hold the word")
    if 1 in refs(["plain version"]):
        failures.append("a block with both words apart matched the phrase")
    if set(refs(["migration", "plain version"])) != {0, 2, 3}:
        failures.append("two terms did not union their hits")
    if refs(["not in any block"]) != []:
        failures.append("a term in no block hit something")
    if 4 not in refs(["설명해줘"]) or 5 in refs(["설명해줘"]):
        failures.append(f"a Korean word hit {refs(['설명해줘'])}, expected the block that holds it and not the one that holds only its stem")
    if set(refs(["설명"])) != {4, 5}:
        failures.append(f"a Korean stem hit {refs(['설명'])}, expected both blocks")
    if refs(["2.1.304"]) != [6]:
        failures.append(f"a dotted number hit {refs(['2.1.304'])}")
    scores = [h["score"] for h in search(index, ["plain version"], text_of)]
    if not (scores[0] > scores[1] > 0):
        failures.append(f"scores do not rank by tf: {scores}")
    if search(index, ["plain version"], text_of) != search(index, ["plain version"], text_of):
        failures.append("the same search gave two answers")
    # the index narrows and the text decides: a text_of that disagrees with the index is believed
    if refs(["plain version"]) and search(index, ["plain version"], lambda ref: "nothing relevant"):
        failures.append("a hit was reported for a block whose text does not hold the term")
    # round trip through JSON
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        dump(index, td + "/i.json")
        # M#5: an index built under another projection is refused where it is CONSUMED, not only where a
        # quote is verified: it lists the words of text the current projection would have masked, so a
        # search over it can name a block by a term that should not have survived. Positive first, above.
        stale = Index("ab" * 32, "r1")
        dump(stale, td + "/stale.json")
        try:
            load(td + "/stale.json")
            failures.append("an index built under another projection version was loaded")
        except SearchError as exc:
            if "REDACTION_VERSION_MISMATCH" not in str(exc):
                failures.append(f"a stale index was refused unnamed: {exc}")
        if load(td + "/stale.json", version=False).redaction_version != "r1":
            failures.append("an explicit unchecked load did not read the stale index it was asked for")
        if load(td + "/i.json").to_json() != index.to_json():
            failures.append("the index did not survive a JSON round trip")
        raw = open(td + "/i.json", encoding="utf-8").read()
        if "plain" not in raw:
            failures.append("instrument control: the dumped index is not readable as text, so a text sweep could not see into it")
    for label, terms, code in (("no terms", [], "SEARCH_NO_TERMS"), ("a blank term", ["plain version", "  "], "SEARCH_TERM_UNUSABLE"),
                               ("punctuation only", ["!!"], "SEARCH_TERM_UNUSABLE"), ("a non-string term", [None], "SEARCH_TERM_UNUSABLE"),
                               ("one CJK character", ["왜"], "SEARCH_TERM_UNUSABLE")):
        try:
            search(index, terms, text_of)
            failures.append(f"{label}: a search with an unusable term was run")
        except SearchError as exc:
            if code not in str(exc):
                failures.append(f"{label}: refused unnamed: {exc}")
    long = Index()
    long.add([0, "/x"], "z" * 60 + " ordinary")
    if "z" * 60 in long.postings or "ordinary" not in long.postings:
        failures.append("a token longer than MAX_KEY was indexed, or an ordinary one was not")
    for failure in failures:
        print(f"search --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"search --self-test: OK ({len(blocks)} blocks; phrase, word, case, apart-words, Korean word and stem, dotted number, "
          "two terms, ranking by tf, determinism, the text decides, JSON round trip, an unusable term refused by name)")
    return 0


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: search.py --self-test")
    sys.exit(self_test())
