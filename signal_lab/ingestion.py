"""Strict validation for minute-step input files."""
from __future__ import annotations

from io import StringIO
from typing import IO
import math

import pandas as pd

REQUIRED_COLUMNS = {"timestamp", "steps"}
OPTIONAL_COLUMNS = {"source", "device", "worn"}
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_ROWS = 750_000
MAX_SPAN_DAYS = 400


class InputValidationError(ValueError):
    """Raised when data cannot safely represent minute-level observations."""


def _parse_worn(value: object) -> object:
    if pd.isna(value) or value == "":
        return pd.NA
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    raise InputValidationError("worn values must be true, false, or blank")


def load_csv(source: str | IO[str], *, timezone: str = "Asia/Kolkata") -> pd.DataFrame:
    """Read CSV data and apply the same validation as dataframe input."""
    if hasattr(source, "read"):
        content = source.read()
    else:
        content = source
    if isinstance(content, bytes):
        if len(content) > MAX_FILE_BYTES:
            raise InputValidationError("file exceeds the 25 MB prototype limit")
        content = content.decode("utf-8")
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise InputValidationError("file exceeds the 25 MB prototype limit")
    try:
        frame = pd.read_csv(StringIO(content))
    except Exception as exc:
        raise InputValidationError(f"could not read CSV: {exc}") from exc
    return validate_records(frame, timezone=timezone)


def validate_records(frame: pd.DataFrame, *, timezone: str = "Asia/Kolkata") -> pd.DataFrame:
    """Validate, localize, sort and safely deduplicate minute observations."""
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise InputValidationError(f"missing required column(s): {', '.join(sorted(missing))}")
    unknown = set(frame.columns) - REQUIRED_COLUMNS - OPTIONAL_COLUMNS
    if unknown:
        raise InputValidationError(f"unsupported column(s): {', '.join(sorted(unknown))}")
    if len(frame) == 0:
        raise InputValidationError("file contains no observations")
    if len(frame) > MAX_ROWS:
        raise InputValidationError(f"file exceeds the {MAX_ROWS:,}-row prototype limit")

    data = frame.copy()[[c for c in ["timestamp", "steps", "source", "device", "worn"] if c in frame]]
    raw_timestamps = data["timestamp"]
    if raw_timestamps.isna().any() or (raw_timestamps.astype(str).str.strip() == "").any():
        raise InputValidationError("timestamp cannot be blank")
    parsed = [pd.Timestamp(value) for value in raw_timestamps]
    aware = [stamp.tzinfo is not None and stamp.utcoffset() is not None for stamp in parsed]
    if any(aware) and not all(aware):
        raise InputValidationError("timestamps cannot mix naive and timezone-aware values")
    try:
        if all(aware):
            # Convert one at a time so an aware export spanning a DST offset
            # transition remains valid even when its source uses fixed offsets.
            timestamps = pd.DatetimeIndex([stamp.tz_convert(timezone) for stamp in parsed])
        else:
            timestamps = pd.DatetimeIndex(parsed).tz_localize(timezone, ambiguous="raise", nonexistent="raise")
    except Exception as exc:
        raise InputValidationError(f"invalid or ambiguous local timestamp: {exc}") from exc
    if ((timestamps.second != 0) | (timestamps.microsecond != 0) | (timestamps.nanosecond != 0)).any():
        raise InputValidationError("sub-minute records are not allowed")
    data["timestamp"] = timestamps

    def parse_steps(value: object) -> object:
        if pd.isna(value) or (isinstance(value, str) and not value.strip()):
            return pd.NA
        try:
            number = float(value)
        except (ValueError, TypeError) as exc:
            raise InputValidationError("steps must be non-negative integer counts or blank") from exc
        if not math.isfinite(number) or number < 0 or not number.is_integer():
            raise InputValidationError("steps must be finite, non-negative integer counts or blank")
        return int(number)

    data["steps"] = pd.array([parse_steps(v) for v in data["steps"]], dtype="Int64")
    if "worn" in data:
        data["worn"] = pd.array([_parse_worn(v) for v in data["worn"]], dtype="boolean")
        invalid_nonwear = (data["worn"] == False) & data["steps"].notna() & (data["steps"] > 0)
        if invalid_nonwear.any():
            raise InputValidationError("positive steps conflict with documented worn=false")
    else:
        data["worn"] = pd.array([pd.NA] * len(data), dtype="boolean")

    for column in ("source", "device"):
        if column in data:
            values = data[column].dropna().astype(str).str.strip()
            values = values[values != ""]
            if values.nunique() > 1:
                raise InputValidationError(f"only one {column} is allowed per analysis")
            data[column] = data[column].replace(r"^\s*$", pd.NA, regex=True)

    if (data["timestamp"].max().date() - data["timestamp"].min().date()).days > MAX_SPAN_DAYS:
        raise InputValidationError(f"date span exceeds the {MAX_SPAN_DAYS}-day prototype limit")
    key_columns = [c for c in data.columns]
    data = data.drop_duplicates().sort_values("timestamp").reset_index(drop=True)
    duplicated_minutes = data.duplicated("timestamp", keep=False)
    if duplicated_minutes.any():
        conflicts = data.loc[duplicated_minutes].groupby("timestamp", dropna=False).apply(
            lambda g: len(g.drop_duplicates()) > 1, include_groups=False
        )
        if conflicts.any():
            raise InputValidationError("conflicting records found for the same minute")
        data = data.drop_duplicates("timestamp")
    return data
