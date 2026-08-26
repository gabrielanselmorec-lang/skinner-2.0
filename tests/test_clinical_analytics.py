import pandas as pd
import pytest

from app.services.clinical_analytics import (
    aggregate_target_exposure,
    calculate_clinical_metrics,
    calculate_mastery_progress,
    calculate_trend_slope,
    calculate_variability,
    calculate_weighted_independence,
    behavior_quality_issues,
    evaluate_performance_criterion,
    prepare_program_sessions,
    prepare_target_sessions,
    quality_issues,
    summarize_interfering_behaviors,
    summarize_targets,
)
from app.web.charts.skill_charts import (
    composition_chart,
    opportunities_chart,
    program_timeline,
    small_multiples,
    target_heatmap,
    target_summary_bar,
    trend_variability_chart,
)


def _target_data():
    return pd.DataFrame(
        {
            "target_name": ["Alvo A", "Alvo A", "Alvo A", "Alvo B"],
            "date": ["2026-07-01", "2026-07-01", "2026-07-08", "2026-07-01"],
            "attempts": [2, 8, 20, 10],
            "independent_rate": [100, 50, 80, 40],
            "prompt_rate": [0, 25, 10, 40],
            "success_rate": [100, 75, 90, 80],
            "phase": ["Linha de base", "Linha de base", "Intervenção", "Linha de base"],
            "prompt_type": ["", "Gestual", "Verbal", "Física parcial"],
            "evolution": ["", "Coleta 1", "Coleta 2", "Coleta 3"],
        }
    )


def test_weighted_mean_uses_real_attempts():
    data = pd.DataFrame({"independent_rate": [100, 50], "attempts": [2, 20]})
    assert calculate_weighted_independence(data) == pytest.approx(54.55, abs=0.01)
    assert data["independent_rate"].mean() == 75


def test_weighted_mean_is_none_without_real_denominator():
    data = pd.DataFrame({"independent_rate": [100, 50], "attempts": [0, None]})
    assert calculate_weighted_independence(data) is None


def test_target_sessions_aggregate_same_date_with_attempt_weights():
    prepared = prepare_target_sessions(_target_data())
    first = prepared[(prepared["target_name"] == "Alvo A") & (prepared["date"] == pd.Timestamp("2026-07-01"))].iloc[0]
    assert first["attempts"] == 10
    assert first["independent_rate"] == pytest.approx(60)
    assert first["prompt_rate"] == pytest.approx(20)
    assert first["independent_trials"] == pytest.approx(6)
    assert first["prompted_trials"] == pytest.approx(2)
    assert first["error_trials"] == pytest.approx(2)


def test_program_sessions_keep_percentages_and_distinguish_duplicate_dates():
    data = pd.DataFrame(
        {
            "date": ["2026-07-01", "2026-07-01"],
            "independent_rate": [50, 70],
            "prompt_rate": [30, 20],
            "success_rate": [80, 90],
            "phase": ["Linha de base", "Intervenção"],
        }
    )
    prepared = prepare_program_sessions(data)
    assert prepared["session_label"].tolist() == ["01/07/2026 · 1", "01/07/2026 · 2"]
    assert prepared["error_rate"].tolist() == [20, 10]
    assert "attempts" not in prepared.columns


def test_missing_components_do_not_turn_into_errors():
    program = prepare_program_sessions(
        pd.DataFrame({"date": ["2026-07-01"], "independent_rate": [None], "prompt_rate": [None]})
    )
    target = prepare_target_sessions(
        pd.DataFrame(
            {
                "target_name": ["Alvo"],
                "date": ["2026-07-01"],
                "attempts": [10],
                "independent_rate": [None],
                "prompt_rate": [None],
            }
        )
    )
    assert pd.isna(program.loc[0, "error_rate"])
    assert pd.isna(target.loc[0, "error_rate"])
    assert pd.isna(target.loc[0, "error_trials"])


def test_trend_variability_and_metrics_are_stable():
    assert calculate_trend_slope([10, 20, 30]) == pytest.approx(10)
    assert calculate_variability([10, 20, 30])["classification"] == "Baixa"
    metrics = calculate_clinical_metrics(
        pd.DataFrame({"independent_rate": [10, 20, 30], "attempts": [10, 10, 10]})
    )
    assert metrics.latest == 30
    assert metrics.weighted_mean == 20
    assert metrics.opportunities == 30


def test_mastery_sequence_counts_distinct_dates_not_duplicate_records():
    data = pd.DataFrame(
        {
            "date": ["2026-07-01", "2026-07-01", "2026-07-02", "2026-07-03"],
            "independent_rate": [100, 100, 95, 92],
        }
    )
    progress = calculate_mastery_progress(data, threshold=90, required_sessions=3)
    assert progress == {"current_rate": 92.0, "streak": 3, "required": 3, "achieved": True}


def test_performance_criterion_does_not_claim_mastery_without_probes():
    data = pd.DataFrame(
        {
            "date": ["2026-07-01", "2026-07-02", "2026-07-03"],
            "independent_rate": [92, 94, 95],
            "attempts": [10, 10, 10],
            "phase": ["Intervenção", "Intervenção", "Intervenção"],
        }
    )
    criterion = evaluate_performance_criterion(data, threshold=90, required_sessions=3)
    assert criterion["performance_criterion_achieved"] is True
    assert criterion["mastery_supported"] is False
    assert criterion["opportunities"] == 30
    assert "manutenção e generalização pendentes" in criterion["status"]


def test_mastery_requires_maintenance_and_generalization_records():
    data = pd.DataFrame(
        {
            "date": ["2026-07-01", "2026-07-02", "2026-07-03"],
            "independent_rate": [92, 94, 95],
            "phase": ["Intervenção", "Manutenção", "Generalização"],
        }
    )
    criterion = evaluate_performance_criterion(data, threshold=90, required_sessions=3)
    assert criterion["mastery_supported"] is True
    assert criterion["maintenance_records"] == 1
    assert criterion["generalization_records"] == 1


def test_single_high_result_stays_in_confirmation():
    data = pd.DataFrame(
        {"date": ["2026-07-01"], "independent_rate": [100], "phase": ["Intervenção"]}
    )
    criterion = evaluate_performance_criterion(data, threshold=90, required_sessions=3)
    assert criterion["performance_criterion_achieved"] is False
    assert criterion["status"] == "Em confirmação por novas datas"


def test_interfering_behavior_summary_uses_level_trend_and_variability():
    data = pd.DataFrame(
        {
            "comportamento": ["Fuga", "Fuga", "Fuga"],
            "date": ["2026-07-01", "2026-07-02", "2026-07-03"],
            "count": [3, 2, 1],
            "rate": [3.0, 2.0, 1.0],
        }
    )
    summary = summarize_interfering_behaviors(data).iloc[0]
    assert summary["measure"] == "taxa"
    assert summary["observed_days"] == 3
    assert summary["trend"] == "Redução"
    assert summary["variability"] == "Baixa"


def test_zero_behavior_measure_is_a_record_not_missing_data():
    data = pd.DataFrame(
        {"comportamento": ["Fuga"], "date": ["2026-07-01"], "count": [0], "rate": [0]}
    )
    summary = summarize_interfering_behaviors(data).iloc[0]
    issues = behavior_quality_issues(data)
    assert summary["records"] == 1
    assert summary["total_count"] == 0
    assert issues["missing_measure"] == 0


def test_behavior_quality_flags_missing_measure_and_duplicates():
    data = pd.DataFrame(
        {
            "comportamento": ["Fuga", "Fuga", "Outro"],
            "date": ["2026-07-01", "2026-07-01", "inválida"],
            "count": [None, None, -1],
            "rate": [None, None, None],
        }
    )
    issues = behavior_quality_issues(data)
    assert issues["missing_measure"] == 2
    assert issues["negative_values"] == 1
    assert issues["invalid_dates"] == 1
    assert issues["potential_duplicates"] == 1


def test_target_summary_and_exposure_are_attempt_weighted():
    summary = summarize_targets(_target_data()).set_index("target_name")
    assert summary.loc["Alvo A", "weighted_mean"] == pytest.approx(73.33, abs=0.01)
    exposure = aggregate_target_exposure(_target_data()).set_index("session_label")
    assert exposure.loc["01/07/2026", "attempts"] == 20
    assert exposure.loc["01/07/2026", "independent_rate"] == pytest.approx(50)


def test_quality_separates_missing_out_of_range_and_duplicates():
    data = pd.DataFrame(
        {
            "target_name": ["A", "A", "B"],
            "date": ["2026-07-01", "2026-07-01", "data inválida"],
            "attempts": [None, None, 10],
            "independent_rate": [110, 110, None],
            "prompt_rate": [10, 10, 30],
            "phase": ["", "", "Intervenção"],
        }
    )
    issues = quality_issues(data, expects_attempts=True)
    assert issues["missing_attempts"] == 2
    assert issues["missing_percentages"] == 1
    assert issues["invalid_percentages"] == 2
    assert issues["inconsistent_sum"] == 2
    assert issues["missing_phase"] == 2
    assert issues["invalid_dates"] == 1
    assert issues["potential_duplicates"] == 1


def test_all_objective_chart_builders_accept_transformed_data():
    targets = prepare_target_sessions(_target_data())
    target_a = targets[targets["target_name"] == "Alvo A"].copy()
    programs = prepare_program_sessions(
        pd.DataFrame(
            {
                "date": ["2026-07-01", "2026-07-08"],
                "independent_rate": [50, 80],
                "prompt_rate": [30, 10],
                "success_rate": [80, 90],
                "phase": ["Linha de base", "Intervenção"],
            }
        )
    )
    summary = summarize_targets(_target_data())
    exposure = aggregate_target_exposure(_target_data())

    figures = [
        program_timeline(programs, 90),
        composition_chart(programs, use_trials=False),
        composition_chart(target_a, use_trials=True),
        trend_variability_chart(programs, 90),
        target_summary_bar(summary, 90),
        target_heatmap(targets, 90),
        opportunities_chart(exposure),
        small_multiples(targets, 90),
    ]
    assert all(figure.data for figure in figures)
