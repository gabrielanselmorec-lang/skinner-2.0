"""Transformações clínicas puras usadas pelo dashboard de habilidades.

Este módulo não depende de Streamlit ou Plotly.  A separação mantém os cálculos
testáveis e impede que a camada visual invente denominadores quando ``attempts``
não está disponível.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.services.dataframe_utils import parse_mixed_dates


BASELINE_PATTERN = r"linha de base|\blb\b|baseline|sondagem"


@dataclass(frozen=True)
class ClinicalMetrics:
    latest: float | None
    simple_mean: float | None
    weighted_mean: float | None
    median: float | None
    slope: float | None
    standard_deviation: float | None
    amplitude: float | None
    variability: str
    sessions: int
    opportunities: int | None


def _number_series(values: Any) -> pd.Series:
    return pd.to_numeric(pd.Series(values), errors="coerce").replace([np.inf, -np.inf], np.nan)


def _optional_round(value: float | int | None, digits: int = 2) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def calculate_weighted_independence(
    data: pd.DataFrame,
    value_column: str = "independent_rate",
    weight_column: str = "attempts",
) -> float | None:
    """Calcula a média ponderada somente com denominadores reais e positivos."""
    if data.empty or value_column not in data or weight_column not in data:
        return None
    values = pd.to_numeric(data[value_column], errors="coerce")
    weights = pd.to_numeric(data[weight_column], errors="coerce")
    valid = values.notna() & weights.notna() & (weights > 0)
    if not valid.any():
        return None
    return _optional_round(np.average(values[valid], weights=weights[valid]))


def calculate_trend_slope(values: Any) -> float | None:
    """Retorna pontos percentuais por observação válida."""
    series = _number_series(values).dropna()
    if len(series) < 2:
        return None
    x = np.arange(len(series), dtype=float)
    return _optional_round(np.polyfit(x, series.to_numpy(dtype=float), 1)[0])


def calculate_variability(values: Any) -> dict[str, float | str | None]:
    series = _number_series(values).dropna()
    if series.empty:
        return {"standard_deviation": None, "amplitude": None, "iqr": None, "classification": "Sem dados"}
    standard_deviation = float(series.std(ddof=0))
    amplitude = float(series.max() - series.min())
    iqr = float(series.quantile(0.75) - series.quantile(0.25))
    if standard_deviation < 10:
        classification = "Baixa"
    elif standard_deviation < 20:
        classification = "Moderada"
    else:
        classification = "Alta"
    return {
        "standard_deviation": _optional_round(standard_deviation),
        "amplitude": _optional_round(amplitude),
        "iqr": _optional_round(iqr),
        "classification": classification,
    }


def calculate_clinical_metrics(data: pd.DataFrame) -> ClinicalMetrics:
    rates = _number_series(data.get("independent_rate", pd.Series(dtype=float))).dropna()
    variability = calculate_variability(rates)
    opportunities = None
    if "attempts" in data:
        attempts = pd.to_numeric(data["attempts"], errors="coerce")
        valid_attempts = attempts[attempts > 0]
        if not valid_attempts.empty:
            opportunities = int(round(valid_attempts.sum()))
    return ClinicalMetrics(
        latest=_optional_round(rates.iloc[-1]) if not rates.empty else None,
        simple_mean=_optional_round(rates.mean()) if not rates.empty else None,
        weighted_mean=calculate_weighted_independence(data),
        median=_optional_round(rates.median()) if not rates.empty else None,
        slope=calculate_trend_slope(rates),
        standard_deviation=variability["standard_deviation"],
        amplitude=variability["amplitude"],
        variability=str(variability["classification"]),
        sessions=int(len(rates)),
        opportunities=opportunities,
    )


def _last_non_empty(values: pd.Series) -> str:
    cleaned = values.dropna().astype(str).str.strip()
    cleaned = cleaned[~cleaned.str.lower().isin(["", "nan", "none", "0"])]
    return cleaned.iloc[-1] if not cleaned.empty else "Não informada"


def prepare_program_sessions(data: pd.DataFrame) -> pd.DataFrame:
    """Normaliza registros de programa sem presumir uma quantidade de tentativas."""
    if data.empty:
        return pd.DataFrame()
    result = data.copy()
    result["date"] = pd.to_datetime(result.get("date"), errors="coerce")
    result = result.dropna(subset=["date"]).sort_values("date", kind="stable").reset_index(drop=True)
    for column in ("independent_rate", "prompt_rate", "success_rate"):
        result[column] = pd.to_numeric(result.get(column), errors="coerce").clip(0, 100)
    if "phase" not in result:
        result["phase"] = ""
    result["phase"] = result["phase"].fillna("").astype(str).str.strip().replace("", "Não informada")
    valid_components = result["independent_rate"].notna() & result["prompt_rate"].notna()
    result["error_rate"] = np.where(
        valid_components,
        (100 - result["independent_rate"] - result["prompt_rate"]).clip(0, 100),
        np.nan,
    )
    result["session_number"] = np.arange(1, len(result) + 1)
    result["session_label"] = result["date"].dt.strftime("%d/%m/%Y")
    duplicate_number = result.groupby("session_label").cumcount() + 1
    duplicate_count = result.groupby("session_label")["session_label"].transform("size")
    result.loc[duplicate_count > 1, "session_label"] += " · " + duplicate_number[duplicate_count > 1].astype(str)
    result["is_baseline"] = result["phase"].str.contains(BASELINE_PATTERN, case=False, na=False, regex=True)
    return result


def prepare_target_sessions(data: pd.DataFrame) -> pd.DataFrame:
    """Agrega alvo/data com média ponderada quando há tentativas reais."""
    if data.empty:
        return pd.DataFrame()
    result = data.copy()
    result["date"] = pd.to_datetime(result.get("date"), errors="coerce")
    result = result.dropna(subset=["date"])
    if "target_name" not in result:
        result["target_name"] = "Alvo"
    result["target_name"] = result["target_name"].fillna("").astype(str).str.strip()
    result = result[result["target_name"] != ""]
    for column in ("attempts", "independent_rate", "prompt_rate", "success_rate"):
        result[column] = pd.to_numeric(result.get(column), errors="coerce")
    result["independent_rate"] = result["independent_rate"].clip(0, 100)
    result["prompt_rate"] = result["prompt_rate"].clip(0, 100)

    rows: list[dict[str, Any]] = []
    for (target_name, date), group in result.groupby(["target_name", "date"], sort=True, dropna=False):
        attempts = group["attempts"]
        valid_weights = attempts.notna() & (attempts > 0)
        total_attempts = float(attempts[valid_weights].sum()) if valid_weights.any() else np.nan

        def aggregate_rate(column: str) -> float:
            values = group[column]
            weighted = valid_weights & values.notna()
            if weighted.any():
                return float(np.average(values[weighted], weights=attempts[weighted]))
            return float(values.mean()) if values.notna().any() else np.nan

        independent_rate = aggregate_rate("independent_rate")
        prompt_rate = aggregate_rate("prompt_rate")
        rows.append(
            {
                "target_name": target_name,
                "date": date,
                "attempts": total_attempts,
                "independent_rate": independent_rate,
                "prompt_rate": prompt_rate,
                "success_rate": aggregate_rate("success_rate"),
                "prompt_type": _last_non_empty(group.get("prompt_type", pd.Series(dtype=str))),
                "evolution": _last_non_empty(group.get("evolution", pd.Series(dtype=str))),
                "phase": _last_non_empty(group.get("phase", pd.Series(dtype=str))),
            }
        )

    prepared = pd.DataFrame(rows).sort_values(["date", "target_name"], kind="stable").reset_index(drop=True)
    valid_components = prepared["independent_rate"].notna() & prepared["prompt_rate"].notna()
    prepared["error_rate"] = np.where(
        valid_components,
        (100 - prepared["independent_rate"] - prepared["prompt_rate"]).clip(0, 100),
        np.nan,
    )
    prepared["has_attempts"] = prepared["attempts"].notna() & (prepared["attempts"] > 0)
    for source, destination in (
        ("independent_rate", "independent_trials"),
        ("prompt_rate", "prompted_trials"),
        ("error_rate", "error_trials"),
    ):
        prepared[destination] = np.where(
            prepared["has_attempts"],
            prepared["attempts"] * prepared[source] / 100,
            np.nan,
        )
    prepared["session_label"] = prepared["date"].dt.strftime("%d/%m/%Y")
    prepared["is_baseline"] = prepared["phase"].str.contains(BASELINE_PATTERN, case=False, na=False, regex=True)
    return prepared


def summarize_targets(data: pd.DataFrame) -> pd.DataFrame:
    prepared = prepare_target_sessions(data)
    if prepared.empty:
        return pd.DataFrame()
    rows = []
    for target_name, group in prepared.groupby("target_name", sort=True):
        metrics = calculate_clinical_metrics(group)
        rows.append(
            {
                "target_name": target_name,
                "independent_rate": metrics.weighted_mean if metrics.weighted_mean is not None else metrics.simple_mean,
                "simple_mean": metrics.simple_mean,
                "weighted_mean": metrics.weighted_mean,
                "median": metrics.median,
                "sessions": metrics.sessions,
                "opportunities": metrics.opportunities,
                "latest": metrics.latest,
                "slope": metrics.slope,
            }
        )
    return pd.DataFrame(rows).sort_values("independent_rate", ascending=False, na_position="last").reset_index(drop=True)


def aggregate_target_exposure(data: pd.DataFrame) -> pd.DataFrame:
    """Soma oportunidades de todos os alvos e pondera o desempenho por data."""
    prepared = prepare_target_sessions(data)
    if prepared.empty:
        return pd.DataFrame()
    rows = []
    for date, group in prepared.groupby("date", sort=True):
        valid_attempts = group["has_attempts"]
        valid_rates = valid_attempts & group["independent_rate"].notna()
        attempts = float(group.loc[valid_attempts, "attempts"].sum()) if valid_attempts.any() else np.nan
        if valid_rates.any():
            independence = float(
                np.average(
                    group.loc[valid_rates, "independent_rate"],
                    weights=group.loc[valid_rates, "attempts"],
                )
            )
        else:
            independence = float(group["independent_rate"].mean())
        rows.append(
            {
                "date": date,
                "session_label": pd.Timestamp(date).strftime("%d/%m/%Y"),
                "attempts": attempts,
                "independent_rate": independence,
                "has_attempts": not pd.isna(attempts) and attempts > 0,
            }
        )
    return pd.DataFrame(rows)


def calculate_mastery_progress(
    data: pd.DataFrame,
    threshold: float,
    required_sessions: int,
) -> dict[str, float | int | bool | None]:
    """Avalia a sequência final em datas distintas, sem contar duplicidades do dia."""
    if data.empty or "date" not in data or "independent_rate" not in data:
        return {"current_rate": None, "streak": 0, "required": max(1, int(required_sessions)), "achieved": False}
    valid = data.copy()
    valid["date"] = pd.to_datetime(valid["date"], errors="coerce").dt.normalize()
    valid["independent_rate"] = pd.to_numeric(valid["independent_rate"], errors="coerce")
    valid = valid.dropna(subset=["date", "independent_rate"])
    if valid.empty:
        return {"current_rate": None, "streak": 0, "required": max(1, int(required_sessions)), "achieved": False}
    daily = valid.groupby("date", as_index=False)["independent_rate"].mean().sort_values("date")
    streak = 0
    for rate in reversed(daily["independent_rate"].tolist()):
        if rate >= threshold:
            streak += 1
        else:
            break
    required = max(1, int(required_sessions))
    return {
        "current_rate": _optional_round(daily["independent_rate"].iloc[-1]),
        "streak": streak,
        "required": required,
        "achieved": streak >= required,
    }


def classify_trend(slope: float | None, *, minimum_change: float = 0.1) -> str:
    """Classifica a direção sem atribuir causalidade à mudança observada."""
    if slope is None or pd.isna(slope):
        return "Dados insuficientes"
    if slope > minimum_change:
        return "Aumento"
    if slope < -minimum_change:
        return "Redução"
    return "Estável"


def evaluate_performance_criterion(
    data: pd.DataFrame,
    threshold: float,
    required_sessions: int,
) -> dict[str, Any]:
    """Separa critério percentual de domínio, manutenção e generalização.

    A sequência de desempenho é calculada em datas distintas. Domínio ampliado
    só é sinalizado quando os próprios registros identificam sondagens de
    manutenção e generalização; a função não inventa esses dados.
    """
    progress = calculate_mastery_progress(data, threshold, required_sessions)
    valid = pd.DataFrame() if data is None else data.copy()
    if not valid.empty:
        valid["date"] = pd.to_datetime(valid.get("date"), errors="coerce").dt.normalize()
        valid = valid.dropna(subset=["date"])
    phases = valid.get("phase", pd.Series(index=valid.index, dtype=str)).fillna("").astype(str)
    maintenance_records = int(
        phases.str.contains(r"manuten[cç][aã]o|follow.?up", case=False, na=False, regex=True).sum()
    )
    generalization_records = int(
        phases.str.contains(r"generaliza[cç][aã]o|generalization", case=False, na=False, regex=True).sum()
    )
    opportunities = None
    if "attempts" in valid:
        attempts = pd.to_numeric(valid["attempts"], errors="coerce")
        positive = attempts[attempts > 0]
        if not positive.empty:
            opportunities = int(round(positive.sum()))

    performance_achieved = bool(progress["achieved"])
    mastery_supported = performance_achieved and maintenance_records > 0 and generalization_records > 0
    if mastery_supported:
        status = "Domínio com manutenção e generalização registradas"
    elif performance_achieved:
        status = "Critério de desempenho atingido; manutenção e generalização pendentes"
    elif progress["current_rate"] is None:
        status = "Sem dados suficientes"
    elif progress["current_rate"] >= threshold:
        status = "Em confirmação por novas datas"
    else:
        status = "Em aquisição"

    return {
        **progress,
        "distinct_dates": int(valid["date"].nunique()) if "date" in valid else 0,
        "opportunities": opportunities,
        "performance_criterion_achieved": performance_achieved,
        "maintenance_records": maintenance_records,
        "generalization_records": generalization_records,
        "mastery_supported": mastery_supported,
        "status": status,
    }


def summarize_interfering_behaviors(data: pd.DataFrame) -> pd.DataFrame:
    """Resume nível, tendência e variabilidade sem inferir função do comportamento."""
    columns = [
        "behavior",
        "records",
        "observed_days",
        "total_count",
        "mean_rate",
        "measure",
        "first_value",
        "latest_value",
        "slope",
        "trend",
        "variability",
    ]
    if data is None or data.empty or "comportamento" not in data:
        return pd.DataFrame(columns=columns)

    prepared = data.copy()
    prepared["date"] = pd.to_datetime(prepared.get("date"), errors="coerce").dt.normalize()
    prepared["count"] = pd.to_numeric(
        prepared.get("count", pd.Series(index=prepared.index, dtype=float)), errors="coerce"
    )
    prepared["rate"] = pd.to_numeric(
        prepared.get("rate", pd.Series(index=prepared.index, dtype=float)), errors="coerce"
    )
    prepared["comportamento"] = prepared["comportamento"].fillna("").astype(str).str.strip()
    prepared = prepared[prepared["comportamento"] != ""]

    rows: list[dict[str, Any]] = []
    for behavior, group in prepared.groupby("comportamento", sort=True):
        dated = group.dropna(subset=["date"]).sort_values("date", kind="stable")
        daily_rate = dated.dropna(subset=["rate"]).groupby("date")["rate"].mean()
        daily_count = dated.dropna(subset=["count"]).groupby("date")["count"].sum()
        if len(daily_rate) >= 2:
            series = daily_rate
            measure = "taxa"
        elif not daily_count.empty:
            series = daily_count
            measure = "contagem"
        else:
            series = daily_rate
            measure = "taxa" if not daily_rate.empty else "sem medida"
        variability = calculate_variability(series)
        slope = calculate_trend_slope(series)
        rows.append(
            {
                "behavior": behavior,
                "records": int(len(group)),
                "observed_days": int(dated["date"].nunique()),
                "total_count": _optional_round(group["count"].sum()) if group["count"].notna().any() else None,
                "mean_rate": _optional_round(group["rate"].mean()) if group["rate"].notna().any() else None,
                "measure": measure,
                "first_value": _optional_round(series.iloc[0]) if not series.empty else None,
                "latest_value": _optional_round(series.iloc[-1]) if not series.empty else None,
                "slope": slope,
                "trend": classify_trend(slope),
                "variability": variability["classification"],
            }
        )
    if not rows:
        return pd.DataFrame(columns=columns)
    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values(["total_count", "mean_rate"], ascending=False, na_position="last")
        .reset_index(drop=True)
    )


def behavior_quality_issues(data: pd.DataFrame) -> dict[str, int]:
    """Aponta limites que impedem tratar ausência de registro como ausência de comportamento."""
    if data is None or data.empty:
        return {
            "records": 0,
            "invalid_dates": 0,
            "missing_measure": 0,
            "negative_values": 0,
            "potential_duplicates": 0,
        }
    counts = pd.to_numeric(
        data.get("count", pd.Series(index=data.index, dtype=float)), errors="coerce"
    )
    rates = pd.to_numeric(
        data.get("rate", pd.Series(index=data.index, dtype=float)), errors="coerce"
    )
    dates = parse_mixed_dates(data.get("date", pd.Series(index=data.index, dtype=object)))
    duplicate_columns = [
        column for column in ("comportamento", "date", "count", "rate") if column in data.columns
    ]
    return {
        "records": int(len(data)),
        "invalid_dates": int(dates.isna().sum()),
        "missing_measure": int((counts.isna() & rates.isna()).sum()),
        "negative_values": int(((counts < 0) | (rates < 0)).fillna(False).sum()),
        "potential_duplicates": int(
            data.duplicated(subset=duplicate_columns, keep="first").sum()
        )
        if duplicate_columns
        else 0,
    }


def quality_issues(data: pd.DataFrame, *, expects_attempts: bool) -> dict[str, int]:
    """Indicadores mínimos de qualidade para o recorte exibido."""
    if data.empty:
        return {
            "records": 0,
            "missing_attempts": 0,
            "missing_percentages": 0,
            "invalid_percentages": 0,
            "inconsistent_sum": 0,
            "missing_phase": 0,
            "invalid_dates": 0,
            "potential_duplicates": 0,
        }
    independent = pd.to_numeric(data.get("independent_rate"), errors="coerce")
    prompt = pd.to_numeric(data.get("prompt_rate"), errors="coerce")
    missing_percentages = independent.isna() | prompt.isna()
    invalid = (~missing_percentages) & (~independent.between(0, 100) | ~prompt.between(0, 100))
    inconsistent = independent.notna() & prompt.notna() & ((independent + prompt) > 100.001)
    phase = data.get("phase", pd.Series(index=data.index, dtype=str)).fillna("").astype(str).str.strip()
    dates = parse_mixed_dates(data.get("date", pd.Series(index=data.index, dtype=object)))
    missing_attempts = 0
    if expects_attempts:
        attempts = pd.to_numeric(data.get("attempts", pd.Series(index=data.index, dtype=float)), errors="coerce")
        missing_attempts = int((attempts.isna() | (attempts <= 0)).sum())
    duplicate_columns = [
        column
        for column in (
            "target_name",
            "programa",
            "date",
            "attempts",
            "independent_rate",
            "prompt_rate",
            "phase",
        )
        if column in data.columns
    ]
    potential_duplicates = int(data.duplicated(subset=duplicate_columns, keep="first").sum()) if duplicate_columns else 0
    return {
        "records": int(len(data)),
        "missing_attempts": missing_attempts,
        "missing_percentages": int(missing_percentages.sum()),
        "invalid_percentages": int(invalid.sum()),
        "inconsistent_sum": int(inconsistent.sum()),
        "missing_phase": int(phase.isin(["", "0", "0.0", "nan", "None"]).sum()),
        "invalid_dates": int(dates.isna().sum()),
        "potential_duplicates": potential_duplicates,
    }
