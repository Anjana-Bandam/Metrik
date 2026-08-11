"""
auth.py
-------
Lightweight mock authentication for the hackathon demo.

Not production auth - passwords are salted+hashed with hashlib and tokens
are opaque random strings held in memory. It is enough to demonstrate
multi-tenant plant accounts and role-based views without pulling in a
database. Swap for real JWT + a user table when you productionise.
"""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional, Dict

# username -> user record
USERS: Dict[str, dict] = {}
# token -> username
SESSIONS: Dict[str, str] = {}

ROLE_OPERATOR = "operator"
ROLE_MANAGER = "manager"

SALT = "metrik-demo-salt"


def _hash(password: str) -> str:
    return hashlib.sha256((SALT + password).encode()).hexdigest()


def register(username: str, password: str, company: str,
             role: str = ROLE_OPERATOR, full_name: str = "") -> dict:
    username = username.strip().lower()
    if username in USERS:
        raise ValueError("That username is already registered.")
    if len(password) < 4:
        raise ValueError("Password must be at least 4 characters.")

    USERS[username] = {
        "username": username,
        "password_hash": _hash(password),
        "company": company.strip() or "Unnamed Plant",
        "role": role if role in (ROLE_OPERATOR, ROLE_MANAGER) else ROLE_OPERATOR,
        "full_name": full_name.strip() or username.title(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return public_user(username)


def login(username: str, password: str) -> Optional[str]:
    """Returns a session token, or None if the credentials do not match."""
    username = username.strip().lower()
    user = USERS.get(username)
    if not user or user["password_hash"] != _hash(password):
        return None
    token = secrets.token_urlsafe(24)
    SESSIONS[token] = username
    return token


def logout(token: str):
    SESSIONS.pop(token, None)


def user_for_token(token: str) -> Optional[dict]:
    username = SESSIONS.get(token)
    return USERS.get(username) if username else None


def public_user(username: str) -> dict:
    """User record safe to send to the frontend (no password hash)."""
    u = USERS[username]
    return {
        "username": u["username"],
        "company": u["company"],
        "role": u["role"],
        "full_name": u["full_name"],
    }


def seed_demo_account():
    """
    Pre-seeded account so judges can log in instantly during the demo
    without registering. Shown on the login screen.
    """
    if "demo" not in USERS:
        register("demo", "metrik123", "Vasavi Precision Works",
                 role=ROLE_MANAGER, full_name="Plant Manager")