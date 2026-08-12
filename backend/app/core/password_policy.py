"""One password policy, for every route that accepts one — and for the CLI.

The rules lived in `api/auth_routes.py`, so they applied to the five HTTP routes
and nothing else: `cli.py reset-admin` checked length alone, and an operator
could set a one-character password out of band that the API would have refused.

Returns a message rather than raising, so the HTTP layer can turn it into a 400
and the CLI into a ClickException without either importing the other's error
types.

Deliberately **not** enforced inside `auth.register_user` / `set_user_password`.
Those are the seams tests and recovery tooling build on; a policy check between
an operator and their own locked-out instance is a trap, and the callers above
are the ones that face a human.
"""

from __future__ import annotations

import re

MIN_PASSWORD_LENGTH = 12

#: bcrypt truncates at 72 bytes, and bcrypt 5 raises rather than truncating.
#: Rejecting here gives the user a real message: `register_user` returned None
#: on the raise, which the API surfaced as a misleading 409 "Registration
#: failed" that looked like a duplicate username.
MAX_PASSWORD_BYTES = 72

PASSWORD_RE = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)'
    r'(?=.*[!@#$%^&*()_+\-=\[\]{};:\"\\|,.<>\/?]).{12,}$'
)

COMPLEXITY_MESSAGE = (
    "Password must contain at least one uppercase letter, one lowercase letter, "
    "one digit, and one special character"
)


def validate_password(password: str, username: str = "") -> str | None:
    """Return why this password is unacceptable, or None if it is fine."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return f"Password must be at most {MAX_PASSWORD_BYTES} bytes"
    if not PASSWORD_RE.match(password):
        return COMPLEXITY_MESSAGE
    if username and username.casefold() in password.casefold():
        return "Password must not contain the username"
    return None
