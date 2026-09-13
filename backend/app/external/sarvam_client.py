"""Sarvam AI client -- speech for the voice guide.

The one upstream that produces nothing AirWatch measures. It turns a paragraph
of the guide into speech in Hindi, Tamil or Indian English, so a resident who
does not read English can still be told what a screen is for.

Two properties of the API shape the client:

* The audio comes back **base64-encoded inside JSON** (``audios``: one string
  per input), not as a binary body, so it is decoded and checked here. A body
  that decodes to nothing is an error, not a silent clip.
* The subscription key travels in the ``api-subscription-key`` header, never in
  the URL, so an upstream failure cannot write it into a log line.
"""

from __future__ import annotations

import base64
import binascii

from app.core.constants import (
    SARVAM_BASE_URL,
    SARVAM_TTS_MAX_CHARACTERS,
    SARVAM_TTS_MODEL,
    SARVAM_TTS_PATH,
    SARVAM_TTS_TIMEOUT_SECONDS,
    VOICE_GUIDE_AUDIO_CODEC,
    VOICE_GUIDE_PACE,
    VOICE_GUIDE_SAMPLE_RATE_HZ,
)
from app.core.exceptions import UpstreamResponseError
from app.core.logging import get_logger
from app.external.base import UpstreamClient

logger = get_logger(__name__)

#: Header Sarvam reads the subscription key from.
_KEY_HEADER = "api-subscription-key"


class SarvamSpeechClient(UpstreamClient):
    """Typed client for Sarvam's text-to-speech endpoint."""

    provider_name = "Sarvam AI"
    base_url = SARVAM_BASE_URL

    def __init__(self, api_key: str, **kwargs: object) -> None:
        kwargs.setdefault("timeout_seconds", SARVAM_TTS_TIMEOUT_SECONDS)
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._api_key = api_key

    async def synthesise(self, text: str, *, language_code: str, speaker: str) -> bytes:
        """Speak one paragraph and return the encoded audio.

        Args:
            text: What to say. At most :data:`SARVAM_TTS_MAX_CHARACTERS`.
            language_code: BCP-47 code such as ``"ta-IN"``.
            speaker: A Bulbul v3 voice name.

        Returns:
            The audio, encoded as :data:`VOICE_GUIDE_AUDIO_CODEC`.

        Raises:
            ValueError: The text is empty or longer than one request accepts --
                a fault in the script, caught before spending a request on it.
            UpstreamResponseError: The response carried no decodable audio.
            UpstreamError: The request failed.
        """
        if not text.strip():
            raise ValueError("Cannot synthesise empty text.")
        if len(text) > SARVAM_TTS_MAX_CHARACTERS:
            raise ValueError(
                f"Text of {len(text)} characters exceeds the {SARVAM_TTS_MAX_CHARACTERS} "
                "a single Sarvam request accepts."
            )

        response = await self.post_json(
            SARVAM_TTS_PATH,
            {
                "text": text,
                "language_code": language_code,
                "speaker": speaker,
                "model": SARVAM_TTS_MODEL,
                "pace": VOICE_GUIDE_PACE,
                "speech_sample_rate": VOICE_GUIDE_SAMPLE_RATE_HZ,
                "output_audio_codec": VOICE_GUIDE_AUDIO_CODEC,
            },
            headers={_KEY_HEADER: self._api_key},
        )
        audio = self._audio(self._decode(response, SARVAM_TTS_PATH))
        logger.info(
            "sarvam.synthesised",
            language_code=language_code,
            speaker=speaker,
            characters=len(text),
            audio_bytes=len(audio),
        )
        return audio

    def _audio(self, payload: object) -> bytes:
        """Extract and decode the single clip from a response body."""
        if not isinstance(payload, dict):
            raise UpstreamResponseError(
                self.provider_name,
                f"Sarvam returned {type(payload).__name__}, expected an object.",
            )
        audios = payload.get("audios")
        if not isinstance(audios, list) or not audios or not isinstance(audios[0], str):
            raise UpstreamResponseError(
                self.provider_name,
                "Sarvam response did not contain an 'audios' array of strings.",
            )
        try:
            audio = base64.b64decode(audios[0], validate=True)
        except binascii.Error as error:
            raise UpstreamResponseError(
                self.provider_name, "Sarvam returned audio that was not valid base64."
            ) from error
        if not audio:
            raise UpstreamResponseError(self.provider_name, "Sarvam returned an empty clip.")
        return audio
