"""Tests for the Google Gemini client."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.core.constants import GEMINI_BASE_URL, GEMINI_MODELS
from app.core.enums import VisibleSource
from app.core.exceptions import UpstreamResponseError, UpstreamUnavailableError
from app.external.gemini_client import GeminiClient

API_KEY = "test-gemini-key-0123456789"
PRIMARY, FALLBACK = GEMINI_MODELS[0], GEMINI_MODELS[-1]


def url(model: str) -> str:
    return f"{GEMINI_BASE_URL}/models/{model}:generateContent"


def answer(document: object, *, finish: str = "STOP", thought: bool = False) -> httpx.Response:
    parts: list[dict[str, object]] = [{"text": json.dumps(document)}]
    if thought:
        parts.insert(0, {"text": "Let me look at the image first.", "thought": True})
    return httpx.Response(
        200, json={"candidates": [{"content": {"parts": parts}, "finishReason": finish}]}
    )


PHOTO = {
    "visible_source": "open_burning",
    "confidence": 0.82,
    "observation": "A pile of waste is burning at the roadside, sending up grey smoke.",
}
BRIEF = {"summary": "PM2.5 read 74 µg/m³.", "suggested_action": "Inspect the landfill."}


@respx.mock
async def test_reads_a_photo_and_records_the_model() -> None:
    respx.post(url(PRIMARY)).mock(return_value=answer(PHOTO))

    async with GeminiClient(API_KEY) as client:
        reading = await client.read_photo(b"jpeg bytes")

    assert reading.visible_source is VisibleSource.OPEN_BURNING
    assert reading.confidence == pytest.approx(0.82)
    assert reading.model == PRIMARY


@respx.mock
async def test_sends_the_key_in_a_header_with_the_image_and_a_schema() -> None:
    route = respx.post(url(PRIMARY)).mock(return_value=answer(PHOTO))

    async with GeminiClient(API_KEY) as client:
        await client.read_photo(b"jpeg bytes")

    request = route.calls.last.request
    assert request.headers["x-goog-api-key"] == API_KEY
    assert API_KEY not in str(request.url)
    body = json.loads(request.content)
    parts = body["contents"][0]["parts"]
    assert parts[1]["inline_data"]["mime_type"] == "image/jpeg"
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert "visible_source" in body["generationConfig"]["responseSchema"]["properties"]


@respx.mock
async def test_a_busy_model_falls_back_to_the_next() -> None:
    respx.post(url(PRIMARY)).mock(return_value=httpx.Response(503, json={"error": "busy"}))
    respx.post(url(FALLBACK)).mock(return_value=answer(BRIEF))

    async with GeminiClient(API_KEY) as client:
        brief = await client.write_brief("Measured: 74 µg/m³")

    assert brief.model == FALLBACK


@respx.mock
async def test_every_model_busy_is_a_typed_error() -> None:
    for model in GEMINI_MODELS:
        respx.post(url(model)).mock(return_value=httpx.Response(503, json={"error": "busy"}))

    async with GeminiClient(API_KEY) as client:
        with pytest.raises(UpstreamUnavailableError):
            await client.write_brief("Measured: 74 µg/m³")


@respx.mock
async def test_thinking_text_is_not_mistaken_for_the_answer() -> None:
    respx.post(url(PRIMARY)).mock(return_value=answer(PHOTO, thought=True))

    async with GeminiClient(API_KEY) as client:
        reading = await client.read_photo(b"jpeg bytes")

    assert reading.visible_source is VisibleSource.OPEN_BURNING


@pytest.mark.parametrize(
    "response",
    [
        answer(PHOTO, finish="SAFETY"),
        httpx.Response(200, json={"candidates": []}),
        httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "not json"}]}, "finishReason": "STOP"}
                ]
            },
        ),
        answer({**PHOTO, "visible_source": "aliens"}),
        answer({**PHOTO, "confidence": 1.5}),
    ],
    ids=["blocked", "no-candidates", "not-json", "unknown-source", "confidence-out-of-range"],
)
@respx.mock
async def test_an_unusable_answer_is_a_typed_error_not_a_model_switch(
    response: httpx.Response,
) -> None:
    # Only the first model is mocked: asking the fallback would raise respx's own
    # unmocked-request error rather than the typed one expected here.
    primary = respx.post(url(PRIMARY)).mock(return_value=response)

    async with GeminiClient(API_KEY) as client:
        with pytest.raises(UpstreamResponseError):
            await client.read_photo(b"jpeg bytes")

    assert primary.call_count == 1
