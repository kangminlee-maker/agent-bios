#!/usr/bin/env python3
"""Parity between the v1 and v2 activation branches, one leg per clause.

leg 1: both branches activate a fresh user identically
leg 2: both branches leave the user record in the same final state
leg 3: repeat activation agrees between branches   <- unmet until the v2 cutover
"""
import json, os, subprocess, sys


def run(v2: bool, state: str) -> dict:
    """One observation: the branch's return (or exception) AND the record it leaves.

    Both are needed. Comparing only the returned string made leg 2 a duplicate of leg 1,
    so a branch that returned the right word while leaving the wrong state passed."""
    env = {**os.environ, "ACTIVATION_V2": "1" if v2 else "0"}
    code = (
        "import json\n"
        "import app.activation as a\n"
        f"u = {{'state': {state!r}}}\n"
        "try:\n"
        "    r = a.activate(u)\n"
        "except ValueError as e:\n"
        "    r = f'raised: {e}'\n"
        "print(json.dumps({'returned': r, 'state': u.get('state')}))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], env=env,
                         capture_output=True, text=True,
                         cwd=os.path.dirname(os.path.dirname(__file__)))
    if out.returncode != 0:
        # The probe never reached the subject. Equality between two failures is not
        # parity — reporting `ok` here is a green result about code that did not run.
        return {"ok": False, "error": (out.stderr.strip().splitlines() or ["exit "
                + str(out.returncode)])[-1]}
    try:
        obs = json.loads(out.stdout)
    except ValueError:
        return {"ok": False, "error": f"unparsable probe output: {out.stdout.strip()[:80]}"}
    return {"ok": True, **obs}


def leg(name: str, a: dict, b: dict, field: str) -> tuple:
    if not a.get("ok") or not b.get("ok"):
        why = a.get("error") or b.get("error")
        return name, None, f"probe did not run ({why})"
    return name, a[field] == b[field], f"{a[field]!r} vs {b[field]!r}"


def main() -> int:
    fresh_v1, fresh_v2 = run(False, "new"), run(True, "new")
    rep_v1, rep_v2 = run(False, "active"), run(True, "active")
    legs = [
        leg("leg 1", fresh_v1, fresh_v2, "returned"),
        leg("leg 2", fresh_v1, fresh_v2, "state"),
        leg("leg 3", rep_v1, rep_v2, "returned"),
    ]
    for name, ok, detail in legs:
        print(f"{name}: {'ok' if ok else ('UNMET' if ok is False else 'NOT RUN')} — {detail}")
    if any(ok is None for _, ok, _ in legs):
        print("parity undetermined: at least one probe never reached the subject")
        return 2
    return 1 if any(ok is False for _, ok, _ in legs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
