"""Delivering an alert to whatever system an authority actually reads.

A webhook rather than email or SMS, because those are the wrong shape for the
receiving end. A state board runs a grievance tracker or a control-room console;
what it needs is a machine-readable event its own software can file, route and
close, not a message a person has to retype. Anything that does need email can be
subscribed to the same webhook by a gateway the authority controls, which keeps
their contact details out of this system entirely.

Delivery is a separate step from detection on purpose. A slow endpoint would
otherwise stall detection, and a failed one would lose the alert.
"""

from __future__ import annotations

import httpx

from app.core.exceptions import UpstreamResponseError
from app.external.base import JsonValue, UpstreamClient


class WebhookClient(UpstreamClient):
    """Posts an alert payload to a configured endpoint."""

    provider_name = "alert webhook"

    def __init__(self, url: str, **kwargs: object) -> None:
        """Construct a client bound to one endpoint.

        Args:
            url: Full URL to post to. Held as an absolute URL rather than as the
                client's base, because httpx joining an empty path onto a base
                appends a trailing slash -- and a receiver that routes strictly
                would reject `/airwatch/` having published `/airwatch`.
            kwargs: Passed through to the base client, so the retry, timeout and
                error mapping in :class:`UpstreamClient` all apply unchanged.
        """
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._url = url

    def sanitise_path(self, path: str) -> str:
        """Keep the endpoint out of logs.

        A webhook URL is frequently a bearer credential in disguise -- anyone
        holding it can post to the receiving system -- so it is treated like one
        rather than logged in full.
        """
        return "<webhook>"

    async def deliver(self, payload: JsonValue) -> int:
        """Post one alert, returning the status the receiver answered with.

        Raises:
            UpstreamTimeoutError: The endpoint did not respond in time.
            UpstreamUnavailableError: The endpoint could not be reached.
            UpstreamResponseError: The endpoint refused the payload.
        """
        try:
            response = await self.post_json(self._url, payload)
        except httpx.InvalidURL as error:
            raise UpstreamResponseError(
                self.provider_name,
                "The configured webhook URL is not valid.",
            ) from error
        return int(response.status_code)
