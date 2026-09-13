"""Operator authentication for the actions that change the accountability trail.

Everything a member of the public needs -- the map, forecasts, the alert inbox --
stays open. What does not is anything that writes to the record an official is
held to: raising alerts, sending them, acknowledging and resolving them. On a
public deployment an anonymous caller who could resolve alerts could erase the
evidence the system exists to keep.

v1 uses one shared operator key rather than user accounts. It is the smallest
thing that closes the hole; named accounts, so the trail records who acted, are
recorded as a known limitation.
"""

from __future__ import annotations

import hmac

from app.core.exceptions import AuthenticationRequiredError, OperatorActionsDisabledError

#: The only scheme accepted in the Authorization header.
_BEARER_PREFIX = "bearer "


def verify_operator(authorization: str | None, expected_key: str) -> None:
    """Allow the request only if it carries the configured operator key.

    Args:
        authorization: The raw ``Authorization`` header, if any.
        expected_key: The configured operator key. Empty means none is set.

    Raises:
        OperatorActionsDisabledError: No key is configured. Write actions are then
            refused outright -- a deployment that forgot to set a key must fail
            closed, never fall back to open.
        AuthenticationRequiredError: The header is missing, malformed or wrong.
    """
    if not expected_key:
        raise OperatorActionsDisabledError
    if authorization is None or not authorization.lower().startswith(_BEARER_PREFIX):
        raise AuthenticationRequiredError
    presented = authorization[len(_BEARER_PREFIX) :].strip()
    # Constant-time comparison, so response timing cannot be used to guess the
    # key one character at a time.
    if not hmac.compare_digest(presented.encode(), expected_key.encode()):
        raise AuthenticationRequiredError
