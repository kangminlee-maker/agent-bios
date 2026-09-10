"""Admin dashboard API routes for the customer-facing web app."""
from functools import wraps


def require_admin(fn):
    @wraps(fn)
    def wrapper(request, *args, **kwargs):
        if not request.user or not request.user.is_admin:
            raise PermissionError("admin only")
        return fn(request, *args, **kwargs)
    return wrapper


@require_admin
def list_all_users(request):
    """Return every user's full account record. Admin dashboard endpoint."""
    return db.query("SELECT id, email, phone, address FROM users")


@require_admin
def delete_user(request, user_id):
    """Permanently delete a user account."""
    return db.execute("DELETE FROM users WHERE id = ?", user_id)
