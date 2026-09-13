"""Per-client request limiting, as a token bucket.

v1 is anonymous, so a limit per caller is the only thing between the API and a
scraper or a runaway client. The limiter is pure: time is passed in, so its
behaviour is tested exactly rather than by sleeping.

**Why a token bucket.** It costs two numbers per client, whatever the rate,
where a log of request times would hold up to a minute's worth of timestamps for
every address. It also allows a short burst up to the full allowance -- a
dashboard loading several panels at once -- while holding the sustained rate to
the configured limit.

**Why forgetting is safe.** A client whose bucket has refilled completely is in
exactly the state of a client never seen, so dropping it loses nothing. That is
what keeps memory bounded when requests arrive from many addresses.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass

#: Seconds per minute, converting the configured per-minute limit to a refill rate.
_SECONDS_PER_MINUTE = 60.0


@dataclass(frozen=True, slots=True)
class RateDecision:
    """Whether one request may proceed, and what the caller should be told."""

    allowed: bool
    limit: int
    remaining: int
    #: Whole seconds until another request would be allowed. Zero when allowed.
    retry_after_seconds: int


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketLimiter:
    """Allow up to ``per_minute`` requests per client, sustained, with bursts."""

    def __init__(self, per_minute: int, *, sweep_threshold: int) -> None:
        """Create a limiter.

        Args:
            per_minute: Sustained requests allowed per client per minute, which
                is also the largest burst.
            sweep_threshold: Number of tracked clients above which fully
                refilled buckets are forgotten.

        Raises:
            ValueError: A limit or threshold below one.
        """
        if per_minute < 1:
            raise ValueError("A rate limit must allow at least one request per minute.")
        if sweep_threshold < 1:
            raise ValueError("The sweep threshold must be at least one client.")
        self._capacity = float(per_minute)
        self._limit = per_minute
        self._refill_per_second = per_minute / _SECONDS_PER_MINUTE
        self._sweep_threshold = sweep_threshold
        self._buckets: dict[str, _Bucket] = {}
        # Requests are admitted on the event loop, but a limiter shared with a
        # threadpool must not lose an update to an interleaved read-modify-write.
        self._lock = threading.Lock()

    @property
    def tracked_clients(self) -> int:
        """How many clients currently hold a partly spent bucket."""
        return len(self._buckets)

    def check(self, client: str, now: float) -> RateDecision:
        """Spend one token for ``client`` if it has one.

        Args:
            client: The key being limited, normally the caller's address.
            now: A monotonic time in seconds.
        """
        with self._lock:
            bucket = self._buckets.get(client)
            if bucket is None:
                bucket = _Bucket(tokens=self._capacity, updated_at=now)
                self._buckets[client] = bucket
            else:
                elapsed = max(now - bucket.updated_at, 0.0)
                bucket.tokens = min(
                    self._capacity, bucket.tokens + elapsed * self._refill_per_second
                )
                bucket.updated_at = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                decision = RateDecision(
                    allowed=True,
                    limit=self._limit,
                    remaining=math.floor(bucket.tokens),
                    retry_after_seconds=0,
                )
            else:
                decision = RateDecision(
                    allowed=False,
                    limit=self._limit,
                    remaining=0,
                    retry_after_seconds=math.ceil((1.0 - bucket.tokens) / self._refill_per_second),
                )

            if len(self._buckets) > self._sweep_threshold:
                self._forget_refilled(now)
            return decision

    def _forget_refilled(self, now: float) -> None:
        """Drop every bucket that has refilled, which is indistinguishable from new."""
        self._buckets = {
            client: bucket
            for client, bucket in self._buckets.items()
            if bucket.tokens + (now - bucket.updated_at) * self._refill_per_second < self._capacity
        }
