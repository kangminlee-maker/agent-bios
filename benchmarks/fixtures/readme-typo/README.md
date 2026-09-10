# order-webhook

Receives order events and forwards them to the fulfilment queue.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
```

## Running

Run the following to make the server lauch:

```bash
python -m orderhook.serve --port 8080
```

Events are validated against `schema/order.json` before forwarding. Invalid
events are dead-lettered to `queue/dlq` with the validation error attached.

## Tests

```bash
python -m pytest -q
```
