"""Tests for the per-client token bucket.

Time is passed in, so every expectation is exact: no sleeping, no flakiness.
"""

from __future__ import annotations

import pytest

from app.core.rate_limit import TokenBucketLimiter

PER_MINUTE = 60  # one token per second, which keeps the arithmetic legible


def limiter(per_minute: int = PER_MINUTE, sweep_threshold: int = 1000) -> TokenBucketLimiter:
    return TokenBucketLimiter(per_minute, sweep_threshold=sweep_threshold)


def spend(bucket: TokenBucketLimiter, client: str, count: int, now: float = 0.0) -> None:
    for _ in range(count):
        assert bucket.check(client, now).allowed


class TestAllowance:
    def test_a_new_client_may_burst_up_to_the_full_allowance(self) -> None:
        bucket = limiter()
        spend(bucket, "a", PER_MINUTE)
        assert not bucket.check("a", 0.0).allowed

    def test_remaining_counts_down_to_zero(self) -> None:
        bucket = limiter(per_minute=3)
        assert [bucket.check("a", 0.0).remaining for _ in range(3)] == [2, 1, 0]

    def test_a_refusal_says_when_to_retry(self) -> None:
        bucket = limiter()
        spend(bucket, "a", PER_MINUTE)

        decision = bucket.check("a", 0.0)

        assert decision.remaining == 0
        assert decision.retry_after_seconds == 1
        assert decision.limit == PER_MINUTE

    def test_the_retry_hint_is_honest(self) -> None:
        bucket = limiter()
        spend(bucket, "a", PER_MINUTE)
        wait = bucket.check("a", 0.0).retry_after_seconds

        assert bucket.check("a", float(wait)).allowed

    def test_a_refused_request_does_not_cost_a_token(self) -> None:
        bucket = limiter()
        spend(bucket, "a", PER_MINUTE)
        for _ in range(50):
            assert not bucket.check("a", 0.0).allowed

        # Hammering while refused must not dig a deeper hole than one second.
        assert bucket.check("a", 1.0).allowed


class TestRefill:
    def test_sustained_rate_is_held_to_the_limit(self) -> None:
        bucket = limiter()
        spend(bucket, "a", PER_MINUTE)

        # At one token per second, 30 seconds buys exactly 30 more requests.
        allowed = sum(bucket.check("a", 30.0).allowed for _ in range(40))
        assert allowed == 30

    def test_idle_time_never_banks_more_than_one_burst(self) -> None:
        bucket = limiter()
        bucket.check("a", 0.0)

        allowed = sum(bucket.check("a", 3600.0).allowed for _ in range(PER_MINUTE * 2))
        assert allowed == PER_MINUTE

    def test_a_clock_that_goes_backwards_grants_nothing(self) -> None:
        bucket = limiter()
        spend(bucket, "a", PER_MINUTE, now=100.0)
        assert not bucket.check("a", 50.0).allowed


def test_clients_are_limited_independently() -> None:
    bucket = limiter()
    spend(bucket, "a", PER_MINUTE)

    assert not bucket.check("a", 0.0).allowed
    assert bucket.check("b", 0.0).allowed


class TestMemory:
    def test_forgets_clients_whose_buckets_have_refilled(self) -> None:
        bucket = limiter(sweep_threshold=10)
        for index in range(10):
            bucket.check(f"old-{index}", 0.0)

        # A minute later every old bucket is full again; the next arrival pushes
        # the count over the threshold and the sweep drops them.
        bucket.check("new", 120.0)

        assert bucket.tracked_clients == 1

    def test_keeps_clients_still_under_restriction(self) -> None:
        bucket = limiter(sweep_threshold=2)
        spend(bucket, "heavy", PER_MINUTE)
        bucket.check("b", 0.0)
        bucket.check("c", 1.0)  # over the threshold: the sweep runs here

        # Forgetting "heavy" would hand it a fresh burst. One second has refilled
        # exactly one token, so it gets one request and no more.
        assert bucket.check("heavy", 1.0).allowed
        assert not bucket.check("heavy", 1.0).allowed


@pytest.mark.parametrize("bad", [0, -5])
def test_rejects_a_limit_that_allows_nothing(bad: int) -> None:
    with pytest.raises(ValueError, match="at least one request"):
        TokenBucketLimiter(bad, sweep_threshold=10)
