"""Google Gemini client -- reading photographs and writing alert briefs.

Two jobs, both deliberately narrow:

* **Reading a residents' photograph** for a *visible* pollution source -- smoke
  from burning waste, dust from a site, exhaust. It never estimates a
  concentration: a photograph cannot measure one, and the haze index already
  says what a camera can.
* **Writing a brief** for an official from an alert's own figures. The model
  is handed the facts as text and told to use nothing else; the service then
  checks every figure in the result against those facts before showing it.

Both requests ask for a JSON response against a schema, so the answer is parsed
and validated like any other upstream payload rather than scraped from prose.
The key travels in the ``x-goog-api-key`` header, never in the URL.

A model that is busy, rate-limited or slow is not retried: the next model in
``GEMINI_MODELS`` is asked instead, and every answer records which model wrote it.
"""

from __future__ import annotations

import base64
import json

from pydantic import BaseModel, Field, ValidationError

from app.core.constants import (
    GEMINI_ACTION_MAX_CHARS,
    GEMINI_ATTEMPTS_PER_MODEL,
    GEMINI_BASE_URL,
    GEMINI_BRIEF_MAX_CHARS,
    GEMINI_MODELS,
    GEMINI_OBSERVATION_MAX_CHARS,
    GEMINI_TEMPERATURE,
    GEMINI_TIMEOUT_SECONDS,
)
from app.core.enums import VisibleSource
from app.core.exceptions import (
    UpstreamError,
    UpstreamRateLimitedError,
    UpstreamResponseError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from app.core.logging import get_logger
from app.external.base import JsonValue, UpstreamClient

logger = get_logger(__name__)

#: Header Gemini reads the key from.
_KEY_HEADER = "x-goog-api-key"

#: The finish reason of a response that completed normally.
_COMPLETED = "STOP"

_PHOTO_PROMPT = (
    "A resident of an Indian city submitted this photograph to an air-quality platform as "
    "evidence of pollution. Describe only what is visible in it.\n"
    "- visible_source: the single most clearly visible source of air pollution. Use "
    "haze_without_visible_source if the air looks hazy or smoggy but nothing in frame shows "
    "where it comes from, none_visible if the air looks clear and nothing is emitting, and "
    "not_outdoor if this is not a photograph of outdoor air (a room, a screenshot, a document).\n"
    "- confidence: your confidence in that choice, from 0 to 1.\n"
    "- observation: one factual sentence of at most 40 words naming what in the image supports "
    "the choice.\n"
    "Do not estimate a concentration, an AQI or a health effect. Do not identify people, "
    "vehicle number plates, or who owns a building."
)

_BRIEF_PROMPT = (
    "Write a brief for a district official about an air-quality alert, using only the facts "
    "below.\n"
    "- summary: two or three plain sentences. Say where it is, what was measured against what "
    "the nearby monitors predicted, and, if a likely source is listed, name it with its "
    "plausibility and call it a candidate to inspect, not an established cause.\n"
    "- suggested_action: one practical sentence on what to inspect first.\n"
    "Rules: do not write any number that does not appear in the facts, and copy dates, times "
    "and figures exactly as they are written there. Do not add sources, "
    "causes, health effects, penalties or laws that are not in the facts.\n\n"
    "Facts:\n"
)

_PHOTO_SCHEMA: dict[str, JsonValue] = {
    "type": "OBJECT",
    "properties": {
        "visible_source": {"type": "STRING", "enum": [member.value for member in VisibleSource]},
        "confidence": {"type": "NUMBER"},
        "observation": {"type": "STRING"},
    },
    "required": ["visible_source", "confidence", "observation"],
}

_BRIEF_SCHEMA: dict[str, JsonValue] = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "suggested_action": {"type": "STRING"},
    },
    "required": ["summary", "suggested_action"],
}


class PhotoReading(BaseModel):
    """What Gemini sees in a photograph."""

    visible_source: VisibleSource
    #: The model's own confidence. Not calibrated against ground truth, and
    #: labelled as the model's wherever it is shown.
    confidence: float = Field(ge=0.0, le=1.0)
    observation: str = Field(min_length=1, max_length=GEMINI_OBSERVATION_MAX_CHARS)
    #: The model that answered.
    model: str = ""


class BriefText(BaseModel):
    """A plain-language brief for one alert, before it is checked against its facts."""

    summary: str = Field(min_length=1, max_length=GEMINI_BRIEF_MAX_CHARS)
    suggested_action: str = Field(min_length=1, max_length=GEMINI_ACTION_MAX_CHARS)
    #: The model that answered.
    model: str = ""


class GeminiClient(UpstreamClient):
    """Typed client for Gemini's ``generateContent`` endpoint."""

    provider_name = "Google Gemini"
    base_url = GEMINI_BASE_URL

    def __init__(self, api_key: str, **kwargs: object) -> None:
        kwargs.setdefault("timeout_seconds", GEMINI_TIMEOUT_SECONDS)
        kwargs.setdefault("max_attempts", GEMINI_ATTEMPTS_PER_MODEL)
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._api_key = api_key

    async def read_photo(self, jpeg: bytes) -> PhotoReading:
        """Name the pollution source visible in a JPEG, if any.

        Raises:
            UpstreamResponseError: The answer was missing, blocked, or not the
                shape the schema demands.
            UpstreamError: The request failed.
        """
        parts: list[JsonValue] = [
            {"text": _PHOTO_PROMPT},
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(jpeg).decode()}},
        ]
        model, document = await self._generate(parts, _PHOTO_SCHEMA)
        reading = self._validated(PhotoReading, document).model_copy(update={"model": model})
        logger.info(
            "gemini.photo_read",
            visible_source=reading.visible_source.value,
            confidence=round(reading.confidence, 2),
            model=model,
        )
        return reading

    async def write_brief(self, facts: str) -> BriefText:
        """Write an alert brief from the given facts and nothing else.

        Raises:
            UpstreamResponseError: The answer was missing, blocked, or malformed.
            UpstreamError: The request failed.
        """
        parts: list[JsonValue] = [{"text": _BRIEF_PROMPT + facts}]
        model, document = await self._generate(parts, _BRIEF_SCHEMA)
        return self._validated(BriefText, document).model_copy(update={"model": model})

    async def _generate(
        self, parts: list[JsonValue], schema: dict[str, JsonValue]
    ) -> tuple[str, JsonValue]:
        """Ask each model in turn until one answers; return which one did, and its answer.

        Raises:
            UpstreamError: Every model was busy, rate-limited or slow (the last
                one's error is raised), or a model answered with something unusable.
        """
        busy: UpstreamError | None = None
        for model in GEMINI_MODELS:
            path = f"/models/{model}:generateContent"
            try:
                response = await self.post_json(
                    path,
                    {
                        "contents": [{"parts": parts}],
                        "generationConfig": {
                            "temperature": GEMINI_TEMPERATURE,
                            "responseMimeType": "application/json",
                            "responseSchema": schema,
                        },
                    },
                    headers={_KEY_HEADER: self._api_key},
                )
            except (
                UpstreamRateLimitedError,
                UpstreamTimeoutError,
                UpstreamUnavailableError,
            ) as error:
                logger.warning("gemini.model_busy", model=model, error_code=error.code)
                busy = error
                continue
            return model, self._answer(self._decode(response, path))
        if busy is None:  # pragma: no cover - GEMINI_MODELS is never empty.
            raise UpstreamUnavailableError(self.provider_name, "No Gemini model is configured.")
        raise busy

    def _answer(self, payload: JsonValue) -> JsonValue:
        """The JSON document inside the first candidate's text.

        Raises:
            UpstreamResponseError: No candidate, a candidate stopped for any
                reason other than completing (safety, length), or text that is
                not JSON.
        """
        candidates = payload.get("candidates") if isinstance(payload, dict) else None
        if not isinstance(candidates, list) or not candidates:
            raise UpstreamResponseError(self.provider_name, "Gemini returned no answer.")
        candidate = candidates[0]
        if not isinstance(candidate, dict):
            raise UpstreamResponseError(self.provider_name, "Gemini's answer was malformed.")
        finish = candidate.get("finishReason")
        if finish != _COMPLETED:
            raise UpstreamResponseError(
                self.provider_name,
                f"Gemini did not complete its answer (finish reason {finish}).",
                details={"finish_reason": str(finish)},
            )
        content = candidate.get("content")
        raw_parts = content.get("parts") if isinstance(content, dict) else None
        texts = [
            part["text"]
            for part in (raw_parts if isinstance(raw_parts, list) else [])
            if isinstance(part, dict)
            and isinstance(part.get("text"), str)
            and not part.get("thought")
        ]
        try:
            return json.loads("".join(str(text) for text in texts))  # type: ignore[no-any-return]
        except ValueError as error:
            raise UpstreamResponseError(
                self.provider_name, "Gemini's answer was not the JSON its schema requires."
            ) from error

    def _validated[ModelT: BaseModel](self, model: type[ModelT], document: JsonValue) -> ModelT:
        try:
            return model.model_validate(document)
        except ValidationError as error:
            raise UpstreamResponseError(
                self.provider_name,
                f"Gemini's answer did not match the {model.__name__} schema.",
                details={"errors": error.error_count()},
            ) from error
