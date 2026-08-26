import os
import logging
from typing import Any

import streamlit as st
import pandas as pd
import requests

API_URL = os.getenv("SKINNER_API_URL", "http://127.0.0.1:8000")
API_TIMEOUT_SECONDS = 90
AGENT_TIMEOUT_SECONDS = int(os.getenv("SKINNER_AGENT_TIMEOUT_SECONDS", "300"))
logger = logging.getLogger(__name__)


class APIClientError(RuntimeError):
    """Falha segura e apresentável na comunicação com a API."""


def _get_json(path: str, *, params: dict[str, Any] | None = None, timeout: int = API_TIMEOUT_SECONDS) -> Any:
    try:
        response = requests.get(f"{API_URL}{path}", params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout as exc:
        raise APIClientError("A API demorou demais para responder.") from exc
    except requests.exceptions.ConnectionError as exc:
        raise APIClientError("Não foi possível conectar à API.") from exc
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "desconhecido"
        raise APIClientError(f"A API respondeu com erro HTTP {status}.") from exc
    except ValueError as exc:
        raise APIClientError("A API retornou uma resposta inválida.") from exc
    except requests.RequestException as exc:
        raise APIClientError("Falha de comunicação com a API.") from exc


def _numeric_columns(data: pd.DataFrame, columns: tuple[str, ...]) -> None:
    for column in columns:
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")


@st.cache_data(ttl=600, show_spinner=False)
def load_patients_from_api() -> list[str]:
    payload = _get_json("/api/pacientes")
    if not isinstance(payload, list):
        raise APIClientError("Formato inesperado na lista de pacientes.")
    return sorted(str(patient) for patient in payload if str(patient).strip())


@st.cache_data(ttl=600, show_spinner=False)
def load_data_from_api(paciente):
    try:
        dados = _get_json(
            "/api/dados_paciente",
            params={"paciente": paciente, "incluir_alvos": "false"},
        )
        if not isinstance(dados, dict):
            raise APIClientError("Formato inesperado nos dados clínicos.")
        df_p = pd.DataFrame(dados.get("programas", []))
        df_b = pd.DataFrame(dados.get("interferentes", []))

        if not df_p.empty:
            if "date" in df_p.columns:
                df_p["date"] = pd.to_datetime(df_p["date"], errors="coerce", dayfirst=True).dt.date
            _numeric_columns(df_p, ("independent_rate", "prompt_rate", "success_rate"))

        if not df_b.empty:
            if "date" in df_b.columns:
                df_b["date"] = pd.to_datetime(df_b["date"], errors="coerce", dayfirst=True).dt.date
            _numeric_columns(df_b, ("rate", "count"))

        return df_p, df_b
    except APIClientError as exc:
        logger.warning("Falha ao carregar dados do paciente: %s", exc)
        st.warning(str(exc))
        return pd.DataFrame(), pd.DataFrame()
    except Exception as exc:
        logger.error("Erro inesperado ao carregar dados do paciente: %s", type(exc).__name__)
        st.warning("Erro inesperado ao carregar os dados do paciente.")
        return pd.DataFrame(), pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def load_targets_from_api(paciente, programa):
    try:
        payload = _get_json("/api/alvos", params={"paciente": paciente, "programa": programa})
        if not isinstance(payload, list):
            raise APIClientError("Formato inesperado nos dados dos alvos.")
        df = pd.DataFrame(payload)

        if not df.empty:
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True).dt.date
            _numeric_columns(df, ("independent_rate", "prompt_rate", "success_rate", "attempts"))

        return df
    except APIClientError as exc:
        logger.warning("Falha ao carregar alvos: %s", exc)
        st.warning(f"Alvos indisponíveis: {exc}")
        return pd.DataFrame()
    except Exception as exc:
        logger.error("Erro inesperado ao carregar alvos: %s", type(exc).__name__)
        st.warning("Erro inesperado ao carregar os alvos.")
        return pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def load_library_from_api():
    try:
        payload = _get_json("/api/biblioteca")
        if not isinstance(payload, list):
            raise APIClientError("Formato inesperado na biblioteca de programas.")
        return pd.DataFrame(payload)
    except APIClientError as exc:
        logger.warning("Falha ao carregar biblioteca: %s", exc)
        st.warning(f"Biblioteca indisponível: {exc}")
    except Exception as exc:
        logger.error("Erro inesperado ao carregar biblioteca: %s", type(exc).__name__)
        st.warning("Erro inesperado ao carregar a biblioteca de programas.")
    return pd.DataFrame()


def ask_clinical_agent(paciente, pergunta, start_date=None, end_date=None):
    payload = {"paciente": paciente, "pergunta": pergunta}
    if start_date:
        payload["data_inicio"] = start_date.isoformat()
    if end_date:
        payload["data_fim"] = end_date.isoformat()
    resposta = requests.post(
        f"{API_URL}/api/agente/clinico",
        json=payload,
        timeout=AGENT_TIMEOUT_SECONDS,
    )
    resposta.raise_for_status()
    return resposta.json()
