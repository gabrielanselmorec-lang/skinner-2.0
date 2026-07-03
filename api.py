from __future__ import annotations
import datetime as dt
import json
from typing import Any, Optional

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from app.data.models import SessionLocal
from app.security import require_env, sanitize_text
from app.services.knowledge_agent import (
    answer_with_knowledge,
    search as search_knowledge,
    status as knowledge_status,
)

app = FastAPI(title="Skinner Project API")

DATABASE_URL = require_env("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
_ASSESSMENT_TABLES_READY = False
_CLINICAL_EVOLUTION_COLUMNS_READY = False

def _clean_query_param(value: str, *, max_length: int) -> str:
    return sanitize_text(value, max_length=max_length, allow_newlines=False)

def _filter_date_range(df: pd.DataFrame, data_inicio: Optional[str], data_fim: Optional[str]) -> pd.DataFrame:
    if df.empty or not data_inicio or not data_fim:
        return df
    inicio = pd.to_datetime(data_inicio, format="%Y-%m-%d", errors="coerce")
    fim = pd.to_datetime(data_fim, format="%Y-%m-%d", errors="coerce")
    if pd.isna(inicio) or pd.isna(fim):
        return df
    df = df.copy()
    df["date_temp"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)
    df = df[(df["date_temp"] >= inicio) & (df["date_temp"] <= fim)]
    return df.drop(columns=["date_temp"])


class AssessmentItemPayload(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=20)
    categoria_codigo: str = Field(..., min_length=1, max_length=8)
    categoria: str = Field(..., min_length=1, max_length=200)
    descricao: str = Field(..., min_length=1, max_length=5000)
    max_pontos: int = Field(..., ge=1, le=10)
    aba: Optional[str] = Field(None, max_length=100)
    numero: Optional[int] = Field(None, ge=0, le=10000)
    detalhes: dict[str, Any] = Field(default_factory=dict)


class AssessmentProtocolSyncPayload(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=80)
    nome: str = Field(..., min_length=1, max_length=200)
    itens: list[AssessmentItemPayload]


class AssessmentScorePayload(BaseModel):
    paciente: str = Field(..., min_length=1, max_length=128)
    codigo_item: str = Field(..., min_length=1, max_length=20)
    pontos: Optional[int] = Field(None, ge=0, le=10)
    data_avaliacao: dt.date = Field(default_factory=dt.date.today)
    observacao: Optional[str] = Field(None, max_length=2000)
    fonte: str = Field("manual", max_length=40)


class AssessmentLinkPayload(BaseModel):
    codigo_item: str = Field(..., min_length=1, max_length=20)
    programa_biblioteca: str = Field(..., min_length=1, max_length=200)
    pontos_automaticos: Optional[int] = Field(None, ge=0, le=10)


class ClinicalAgentPayload(BaseModel):
    paciente: str = Field(..., min_length=1, max_length=128)
    pergunta: str = Field(..., min_length=3, max_length=4000)
    data_inicio: Optional[dt.date] = None
    data_fim: Optional[dt.date] = None
    limite_fontes: int = Field(6, ge=1, le=10)


def init_assessment_tables() -> None:
    """Fallback de segurança — as tabelas agora são gerenciadas pela migration
    alembic/versions/a1b2c3d4e5f6_assessment_tables.py.
    Esta função pode ser removida após confirmar que `alembic upgrade head` foi executado."""
    global _ASSESSMENT_TABLES_READY
    if _ASSESSMENT_TABLES_READY:
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS assessment_protocols (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(80) UNIQUE NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE TABLE IF NOT EXISTS assessment_items (
                    id SERIAL PRIMARY KEY,
                    protocol_id INTEGER NOT NULL REFERENCES assessment_protocols(id) ON DELETE CASCADE,
                    item_code VARCHAR(20) NOT NULL,
                    source_sheet VARCHAR(100),
                    category_code VARCHAR(8) NOT NULL,
                    category_name VARCHAR(200) NOT NULL,
                    item_number INTEGER,
                    description TEXT NOT NULL,
                    max_points INTEGER NOT NULL CHECK (max_points BETWEEN 1 AND 10),
                    details JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE(protocol_id, item_code)
                );

                CREATE TABLE IF NOT EXISTS assessment_scores (
                    id SERIAL PRIMARY KEY,
                    patient_id VARCHAR NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                    item_id INTEGER NOT NULL REFERENCES assessment_items(id) ON DELETE CASCADE,
                    assessment_date DATE NOT NULL DEFAULT CURRENT_DATE,
                    points INTEGER CHECK (points >= 0),
                    source VARCHAR(40) NOT NULL DEFAULT 'manual',
                    notes TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE(patient_id, item_id, assessment_date)
                );

                CREATE TABLE IF NOT EXISTS assessment_item_program_links (
                    id SERIAL PRIMARY KEY,
                    item_id INTEGER NOT NULL REFERENCES assessment_items(id) ON DELETE CASCADE,
                    program_library_name VARCHAR(200) NOT NULL,
                    auto_points INTEGER CHECK (auto_points IS NULL OR auto_points >= 0),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE(item_id, program_library_name)
                );

                CREATE INDEX IF NOT EXISTS idx_assessment_scores_patient_date
                    ON assessment_scores(patient_id, assessment_date);
                CREATE INDEX IF NOT EXISTS idx_assessment_items_protocol_category
                    ON assessment_items(protocol_id, category_code, item_number);
                """
            )
        )
    _ASSESSMENT_TABLES_READY = True


def ensure_clinical_evolution_columns() -> None:
    """Fallback de segurança — a coluna `evolution` agora é parte da migration inicial
    563592740d7d. Esta função pode ser removida após confirmar que `alembic upgrade head` foi executado."""
    global _CLINICAL_EVOLUTION_COLUMNS_READY
    if _CLINICAL_EVOLUTION_COLUMNS_READY:
        return
    with engine.begin() as conn:
        for ddl in [
            "ALTER TABLE program_records ADD COLUMN IF NOT EXISTS evolution TEXT",
            "ALTER TABLE program_target_records ADD COLUMN IF NOT EXISTS evolution TEXT",
            "ALTER TABLE interfering_records ADD COLUMN IF NOT EXISTS evolution TEXT",
        ]:
            conn.execute(text(ddl))
    _CLINICAL_EVOLUTION_COLUMNS_READY = True


@app.on_event("startup")
def _startup_assessment_tables() -> None:
    init_assessment_tables()
    ensure_clinical_evolution_columns()


def _protocol_id(conn, protocolo: str) -> int:
    protocolo_limpo = _clean_query_param(protocolo, max_length=80)
    row = conn.execute(
        text("SELECT id FROM assessment_protocols WHERE code = :code AND active = TRUE"),
        {"code": protocolo_limpo},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Protocolo avaliativo nao encontrado.")
    return int(row["id"])


def _patient_id(conn, paciente: str) -> str:
    paciente_limpo = _clean_query_param(paciente, max_length=128)
    row = conn.execute(
        text("SELECT id FROM patients WHERE name_hash = :paciente OR name = :paciente"),
        {"paciente": paciente_limpo},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Paciente nao encontrado.")
    return str(row["id"])


def _row_dict(row) -> dict[str, Any]:
    data = dict(row)
    for key, value in list(data.items()):
        if isinstance(value, (dt.date, dt.datetime)):
            data[key] = value.isoformat()
    return data


def _ordered_program_records_sql() -> str:
    return """
        SELECT date, success_rate
        FROM program_records
        WHERE program_id = :program_id
        ORDER BY
            CASE
                WHEN date ~ '^\\d{4}-\\d{2}-\\d{2}$' THEN to_date(date, 'YYYY-MM-DD')
                WHEN date ~ '^\\d{2}/\\d{2}/\\d{4}$' THEN to_date(date, 'DD/MM/YYYY')
                ELSE NULL
            END DESC NULLS LAST,
            id DESC
        LIMIT :limit
    """

@app.get("/api/pacientes")
def listar_pacientes():
    try:
        df = pd.read_sql(text("SELECT name_hash, name FROM patients"), engine)
        lista_pacientes = []
        for _, row in df.iterrows():
            if pd.notna(row.get('name')) and str(row['name']).strip():
                lista_pacientes.append(str(row['name']))
            else:
                lista_pacientes.append(str(row['name_hash']))
        return lista_pacientes
    except Exception as exc:
        print(f"Erro ao listar pacientes: {sanitize_text(exc, max_length=200)}")
        return []

@app.get("/api/dados_paciente")
def obter_dados_paciente(
    paciente: str = Query(..., min_length=1, max_length=128),
    data_inicio: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    data_fim: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
):
    try:
        ensure_clinical_evolution_columns()
        paciente_id = _clean_query_param(paciente, max_length=128)
        q_prog = text(
            """
            SELECT p.name as programa, p.objective, pr.date, pr.success_rate,
                   pr.independent_rate, pr.prompt_rate, pr.phase, pr.evolution
            FROM program_records pr
            JOIN programs p ON pr.program_id = p.id
            JOIN patients pat ON p.patient_id = pat.id
            WHERE pat.name_hash = :paciente OR pat.name = :paciente
            """
        )
        q_beh = text("""
            SELECT b.name as comportamento, ir.date, ir.count, ir.rate, ir.evolution
            FROM interfering_records ir
            JOIN interfering_behaviors b ON ir.behavior_id = b.id
            JOIN patients pat ON b.patient_id = pat.id
            WHERE pat.name_hash = :paciente OR pat.name = :paciente
        """)
        q_targets = text("""
            SELECT p.name as programa, p.objective, tr.target_name, tr.attempts,
                   tr.independent_rate, tr.prompt_rate, tr.success_rate, tr.prompt_type,
                   tr.date, tr.evolution, phase_by_date.phase
            FROM program_target_records tr
            JOIN programs p ON tr.program_id = p.id
            JOIN patients pat ON p.patient_id = pat.id
            LEFT JOIN (
                SELECT program_id, date, MAX(phase) as phase
                FROM program_records
                GROUP BY program_id, date
            ) phase_by_date ON phase_by_date.program_id = tr.program_id
                AND phase_by_date.date = tr.date
            WHERE pat.name_hash = :paciente OR pat.name = :paciente
        """)
        params = {"paciente": paciente_id}
        df_p = pd.read_sql(q_prog, engine, params=params).fillna(0)
        df_b = pd.read_sql(q_beh, engine, params=params).fillna(0)
        df_t = pd.read_sql(q_targets, engine, params=params).fillna(0)
        df_p = _filter_date_range(df_p, data_inicio, data_fim)
        df_b = _filter_date_range(df_b, data_inicio, data_fim)
        df_t = _filter_date_range(df_t, data_inicio, data_fim)
        for df in (df_p, df_b, df_t):
            if "evolution" in df.columns:
                df["evolution"] = df["evolution"].replace(0, "").fillna("").astype(str)
        return {
            "programas": df_p.to_dict(orient="records"),
            "interferentes": df_b.to_dict(orient="records"),
            "alvos": df_t.to_dict(orient="records"),
        }
    except Exception as exc:
        print(f"Erro ao buscar dados do paciente: {sanitize_text(exc, max_length=200)}")
        return {"programas": [], "interferentes": [], "alvos": []}

@app.get("/api/alvos")
def obter_alvos(
    paciente: str = Query(..., min_length=1, max_length=128),
    programa: str = Query(..., min_length=1, max_length=200),
):
    try:
        ensure_clinical_evolution_columns()
        paciente_id = _clean_query_param(paciente, max_length=128)
        programa_nome = _clean_query_param(programa, max_length=200)
        query = text("""
            SELECT tr.*
            FROM program_target_records tr
            JOIN programs p ON tr.program_id = p.id
            JOIN patients pat ON p.patient_id = pat.id
            WHERE (pat.name_hash = :paciente OR pat.name = :paciente) AND p.name = :programa
        """)
        df = pd.read_sql(query, engine, params={"paciente": paciente_id, "programa": programa_nome})
        return df.fillna(0).to_dict(orient="records")
    except Exception as exc:
        print(f"Erro ao buscar alvos do programa: {sanitize_text(exc, max_length=200)}")
        return []

@app.get("/api/biblioteca")
def get_biblioteca():
    session = SessionLocal()
    try:
        q = text("SELECT name, objective_template, mastery_threshold_percent, mastery_days, suggested_targets FROM program_library")
        result = session.execute(q).fetchall()
        biblioteca = []
        for row in result:
            biblioteca.append({
                "name": sanitize_text(row[0], max_length=200),
                "objective_template": sanitize_text(row[1], max_length=4000, allow_newlines=True),
                "mastery_threshold_percent": float(row[2]) if row[2] else 90,
                "mastery_days": row[3] if row[3] else 3,
                "suggested_targets": row[4],
            })
        return biblioteca
    except Exception as exc:
        return {"erro": sanitize_text(exc, max_length=200)}
    finally:
        session.close()


@app.get("/api/conhecimento/status")
def obter_status_conhecimento():
    try:
        return knowledge_status()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao carregar base de conhecimento: {sanitize_text(exc, max_length=200)}",
        )


@app.get("/api/conhecimento/buscar")
def buscar_conhecimento(
    q: str = Query(..., min_length=3, max_length=4000),
    limite: int = Query(6, ge=1, le=10),
):
    try:
        return search_knowledge(q, limit=limite)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao buscar na base de conhecimento: {sanitize_text(exc, max_length=200)}",
        )


@app.post("/api/agente/clinico")
def consultar_agente_clinico(payload: ClinicalAgentPayload):
    data_inicio = payload.data_inicio.isoformat() if payload.data_inicio else None
    data_fim = payload.data_fim.isoformat() if payload.data_fim else None
    contexto_paciente = obter_dados_paciente(
        paciente=payload.paciente,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
    return answer_with_knowledge(
        question=payload.pergunta,
        patient_context=contexto_paciente,
        limit=payload.limite_fontes,
    )


@app.get("/api/avaliacoes")
def listar_avaliacoes():
    init_assessment_tables()
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT p.code, p.name, COUNT(i.id) AS total_itens
                FROM assessment_protocols p
                LEFT JOIN assessment_items i ON i.protocol_id = p.id
                WHERE p.active = TRUE
                GROUP BY p.id, p.code, p.name
                ORDER BY p.name
                """
            )
        ).mappings().all()
    return [_row_dict(row) for row in rows]


@app.post("/api/avaliacoes/sincronizar")
def sincronizar_protocolo_avaliativo(payload: AssessmentProtocolSyncPayload):
    init_assessment_tables()
    codigo = _clean_query_param(payload.codigo, max_length=80)
    nome = _clean_query_param(payload.nome, max_length=200)

    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO assessment_protocols (code, name, updated_at)
                VALUES (:code, :name, now())
                ON CONFLICT (code) DO UPDATE
                SET name = EXCLUDED.name, active = TRUE, updated_at = now()
                RETURNING id
                """
            ),
            {"code": codigo, "name": nome},
        ).mappings().first()
        protocol_id = int(row["id"])

        for item in payload.itens:
            item_code = _clean_query_param(item.codigo, max_length=20)
            categoria_codigo = _clean_query_param(item.categoria_codigo, max_length=8)
            categoria = _clean_query_param(item.categoria, max_length=200)
            descricao = sanitize_text(item.descricao, max_length=5000, allow_newlines=True)
            aba = sanitize_text(item.aba or "", max_length=100, allow_newlines=False) or None
            detalhes_json = json.dumps(item.detalhes or {}, ensure_ascii=True)

            conn.execute(
                text(
                    """
                    INSERT INTO assessment_items (
                        protocol_id, item_code, source_sheet, category_code,
                        category_name, item_number, description, max_points,
                        details, updated_at
                    )
                    VALUES (
                        :protocol_id, :item_code, :source_sheet, :category_code,
                        :category_name, :item_number, :description, :max_points,
                        CAST(:details AS jsonb), now()
                    )
                    ON CONFLICT (protocol_id, item_code) DO UPDATE
                    SET source_sheet = EXCLUDED.source_sheet,
                        category_code = EXCLUDED.category_code,
                        category_name = EXCLUDED.category_name,
                        item_number = EXCLUDED.item_number,
                        description = EXCLUDED.description,
                        max_points = EXCLUDED.max_points,
                        details = EXCLUDED.details,
                        updated_at = now()
                    """
                ),
                {
                    "protocol_id": protocol_id,
                    "item_code": item_code,
                    "source_sheet": aba,
                    "category_code": categoria_codigo,
                    "category_name": categoria,
                    "item_number": item.numero,
                    "description": descricao,
                    "max_points": item.max_pontos,
                    "details": detalhes_json,
                },
            )

    return {"ok": True, "protocolo": codigo, "itens": len(payload.itens)}


@app.get("/api/avaliacoes/{protocolo}/itens")
def listar_itens_avaliacao(protocolo: str):
    init_assessment_tables()
    with engine.begin() as conn:
        protocol_id = _protocol_id(conn, protocolo)
        rows = conn.execute(
            text(
                """
                SELECT item_code AS codigo, source_sheet AS aba,
                       category_code AS categoria_codigo, category_name AS categoria,
                       item_number AS numero, description AS descricao,
                       max_points AS max_pontos, details AS detalhes
                FROM assessment_items
                WHERE protocol_id = :protocol_id
                ORDER BY category_code, item_number, item_code
                """
            ),
            {"protocol_id": protocol_id},
        ).mappings().all()
    return [_row_dict(row) for row in rows]


@app.get("/api/avaliacoes/{protocolo}/resultados")
def obter_resultados_avaliacao(
    protocolo: str,
    paciente: str = Query(..., min_length=1, max_length=128),
    data_avaliacao: Optional[dt.date] = Query(None),
):
    init_assessment_tables()
    data_ref = data_avaliacao or dt.date.today()
    with engine.begin() as conn:
        protocol_id = _protocol_id(conn, protocolo)
        patient_id = _patient_id(conn, paciente)
        rows = conn.execute(
            text(
                """
                SELECT i.item_code AS codigo, i.source_sheet AS aba,
                       i.category_code AS categoria_codigo, i.category_name AS categoria,
                       i.item_number AS numero, i.description AS descricao,
                       i.max_points AS max_pontos, i.details AS detalhes,
                       s.points AS pontos, s.source AS fonte, s.notes AS observacao,
                       s.updated_at,
                       EXISTS (
                           SELECT 1
                           FROM assessment_scores prev
                           WHERE prev.patient_id = :patient_id
                             AND prev.item_id = i.id
                             AND prev.assessment_date < :assessment_date
                       ) AS reavaliacao,
                       (
                           SELECT prev.points
                           FROM assessment_scores prev
                           WHERE prev.patient_id = :patient_id
                             AND prev.item_id = i.id
                             AND prev.assessment_date < :assessment_date
                           ORDER BY prev.assessment_date DESC, prev.updated_at DESC
                           LIMIT 1
                       ) AS pontos_anteriores
                FROM assessment_items i
                LEFT JOIN assessment_scores s
                  ON s.item_id = i.id
                 AND s.patient_id = :patient_id
                 AND s.assessment_date = :assessment_date
                WHERE i.protocol_id = :protocol_id
                ORDER BY i.category_code, i.item_number, i.item_code
                """
            ),
            {
                "protocol_id": protocol_id,
                "patient_id": patient_id,
                "assessment_date": data_ref,
            },
        ).mappings().all()
    return [_row_dict(row) for row in rows]


@app.post("/api/avaliacoes/{protocolo}/pontuar")
def salvar_pontuacao_avaliacao(protocolo: str, payload: AssessmentScorePayload):
    init_assessment_tables()
    with engine.begin() as conn:
        protocol_id = _protocol_id(conn, protocolo)
        patient_id = _patient_id(conn, payload.paciente)
        item = conn.execute(
            text(
                """
                SELECT id, max_points
                FROM assessment_items
                WHERE protocol_id = :protocol_id AND item_code = :item_code
                """
            ),
            {
                "protocol_id": protocol_id,
                "item_code": _clean_query_param(payload.codigo_item, max_length=20),
            },
        ).mappings().first()
        if not item:
            raise HTTPException(status_code=404, detail="Item avaliativo nao encontrado.")

        item_id = int(item["id"])
        max_points = int(item["max_points"])
        if payload.pontos is None:
            conn.execute(
                text(
                    """
                    DELETE FROM assessment_scores
                    WHERE patient_id = :patient_id
                      AND item_id = :item_id
                      AND assessment_date = :assessment_date
                    """
                ),
                {
                    "patient_id": patient_id,
                    "item_id": item_id,
                    "assessment_date": payload.data_avaliacao,
                },
            )
            return {"ok": True, "removido": True}

        if payload.pontos > max_points:
            raise HTTPException(status_code=400, detail=f"Este item aceita no maximo {max_points} ponto(s).")

        source = _clean_query_param(payload.fonte or "manual", max_length=40)
        if source not in {"manual", "auto_bhave"}:
            source = "manual"
        observacao = sanitize_text(payload.observacao or "", max_length=2000, allow_newlines=True) or None
        conn.execute(
            text(
                """
                INSERT INTO assessment_scores (
                    patient_id, item_id, assessment_date, points, source, notes, updated_at
                )
                VALUES (:patient_id, :item_id, :assessment_date, :points, :source, :notes, now())
                ON CONFLICT (patient_id, item_id, assessment_date) DO UPDATE
                SET points = EXCLUDED.points,
                    source = EXCLUDED.source,
                    notes = EXCLUDED.notes,
                    updated_at = now()
                """
            ),
            {
                "patient_id": patient_id,
                "item_id": item_id,
                "assessment_date": payload.data_avaliacao,
                "points": payload.pontos,
                "source": source,
                "notes": observacao,
            },
        )
    return {"ok": True}


@app.get("/api/avaliacoes/biblioteca_bhave")
def listar_biblioteca_bhave_para_avaliacao():
    df = pd.read_sql(
        text(
            """
            SELECT name, objective_template, mastery_threshold_percent, mastery_days
            FROM program_library
            ORDER BY name
            """
        ),
        engine,
    )
    return df.fillna("").to_dict(orient="records")


@app.get("/api/avaliacoes/{protocolo}/vinculos_bhave")
def listar_vinculos_bhave(
    protocolo: str,
    codigo_item: Optional[str] = Query(None, min_length=1, max_length=20),
):
    init_assessment_tables()
    with engine.begin() as conn:
        protocol_id = _protocol_id(conn, protocolo)
        params: dict[str, Any] = {"protocol_id": protocol_id}
        filtro_item = ""
        if codigo_item:
            filtro_item = "AND i.item_code = :item_code"
            params["item_code"] = _clean_query_param(codigo_item, max_length=20)

        rows = conn.execute(
            text(
                f"""
                SELECT i.item_code AS codigo, l.program_library_name AS programa_biblioteca,
                       l.auto_points AS pontos_automaticos, l.updated_at
                FROM assessment_item_program_links l
                JOIN assessment_items i ON i.id = l.item_id
                WHERE i.protocol_id = :protocol_id
                {filtro_item}
                ORDER BY i.item_code, l.program_library_name
                """
            ),
            params,
        ).mappings().all()
    return [_row_dict(row) for row in rows]


@app.post("/api/avaliacoes/{protocolo}/vincular_bhave")
def vincular_item_ao_bhave(protocolo: str, payload: AssessmentLinkPayload):
    init_assessment_tables()
    with engine.begin() as conn:
        protocol_id = _protocol_id(conn, protocolo)
        item = conn.execute(
            text(
                """
                SELECT id, max_points
                FROM assessment_items
                WHERE protocol_id = :protocol_id AND item_code = :item_code
                """
            ),
            {
                "protocol_id": protocol_id,
                "item_code": _clean_query_param(payload.codigo_item, max_length=20),
            },
        ).mappings().first()
        if not item:
            raise HTTPException(status_code=404, detail="Item avaliativo nao encontrado.")

        programa = _clean_query_param(payload.programa_biblioteca, max_length=200)
        pontos_auto = payload.pontos_automaticos
        if pontos_auto is not None and pontos_auto > int(item["max_points"]):
            raise HTTPException(status_code=400, detail="Pontuacao automatica acima do maximo do item.")

        conn.execute(
            text(
                """
                INSERT INTO assessment_item_program_links (
                    item_id, program_library_name, auto_points, updated_at
                )
                VALUES (:item_id, :program_library_name, :auto_points, now())
                ON CONFLICT (item_id, program_library_name) DO UPDATE
                SET auto_points = EXCLUDED.auto_points,
                    updated_at = now()
                """
            ),
            {
                "item_id": int(item["id"]),
                "program_library_name": programa,
                "auto_points": pontos_auto,
            },
        )
    return {"ok": True}


@app.get("/api/avaliacoes/{protocolo}/sugestoes_bhave")
def sugerir_pontuacao_bhave(
    protocolo: str,
    paciente: str = Query(..., min_length=1, max_length=128),
):
    init_assessment_tables()
    sugestoes = []

    with engine.begin() as conn:
        protocol_id = _protocol_id(conn, protocolo)
        patient_id = _patient_id(conn, paciente)
        links = conn.execute(
            text(
                """
                SELECT i.id AS item_id, i.item_code, i.description, i.max_points,
                       l.program_library_name, l.auto_points,
                       COALESCE(pl.mastery_threshold_percent, 90) AS threshold,
                       COALESCE(pl.mastery_days, 3) AS mastery_days,
                       p.id AS program_id
                FROM assessment_item_program_links l
                JOIN assessment_items i ON i.id = l.item_id
                JOIN programs p ON p.name = l.program_library_name AND p.patient_id = :patient_id
                LEFT JOIN program_library pl ON pl.name = l.program_library_name
                WHERE i.protocol_id = :protocol_id
                """
            ),
            {"protocol_id": protocol_id, "patient_id": patient_id},
        ).mappings().all()

        for link in links:
            mastery_sessions = max(1, int(link["mastery_days"] or 3))
            threshold = float(link["threshold"] or 90)
            historico = conn.execute(
                text(_ordered_program_records_sql()),
                {"program_id": int(link["program_id"]), "limit": mastery_sessions},
            ).mappings().all()

            if len(historico) < mastery_sessions:
                continue

            taxas = [float(row["success_rate"] or 0) for row in historico]
            if all(taxa >= threshold for taxa in taxas):
                sugestoes.append(
                    {
                        "codigo": link["item_code"],
                        "descricao": link["description"],
                        "programa": link["program_library_name"],
                        "threshold": threshold,
                        "mastery_days": mastery_sessions,
                        "taxas": taxas,
                        "pontos_sugeridos": int(link["auto_points"] or link["max_points"]),
                    }
                )

    return sugestoes
