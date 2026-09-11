"""Tests for the global error envelope.

The regression these exist for: a handler that cannot serialise its own output
turns a 422 the client could have acted on into an opaque 500. That happened
because Pydantic puts the raised ``ValueError`` object into an error's ``ctx``
when a custom field validator rejects a value, and the handler passed the whole
error list into the response unchanged.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, field_validator

from app.error_handlers import _serialisable_errors, register_error_handlers


class Payload(BaseModel):
    """A body whose validator rejects by raising, as several real ones do."""

    note: str = Field(min_length=1)
    count: int = Field(default=1, ge=1)

    @field_validator("note")
    @classmethod
    def _reject_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A note cannot be blank.")
        return value


@pytest.fixture
def api() -> TestClient:
    """A minimal application carrying only the error handlers."""
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/echo")
    def echo(payload: Payload) -> dict[str, str]:
        return {"note": payload.note}

    return TestClient(app, raise_server_exceptions=False)


class TestValidatorRaisingValueError:
    def test_returns_422_rather_than_500(self, api: TestClient) -> None:
        # The bug: the handler raised while rendering, so the client saw an
        # internal error for a request it could have corrected itself.
        response = api.post("/echo", json={"note": "   "})

        assert response.status_code == 422

    def test_the_body_is_the_standard_envelope(self, api: TestClient) -> None:
        body = api.post("/echo", json={"note": "   "}).json()

        assert body["error"]["code"] == "validation_error"
        assert body["error"]["details"]["fields"][0]["loc"] == ["body", "note"]
        assert "blank" in body["error"]["details"]["fields"][0]["msg"]

    def test_the_response_is_json_serialisable(self, api: TestClient) -> None:
        # Asserting the property directly, not just the status code: a future
        # field that smuggles an unserialisable object into ctx would fail here
        # rather than in production.
        json.dumps(api.post("/echo", json={"note": "   "}).json())


class TestOrdinaryValidationStillWorks:
    def test_a_type_error_is_reported(self, api: TestClient) -> None:
        body = api.post("/echo", json={"note": "ok", "count": "many"}).json()

        fields = body["error"]["details"]["fields"]
        assert any(field["loc"] == ["body", "count"] for field in fields)

    def test_a_missing_field_is_reported(self, api: TestClient) -> None:
        body = api.post("/echo", json={}).json()

        assert body["error"]["details"]["fields"][0]["type"] == "missing"

    def test_malformed_json_is_reported(self, api: TestClient) -> None:
        response = api.post(
            "/echo",
            content=b"{not json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_a_valid_body_passes_through(self, api: TestClient) -> None:
        assert api.post("/echo", json={"note": "fine"}).json() == {"note": "fine"}


class TestErrorRendering:
    def test_drops_the_unserialisable_context(self) -> None:
        rendered = _serialisable_errors(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "note"),
                    "msg": "Value error, blank",
                    "input": "   ",
                    "ctx": {"error": ValueError("blank")},
                }
            ]
        )

        assert "ctx" not in rendered[0]
        json.dumps(rendered)

    def test_truncates_a_long_rejected_input(self) -> None:
        # A request body can be arbitrarily large; a response is not the place
        # to mirror one back in full.
        rendered = _serialisable_errors(
            [{"type": "value_error", "loc": ("body", "note"), "msg": "no", "input": "x" * 10_000}]
        )

        assert len(rendered[0]["input"]) < 1_000

    def test_renders_a_tuple_location_as_a_list(self) -> None:
        rendered = _serialisable_errors(
            [{"type": "missing", "loc": ("body", 0, "note"), "msg": "Field required"}]
        )

        assert rendered[0]["loc"] == ["body", "0", "note"]

    def test_an_error_without_input_is_still_rendered(self) -> None:
        rendered = _serialisable_errors([{"type": "missing", "loc": ("body",), "msg": "required"}])

        assert rendered[0]["type"] == "missing"
        assert "input" not in rendered[0]
