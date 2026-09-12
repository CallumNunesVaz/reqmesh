"""Logout must revoke the session token, not just clear the cookie.

A JWT stays valid for its full TTL otherwise, so a captured token remained
replayable after the user signed out. Revocation is per-token (``jti``), so
``logout-everywhere`` remains the deliberate all-device action.
"""
from app.core import auth


def test_revoke_token_only_affects_that_token(workspace):
    auth.register_user("lu", "Password123!long", "contributor")
    t1 = auth.create_token("lu", "contributor")
    t2 = auth.create_token("lu", "contributor")
    assert auth.get_user_from_token(t1) is not None
    auth.revoke_token(t1)
    assert auth.get_user_from_token(t1) is None
    assert auth.get_user_from_token(t2) is not None


def test_logout_endpoint_revokes_the_presented_token(guest_client, workspace):
    auth.register_user("lu2", "Password123!long", "contributor")
    token = auth.create_token("lu2", "contributor")
    res = guest_client.post("/api/auth/logout",
                            headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.text
    assert auth.get_user_from_token(token) is None
