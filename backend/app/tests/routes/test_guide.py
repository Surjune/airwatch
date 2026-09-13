"""Tests for the spoken screen guide endpoints."""

from __future__ import annotations

import base64
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.constants import SARVAM_BASE_URL, SARVAM_TTS_PATH
from app.main import create_app
from app.repositories.session import get_db_session

URL = f"{SARVAM_BASE_URL}{SARVAM_TTS_PATH}"


def bound_to(app: FastAPI, session: Session) -> TestClient:
    """A client whose requests run inside the test's own transaction."""

    def _session() -> Iterator[Any]:
        yield session

    app.dependency_overrides[get_db_session] = _session
    return TestClient(app)


class TestTranscript:
    def test_returns_the_guide_in_the_chosen_language(self, client: TestClient) -> None:
        body = client.get("/v1/guide/citizen", params={"language": "ta"}).json()

        assert body["language"] == "ta"
        assert body["sections"]
        assert body["voice_available"] is False
        path = body["sections"][0]["audio_path"]
        assert path.startswith("/guide/citizen/sections/0/audio?language=ta&v=")

    def test_defaults_to_english(self, client: TestClient) -> None:
        assert client.get("/v1/guide/map").json()["language"] == "en"

    @pytest.mark.parametrize(
        "path", ["/v1/guide/settings", "/v1/guide/map?language=fr"], ids=["screen", "language"]
    )
    def test_refuses_what_has_no_guide(self, client: TestClient, path: str) -> None:
        assert client.get(path).status_code == 422

    def test_refuses_a_malformed_version(self, client: TestClient) -> None:
        response = client.get("/v1/guide/map/sections/0/audio", params={"v": "../../etc"})

        assert response.status_code == 422


@pytest.mark.integration
class TestAudio:
    @pytest.fixture
    def api(self, settings: Settings, session: Session) -> Iterator[TestClient]:
        voiced = settings.model_copy(update={"sarvam_api_key": "sk_test_0123456789"})
        with bound_to(create_app(voiced), session) as client:
            yield client

    @respx.mock(assert_all_mocked=False)
    def test_a_current_version_is_cached_and_any_other_is_not(self, api: TestClient) -> None:
        clip = base64.b64encode(b"mp3 bytes").decode()
        respx.post(URL).mock(return_value=httpx.Response(200, json={"audios": [clip]}))
        transcript = api.get("/v1/guide/map", params={"language": "hi"}).json()
        path = transcript["sections"][0]["audio_path"]

        current = api.get(f"/v1{path}")
        stale = api.get("/v1/guide/map/sections/0/audio", params={"language": "hi", "v": "0" * 12})

        assert current.status_code == 200
        assert current.headers["content-type"] == "audio/mpeg"
        assert current.content == b"mp3 bytes"
        assert "immutable" in current.headers["cache-control"]
        assert stale.headers["cache-control"] == "no-cache"

    def test_a_paragraph_beyond_the_script_is_not_found(self, api: TestClient) -> None:
        assert api.get("/v1/guide/alerts/sections/40/audio").status_code == 404


@pytest.mark.integration
def test_without_a_key_new_speech_is_a_configuration_error(app: FastAPI, session: Session) -> None:
    with bound_to(app, session) as client:
        response = client.get("/v1/guide/map/sections/0/audio", params={"language": "ta"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "missing_credential"
