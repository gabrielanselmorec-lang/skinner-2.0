import os
import sys
import re
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import requests
import plotly.express as px



# Ajuste de Caminho para importar o main.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from main import sincronizar_bhave_api

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from ablls_view import render_ablls_module

# Configuração da Página
st.set_page_config(page_title="Skinner Project", layout="wide")

# CSS para visual profissional
st.markdown("""
    <style>
    [data-testid="stStatusWidget"] { visibility: hidden; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

API_URL = "http://127.0.0.1:8000"
API_TIMEOUT_SECONDS = 90
AGENT_TIMEOUT_SECONDS = int(os.getenv("SKINNER_AGENT_TIMEOUT_SECONDS", "300"))
PEI_TEMPLATE_PATH = os.getenv(
    "SKINNER_PEI_TEMPLATE_PATH",
    r"C:\Users\coord\Desktop\PEI_2026_TEMPLATE_V3.docx",
)

from api_client import (
    load_data_from_api,
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
    distribuir_objetivos_por_area as distribuir_objetivos_por_area_service,
    filtrar_periodo_pei as filtrar_periodo_pei_service,
    resumo_objetivos_por_area as resumo_objetivos_por_area_service,
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

st.title("Skinner Project - Análise Clínica")
st.markdown("---")

# Verificação da API
try:
    lista_pacientes = requests.get(f"{API_URL}/api/pacientes", timeout=API_TIMEOUT_SECONDS).json()
    lista_pacientes = sorted(lista_pacientes) 
except requests.exceptions.ConnectionError:
    st.error("ERRO: A API não está respondendo. Ligue o Uvicorn no terminal.")
    st.stop()
except requests.exceptions.Timeout:
    st.error("ERRO: A API demorou demais para responder. Tente novamente.")
    st.stop()
except Exception as e:
    st.error(f"ERRO ao conectar à API: {type(e).__name__}. Verifique o terminal.")
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
            
            tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Habilidades", "Decisão", "Interferentes", "PEI", "Avaliações", "Assistente"
    ])

            # ==========================================
            # --- ABA 1: HABILIDADES ---
            # ==========================================
            with tab1:
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
                            fig_resumo = px.bar(df_resumo, y='programa', x='independent_rate', orientation='h', text='independent_rate', color_discrete_sequence=['#2ECC71'], labels={'programa': 'Programa', 'independent_rate': 'Independência (%)'})
                            fig_resumo.update_traces(textposition='outside')
                            fig_resumo.update_layout(xaxis_range=[0, 100])
                            st.plotly_chart(fig_resumo, width='stretch')
                        
                    elif prog_sel:
                        df_p_view = df_prog[df_prog['programa'] == prog_sel].sort_values('date').copy()
                        df_alvos_brutos = load_targets_from_api(paciente_sel, prog_sel)
                        lista_alvos = sorted([alvo for alvo in df_alvos_brutos['target_name'].unique().tolist() if alvo.strip() != ""]) if not df_alvos_brutos.empty else []
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
                                
                        st.markdown(f"** Meta do Programa:** {objetivo_texto}")
                        st.markdown("###  Desempenho no Período Selecionado")

                        if not df_p_view.empty:
                            if 'phase' not in df_p_view.columns: df_p_view['phase'] = ""
                            
                            mask_lb_prog = df_p_view['phase'].astype(str).str.contains(r'linha de base|\blb\b|baseline|sondagem', case=False, na=False)
                            df_p_int = df_p_view[~mask_lb_prog] 
                            df_p_lb = df_p_view[mask_lb_prog]   
                            
                            media_indep_int = df_p_int['independent_rate'].mean() if not df_p_int.empty else None
                            media_indep_lb = df_p_lb['independent_rate'].mean() if not df_p_lb.empty else None
                            
                            ultima_data = df_p_view['date'].iloc[-1]
                            data_formatada = pd.to_datetime(ultima_data).strftime("%d/%m/%Y")
                            
                            col_m1, col_m2, col_m3 = st.columns(3)
                            
                            col_m1.metric(" Última Aplicação", data_formatada)
                            
                            delta_lb = f"{media_indep_int - media_indep_lb:.1f}% vs LB" if (pd.notnull(media_indep_int) and pd.notnull(media_indep_lb)) else None
                            col_m2.metric(" Indep. Média (Intervenção)", f"{media_indep_int:.1f}%" if pd.notnull(media_indep_int) else "N/A", delta=delta_lb)
                            col_m3.metric(" Média Linha de Base", f"{media_indep_lb:.1f}%" if pd.notnull(media_indep_lb) else "N/A")

                            st.markdown("---")
                            col_geral, col_especifica = st.columns([1, 1])

                            with col_geral:
                                st.subheader(" Gráfico de Colunas (Sessões)")
                                
                                df_p_view['data_str'] = pd.to_datetime(df_p_view['date']).dt.strftime('%d/%m/%Y')
                                df_p_view['phase_clean'] = df_p_view['phase'].astype(str).str.upper().str.strip()
                                df_p_view['phase_clean'] = df_p_view['phase_clean'].replace(["NAN", "NONE", ""], "NÃO INFORMADA")

                                # AGRUPAMENTO DIÁRIO PARA EVITAR DUPLICIDADE (QUADRADOS DUPLOS NO GRÁFICO)
                                df_chart = df_p_view.groupby(['data_str', 'date'], as_index=False).agg({
                                    'independent_rate': 'mean',
                                    'prompt_rate': 'mean',
                                    'phase_clean': 'last'
                                }).sort_values('date')

                                df_chart['Independentes'] = (df_chart['independent_rate'] * 10 / 100).round(0)
                                df_chart['Com Ajuda'] = (df_chart['prompt_rate'] * 10 / 100).round(0)
                                df_chart['Erros'] = (10 - (df_chart['Independentes'] + df_chart['Com Ajuda'])).clip(lower=0)

                                fases_mudanca = []
                                last_valid_phase = None
                                for i, row_fase in df_chart.iterrows():
                                    curr_phase = str(row_fase['phase_clean'])
                                    if curr_phase not in ["NÃO INFORMADA"]:
                                        if last_valid_phase is not None and curr_phase != last_valid_phase:
                                            fases_mudanca.append({'data_str': row_fase['data_str'], 'fase': curr_phase})
                                        last_valid_phase = curr_phase

                                df_p_melt = df_chart.melt(id_vars=['data_str'], value_vars=['Independentes', 'Com Ajuda', 'Erros'], var_name='Status', value_name='Quantidade')
                                fig_p = px.bar(df_p_melt, x='data_str', y='Quantidade', color='Status', 
                                               color_discrete_map={'Independentes': '#2ECC71', 'Com Ajuda': '#F1C40F', 'Erros': '#E74C3C'})
                                
                                fig_p.update_yaxes(range=[0, 11])
                                fig_p.update_xaxes(type='category', tickangle=-45)
                                
                                for mudanca in fases_mudanca:
                                    fig_p.add_vline(x=mudanca['data_str'], line_width=2, line_dash="dash", line_color="black")
                                    fig_p.add_annotation(
                                        x=mudanca['data_str'], y=10.5, 
                                        text=f"  {mudanca['fase']} ",
                                        showarrow=False, textangle=-90, yanchor="bottom",
                                        font=dict(color="black", size=11, weight="bold")
                                    )
                                    
                                st.plotly_chart(fig_p, width="stretch")

                            with col_especifica:
                                if alvo_sel == "TODOS OS ALVOS":
                                    st.subheader(" Desempenho por Alvo (%)")
                                    if not df_alvos_brutos.empty:
                                        if 'phase' not in df_alvos_brutos.columns: df_alvos_brutos['phase'] = ""
                                        mask_a_lb_geral = df_alvos_brutos['phase'].astype(str).str.contains(r'linha de base|\blb\b|baseline|sondagem', case=False, na=False)
                                        df_alvos_int = df_alvos_brutos[~mask_a_lb_geral]
                                        
                                        if not df_alvos_int.empty:
                                            df_res_alvos = df_alvos_int.groupby('target_name')['independent_rate'].mean().reset_index().sort_values('independent_rate', ascending=False)
                                            fig_bar_alvos = px.bar(df_res_alvos, x='target_name', y='independent_rate', text_auto='.1f', color='independent_rate', color_continuous_scale='RdYlGn', range_y=[0, 100])
                                            st.plotly_chart(fig_bar_alvos, width='stretch')
                                        else:
                                            st.info(" Todos os alvos encontram-se em Linha de Base (Aguardando intervenção).")
                                else:
                                    st.subheader(f" Detalhe: {alvo_sel}")
                                    df_a_view = df_alvos_brutos[df_alvos_brutos['target_name'] == alvo_sel].sort_values('date').copy()
                                    if not df_a_view.empty:
                                        df_a_view['data_str'] = pd.to_datetime(df_a_view['date']).dt.strftime('%d/%m/%Y')
                                        
                                        # Agrupamento também nos alvos para evitar barras duplas
                                        df_a_chart = df_a_view.groupby(['data_str', 'date'], as_index=False).agg({
                                            'independent_rate': 'mean',
                                            'prompt_rate': 'mean'
                                        }).sort_values('date')

                                        df_a_chart['Independentes'] = (df_a_chart['independent_rate'] * 10 / 100).round(0)
                                        df_a_chart['Com Ajuda'] = (df_a_chart['prompt_rate'] * 10 / 100).round(0)
                                        df_a_chart['Erros'] = (10 - (df_a_chart['Independentes'] + df_a_chart['Com Ajuda'])).clip(lower=0)
                                        df_melt_a = df_a_chart.melt(id_vars=['data_str'], value_vars=['Independentes', 'Com Ajuda', 'Erros'], var_name='Status', value_name='Qtd')
                                        
                                        fig_a = px.bar(df_melt_a, x='data_str', y='Qtd', color='Status', color_discrete_map={'Independentes': '#2ECC71', 'Com Ajuda': '#F1C40F', 'Erros': '#E74C3C'})
                                        fig_a.update_xaxes(type='category', tickangle=-45)
                                        st.plotly_chart(fig_a, width='stretch')
                               
            # ==========================================
            # --- ABA 2: DECISÃO CLÍNICA ---
            # ==========================================
            with tab2:
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
                            streak = 0
                            for rate in df_h['independent_rate']:
                                if rate >= m_pct: streak += 1
                                else: streak = 0
                            status = "Atingido" if streak >= m_dias else "Em Evolução" if streak > 0 else "Estagnado"
                            resumo_decisao.append({"Programa": p, "Status": status, "Sessões Consecutivas": streak, "Meta": f"{m_pct}% / {m_dias}d"})
                        st.subheader("Status dos Objetivos")
                        st.dataframe(pd.DataFrame(resumo_decisao).style.map(
                            lambda val: 'background-color: #d4edda; color: #155724;' if val == 'Atingido' else 'background-color: #fff3cd; color: #856404;' if val == 'Em Evolução' else 'background-color: #f8d7da; color: #721c24;' if val == 'Estagnado' else '', subset=['Status']
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
                                stk = 0
                                sessoes_lb = 0
                                sessoes_ajuda = 0
                                for index, row in df_a_s.iterrows():
                                    fase_orig = str(fases_map.get(row['date'], "")).lower().strip()
                                    is_lb = any(termo in fase_orig for termo in ["linha de base", "baseline", "sondagem"]) or bool(re.search(r'\blb\b', fase_orig))
                                    if is_lb: sessoes_lb += 1
                                    else: sessoes_ajuda += 1
                                    if row['independent_rate'] >= adj_pct: stk += 1
                                    else: stk = 0
                                res_a = "Independente" if stk >= adj_dias else "Em Treino"
                                status_alvos.append({
                                    "Alvo": alvo, "Status": res_a, "Sessões em LB": sessoes_lb, 
                                    "Sessões em Ensino": sessoes_ajuda, "Seq. Independência": stk, 
                                    "Última Indep.": f"{df_a_s['independent_rate'].iloc[-1]}%"
                                })
                            st.table(pd.DataFrame(status_alvos))

                st.markdown("---")
                st.subheader("Interferentes no periodo de analise")
                if df_b_decisao.empty:
                    st.info("Sem comportamentos interferentes registrados para o periodo selecionado.")
                else:
                    df_b_decisao['date_pd'] = pd.to_datetime(df_b_decisao['date'])
                    df_b_decisao['data_str'] = df_b_decisao['date_pd'].dt.strftime('%d/%m/%Y')
                    resumo_interferentes = (
                        df_b_decisao.groupby('comportamento', as_index=False)
                        .agg(
                            total_ocorrencias=('count', 'sum'),
                            taxa_media=('rate', 'mean'),
                            taxa_maxima=('rate', 'max'),
                            registros=('date', 'count'),
                            ultima_data=('date_pd', 'max'),
                        )
                        .sort_values(['total_ocorrencias', 'taxa_media'], ascending=False)
                    )

                    total_ocorrencias = resumo_interferentes['total_ocorrencias'].sum()
                    taxa_media_periodo = df_b_decisao['rate'].mean()
                    comportamento_principal = resumo_interferentes['comportamento'].iloc[0]
                    col_int_1, col_int_2, col_int_3 = st.columns(3)
                    col_int_1.metric("Ocorrencias", f"{total_ocorrencias:.0f}")
                    col_int_2.metric("Comportamentos", df_b_decisao['comportamento'].nunique())
                    col_int_3.metric("Taxa media", f"{taxa_media_periodo:.2f}" if pd.notnull(taxa_media_periodo) else "N/A")

                    st.info(
                        "Leitura inicial: o comportamento com maior peso no periodo foi "
                        f"{comportamento_principal}. Considere cruzar os dias de pico com demandas, fases de ensino, "
                        "nivel de ajuda e eventos antecedentes/consequentes antes de decidir proximos passos."
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
                        st.plotly_chart(fig_int_count, width="stretch")
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
                        st.plotly_chart(fig_int_rate, width="stretch")

                    resumo_interferentes['ultima_data'] = resumo_interferentes['ultima_data'].dt.strftime('%d/%m/%Y')
                    st.dataframe(
                        resumo_interferentes.rename(columns={
                            'comportamento': 'Comportamento',
                            'total_ocorrencias': 'Ocorrencias',
                            'taxa_media': 'Taxa media',
                            'taxa_maxima': 'Taxa maxima',
                            'registros': 'Registros',
                            'ultima_data': 'Ultima data',
                        }),
                        width="stretch",
                        hide_index=True,
                    )

            # ==========================================
            # --- ABA 3: INTERFERENTES ---
            # ==========================================
            with tab3:
                st.markdown(f"###  Manejo de Crises: **{paciente_sel}**")
                if not df_b_raw.empty and not df_b_raw['date'].dropna().empty:
                    min_d_b, max_d_b = df_b_raw['date'].min(), df_b_raw['date'].max()
                    c_dt_b, _ = st.columns([1, 2])
                    periodo_b = c_dt_b.date_input(" Período (Interferentes)", value=(min_d_b, max_d_b), format="DD/MM/YYYY", key="periodo_b")
                    st_b, en_b = (periodo_b[0], periodo_b[1]) if len(periodo_b) == 2 else (min_d_b, max_d_b)
                    df_beh = df_b_raw[(df_b_raw['date'] >= st_b) & (df_b_raw['date'] <= en_b)]
                    
                    if df_beh.empty:
                        st.info("Sem comportamentos interferentes para este período.")
                    else:
                        beh_sel = st.selectbox("Selecione o Comportamento", ["VISÃO GERAL (Todos)"] + sorted(df_beh['comportamento'].unique().tolist()))
                        if beh_sel == "VISÃO GERAL (Todos)":
                            c1, c2 = st.columns(2)
                            with c1:
                                fig1 = px.bar(df_beh, x='date', y='count', color='comportamento', barmode='group', title="Frequência (Contagem)")
                                fig1.update_xaxes(type='category', tickangle=-45) 
                                st.plotly_chart(fig1, width="stretch")
                            with c2:
                                fig2 = px.line(df_beh, x='date', y='rate', color='comportamento', markers=True, title="Taxa (Ocorrências/Hora)")
                                fig2.update_xaxes(type='date', tickformat="%d/%m/%y", tickangle=-45)
                                st.plotly_chart(fig2, width="stretch")
                        else:
                            df_f = df_beh[df_beh['comportamento'] == beh_sel].sort_values('date')
                            fig = px.line(df_f, x='date', y='rate', markers=True, title=f"Evolução: {beh_sel}")
                            fig.update_xaxes(type='date', tickformat="%d/%m/%y", tickangle=-45)
                            st.plotly_chart(fig, width="stretch")

            # ==========================================
            # --- ABA 4: RELATÓRIO PEI ---
            # ==========================================
            with tab4:
                
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
                    st.plotly_chart(fig_obj_pei, width="stretch")

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
                        st.plotly_chart(fig_pei, width="stretch")

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
            with tab5:
                render_ablls_module(paciente_sel, df_p_raw)

            # ==========================================
            # --- ABA 6: ASSISTENTE ---
            # ==========================================
            with tab6:
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
