#!/usr/bin/env python3
"""Disclosing controls and how a verdict wears them (design, "Controls", "Cache order").

These controls do not block; they flag, the verdict is computed with and without the
flagged runs, and the flags are printed in the verdict's FIRST lines so a disclosure
nobody reads cannot become the failure mode of this class. What blocks lives in usage.py
(reconciliation, partition), pin.py (seat), level.py (leak, checker), protocol.py (ledger).

The cache band and the known-opposite spread take their reference numbers from Stage-0
live probes (a primed fresh run's first-request cache read; a two-seat cost pair). Those
measurements need a seat; the band/spread LOGIC is here and proven on synthetic inputs,
and the live measurement is wired in live.py.
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import usage  # noqa: E402

CACHE_BAND_TOL = 0.10  # ±10% of the seat's standing-prefix length


def standing_prefix_len(participant) -> int:
    """The warm standing prefix a fresh run reads on its first request. Measured once per
    seat in Stage 0 (after a priming request), then every run's first request is held to
    it. On the haiku probe this was 18000; on a Codex sol turn, 6912."""
    if not participant.requests:
        raise usage.UsageError(f"{participant.id}: no request to read a prefix length from")
    return participant.requests[0].kinds["cache_read"]


def cache_band_flag(first_request_cache_read: int, prefix_len: int,
                    tol: float = CACHE_BAND_TOL) -> str | None:
    """Disclose when a run's first request did not read the seat's standing prefix within
    the band. Far below = the prefix was cold (priming did not take). Far above = a sibling
    arm's suffix warmed this run's cache — the exact confound counterbalancing cannot fix
    on Claude, where the 1h cache outlives the gap between arms."""
    if prefix_len <= 0:
        return "standing-prefix length is 0 — the band cannot be checked (probe first)"
    lo, hi = prefix_len * (1 - tol), prefix_len * (1 + tol)
    if first_request_cache_read < lo:
        return (f"cold: first request read {first_request_cache_read} of a "
                f"{prefix_len} standing prefix (< {lo:.0f})")
    if first_request_cache_read > hi:
        return (f"warm: first request read {first_request_cache_read} > {hi:.0f} — a "
                f"sibling arm's suffix is in this run's cache")
    return None


def codex_differential(participant) -> dict:
    """The design's Codex differential probe: per-turn `last` summed against the
    cumulative `total`. usage.py already bills from the total's deltas; this reports
    whether the two agree, and by how much, as a disclosure. A large gap means duplicate
    or reset token_count events — normal, but recorded."""
    # usage.py stored the disclosure as notes; expose it structured.
    return {"notes": participant.notes,
            "billed_from": "cumulative-total deltas",
            "clean": not participant.notes}


def known_opposite_spread(cheap_usd: float, dear_usd: float,
                          min_ratio: float) -> str | None:
    """The seat-spread control: two seats that must differ by a known large factor. On
    Claude opus→haiku is 5×, fable→haiku 10×; on Codex sol→luna 20×. A pair that does not
    show the spread means the pricing is not seat-sensitive — the instrument is flat."""
    if cheap_usd <= 0:
        return "cheap seat priced at 0 — cannot check the spread"
    ratio = dear_usd / cheap_usd
    if ratio < min_ratio:
        return (f"seat spread {ratio:.1f}× is below the expected {min_ratio}× — pricing is "
                f"not seat-sensitive")
    return None


def verdict_header(flags: dict) -> list[str]:
    """Render a cell's disclosures BEFORE its numbers. `flags` maps a control name to
    None (clean) or a message. Every non-clean flag is a line; a clean cell says so, so a
    reader never mistakes silence for absence of a check."""
    lines = []
    fired = {k: v for k, v in flags.items() if v}
    if not fired:
        lines.append("disclosures: all clear (" + ", ".join(sorted(flags)) + ")")
    else:
        lines.append(f"disclosures fired ({len(fired)} of {len(flags)}):")
        for k in sorted(fired):
            lines.append(f"  ! {k}: {fired[k]}")
    return lines


def output_dominance_flag(share: float | None, floor: float = 0.40) -> str | None:
    """The output-priced-share label (disclosing, design "Task"): a cell whose comparator
    share is below the floor is 'not output-dominated' and says so first."""
    if share is None:
        return "output-priced share is undefined (zero cost) — cannot label"
    if share < floor:
        return f"not output-dominated: comparator output-priced share {share:.0%} < {floor:.0%}"
    return None
