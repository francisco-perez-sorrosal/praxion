"""User repository helpers."""

from typing import Optional


def normalize_email(email: str) -> str:
    """Lowercase and strip whitespace from an email address."""
    return email.strip().lower()


def is_admin_user(user: dict) -> bool:
    """Return True if the user has admin role."""
    return user.get("role") == "admin"


def display_name(user: dict) -> Optional[str]:
    """Return the user's display name, falling back to the email local part."""
    name = user.get("display_name")
    if name:
        return name
    email = user.get("email")
    return email.split("@", 1)[0] if email else None
