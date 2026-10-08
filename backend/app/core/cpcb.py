"""How CPCB writes its station figures, wherever they are republished.

data.gov.in's feed and TNPCB's website carry the same CPCB figures in the same
conventions: pollutant labels such as "PM2.5" and "OZONE", timestamps in Indian
Standard Time as ``dd-mm-yyyy HH:MM:SS``, and "NA" for a value the sensor did not
report. Reading them in one place keeps the relays from drifting apart.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Final

from app.core.constants import IST_UTC_OFFSET_MINUTES
from app.core.enums import Pollutant

#: CPCB's pollutant labels, mapped to AirWatch's identifiers. The live feeds
#: write ozone as "OZONE"; the daily bulletin writes it as "O3".
POLLUTANT_LABELS: Final[dict[str, Pollutant]] = {
    "PM2.5": Pollutant.PM25,
    "PM10": Pollutant.PM10,
    "NO2": Pollutant.NO2,
    "SO2": Pollutant.SO2,
    "OZONE": Pollutant.O3,
    "O3": Pollutant.O3,
    "CO": Pollutant.CO,
    "NH3": Pollutant.NH3,
}

#: What CPCB writes when a sensor has no value for the period.
MISSING: Final[str] = "NA"

#: India Standard Time, in which CPCB stamps every figure.
IST: Final[timezone] = timezone(timedelta(minutes=IST_UTC_OFFSET_MINUTES))

_TIMESTAMP_FORMAT = "%d-%m-%Y %H:%M:%S"


def pollutant(label: str) -> Pollutant | None:
    """The pollutant a CPCB label names, or None for one AirWatch does not track."""
    return POLLUTANT_LABELS.get(label.strip().upper())


def parse_timestamp(text: str) -> datetime:
    """A CPCB timestamp, ``dd-mm-yyyy HH:MM:SS`` in IST, as a UTC datetime.

    Raises:
        ValueError: The text is not in CPCB's format.
    """
    # IST -> UTC: CPCB stamps local time; storage is UTC.
    return datetime.strptime(text.strip(), _TIMESTAMP_FORMAT).replace(tzinfo=IST).astimezone(UTC)


def optional_value(raw: str) -> float | None:
    """A figure CPCB may have left out, or None where it wrote "NA" or nothing."""
    text = raw.strip()
    if text == MISSING or not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
