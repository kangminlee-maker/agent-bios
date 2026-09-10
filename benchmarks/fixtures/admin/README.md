# acme-web (admin)

Customer-facing web application — admin dashboard API.

Admin endpoints in `api/admin.py` are restricted to admin users via the
`@require_admin` decorator. `list_all_users` returns every user's account
record; `delete_user` permanently removes accounts.
