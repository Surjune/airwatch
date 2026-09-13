"""Request dependencies shared by several routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.core.security import verify_operator


def require_operator(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Admit only requests carrying the operator key.

    Raises:
        OperatorActionsDisabledError: No key is configured on this deployment.
        AuthenticationRequiredError: The key is missing or wrong.
    """
    verify_operator(authorization, settings.operator_api_key)


#: Attach to any route that writes to the accountability trail.
OperatorOnly = Depends(require_operator)
