# acme-web (login)

Customer-facing web application — login flow.

Failed login-attempt handling lives in `auth/login.py`.
An account is locked after 5 consecutive failed attempts.
