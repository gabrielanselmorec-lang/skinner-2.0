"""Figuras Plotly para objetivos e alvos terapêuticos."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


STATUS_COLORS = {
    "Independentes": "#587e52",
    "Com ajuda": "#c49a32",
    "Erros": "#b85f57",
}
PHASE_COLORS = {
    "Linha de base": "#6f86a4",
    "Intervenção": "#587e52",
}


def _add_mastery_line(fig: go.Figure, threshold: float) -> None:
    fig.add_hline(
        y=threshold,
        line_dash="dash",
        line_color="#7b4f2c",
        annotation_text=f"Critério: {threshold:.0f}%",
        annotation_position="top left",
    )


def _phase_changes(data: pd.DataFrame) -> list[tuple[str, str]]:
    if data.empty or "phase" not in data:
        return []
    changes: list[tuple[str, str]] = []
    previous = None
    for _, row in data.iterrows():
        phase = str(row.get("phase", "")).strip()
        if not phase or phase.lower() in {"não informada", "nao informada", "nan", "none", "0"}:
            continue
        if previous is not None and phase != previous:
            changes.append((str(row["session_label"]), phase))
        previous = phase
    return changes


def _add_phase_changes(fig: go.Figure, data: pd.DataFrame) -> None:
    for label, phase in _phase_changes(data):
        fig.add_vline(x=label, line_width=1.5, line_dash="dot", line_color="#8b6b43")
        fig.add_annotation(
            x=label,
            y=1,
            yref="paper",
            text=f"Mudança: {phase}",
            showarrow=False,
            textangle=-90,
            xanchor="left",
            yanchor="top",
            font=dict(size=10, color="#5d4630"),
        )


def program_timeline(data: pd.DataFrame, threshold: float) -> go.Figure:
    fig = go.Figure()
    phase_label = np.where(data.get("is_baseline", False), "Linha de base", "Intervenção")
    empty_text = pd.Series("Não informado", index=data.index)
    attempt_values = pd.to_numeric(
        data.get("attempts", pd.Series(np.nan, index=data.index)), errors="coerce"
    )
    attempts = attempt_values.apply(
        lambda value: "Não informado" if pd.isna(value) else f"{value:.0f}"
    )
    therapist = data.get("therapist", empty_text).fillna("Não informado").astype(str)
    prompt_type = data.get("prompt_type", empty_text).fillna("Não informado").astype(str)
    evolution = data.get("evolution", empty_text).fillna("").astype(str)
    fig.add_trace(
        go.Scatter(
            x=data["session_label"],
            y=data["independent_rate"],
            mode="lines+markers",
            name="Independência",
            line=dict(color="#587e52", width=2.5),
            marker=dict(size=9, color=[PHASE_COLORS[label] for label in phase_label], line=dict(color="#fffdf8", width=1)),
            customdata=np.column_stack(
                [
                    data["phase"],
                    data["prompt_rate"],
                    data.get("success_rate", pd.Series(index=data.index, dtype=float)),
                    attempts,
                    therapist,
                    prompt_type,
                    evolution,
                ]
            ),
            hovertemplate=(
                "<b>%{x}</b><br>Independência: %{y:.1f}%"
                "<br>Ajuda: %{customdata[1]:.1f}%<br>Sucesso: %{customdata[2]:.1f}%"
                "<br>Fase: %{customdata[0]}<br>Oportunidades: %{customdata[3]}"
                "<br>Terapeuta: %{customdata[4]}<br>Tipo de ajuda: %{customdata[5]}"
                "<br>Evolução: %{customdata[6]}<extra></extra>"
            ),
        )
    )
    _add_mastery_line(fig, threshold)
    _add_phase_changes(fig, data)
    fig.update_layout(title="Linha temporal do objetivo", xaxis_title="Sessão / registro", yaxis_title="Independência (%)", hovermode="x unified")
    fig.update_xaxes(type="category", tickangle=-45)
    fig.update_yaxes(range=[0, 105])
    return fig


def composition_chart(data: pd.DataFrame, *, use_trials: bool) -> go.Figure:
    if use_trials:
        columns = {"independent_trials": "Independentes", "prompted_trials": "Com ajuda", "error_trials": "Erros"}
        y_title = "Oportunidades reais"
        title = "Composição por oportunidades registradas"
    else:
        columns = {"independent_rate": "Independentes", "prompt_rate": "Com ajuda", "error_rate": "Erros"}
        y_title = "Distribuição (%)"
        title = "Composição percentual por sessão"
    fig = go.Figure()
    for column, label in columns.items():
        fig.add_bar(
            x=data["session_label"],
            y=data[column],
            name=label,
            marker_color=STATUS_COLORS[label],
            customdata=data.get("attempts", pd.Series(index=data.index, dtype=float)),
            hovertemplate="<b>%{x}</b><br>" + label + ": %{y:.1f}<br>Oportunidades: %{customdata}<extra></extra>",
        )
    fig.update_layout(barmode="stack", title=title, xaxis_title="Sessão", yaxis_title=y_title)
    fig.update_xaxes(type="category", tickangle=-45)
    if not use_trials:
        fig.update_yaxes(range=[0, 105])
    return fig


def trend_variability_chart(data: pd.DataFrame, threshold: float) -> go.Figure:
    rates = pd.to_numeric(data["independent_rate"], errors="coerce")
    valid = rates.notna()
    x_numeric = np.arange(len(data), dtype=float)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=data["session_label"], y=rates, mode="lines+markers", name="Dados brutos",
            line=dict(color="#6f86a4", width=2), marker=dict(size=8),
        )
    )
    if valid.sum() >= 2:
        slope, intercept = np.polyfit(x_numeric[valid], rates[valid], 1)
        fig.add_trace(
            go.Scatter(
                x=data["session_label"], y=intercept + slope * x_numeric,
                mode="lines", name=f"Tendência ({slope:+.1f} p.p./sessão)",
                line=dict(color="#7d4f82", dash="dash", width=2.5),
            )
        )
    if valid.any():
        mean = float(rates[valid].mean())
        q1, q3 = rates[valid].quantile([0.25, 0.75])
        fig.add_hrect(y0=q1, y1=q3, fillcolor="#d8bd72", opacity=0.18, line_width=0, annotation_text="Faixa interquartil")
        fig.add_hline(y=mean, line_color="#8b6b43", line_width=1.5, annotation_text=f"Média: {mean:.1f}%", annotation_position="bottom right")
    _add_mastery_line(fig, threshold)
    _add_phase_changes(fig, data)
    fig.update_layout(title="Nível, tendência e variabilidade", xaxis_title="Sessão", yaxis_title="Independência (%)")
    fig.update_xaxes(type="category", tickangle=-45)
    fig.update_yaxes(range=[0, 105])
    return fig


def mastery_progress_chart(current_rate: float | None, threshold: float, streak: int, required: int) -> go.Figure:
    rate = 0 if current_rate is None else float(current_rate)
    fig = make_subplots(rows=2, cols=1, vertical_spacing=0.28, subplot_titles=("Desempenho atual", "Sequência válida em datas distintas"))
    fig.add_trace(go.Bar(x=[rate], y=["Independência"], orientation="h", marker_color="#587e52", text=[f"{rate:.1f}%"], textposition="inside", name="Atual"), row=1, col=1)
    fig.add_trace(go.Bar(x=[min(streak, required)], y=["Sequência"], orientation="h", marker_color="#6f86a4", text=[f"{streak} de {required}"], textposition="inside", name="Datas"), row=2, col=1)
    fig.add_vline(x=threshold, line_dash="dash", line_color="#7b4f2c", row=1, col=1)
    fig.update_xaxes(range=[0, 100], title_text="Percentual", row=1, col=1)
    fig.update_xaxes(range=[0, max(required, 1)], title_text="Datas com coleta", dtick=1, row=2, col=1)
    fig.update_layout(title="Progresso até o critério", showlegend=False, height=430)
    return fig


def target_summary_bar(summary: pd.DataFrame, threshold: float) -> go.Figure:
    plot_data = summary.sort_values("independent_rate", ascending=True)
    fig = px.bar(
        plot_data,
        x="independent_rate",
        y="target_name",
        orientation="h",
        text="independent_rate",
        color="independent_rate",
        color_continuous_scale=[[0, "#b85f57"], [0.7, "#d8bd72"], [1, "#587e52"]],
        range_color=[0, 100],
        custom_data=["weighted_mean", "simple_mean", "opportunities", "sessions", "latest"],
        labels={"target_name": "Alvo", "independent_rate": "Independência (%)"},
        title="Comparação entre alvos",
    )
    fig.update_traces(
        texttemplate="%{x:.1f}%",
        textposition="outside",
        hovertemplate=(
            "<b>%{y}</b><br>Resultado exibido: %{x:.1f}%"
            "<br>Média ponderada: %{customdata[0]}<br>Média simples: %{customdata[1]}"
            "<br>Oportunidades: %{customdata[2]}<br>Datas: %{customdata[3]}"
            "<br>Última medida: %{customdata[4]}<extra></extra>"
        ),
    )
    _add_mastery_line_vertical(fig, threshold)
    fig.update_xaxes(range=[0, 105])
    return fig


def _add_mastery_line_vertical(fig: go.Figure, threshold: float) -> None:
    fig.add_vline(x=threshold, line_dash="dash", line_color="#7b4f2c", annotation_text=f"Critério: {threshold:.0f}%", annotation_position="top")


def target_heatmap(data: pd.DataFrame, threshold: float) -> go.Figure:
    heatmap = data.pivot(index="target_name", columns="session_label", values="independent_rate")
    text = heatmap.map(lambda value: "—" if pd.isna(value) else f"{value:.0f}%")
    fig = go.Figure(
        go.Heatmap(
            z=heatmap.to_numpy(dtype=float),
            x=heatmap.columns,
            y=heatmap.index,
            zmin=0,
            zmax=100,
            colorscale=[[0, "#b85f57"], [0.4, "#d69b72"], [0.7, "#d8bd72"], [0.9, "#8faa7e"], [1, "#587e52"]],
            text=text.to_numpy(),
            texttemplate="%{text}",
            hovertemplate="<b>%{y}</b><br>%{x}<br>Independência: %{z:.1f}%<extra></extra>",
            colorbar=dict(title="Indep. %"),
            hoverongaps=False,
        )
    )
    fig.update_layout(title=f"Heatmap de alvos por data · critério {threshold:.0f}%", xaxis_title="Data", yaxis_title="Alvo", height=max(420, 36 * len(heatmap) + 180))
    fig.update_xaxes(type="category", tickangle=-45)
    return fig


def opportunities_chart(data: pd.DataFrame) -> go.Figure:
    chart_data = data[data["has_attempts"]].copy()
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=chart_data["session_label"], y=chart_data["attempts"], name="Oportunidades",
            marker_color="#6f86a4", opacity=0.72,
            hovertemplate="<b>%{x}</b><br>Oportunidades: %{y:.0f}<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=chart_data["session_label"], y=chart_data["independent_rate"], name="Independência",
            mode="lines+markers", line=dict(color="#587e52", width=3),
            hovertemplate="<b>%{x}</b><br>Independência: %{y:.1f}%<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.update_layout(title="Exposição ao ensino versus independência", hovermode="x unified")
    fig.update_xaxes(type="category", title_text="Data", tickangle=-45)
    fig.update_yaxes(title_text="Oportunidades reais", rangemode="tozero", secondary_y=False)
    fig.update_yaxes(title_text="Independência (%)", range=[0, 105], secondary_y=True)
    return fig


def small_multiples(data: pd.DataFrame, threshold: float) -> go.Figure:
    fig = px.line(
        data,
        x="date",
        y="independent_rate",
        facet_col="target_name",
        facet_col_wrap=3,
        markers=True,
        labels={"date": "Data", "independent_rate": "Independência (%)", "target_name": "Alvo"},
        title="Evolução individual dos alvos",
    )
    fig.for_each_annotation(lambda annotation: annotation.update(text=annotation.text.split("=")[-1]))
    fig.add_hline(y=threshold, line_dash="dash", line_color="#7b4f2c")
    fig.update_yaxes(range=[0, 105])
    fig.update_xaxes(tickformat="%d/%m", tickangle=-45)
    rows = int(np.ceil(max(1, data["target_name"].nunique()) / 3))
    fig.update_layout(height=max(420, rows * 300))
    return fig
