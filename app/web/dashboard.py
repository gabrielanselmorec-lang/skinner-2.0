import os
import sys
import re
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.express as px



# Ajuste de Caminho para importar o main.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from main import sincronizar_bhave_api

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from ablls_view import render_ablls_module

# Configuração da Página
BASE_DIR = Path(__file__).resolve().parent
STYLE_PATH = BASE_DIR / "assets" / "style.css"
PASTEL_CHART_COLORS = [
    "#7d9b76",
    "#c17c74",
    "#d8bd72",
    "#6f86a4",
    "#b77ba5",
    "#a7b78a",
    "#c99b6c",
]
PASTEL_STATUS_COLORS = {
    "Independentes": "#7d9b76",
    "Com Ajuda": "#d8bd72",
    "Erros": "#c17c74",
}
PASTEL_SCALE = [
    [0.0, "#c17c74"],
    [0.5, "#d8bd72"],
    [1.0, "#7d9b76"],
]

px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = PASTEL_CHART_COLORS


def inject_css(css_path: Path = STYLE_PATH) -> None:
    """Load and inject the dashboard stylesheet into Streamlit."""
    if not css_path.exists():
        return

    css = css_path.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def apply_pastel_chart_theme(fig):
    """Apply the readable pastel beige chart theme used across the dashboard."""
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#fffdf8",
        plot_bgcolor="#f3eadb",
        font=dict(color="#33291f", family="Inter, Segoe UI, sans-serif", size=12),
        title=dict(font=dict(color="#33291f", size=18)),
        legend=dict(
            bgcolor="rgba(255, 253, 248, 0.94)",
            bordercolor="#ded0b8",
            borderwidth=1,
            font=dict(color="#3a2d20"),
        ),
        margin=dict(l=36, r=24, t=58, b=44),
    )
    fig.update_xaxes(
        gridcolor="#e5d9c7",
        linecolor="#c9b897",
        tickfont=dict(color="#33291f"),
        title_font=dict(color="#33291f"),
        zerolinecolor="#d6c6aa",
    )
    fig.update_yaxes(
        gridcolor="#e5d9c7",
        linecolor="#c9b897",
        tickfont=dict(color="#33291f"),
        title_font=dict(color="#33291f"),
        zerolinecolor="#d6c6aa",
    )
    return fig


def render_plotly_chart(fig, **kwargs) -> None:
    """Render Plotly charts with the app theme instead of Streamlit dark defaults."""
    st.plotly_chart(apply_pastel_chart_theme(fig), theme=None, **kwargs)


st.set_page_config(page_title="Skinner Project", layout="wide")
inject_css()

AGENT_TIMEOUT_SECONDS = int(os.getenv("SKINNER_AGENT_TIMEOUT_SECONDS", "300"))
PEI_TEMPLATE_PATH = os.getenv(
    "SKINNER_PEI_TEMPLATE_PATH",
    r"C:\Users\coord\Desktop\PEI_2026_TEMPLATE_V3.docx",
)

from api_client import (
    APIClientError,
    load_data_from_api,
    load_patients_from_api,
    load_targets_from_api,
    load_library_from_api,
    ask_clinical_agent,
)
from app.services.pei_docx import (
    estilizar_status_preview_pei as estilizar_status_preview_pei_service,
    gerar_doc_anual_pei as gerar_doc_anual_pei_service,
    gerar_doc_completo as gerar_doc_completo_service,
    gerar_resumo_comportamentos_problema_pei as gerar_resumo_comportamentos_problema_pei_service,
    gerar_texto_trimestral_pei as gerar_texto_trimestral_pei_service,
    preparar_programas_pei,
    resumo_alvos_por_objetivo as resumo_alvos_por_objetivo_service,
)
from app.services.pei_rules import (
    avaliar_objetivo_observavel,
    distribuir_objetivos_por_area as distribuir_objetivos_por_area_service,
    filtrar_periodo_pei as filtrar_periodo_pei_service,
    resumo_objetivos_por_area as resumo_objetivos_por_area_service,
)
from app.services.clinical_analytics import (
    aggregate_target_exposure,
    calculate_clinical_metrics,
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
    mastery_progress_chart,
    opportunities_chart,
    program_timeline,
    small_multiples,
    target_heatmap,
    target_summary_bar,
    trend_variability_chart,
)

def render_agent_references(fontes):
    if not fontes:
        return
    st.markdown("#### Referencias bibliograficas")
    for idx, fonte in enumerate(fontes, start=1):
        arquivo = str(fonte.get("fonte") or "Fonte nao informada").strip()
        titulo = str(fonte.get("titulo") or "").strip()
        indice = fonte.get("indice", "")
        partes = [f"arquivo: {arquivo}"]
        if titulo:
            partes.append(f"titulo/capitulo: {titulo}")
        if indice != "":
            partes.append(f"trecho: {indice}")
        st.markdown(f"- **Fonte {idx}:** " + "; ".join(partes) + ".")

st.markdown(
    """
    <section class="skinner-page-header">
        <div>
            <span class="skinner-eyebrow">Skinner Project</span>
            <h1>Análise Clínica</h1>
        </div>
        <span class="skinner-header-badge">Dashboard profissional</span>
    </section>
    """,
    unsafe_allow_html=True,
)

# Verificação da API
try:
    lista_pacientes = load_patients_from_api()
except APIClientError as exc:
    st.error(f"ERRO: {exc}")
    st.stop()
except Exception:
    st.error("ERRO inesperado ao carregar a lista de pacientes. Verifique o terminal.")
    st.stop()

if not lista_pacientes:
    st.warning("Banco de dados vazio.")
    if st.button("Sincronizar bHave (Primeira Vez)"):
        sincronizar_bhave_api()
        st.rerun()
else:
    paciente_sel = st.sidebar.selectbox("Selecione o Paciente", lista_pacientes)
    
    st.sidebar.markdown("---")
    if st.sidebar.button("Sincronizar bHave Agora"):
        with st.spinner("Buscando novos relatórios..."):
            sincronizar_bhave_api()
            st.cache_data.clear() 
            st.rerun()
    
    if paciente_sel:
        df_p_raw, df_b_raw = load_data_from_api(paciente_sel)
        df_lib = load_library_from_api()
        
        if not df_p_raw.empty:
            df_p_raw = df_p_raw[df_p_raw['programa'].str.strip() != ""]
            
            active_tab = st.radio(
                "Navegacao principal",
                ["Habilidades", "Decisão", "Interferentes", "PEI", "Avaliações", "Assistente"],
                horizontal=True,
                label_visibility="collapsed",
                key="dashboard_active_tab",
            )

            # ==========================================
            # --- ABA 1: HABILIDADES ---
            # ==========================================
            if active_tab == "Habilidades":
                st.markdown(f"###  Gestão de Habilidades: **{paciente_sel}**")
                
                if not df_p_raw.empty and not df_p_raw['date'].dropna().empty:
                    min_d_p, max_d_p = df_p_raw['date'].min(), df_p_raw['date'].max()
                else:
                    min_d_p, max_d_p = datetime.today().date(), datetime.today().date()
                
                c_data_p, _ = st.columns([1, 2])
                with c_data_p:
                    periodo_prog = st.date_input(" Período", value=(min_d_p, max_d_p), format="DD/MM/YYYY", key="hab_periodo")
                
                start_p, end_p = (periodo_prog[0], periodo_prog[1]) if len(periodo_prog) == 2 else (min_d_p, max_d_p)
                df_prog = df_p_raw[(df_p_raw['date'] >= start_p) & (df_p_raw['date'] <= end_p)] if not df_p_raw.empty else pd.DataFrame()
                
                if df_prog.empty:
                    st.info("Nenhum dado registrado para este período.")
                else:
                    if 'phase' not in df_prog.columns: df_prog['phase'] = ""
                    # Expressão regular blindada (\blb\b) para não confundir nomes
                    mask_lb = df_prog['phase'].astype(str).str.contains(r'linha de base|\blb\b|baseline|sondagem', case=False, na=False)
                    
                    df_prog['date_pd'] = pd.to_datetime(df_prog['date'])
                    ultima_data_geral = df_prog.groupby('programa')['date_pd'].max()
                    data_corte = pd.to_datetime(end_p) - pd.Timedelta(days=30)
                    programas_ativos = ultima_data_geral[ultima_data_geral >= data_corte].index.tolist()
                    programas_arquivados = ultima_data_geral[ultima_data_geral < data_corte].index.tolist()
                    
                    mostrar_arquivados = st.toggle(" Mostrar Programas Inativos (> 30 dias)")
                    programas_no_periodo = df_prog['programa'].unique().tolist()
                    prog_lista = sorted([p for p in programas_no_periodo if p in (programas_arquivados if mostrar_arquivados else programas_ativos)])
                    
                    if prog_lista:
                        prog_sel = st.selectbox(" 1. Selecione o Programa", ["RESUMO GERAL"] + prog_lista)
                    else:
                        prog_sel = None
                    
                    if prog_sel == "RESUMO GERAL":
                        st.subheader(" Desempenho (Intervenção vs LB)")
                        df_prog_int = df_prog[~mask_lb] # Apenas Intervenção
                        
                        c1, c2, c3 = st.columns(3)
                        media_int = df_prog_int['independent_rate'].mean() if not df_prog_int.empty else None
                        media_lb = df_prog[mask_lb]['independent_rate'].mean() if not df_prog[mask_lb].empty else None
                        
                        c1.metric(" Média TOTAL (Intervenção)", f"{media_int:.1f}%" if pd.notnull(media_int) else "N/A")
                        c2.metric(" Média TOTAL (Linha de Base)", f"{media_lb:.1f}%" if pd.notnull(media_lb) else "N/A")
                        c3.metric(" Programas Ativos", len(programas_ativos))
                        
                        st.markdown("---")
                        if not df_prog_int.empty:
                            df_resumo = df_prog_int[df_prog_int['programa'].isin(prog_lista)].groupby('programa')['independent_rate'].mean().round(1).reset_index().sort_values('independent_rate')
                            fig_resumo = px.bar(df_resumo, y='programa', x='independent_rate', orientation='h', text='independent_rate', color_discrete_sequence=['#7d9b76'], labels={'programa': 'Programa', 'independent_rate': 'Independência (%)'})
                            fig_resumo.update_traces(textposition='outside')
                            fig_resumo.update_layout(xaxis_range=[0, 100])
                            render_plotly_chart(fig_resumo, width='stretch')
                        
                    elif prog_sel:
                        df_p_view = df_prog[df_prog['programa'] == prog_sel].sort_values('date').copy()
                        df_alvos_brutos = load_targets_from_api(paciente_sel, prog_sel)
                        if not df_alvos_brutos.empty:
                            df_alvos_brutos = df_alvos_brutos[
                                (df_alvos_brutos['date'] >= start_p) & (df_alvos_brutos['date'] <= end_p)
                            ].copy()
                        lista_alvos = sorted([
                            str(alvo) for alvo in df_alvos_brutos['target_name'].unique().tolist()
                            if str(alvo).strip() not in {"", "0", "nan", "None"}
                        ]) if not df_alvos_brutos.empty else []
                        alvo_sel = st.selectbox(" 2. Selecione o Alvo", ["TODOS OS ALVOS"] + lista_alvos)

                        st.markdown("<br>", unsafe_allow_html=True)
                        
                        objetivo_texto = "Não informado"
                        if not df_p_view.empty and 'objective' in df_p_view.columns:
                            val_bhave = df_p_view['objective'].iloc[0]
                            if pd.notna(val_bhave) and str(val_bhave).strip() not in ["", "None", "nan"]:
                                objetivo_texto = val_bhave
                                
                        if objetivo_texto == "Não informado" and not df_lib.empty and prog_sel in df_lib['name'].values:
                            obj_val = df_lib[df_lib['name'] == prog_sel].iloc[0]['objective_template']
                            if pd.notna(obj_val) and str(obj_val).strip() != "":
                                objetivo_texto = obj_val

                        mastery_threshold = 90.0
                        mastery_sessions = 3
                        if not df_lib.empty and prog_sel in df_lib['name'].values:
                            library_row = df_lib[df_lib['name'] == prog_sel].iloc[0]
                            mastery_threshold = float(library_row.get('mastery_threshold_percent', 90) or 90)
                            mastery_sessions = int(library_row.get('mastery_days', 3) or 3)

                        st.markdown(f"** Meta do Programa:** {objetivo_texto}")
                        avaliacao_objetivo = avaliar_objetivo_observavel(objetivo_texto)
                        if avaliacao_objetivo["faltantes"]:
                            st.warning(
                                f"Objetivo com {avaliacao_objetivo['pontuacao']}/{avaliacao_objetivo['total']} "
                                f"componentes operacionais. {avaliacao_objetivo['recomendacao']}"
                            )
                        else:
                            st.success("Objetivo contém resposta observável, contexto, medida, critério e generalização/manutenção.")
                        st.caption(
                            f"Critério configurado: {mastery_threshold:.0f}% em {mastery_sessions} datas distintas com coleta."
                        )
                        st.markdown("### Desempenho no período selecionado")

                        program_sessions = prepare_program_sessions(df_p_view)
                        all_target_sessions = prepare_target_sessions(df_alvos_brutos)
                        if alvo_sel == "TODOS OS ALVOS":
                            analysis_data = program_sessions
                        else:
                            analysis_data = all_target_sessions[
                                all_target_sessions['target_name'] == alvo_sel
                            ].copy()

                        if analysis_data.empty:
                            st.info("Sem registros válidos para a visualização selecionada.")
                        else:
                            metrics = calculate_clinical_metrics(analysis_data)
                            metric_cols = st.columns(5)
                            metric_cols[0].metric(
                                "Última independência",
                                f"{metrics.latest:.1f}%" if metrics.latest is not None else "N/A",
                            )
                            main_average = metrics.weighted_mean if metrics.weighted_mean is not None else metrics.simple_mean
                            average_label = "Média ponderada" if metrics.weighted_mean is not None else "Média simples"
                            metric_cols[1].metric(
                                average_label,
                                f"{main_average:.1f}%" if main_average is not None else "N/A",
                            )
                            metric_cols[2].metric(
                                "Mediana",
                                f"{metrics.median:.1f}%" if metrics.median is not None else "N/A",
                            )
                            metric_cols[3].metric(
                                "Tendência",
                                f"{metrics.slope:+.1f} p.p./sessão" if metrics.slope is not None else "N/A",
                            )
                            metric_cols[4].metric(
                                "Oportunidades",
                                str(metrics.opportunities) if metrics.opportunities is not None else "Não informadas",
                            )
                            st.caption(
                                f"Variabilidade: **{metrics.variability}** · "
                                f"desvio-padrão: {metrics.standard_deviation if metrics.standard_deviation is not None else 'N/A'} · "
                                f"amplitude: {metrics.amplitude if metrics.amplitude is not None else 'N/A'} p.p."
                            )

                            if alvo_sel == "TODOS OS ALVOS":
                                view_options = [
                                    "Linha temporal do programa",
                                    "Composição percentual",
                                    "Nível, tendência e variabilidade",
                                    "Progresso até o critério de desempenho",
                                    "Comparação entre alvos",
                                    "Heatmap dos alvos",
                                    "Exposição e oportunidades",
                                    "Small multiples por alvo",
                                ]
                            else:
                                view_options = [
                                    "Linha temporal do alvo",
                                    "Composição das respostas",
                                    "Nível, tendência e variabilidade",
                                    "Progresso até o critério de desempenho",
                                    "Exposição e oportunidades",
                                ]

                            chart_view = st.selectbox(
                                "3. Escolha a visualização",
                                view_options,
                                key=f"skill_chart::{prog_sel}::{alvo_sel}",
                            )
                            chart_data = analysis_data
                            fig_skill = None

                            if chart_view in {"Linha temporal do programa", "Linha temporal do alvo"}:
                                fig_skill = program_timeline(chart_data, mastery_threshold)
                            elif chart_view == "Composição percentual":
                                fig_skill = composition_chart(chart_data, use_trials=False)
                                st.info(
                                    "O programa não registra o total de tentativas. Este gráfico usa percentuais e não converte os dados para uma base fictícia de 10 oportunidades."
                                )
                            elif chart_view == "Composição das respostas":
                                use_trials = bool(chart_data['has_attempts'].all())
                                fig_skill = composition_chart(chart_data, use_trials=use_trials)
                                if not use_trials:
                                    st.warning(
                                        "Há sessões sem número de oportunidades. Para não inventar contagens, a composição é exibida em percentual."
                                    )
                            elif chart_view == "Nível, tendência e variabilidade":
                                fig_skill = trend_variability_chart(chart_data, mastery_threshold)
                            elif chart_view == "Progresso até o critério de desempenho":
                                mastery = evaluate_performance_criterion(
                                    chart_data, mastery_threshold, mastery_sessions
                                )
                                fig_skill = mastery_progress_chart(
                                    mastery['current_rate'], mastery_threshold, mastery['streak'], mastery['required']
                                )
                                st.caption(
                                    f"{mastery['status']}. A sequência considera datas distintas; "
                                    f"manutenção: {mastery['maintenance_records']} registro(s); "
                                    f"generalização: {mastery['generalization_records']} registro(s)."
                                )
                            elif chart_view == "Comparação entre alvos":
                                target_summary = summarize_targets(df_alvos_brutos)
                                if target_summary.empty:
                                    st.info("Sem dados de alvos para comparação.")
                                else:
                                    fig_skill = target_summary_bar(target_summary, mastery_threshold)
                                    chart_data = target_summary
                            elif chart_view == "Heatmap dos alvos":
                                if all_target_sessions.empty:
                                    st.info("Sem dados de alvos para o heatmap.")
                                else:
                                    fig_skill = target_heatmap(all_target_sessions, mastery_threshold)
                                    chart_data = all_target_sessions
                            elif chart_view == "Exposição e oportunidades":
                                if alvo_sel == "TODOS OS ALVOS":
                                    exposure_data = aggregate_target_exposure(df_alvos_brutos)
                                else:
                                    exposure_data = chart_data
                                if exposure_data.empty or not exposure_data['has_attempts'].any():
                                    st.warning("Não há número real de oportunidades no período para esta visualização.")
                                else:
                                    missing_count = int((~exposure_data['has_attempts']).sum())
                                    if missing_count:
                                        st.warning(f"{missing_count} data(s) sem oportunidades foram omitidas das barras de exposição.")
                                    fig_skill = opportunities_chart(exposure_data)
                                    chart_data = exposure_data
                            elif chart_view == "Small multiples por alvo":
                                if all_target_sessions.empty:
                                    st.info("Sem dados de alvos para esta visualização.")
                                else:
                                    fig_skill = small_multiples(all_target_sessions, mastery_threshold)
                                    chart_data = all_target_sessions

                            if fig_skill is not None:
                                safe_program_name = re.sub(r'[^\w.-]+', '_', prog_sel, flags=re.UNICODE).strip('_') or 'objetivo'
                                safe_view_name = re.sub(r'[^\w.-]+', '_', chart_view, flags=re.UNICODE).strip('_') or 'grafico'
                                render_plotly_chart(
                                    fig_skill,
                                    width="stretch",
                                    config={
                                        "displaylogo": False,
                                        "toImageButtonOptions": {
                                            "format": "png",
                                            "filename": f"objetivo_{safe_program_name}",
                                            "scale": 2,
                                        },
                                    },
                                )
                                csv_data = chart_data.to_csv(index=False).encode("utf-8-sig")
                                st.download_button(
                                    "Baixar dados desta visualização (CSV)",
                                    data=csv_data,
                                    file_name=f"objetivo_{safe_program_name}_{safe_view_name}.csv",
                                    mime="text/csv",
                                    key=f"download_chart::{prog_sel}::{alvo_sel}::{chart_view}",
                                )

                            with st.expander("Qualidade dos dados deste recorte"):
                                quality_source = df_alvos_brutos if alvo_sel != "TODOS OS ALVOS" else df_p_view
                                if alvo_sel != "TODOS OS ALVOS":
                                    quality_source = quality_source[quality_source['target_name'] == alvo_sel]
                                issues = quality_issues(
                                    quality_source,
                                    expects_attempts=alvo_sel != "TODOS OS ALVOS",
                                )
                                q_cols = st.columns(4)
                                q_cols[0].metric("Registros", issues['records'])
                                q_cols[1].metric("Sem oportunidades", issues['missing_attempts'])
                                q_cols[2].metric("Percentuais ausentes", issues['missing_percentages'])
                                q_cols[3].metric("Fora da faixa 0–100", issues['invalid_percentages'])
                                q_cols_extra = st.columns(4)
                                q_cols_extra[0].metric("Soma > 100%", issues['inconsistent_sum'])
                                q_cols_extra[1].metric("Fase ausente", issues['missing_phase'])
                                q_cols_extra[2].metric("Datas inválidas", issues['invalid_dates'])
                                q_cols_extra[3].metric("Duplicidades potenciais", issues['potential_duplicates'])
                                if alvo_sel == "TODOS OS ALVOS":
                                    st.caption(
                                        "O total de oportunidades não existe nos registros de programa; selecione um alvo para analisar exposição real."
                                    )
                               
            # ==========================================
            # --- ABA 2: DECISÃO CLÍNICA ---
            # ==========================================
            elif active_tab == "Decisão":
                st.markdown(f"### Motor de Decisão Clínica: **{paciente_sel}**")
                df_p_filt = pd.DataFrame()
                df_b_decisao = pd.DataFrame()
                if not df_p_raw.empty:
                    min_d_d, max_d_d = df_p_raw['date'].min(), df_p_raw['date'].max()
                    c_dt_d, _ = st.columns([1, 2])
                    periodo_d = c_dt_d.date_input("Período de Análise", value=(min_d_d, max_d_d), format="DD/MM/YYYY", key="decisao_periodo")
                    start_d, end_d = (periodo_d[0], periodo_d[1]) if len(periodo_d) == 2 else (min_d_d, max_d_d)
                    df_p_filt = df_p_raw[(df_p_raw['date'] >= start_d) & (df_p_raw['date'] <= end_d)]
                    if not df_b_raw.empty:
                        df_b_decisao = df_b_raw[(df_b_raw['date'] >= start_d) & (df_b_raw['date'] <= end_d)].copy()
                
                with st.expander("Critério Padrão da Clínica (Global)"):
                    col_cfg1, col_cfg2 = st.columns(2)
                    global_pct = col_cfg1.number_input("Independência (%)", value=90, key="glob_pct")
                    global_dias = col_cfg2.number_input("Dias Consecutivos", value=10, key="glob_dias")

                st.markdown("---")
                if df_p_filt.empty:
                    st.warning("Sem dados no período selecionado.")
                else:
                    progs_ativos = sorted(df_p_filt['programa'].unique().tolist())
                    prog_decisao = st.selectbox("Selecione o Programa para Análise Detalhada", ["RESUMO GERAL"] + progs_ativos)

                    if prog_decisao == "RESUMO GERAL":
                        resumo_decisao = []
                        for p in progs_ativos:
                            df_h = df_p_filt[df_p_filt['programa'] == p].sort_values('date')
                            m_pct, m_dias = global_pct, global_dias
                            if not df_lib.empty and p in df_lib['name'].values:
                                reg = df_lib[df_lib['name'] == p].iloc[0]
                                m_pct, m_dias = int(reg['mastery_threshold_percent']), int(reg['mastery_days'])
                            criterio = evaluate_performance_criterion(df_h, m_pct, m_dias)
                            resumo_decisao.append({
                                "Programa": p,
                                "Status": criterio["status"],
                                "Sequência em datas": criterio["streak"],
                                "Datas observadas": criterio["distinct_dates"],
                                "Meta": f"{m_pct}% / {m_dias} datas",
                            })
                        st.subheader("Status dos Objetivos")
                        st.dataframe(pd.DataFrame(resumo_decisao).style.map(
                            lambda val: 'background-color: #d4edda; color: #155724;' if str(val).startswith('Domínio') else 'background-color: #fff3cd; color: #856404;' if str(val).startswith(('Critério', 'Em confirmação')) else '', subset=['Status']
                        ), width='stretch', hide_index=True)
                    else:
                        st.subheader(f"Análise Detalhada: {prog_decisao}")
                        m_pct, m_dias = global_pct, global_dias
                        if not df_lib.empty and prog_decisao in df_lib['name'].values:
                            reg = df_lib[df_lib['name'] == prog_decisao].iloc[0]
                            m_pct, m_dias = int(reg['mastery_threshold_percent']), int(reg['mastery_days'])
                        
                        c_adj1, c_adj2 = st.columns(2)
                        adj_pct = c_adj1.number_input(f"Ajustar Independência %", value=m_pct, key="adj_pct")
                        adj_dias = c_adj2.number_input(f"Ajustar Dias Consecutivos", value=m_dias, key="adj_dias")

                        df_alvos = load_targets_from_api(paciente_sel, prog_decisao)
                        df_alvos_filt = df_alvos[(df_alvos['date'] >= start_d) & (df_alvos['date'] <= end_d)] if not df_alvos.empty else pd.DataFrame()
                        
                        if not df_alvos_filt.empty:
                            fases_map = df_p_raw[df_p_raw['programa'] == prog_decisao][['date', 'phase']].set_index('date')['phase'].to_dict()
                            status_alvos = []
                            for alvo in sorted(df_alvos_filt['target_name'].unique()):
                                df_a_s = df_alvos_filt[df_alvos_filt['target_name'] == alvo].sort_values('date')
                                sessoes_lb = 0
                                sessoes_ajuda = 0
                                for index, row in df_a_s.iterrows():
                                    fase_orig = str(fases_map.get(row['date'], "")).lower().strip()
                                    is_lb = any(termo in fase_orig for termo in ["linha de base", "baseline", "sondagem"]) or bool(re.search(r'\blb\b', fase_orig))
                                    if is_lb: sessoes_lb += 1
                                    else: sessoes_ajuda += 1
                                criterio_alvo = evaluate_performance_criterion(df_a_s, adj_pct, adj_dias)
                                status_alvos.append({
                                    "Alvo": alvo, "Status": criterio_alvo["status"], "Sessões em LB": sessoes_lb,
                                    "Sessões em Ensino": sessoes_ajuda, "Seq. Independência": criterio_alvo["streak"],
                                    "Última Indep.": f"{df_a_s['independent_rate'].iloc[-1]}%"
                                })
                            st.table(pd.DataFrame(status_alvos))

                st.markdown("---")
                st.subheader("Interferentes no periodo de analise")
                if df_b_decisao.empty:
                    st.info("Sem registros de comportamentos interferentes no período; isso não equivale a zero observado.")
                else:
                    df_b_decisao['date_pd'] = pd.to_datetime(df_b_decisao['date'])
                    df_b_decisao['data_str'] = df_b_decisao['date_pd'].dt.strftime('%d/%m/%Y')
                    resumo_interferentes = summarize_interfering_behaviors(df_b_decisao)
                    qualidade_interferentes = behavior_quality_issues(df_b_decisao)
                    total_ocorrencias = resumo_interferentes['total_count'].dropna().sum()
                    taxa_media_periodo = pd.to_numeric(
                        df_b_decisao.get('rate', pd.Series(index=df_b_decisao.index, dtype=float)),
                        errors='coerce',
                    ).mean()
                    comportamento_principal = resumo_interferentes['behavior'].iloc[0]
                    col_int_1, col_int_2, col_int_3 = st.columns(3)
                    col_int_1.metric("Ocorrencias", f"{total_ocorrencias:.0f}")
                    col_int_2.metric("Comportamentos", df_b_decisao['comportamento'].nunique())
                    col_int_3.metric("Taxa media", f"{taxa_media_periodo:.2f}" if pd.notnull(taxa_media_periodo) else "N/A")

                    st.info(
                        "Leitura descritiva: o primeiro item por volume foi "
                        f"{comportamento_principal}. A ordenação não identifica função nem causalidade. "
                        "Cruze os dados com antecedentes, resposta, consequências, duração da observação e oportunidades "
                        "antes de formular hipóteses funcionais."
                    )
                    if qualidade_interferentes['missing_measure'] or qualidade_interferentes['invalid_dates'] or qualidade_interferentes['potential_duplicates']:
                        st.warning(
                            f"Qualidade dos dados: {qualidade_interferentes['missing_measure']} sem medida, "
                            f"{qualidade_interferentes['invalid_dates']} datas inválidas e "
                            f"{qualidade_interferentes['potential_duplicates']} possíveis duplicidades."
                        )

                    col_graf_int_1, col_graf_int_2 = st.columns(2)
                    with col_graf_int_1:
                        fig_int_count = px.bar(
                            df_b_decisao.sort_values('date_pd'),
                            x='data_str',
                            y='count',
                            color='comportamento',
                            barmode='group',
                            title="Interferentes por sessao",
                            labels={'data_str': 'Data', 'count': 'Contagem', 'comportamento': 'Comportamento'},
                        )
                        fig_int_count.update_xaxes(type='category', tickangle=-45)
                        render_plotly_chart(fig_int_count, width="stretch")
                    with col_graf_int_2:
                        fig_int_rate = px.line(
                            df_b_decisao.sort_values('date_pd'),
                            x='date_pd',
                            y='rate',
                            color='comportamento',
                            markers=True,
                            title="Taxa de interferentes",
                            labels={'date_pd': 'Data', 'rate': 'Taxa', 'comportamento': 'Comportamento'},
                        )
                        fig_int_rate.update_xaxes(type='date', tickformat="%d/%m/%y", tickangle=-45)
                        render_plotly_chart(fig_int_rate, width="stretch")

                    st.dataframe(
                        resumo_interferentes.rename(columns={
                            'behavior': 'Comportamento',
                            'records': 'Registros',
                            'observed_days': 'Dias observados',
                            'total_count': 'Ocorrências',
                            'mean_rate': 'Taxa média',
                            'measure': 'Medida analisada',
                            'latest_value': 'Último valor',
                            'slope': 'Inclinação',
                            'trend': 'Tendência',
                            'variability': 'Variabilidade',
                        }),
                        width="stretch",
                        hide_index=True,
                    )

            # ==========================================
            # --- ABA 3: INTERFERENTES ---
            # ==========================================
            elif active_tab == "Interferentes":
                st.markdown(f"###  Manejo de Crises: **{paciente_sel}**")
                if not df_b_raw.empty and not df_b_raw['date'].dropna().empty:
                    min_d_b, max_d_b = df_b_raw['date'].min(), df_b_raw['date'].max()
                    c_dt_b, _ = st.columns([1, 2])
                    periodo_b = c_dt_b.date_input(" Período (Interferentes)", value=(min_d_b, max_d_b), format="DD/MM/YYYY", key="periodo_b")
                    st_b, en_b = (periodo_b[0], periodo_b[1]) if len(periodo_b) == 2 else (min_d_b, max_d_b)
                    df_beh = df_b_raw[(df_b_raw['date'] >= st_b) & (df_b_raw['date'] <= en_b)]
                    
                    if df_beh.empty:
                        st.info("Sem registros de comportamentos interferentes para este período; isso não equivale a zero observado.")
                    else:
                        leitura_beh = summarize_interfering_behaviors(df_beh)
                        st.dataframe(
                            leitura_beh.rename(columns={
                                'behavior': 'Comportamento', 'records': 'Registros',
                                'observed_days': 'Dias observados', 'total_count': 'Ocorrências',
                                'mean_rate': 'Taxa média', 'measure': 'Medida',
                                'latest_value': 'Último valor', 'trend': 'Tendência',
                                'variability': 'Variabilidade',
                            }),
                            width="stretch",
                            hide_index=True,
                        )
                        st.caption(
                            "A tabela descreve nível, tendência e variabilidade; não determina função. "
                            "Hipóteses funcionais exigem dados de antecedentes, resposta e consequências."
                        )
                        beh_sel = st.selectbox("Selecione o Comportamento", ["VISÃO GERAL (Todos)"] + sorted(df_beh['comportamento'].unique().tolist()))
                        if beh_sel == "VISÃO GERAL (Todos)":
                            c1, c2 = st.columns(2)
                            with c1:
                                fig1 = px.bar(df_beh, x='date', y='count', color='comportamento', barmode='group', title="Frequência (Contagem)")
                                fig1.update_xaxes(type='category', tickangle=-45) 
                                render_plotly_chart(fig1, width="stretch")
                            with c2:
                                fig2 = px.line(df_beh, x='date', y='rate', color='comportamento', markers=True, title="Taxa (Ocorrências/Hora)")
                                fig2.update_xaxes(type='date', tickformat="%d/%m/%y", tickangle=-45)
                                render_plotly_chart(fig2, width="stretch")
                        else:
                            df_f = df_beh[df_beh['comportamento'] == beh_sel].sort_values('date')
                            fig = px.line(df_f, x='date', y='rate', markers=True, title=f"Evolução: {beh_sel}")
                            fig.update_xaxes(type='date', tickformat="%d/%m/%y", tickangle=-45)
                            render_plotly_chart(fig, width="stretch")

            # ==========================================
            # --- ABA 4: RELATÓRIO PEI ---
            # ==========================================
            elif active_tab == "PEI":
                
                st.markdown(f"### Relatorio PEI: **{paciente_sel}**")
                
                START_DATE = datetime(2026, 3, 27)
                ref_date = START_DATE.date()
                hoje = datetime.now().date()

                modo_relatorio = st.radio(
                    "Tipo de relatório",
                    ["Personalizado", "Trimestral", "Anual"],
                    horizontal=True,
                    key="pei_modo_relatorio",
                )

                TRIMESTRES_PEI = {
                    "T1 (Mar–Jun 2026)": (
                        START_DATE.date(),
                        (START_DATE + timedelta(days=89)).date(),
                    ),
                    "T2 (Jun–Set 2026)": (
                        (START_DATE + timedelta(days=90)).date(),
                        (START_DATE + timedelta(days=179)).date(),
                    ),
                    "T3 (Set–Dez 2026)": (
                        (START_DATE + timedelta(days=180)).date(),
                        (START_DATE + timedelta(days=269)).date(),
                    ),
                    "T4 (Dez 2026–Mar 2027)": (
                        (START_DATE + timedelta(days=270)).date(),
                        (START_DATE + timedelta(days=359)).date(),
                    ),
                }

                if modo_relatorio == "Personalizado":
                    periodo_pei = st.date_input(
                        "Periodo do PEI",
                        value=(max(ref_date, hoje - timedelta(days=90)), hoje if hoje >= ref_date else ref_date),
                        min_value=ref_date,
                        max_value=hoje,
                        format="DD/MM/YYYY",
                        key="pei_periodo",
                    )
                    if isinstance(periodo_pei, tuple) and len(periodo_pei) == 2:
                        ciclo_inicio_pei, ciclo_fim_pei = periodo_pei
                    else:
                        ciclo_inicio_pei, ciclo_fim_pei = ref_date, hoje
                    if ciclo_inicio_pei > ciclo_fim_pei:
                        ciclo_inicio_pei, ciclo_fim_pei = ciclo_fim_pei, ciclo_inicio_pei
                elif modo_relatorio == "Trimestral":
                    trimestre_sel = st.selectbox(
                        "Selecione o trimestre",
                        list(TRIMESTRES_PEI.keys()),
                        key="pei_trimestre_sel",
                    )
                    ciclo_inicio_pei, ciclo_fim_pei = TRIMESTRES_PEI[trimestre_sel]
                else:  # Anual
                    ciclo_inicio_pei = START_DATE.date()
                    ciclo_fim_pei = (START_DATE + timedelta(days=359)).date()

                ciclo_fim_exclusivo_pei = ciclo_fim_pei + timedelta(days=1)
                st.caption(
                    "Periodo selecionado: "
                    f"{ciclo_inicio_pei.strftime('%d/%m/%Y')} a {ciclo_fim_pei.strftime('%d/%m/%Y')}"
                )

                programas_pei = sorted([
                    str(programa).strip()
                    for programa in df_p_raw.get("programa", pd.Series(dtype=str)).dropna().unique()
                    if str(programa).strip()
                ])
                objetivo_grafico_pei = st.selectbox(
                    "Objetivo para o grafico do PEI",
                    ["Media geral dos objetivos"] + programas_pei,
                    key="pei_objetivo_grafico",
                )
                usar_ia_texto_pei = st.checkbox(
                    "Gerar texto do periodo com IA",
                    value=True,
                    key="pei_usar_ia_texto",
                )

                def carregar_alvos_programas_pei(programas):
                    todos_alvos = []
                    for prog in programas:
                        alvos = load_targets_from_api(paciente_sel, prog)
                        if not alvos.empty:
                            alvos = alvos.copy()
                            alvos["programa"] = prog
                            todos_alvos.append(alvos)
                    return pd.concat(todos_alvos, ignore_index=True) if todos_alvos else pd.DataFrame()

                # Visualização na Tela do Dashboard
                df_pei = filtrar_periodo_pei_service(df_p_raw, ciclo_inicio_pei, ciclo_fim_exclusivo_pei)
                df_alvos_preview = carregar_alvos_programas_pei(programas_pei)
                df_alvos_periodo_preview = filtrar_periodo_pei_service(df_alvos_preview, ciclo_inicio_pei, ciclo_fim_exclusivo_pei)

                st.subheader("Gráfico de independência média dos objetivos")
                df_obj_visual = df_pei.copy()
                if objetivo_grafico_pei != "Media geral dos objetivos" and not df_obj_visual.empty:
                    df_obj_visual = df_obj_visual[df_obj_visual["programa"] == objetivo_grafico_pei]
                if df_obj_visual.empty:
                    st.info("Sem registros para o objetivo selecionado no periodo.")
                else:
                    df_obj_plot = (
                        df_obj_visual.groupby("date_pd", as_index=False)
                        .agg({"independent_rate": "mean"})
                        .sort_values("date_pd")
                    )
                    df_obj_plot = df_obj_plot.rename(columns={
                        "date_pd": "Data",
                        "independent_rate": "Independência média",
                    })
                    titulo_grafico_pei = (
                        "Independência média dos objetivos"
                        if objetivo_grafico_pei == "Media geral dos objetivos"
                        else f"Independência média - {objetivo_grafico_pei}"
                    )
                    fig_obj_pei = px.line(
                        df_obj_plot,
                        x="Data",
                        y="Independência média",
                        markers=True,
                        title=titulo_grafico_pei,
                        labels={"Independência média": "Independência média (%)"},
                    )
                    fig_obj_pei.update_yaxes(range=[0, 100], title="Independência média (%)")
                    fig_obj_pei.update_xaxes(type="date", tickformat="%d/%m/%Y", tickangle=-45)
                    render_plotly_chart(fig_obj_pei, width="stretch")

                st.subheader("Areas e objetivos no periodo selecionado")
                areas_preview = distribuir_objetivos_por_area_service(
                    df_pei,
                    filtrar_periodo_pei_service(df_b_raw, ciclo_inicio_pei, ciclo_fim_exclusivo_pei),
                )
                resumo_objetivos_preview = resumo_objetivos_por_area_service(areas_preview)
                if resumo_objetivos_preview.empty:
                    st.info("Sem objetivos registrados no periodo selecionado.")
                else:
                    st.dataframe(resumo_objetivos_preview, hide_index=True, width="stretch")

                st.subheader("Alvos trabalhados e desempenho no periodo selecionado")
                resumo_alvos_preview = resumo_alvos_por_objetivo_service(
                    areas_preview,
                    df_p_raw,
                    df_alvos_preview,
                    df_alvos_periodo_preview,
                    df_lib,
                    ciclo_inicio_pei,
                    ciclo_fim_pei,
                )
                if resumo_alvos_preview.empty:
                    st.info("Sem alvos trabalhados no periodo selecionado.")
                else:
                    st.dataframe(
                        estilizar_status_preview_pei_service(resumo_alvos_preview),
                        hide_index=True,
                        width="stretch",
                    )

                if not df_b_raw.empty:
                    st.subheader("Evolucao de Comportamentos Interferentes")
                    df_b_pei = filtrar_periodo_pei_service(df_b_raw, ciclo_inicio_pei, ciclo_fim_exclusivo_pei)
                    if not df_b_pei.empty:
                        y_interf = 'rate' if 'rate' in df_b_pei.columns else 'count'
                        fig_pei = px.bar(df_b_pei, x='date', y=y_interf, color='comportamento', title="Interferentes no periodo selecionado")
                        fig_pei.update_xaxes(type='date', tickformat="%d/%m/%Y", tickangle=-45)
                        render_plotly_chart(fig_pei, width="stretch")

                pei_key = f"pei_docx::{paciente_sel}"
                pei_name_key = f"pei_docx_name::{paciente_sel}"

                if modo_relatorio != "Anual" and st.button("Gerar Documento PEI Oficial com Graficos"):
                    with st.spinner("Compilando graficos, grade de objetivos e resumo dos comportamentos. Aguarde..."):
                        df_alvos_completo = df_alvos_preview.copy()
                        
                        df_prog_dados = preparar_programas_pei(df_p_raw, df_lib)
                        df_alvos_periodo_pei = filtrar_periodo_pei_service(df_alvos_completo, ciclo_inicio_pei, ciclo_fim_exclusivo_pei)
                        df_beh_periodo_pei = filtrar_periodo_pei_service(df_b_raw, ciclo_inicio_pei, ciclo_fim_exclusivo_pei)
                        df_hist_periodo_pei = filtrar_periodo_pei_service(df_p_raw, ciclo_inicio_pei, ciclo_fim_exclusivo_pei)
                        texto_analise_trimestral = gerar_texto_trimestral_pei_service(
                            paciente_sel,
                            df_hist_periodo_pei,
                            df_alvos_periodo_pei,
                            df_beh_periodo_pei,
                            objetivo_grafico_pei,
                            ciclo_inicio_pei,
                            ciclo_fim_pei,
                            usar_ia=usar_ia_texto_pei,
                            ask_agent_fn=ask_clinical_agent if usar_ia_texto_pei else None,
                        )
                        texto_resumo_comportamentos = gerar_resumo_comportamentos_problema_pei_service(
                            paciente_sel,
                            df_beh_periodo_pei,
                            ciclo_inicio_pei,
                            ciclo_fim_pei,
                            usar_ia=usar_ia_texto_pei,
                            ask_agent_fn=ask_clinical_agent if usar_ia_texto_pei else None,
                        )

                        # Gera o buffer do documento
                        buffer_file = gerar_doc_completo_service(
                            paciente_sel,
                            df_prog_dados,
                            df_p_raw,
                            df_alvos_completo,
                            df_lib,
                            df_b_raw,
                            objetivo_grafico_pei,
                            ciclo_inicio_pei,
                            ciclo_fim_pei,
                            ciclo_fim_exclusivo_pei,
                            texto_analise_trimestral,
                            texto_resumo_comportamentos,
                            pei_template_path=PEI_TEMPLATE_PATH,
                            start_date=START_DATE,
                        )
                        st.session_state[pei_key] = buffer_file.getvalue()
                        st.session_state[pei_name_key] = (
                            f"PEI_{paciente_sel.replace(' ', '_')}_"
                            f"{ciclo_inicio_pei.strftime('%Y%m%d')}_{ciclo_fim_pei.strftime('%Y%m%d')}.docx"
                        )
                        st.success("PEI gerado. Use o botao abaixo para baixar o arquivo.")

                if modo_relatorio == "Anual":
                    if st.button("Gerar Relatório Anual Unificado (4 Trimestres)", key="btn_pei_anual"):
                        with st.spinner("Gerando os 4 trimestres e unificando. Isso pode levar alguns minutos..."):
                            df_alvos_anual = df_alvos_preview.copy()
                            df_prog_anual = preparar_programas_pei(df_p_raw, df_lib)
                            buffer_anual = gerar_doc_anual_pei_service(
                                paciente_sel,
                                df_prog_anual,
                                df_p_raw,
                                df_alvos_anual,
                                df_lib,
                                df_b_raw,
                                objetivo_grafico_pei,
                                start_date=START_DATE,
                                ask_agent_fn=ask_clinical_agent if usar_ia_texto_pei else None,
                            )
                            st.session_state[pei_key] = buffer_anual.getvalue()
                            st.session_state[pei_name_key] = (
                                f"PEI_ANUAL_{paciente_sel.replace(' ', '_')}_"
                                f"{START_DATE.strftime('%Y')}.docx"
                            )
                            st.success("Relatório anual gerado. Use o botao abaixo para baixar.")

                if st.session_state.get(pei_key):
                    st.download_button(
                        label="Baixar PEI em DOCX",
                        data=st.session_state[pei_key],
                        file_name=st.session_state.get(pei_name_key, f"PEI_{paciente_sel.replace(' ', '_')}.docx"),
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        width="stretch",
                    )

            # ==========================================
            # --- ABA 5: AVALIAÇÕES (ABLLS-R) ---
            # ==========================================
            elif active_tab == "Avaliações":
                try:
                    render_ablls_module(paciente_sel, df_p_raw)
                except Exception as exc:
                    st.error(f"Nao consegui carregar a aba de avaliacoes: {exc}")

            # ==========================================
            # --- ABA 6: ASSISTENTE ---
            # ==========================================
            elif active_tab == "Assistente":
                st.markdown(f"### Assistente clinico: **{paciente_sel}**")

                min_d_a, max_d_a = df_p_raw['date'].min(), df_p_raw['date'].max()
                c_dt_a, _ = st.columns([1, 2])
                periodo_a = c_dt_a.date_input(
                    "Periodo de analise",
                    value=(min_d_a, max_d_a),
                    format="DD/MM/YYYY",
                    key="assistente_periodo",
                )
                start_a, end_a = (periodo_a[0], periodo_a[1]) if len(periodo_a) == 2 else (min_d_a, max_d_a)

                resposta_agente_key = f"resposta_agente_clinico_{paciente_sel}"
                pergunta_agente = st.text_area(
                    "Pergunta clinica",
                    value=(
                        "Quais hipoteses clinicas e proximos passos observaveis fazem sentido "
                        "para este paciente neste periodo, considerando habilidades, alvos e comportamentos interferentes?"
                    ),
                    height=140,
                    key="pergunta_agente_clinico",
                )

                if st.button("Consultar assistente", key="botao_agente_clinico"):
                    if not pergunta_agente.strip():
                        st.warning("Informe uma pergunta clinica.")
                    else:
                        with st.spinner("Consultando a base local e preparando a sintese..."):
                            try:
                                st.session_state[resposta_agente_key] = ask_clinical_agent(
                                    paciente_sel,
                                    pergunta_agente,
                                    start_a,
                                    end_a,
                                )
                            except Exception as exc:
                                st.error(f"Erro ao consultar o assistente: {exc}")

                resposta_agente = st.session_state.get(resposta_agente_key)
                if resposta_agente:
                    st.markdown("#### Sintese")
                    modo_agente = resposta_agente.get("modo", "")
                    texto_resposta_agente = resposta_agente.get("resposta", "")
                    if modo_agente == "limite_ia":
                        st.warning(texto_resposta_agente)
                    elif modo_agente in ["busca_local", "busca_local_fallback"]:
                        st.info(texto_resposta_agente)
                    else:
                        st.write(texto_resposta_agente)
                    texto_referencias = texto_resposta_agente.casefold()
                    if (
                        resposta_agente.get("fontes")
                        and "referencias utilizadas" not in texto_referencias
                        and "referências utilizadas" not in texto_referencias
                    ):
                        render_agent_references(resposta_agente.get("fontes", []))
