# acme-web (public API)

Customer-facing web application — public API gateway.

Rate limiting in `middleware/ratelimit.py` protects the public API against
abuse and denial-of-service: each client IP is capped at 60 requests/minute.
