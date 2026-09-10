# activation-cutover

v1 raises on repeat activation; v2 (behind `ACTIVATION_V2`) is idempotent.
CI runs `python -m pytest -q`, and the `check_parity` job runs `python scripts/check-parity.py`.
