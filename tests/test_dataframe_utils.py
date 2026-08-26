import datetime as dt

import numpy as np
import pandas as pd

from app.services.dataframe_utils import filter_clinical_date_range, parse_mixed_dates, records_with_nulls


def test_records_with_nulls_preserves_zero_and_serializes_missing_as_none():
    data = pd.DataFrame(
        {
            "attempts": [0, np.nan],
            "independent_rate": [0.0, np.nan],
            "phase": ["Linha de base", None],
        }
    )
    records = records_with_nulls(data)
    assert records[0] == {"attempts": 0.0, "independent_rate": 0.0, "phase": "Linha de base"}
    assert records[1] == {"attempts": None, "independent_rate": None, "phase": None}


def test_records_with_nulls_converts_dates_and_numpy_scalars():
    data = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-07-31")],
            "count": [np.int64(3)],
            "created": [dt.date(2026, 7, 30)],
        }
    )
    assert records_with_nulls(data) == [
        {"date": "2026-07-31T00:00:00", "count": 3, "created": "2026-07-30"}
    ]


def test_records_with_nulls_handles_empty_dataframe():
    assert records_with_nulls(pd.DataFrame()) == []


def test_parse_mixed_dates_accepts_iso_and_brazilian_formats():
    parsed = parse_mixed_dates(["2026-07-01", "02/07/2026", "inválida"])
    assert parsed.iloc[0] == pd.Timestamp("2026-07-01")
    assert parsed.iloc[1] == pd.Timestamp("2026-07-02")
    assert pd.isna(parsed.iloc[2])


def test_filter_date_range_accepts_independent_start_or_end_boundaries():
    data = pd.DataFrame(
        {
            "date": ["01/07/2026", "2026-07-15", "31/07/2026", "inválida"],
            "value": [1, 2, 3, 4],
        }
    )
    from_start = filter_clinical_date_range(data, start="2026-07-15")
    until_end = filter_clinical_date_range(data, end="2026-07-15")
    assert from_start["value"].tolist() == [2, 3]
    assert until_end["value"].tolist() == [1, 2]
