from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from app.security import ensure_https_url
from main import (
    ACCOUNT_ID,
    FIREBASE_HOSTS,
    HTTP,
    REQUEST_TIMEOUT,
    _auth_headers,
    _response_json,
    obter_token,
)


OUTPUT_DIR = Path("output") / "bhave_library"
CSV_PATH = OUTPUT_DIR / "objetivos_bhave.csv"
JSONL_PATH = OUTPUT_DIR / "objetivos_bhave.jsonl"
MANIFEST_PATH = OUTPUT_DIR / "manifesto.json"
MARKDOWN_PATH = OUTPUT_DIR / "objetivos_bhave.md"


def _stable_id(external_id: str, name: str) -> str:
    source = external_id or name
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    return f"bhave_program_{digest}"


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn").lower()


def _mastery_from_goal(goal: str) -> tuple[int, int]:
    threshold = 90
    days = 3
    folded = _fold_text(goal)

    match_percent = re.search(r"(\d{1,3})\s*%", folded)
    if match_percent:
        threshold = max(0, min(int(match_percent.group(1)), 100))

    match_time = re.search(r"(\d{1,3})\s*(sessoes|dias|semanas|meses)", folded)
    if match_time:
        quantity = max(0, min(int(match_time.group(1)), 365))
        unit = match_time.group(2)
        if "semana" in unit:
            days = quantity * 5
        elif "mes" in unit:
            days = quantity * 20
        else:
            days = quantity
    return threshold, days


def _firestore_value(value: dict[str, Any]) -> Any:
    if "nullValue" in value:
        return None
    if "stringValue" in value:
        return value["stringValue"]
    if "booleanValue" in value:
        return bool(value["booleanValue"])
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "timestampValue" in value:
        return value["timestampValue"]
    if "referenceValue" in value:
        return value["referenceValue"]
    if "bytesValue" in value:
        return value["bytesValue"]
    if "geoPointValue" in value:
        return value["geoPointValue"]
    if "arrayValue" in value:
        return [_firestore_value(item) for item in value["arrayValue"].get("values", [])]
    if "mapValue" in value:
        fields = value["mapValue"].get("fields", {})
        return {key: _firestore_value(item) for key, item in fields.items()}
    return None


def _fetch_programs() -> list[dict[str, Any]]:
    token = obter_token()
    if not token:
        raise RuntimeError("Não foi possível autenticar na API do bHave.")

    url = ensure_https_url(
        "https://firestore.googleapis.com/v1/projects/aplicatudo-prod/databases/"
        f"(default)/documents/accounts/{ACCOUNT_ID}/programs",
        allowed_hosts=FIREBASE_HOSTS,
    )
    documents: list[dict[str, Any]] = []
    page_token = ""

    for _ in range(50):
        params = {"pageSize": "300"}
        if page_token:
            params["pageToken"] = page_token
        response = HTTP.get(
            url,
            params=params,
            headers=_auth_headers(token),
            timeout=REQUEST_TIMEOUT,
            verify=True,
        )
        response.raise_for_status()
        payload = _response_json(response)
        if not isinstance(payload, dict):
            raise RuntimeError("A API do bHave retornou um formato inesperado.")
        documents.extend(payload.get("documents", []))
        page_token = _clean(payload.get("nextPageToken"))
        if not page_token:
            break
    else:
        raise RuntimeError("A paginação da biblioteca excedeu o limite de segurança.")

    programs: list[dict[str, Any]] = []
    for document in documents:
        raw_fields = document.get("fields", {})
        fields = {key: _firestore_value(value) for key, value in raw_fields.items()}
        name = _clean(fields.get("name"))
        if not name:
            continue
        fields["_document_name"] = _clean(document.get("name"))
        programs.append(fields)

    return sorted(programs, key=lambda item: _clean(item.get("name")).casefold())


def export_library() -> tuple[int, Path, Path, Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    programs = _fetch_programs()
    fieldnames = [
        "document_id",
        "bhave_id",
        "source_id",
        "programa",
        "objetivo",
        "descricao",
        "area",
        "criterio_percentual",
        "criterio_dias",
        "arquivado",
        "tags_json",
        "contingencia_json",
        "folhas_registro_json",
        "resumos_folhas_json",
        "tipo",
        "fonte",
    ]

    markdown_sections = [
        "# Biblioteca de objetivos de ensino — Estimular ABA",
        "",
        "Fonte: biblioteca institucional no bHave. Não contém dados de pacientes.",
        "",
    ]

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as csv_file, JSONL_PATH.open(
        "w", encoding="utf-8", newline="\n"
    ) as jsonl_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for program in programs:
            name = _clean(program.get("name"))
            goal = _clean(program.get("goal"))
            description = _clean(program.get("description"))
            area = _clean(program.get("area"))
            bhave_id = _clean(program.get("id")) or _clean(program.get("_document_name")).rsplit("/", 1)[-1]
            source_id = _clean(program.get("sourceId"))
            archived = bool(program.get("isArchived", False))
            threshold, days = _mastery_from_goal(goal)
            document_id = _stable_id(bhave_id, name)
            tags = program.get("tags") or {}
            contingency = program.get("contingency") or {}
            datasheets = program.get("datasheets") or {}
            summaries = program.get("datasheetSummaries") or {}

            flat_record = {
                "document_id": document_id,
                "bhave_id": bhave_id,
                "source_id": source_id,
                "programa": name,
                "objetivo": goal,
                "descricao": description,
                "area": area,
                "criterio_percentual": threshold,
                "criterio_dias": days,
                "arquivado": archived,
                "tags_json": json.dumps(tags, ensure_ascii=False, separators=(",", ":")),
                "contingencia_json": json.dumps(contingency, ensure_ascii=False, separators=(",", ":")),
                "folhas_registro_json": json.dumps(datasheets, ensure_ascii=False, separators=(",", ":")),
                "resumos_folhas_json": json.dumps(summaries, ensure_ascii=False, separators=(",", ":")),
                "tipo": "ensino_estruturado",
                "fonte": "bHave - Estimular ABA",
            }
            writer.writerow(flat_record)

            text_parts = [name]
            if description:
                text_parts.append(f"Descrição: {description}")
            if goal:
                text_parts.append(f"Objetivo: {goal}")
            text_parts.append(f"Critério de domínio: {threshold}% por {days} dias/sessões.")
            if area:
                text_parts.append(f"Área: {area}")

            rag_record = {
                "id": document_id,
                "title": name,
                "text": "\n".join(text_parts),
                "metadata": {
                    "bhave_id": bhave_id,
                    "source_id": source_id,
                    "tipo": "ensino_estruturado",
                    "fonte": "bHave - Estimular ABA",
                    "area": area,
                    "criterio_percentual": threshold,
                    "criterio_dias": days,
                    "arquivado": archived,
                    "tags": tags,
                    "contingencia": contingency,
                    "folhas_registro": datasheets,
                    "resumos_folhas": summaries,
                },
            }
            jsonl_file.write(json.dumps(rag_record, ensure_ascii=False, separators=(",", ":")) + "\n")

            markdown_sections.extend(
                [
                    f"## {name}",
                    "",
                    f"- Status: {'arquivado' if archived else 'ativo'}",
                    f"- Área: {area or 'não informada'}",
                    f"- Critério de domínio: {threshold}% por {days} dias/sessões",
                ]
            )
            if description:
                markdown_sections.extend(["", f"Descrição: {description}"])
            if goal:
                markdown_sections.extend(["", f"Objetivo: {goal}"])
            markdown_sections.append("")

    markdown_text = "\n".join(markdown_sections).rstrip() + "\n"
    MARKDOWN_PATH.write_text(markdown_text, encoding="utf-8")

    active_count = sum(not bool(program.get("isArchived", False)) for program in programs)
    manifest = {
        "fonte": "bHave - Estimular ABA",
        "colecao": "programs",
        "total": len(programs),
        "ativos": active_count,
        "arquivados": len(programs) - active_count,
        "inclui_dados_de_pacientes": False,
        "arquivos": [CSV_PATH.name, JSONL_PATH.name, MARKDOWN_PATH.name],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(programs), CSV_PATH.resolve(), JSONL_PATH.resolve(), MARKDOWN_PATH.resolve(), MANIFEST_PATH.resolve()


if __name__ == "__main__":
    count, csv_path, jsonl_path, markdown_path, manifest_path = export_library()
    print(f"{count} programas exportados")
    print(csv_path)
    print(jsonl_path)
    print(markdown_path)
    print(manifest_path)
