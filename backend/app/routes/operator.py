"""Operator session check, so the console can confirm a key before offering actions."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.routes.dependencies import OperatorOnly

router = APIRouter(prefix="/operator", tags=["operator"])


class OperatorSessionResponse(BaseModel):
    """Confirmation that the presented key is valid."""

    authorised: bool


@router.get(
    "/session",
    response_model=OperatorSessionResponse,
    summary="Check an operator key",
    dependencies=[OperatorOnly],
)
def operator_session() -> OperatorSessionResponse:
    """Return 200 for a valid key; 401 or 403 otherwise, from the dependency."""
    return OperatorSessionResponse(authorised=True)
