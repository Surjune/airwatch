"""Tests for the Sarvam AI text-to-speech client."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
import respx

from app.core.constants import SARVAM_BASE_URL, SARVAM_TTS_MAX_CHARACTERS, SARVAM_TTS_PATH
from app.core.exceptions import UpstreamResponseError
from app.external.sarvam_client import SarvamSpeechClient

API_KEY = "sk_test_0123456789abcdef"
URL = f"{SARVAM_BASE_URL}{SARVAM_TTS_PATH}"
#: The first bytes of an MPEG frame, standing in for a clip.
CLIP = b"\xff\xf3\xc4\xc4 speech"


def audio_response(clip: bytes = CLIP) -> httpx.Response:
    return httpx.Response(
        200, json={"request_id": "r-1", "audios": [base64.b64encode(clip).decode()]}
    )


async def speak(client: SarvamSpeechClient, text: str = "வணக்கம்") -> bytes:
    return await client.synthesise(text, language_code="ta-IN", speaker="kavitha")


@respx.mock
async def test_returns_the_decoded_clip() -> None:
    respx.post(URL).mock(return_value=audio_response())

    async with SarvamSpeechClient(API_KEY) as client:
        assert await speak(client) == CLIP


@respx.mock
async def test_sends_the_key_in_a_header_and_asks_for_mp3() -> None:
    route = respx.post(URL).mock(return_value=audio_response())

    async with SarvamSpeechClient(API_KEY) as client:
        await speak(client)

    request = route.calls.last.request
    assert request.headers["api-subscription-key"] == API_KEY
    # Never in the URL, where a failure would write it into a log line.
    assert API_KEY not in str(request.url)
    body = json.loads(request.content)
    assert body["language_code"] == "ta-IN"
    assert body["speaker"] == "kavitha"
    assert body["output_audio_codec"] == "mp3"


@respx.mock
async def test_a_rejected_key_is_a_typed_error_and_is_not_retried() -> None:
    route = respx.post(URL).mock(
        return_value=httpx.Response(403, json={"error": {"code": "invalid_api_key_error"}})
    )

    async with SarvamSpeechClient(API_KEY, backoff_base_seconds=0) as client:
        with pytest.raises(UpstreamResponseError):
            await speak(client)
    assert route.call_count == 1


@pytest.mark.parametrize(
    "body",
    [
        {"request_id": "r-1"},
        {"audios": []},
        {"audios": ["not base64 at all!"]},
        {"audios": [""]},
    ],
    ids=["no-audios", "empty-list", "bad-base64", "empty-clip"],
)
@respx.mock
async def test_a_response_without_a_usable_clip_is_an_error(body: dict[str, object]) -> None:
    respx.post(URL).mock(return_value=httpx.Response(200, json=body))

    async with SarvamSpeechClient(API_KEY) as client:
        with pytest.raises(UpstreamResponseError):
            await speak(client)


@pytest.mark.parametrize("text", ["", "   ", "x" * (SARVAM_TTS_MAX_CHARACTERS + 1)])
@respx.mock
async def test_text_it_cannot_send_is_refused_before_any_request(text: str) -> None:
    route = respx.post(URL)

    async with SarvamSpeechClient(API_KEY) as client:
        with pytest.raises(ValueError, match=r"synthesise|exceeds"):
            await speak(client, text)
    assert not route.called
