"""Tests for the operator gate on actions that change the accountability trail.

No database is involved: every request here is refused or admitted before a
session would be opened, which is the property being tested.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import AuthenticationRequiredError
from app.core.security import verify_operator
from app.main import create_app
from app.tests.conftest import OPERATOR_KEY

WRITE_ROUTES = [
    ("post", "/v1/alerts/dispatch"),
    ("post", "/v1/alerts/deliver"),
    ("post", "/v1/alerts/1/acknowledge"),
    ("post", "/v1/alerts/1/resolve"),
]


@pytest.mark.parametrize(("method", "path"), WRITE_ROUTES)
def test_an_anonymous_caller_cannot_change_the_trail(
    client: TestClient, method: str, path: str
) -> None:
    response = getattr(client, method)(path, json={"note": "closing it"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


@pytest.mark.parametrize(("method", "path"), WRITE_ROUTES)
def test_a_wrong_key_is_refused(client: TestClient, method: str, path: str) -> None:
    response = getattr(client, method)(
        path, json={"note": "closing it"}, headers={"Authorization": "Bearer not-the-key"}
    )
    assert response.status_code == 401


def test_a_deployment_without_a_key_fails_closed(settings: Settings) -> None:
    unkeyed = TestClient(create_app(settings.model_copy(update={"operator_api_key": ""})))

    response = unkeyed.post(
        "/v1/alerts/dispatch", headers={"Authorization": f"Bearer {OPERATOR_KEY}"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "operator_actions_disabled"


def test_the_session_check_confirms_a_valid_key(client: TestClient) -> None:
    response = client.get(
        "/v1/operator/session", headers={"Authorization": f"Bearer {OPERATOR_KEY}"}
    )
    assert response.json() == {"authorised": True}


def test_reading_stays_open_to_everyone(client: TestClient) -> None:
    assert client.get("/v1/health").status_code == 200
    assert client.get("/v1/cities").status_code == 200


class TestVerifyOperator:
    def test_accepts_the_scheme_case_insensitively(self) -> None:
        verify_operator(f"bearer {OPERATOR_KEY}", OPERATOR_KEY)

    @pytest.mark.parametrize("header", [None, "", OPERATOR_KEY, f"Basic {OPERATOR_KEY}"])
    def test_refuses_anything_but_a_bearer_token(self, header: str | None) -> None:
        with pytest.raises(AuthenticationRequiredError):
            verify_operator(header, OPERATOR_KEY)


def test_a_short_key_is_rejected_at_startup(settings: Settings) -> None:
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(**{**settings.model_dump(), "operator_api_key": "too-short"})
