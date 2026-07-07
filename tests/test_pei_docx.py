"""Testes das regras de montagem do DOCX PEI."""
import os
import sys
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.pei_docx import preparar_programas_pei, resumo_alvos_por_objetivo


def test_resumo_alvos_por_objetivo_exibe_codigo_e_nome_do_objetivo():
    areas = {1: [{"programa": "Mando com frases", "texto": "Usar frases para pedir."}]}
    df_hist = pd.DataFrame({
        "programa": ["Mando com frases"],
        "date": ["2026-07-01"],
        "independent_rate": [80],
        "phase": [""],
    })
    df_alvos = pd.DataFrame({
        "programa": ["Mando com frases"],
        "target_name": ["Pedir ajuda"],
        "date": ["2026-07-01"],
        "independent_rate": [80],
        "phase": [""],
    })

    resultado = resumo_alvos_por_objetivo(
        areas,
        df_hist,
        df_alvos,
        df_alvos,
        pd.DataFrame(),
        date(2026, 7, 1),
        date(2026, 7, 31),
    )

    assert resultado.iloc[0]["Objetivo"] == "1.1 Mando com frases"


def test_preparar_programas_pei_usa_template_da_biblioteca_quando_objetivo_vazio():
    df_prog = pd.DataFrame({"programa": ["Mando com frases"], "objective": [""]})
    df_lib = pd.DataFrame({
        "name": ["Mando com frases"],
        "mastery_threshold_percent": [90],
        "objective_template": ["Emitir mandos com frases funcionais."],
    })

    resultado = preparar_programas_pei(df_prog, df_lib)

    assert resultado.iloc[0]["objective"] == "Emitir mandos com frases funcionais."
