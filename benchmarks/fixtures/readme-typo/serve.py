"""Entry point for the order webhook (see README for usage)."""
import json, sys


def validate(event: dict) -> list[str]:
    problems = []
    for field in ("order_id", "sku", "quantity"):
        if field not in event:
            problems.append(f"missing {field}")
    if event.get("quantity", 1) <= 0:
        problems.append("quantity must be positive")
    return problems


def main() -> int:
    event = json.load(sys.stdin)
    problems = validate(event)
    if problems:
        print("; ".join(problems), file=sys.stderr)
        return 1
    print(json.dumps({"forwarded": event["order_id"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
