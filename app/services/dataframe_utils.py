"""Utilitários seguros para transportar DataFrames pela API clínica."""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd


def _json_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return value


def records_with_nulls(data: pd.DataFrame) -> list[dict[str, Any]]:
    """Converte DataFrame em registros JSON sem transformar ausência em zero."""
    if data.empty:
        return []
    safe = data.astype(object).where(pd.notna(data), None)
    return [
        {key: _json_scalar(value) for key, value in row.items()}
        for row in safe.to_dict(orient="records")
    ]


def parse_mixed_dates(values: Any) -> pd.Series:
    """Interpreta datas ISO e brasileiras sem depender da primeira linha."""
    series = pd.Series(values)
    text_values = series.astype("string").str.strip()
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    iso_mask = text_values.str.match(r"^\d{4}-\d{2}-\d{2}", na=False)
    brazilian_mask = text_values.str.match(r"^\d{2}/\d{2}/\d{4}", na=False)
    if iso_mask.any():
        parsed.loc[iso_mask] = pd.to_datetime(series.loc[iso_mask], errors="coerce", yearfirst=True)
    if brazilian_mask.any():
        parsed.loc[brazilian_mask] = pd.to_datetime(
            series.loc[brazilian_mask], errors="coerce", dayfirst=True
        )
    remaining = ~(iso_mask | brazilian_mask)
    if remaining.any():
        parsed.loc[remaining] = pd.to_datetime(
            series.loc[remaining], errors="coerce", dayfirst=True
        )
    return parsed


def filter_clinical_date_range(
    data: pd.DataFrame,
    start: str | dt.date | None = None,
    end: str | dt.date | None = None,
    *,
    date_column: str = "date",
) -> pd.DataFrame:
    """Filtra limites independentes e preserva as colunas originais."""
    if data.empty or date_column not in data.columns or (start is None and end is None):
        return data
    parsed_dates = parse_mixed_dates(data[date_column])
    mask = parsed_dates.notna()
    if start is not None:
        start_date = pd.to_datetime(start, errors="coerce")
        if pd.isna(start_date):
            raise ValueError("Data inicial inválida.")
        mask &= parsed_dates >= start_date
    if end is not None:
        end_date = pd.to_datetime(end, errors="coerce")
        if pd.isna(end_date):
            raise ValueError("Data final inválida.")
        mask &= parsed_dates <= end_date
    return data.loc[mask].copy()
