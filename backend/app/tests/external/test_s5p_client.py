"""Tests for the Sentinel-5P client.

Earth Engine itself is never called: the two methods that touch it are stubbed,
and what is tested is everything around them -- credential checks, error
mapping, and turning reduced features into cell means.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import ee
import pytest

from app.core.config import Settings
from app.core.constants import SATELLITE_MIN_PIXELS
from app.core.enums import SatelliteProduct
from app.core.exceptions import (
    MissingCredentialError,
    UpstreamResponseError,
    UpstreamUnavailableError,
)
from app.external.s5p_client import Sentinel5PClient

DAY = date(2026, 9, 10)
CELLS = {"86608b687ffffff": [(77.0, 28.5), (77.1, 28.5), (77.1, 28.6)]}


def configured(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "gee_service_account_email": "svc@project.iam.gserviceaccount.com",
            "gee_private_key_path": "C:/keys/key.json",
            "gee_project_id": "project",
        }
    )


@pytest.fixture
def client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Sentinel5PClient:
    monkeypatch.setattr(ee, "ServiceAccountCredentials", lambda *a, **k: object())
    monkeypatch.setattr(ee, "Initialize", lambda *a, **k: None)
    created = Sentinel5PClient(configured(settings))
    monkeypatch.setattr(created, "_images", lambda *a, **k: SimpleNamespace(mean=object))
    return created


def feature(cell: str, mean: float | None, count: int | None) -> dict[str, Any]:
    return {"properties": {"cell": cell, "mean": mean, "count": count}}


class TestCredentials:
    @pytest.mark.parametrize(
        ("missing", "env_var"),
        [
            ("gee_service_account_email", "GEE_SERVICE_ACCOUNT_EMAIL"),
            ("gee_private_key_path", "GEE_PRIVATE_KEY_PATH"),
            ("gee_project_id", "GEE_PROJECT_ID"),
        ],
    )
    def test_each_setting_is_required(self, settings: Settings, missing: str, env_var: str) -> None:
        incomplete = configured(settings).model_copy(update={missing: ""})
        with pytest.raises(MissingCredentialError, match=env_var):
            Sentinel5PClient(incomplete)

    def test_a_refused_project_is_a_typed_upstream_error(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ee, "ServiceAccountCredentials", lambda *a, **k: object())

        def refuse(*_: object, **__: object) -> None:
            raise ee.EEException("Caller does not have required permission to use project")

        monkeypatch.setattr(ee, "Initialize", refuse)
        with pytest.raises(UpstreamUnavailableError, match="required permission"):
            Sentinel5PClient(configured(settings))


class TestDailyMeans:
    def test_returns_each_observed_cell(
        self, client: Sentinel5PClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(client, "_count", lambda images: 2)
        monkeypatch.setattr(
            client, "_reduce", lambda image, cells: [feature("86608b687ffffff", 5.7e-5, 40)]
        )

        means = client.daily_cell_means(SatelliteProduct.NO2, CELLS, DAY)

        assert len(means) == 1
        assert means[0].value == pytest.approx(5.7e-5)
        assert means[0].pixel_count == 40

    def test_a_day_without_an_overpass_returns_nothing_rather_than_zero(
        self, client: Sentinel5PClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(client, "_count", lambda images: 0)
        assert client.daily_cell_means(SatelliteProduct.NO2, CELLS, DAY) == []

    def test_a_fully_clouded_cell_is_omitted(
        self, client: Sentinel5PClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(client, "_count", lambda images: 1)
        monkeypatch.setattr(client, "_reduce", lambda image, cells: [feature("a", None, 0)])
        assert client.daily_cell_means(SatelliteProduct.CO, CELLS, DAY) == []

    def test_a_thinly_observed_cell_is_omitted(
        self, client: Sentinel5PClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(client, "_count", lambda images: 1)
        monkeypatch.setattr(
            client, "_reduce", lambda image, cells: [feature("a", 1.0, SATELLITE_MIN_PIXELS - 1)]
        )
        assert client.daily_cell_means(SatelliteProduct.AEROSOL_INDEX, CELLS, DAY) == []

    def test_a_malformed_feature_is_an_error_not_a_skip(
        self, client: Sentinel5PClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(client, "_count", lambda images: 1)
        monkeypatch.setattr(client, "_reduce", lambda image, cells: [{"geometry": {}}])
        with pytest.raises(UpstreamResponseError):
            client.daily_cell_means(SatelliteProduct.SO2, CELLS, DAY)

    def test_an_earth_engine_failure_is_a_typed_upstream_error(
        self, client: Sentinel5PClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail(images: object) -> int:
            raise ee.EEException("Computation timed out.")

        monkeypatch.setattr(client, "_count", fail)
        with pytest.raises(UpstreamUnavailableError, match="timed out"):
            client.daily_cell_means(SatelliteProduct.NO2, CELLS, DAY)
