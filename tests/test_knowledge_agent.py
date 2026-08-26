from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from app.services import knowledge_agent


@pytest.fixture
def isolated_knowledge_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    markdown_dir = tmp_path / "markdown"
    pdf_dir = tmp_path / "pdfs"
    cache_dir = tmp_path / "cache"
    markdown_dir.mkdir()
    pdf_dir.mkdir()
    monkeypatch.setenv("SKINNER_KNOWLEDGE_DIR", str(markdown_dir))
    monkeypatch.setenv("SKINNER_KNOWLEDGE_PDF_DIRS", str(pdf_dir))
    monkeypatch.setenv("SKINNER_KNOWLEDGE_CACHE_DIR", str(cache_dir))
    knowledge_agent.clear_knowledge_memory_cache()
    yield markdown_dir, pdf_dir, cache_dir
    knowledge_agent.clear_knowledge_memory_cache()


def test_tokens_are_accent_insensitive():
    assert knowledge_agent._tokens("Análise, função e reforçamento") == [
        "analise",
        "funcao",
        "reforcamento",
    ]


def test_canonical_source_key_matches_markdown_and_pdf_variants():
    assert knowledge_agent._canonical_source_key(
        "Análise do comportamento aplicada.md"
    ) == knowledge_agent._canonical_source_key(
        "pdf/Análise_do_comportamento_aplicada.pdf"
    )


def test_large_markdown_is_not_silently_ignored(tmp_path: Path):
    source = tmp_path / "fonte.md"
    source.write_text("x" * 2_100_000, encoding="utf-8")

    assert len(knowledge_agent._read_markdown(source)) == 2_100_000


def test_split_markdown_keeps_content_after_previous_300k_limit():
    source = "# Capitulo\n\n" + ("conteudo aplicado " * 20_000) + "\n\nMARCADOR_FINAL"

    chunks = knowledge_agent._split_markdown(source)

    assert any("MARCADOR_FINAL" in chunk for chunk in chunks)


def test_snapshot_is_reused_and_invalidated_when_source_changes(isolated_knowledge_base):
    markdown_dir, _pdf_dir, _cache_dir = isolated_knowledge_base
    source = markdown_dir / "fonte.md"
    source.write_text("# Ensino\n\nReforcamento diferencial.", encoding="utf-8")

    first = knowledge_agent._snapshot()
    second = knowledge_agent._snapshot()
    source.write_text("# Ensino\n\nReforcamento diferencial e comunicacao funcional.", encoding="utf-8")
    third = knowledge_agent._snapshot()

    assert first is second
    assert third is not second
    assert len(third.chunks) == 1
    assert "comunicacao funcional" in third.chunks[0].text


def test_document_frequency_counts_chunks_not_term_repetitions(isolated_knowledge_base):
    markdown_dir, _pdf_dir, _cache_dir = isolated_knowledge_base
    (markdown_dir / "fonte.md").write_text(
        "# Ensino\n\nreforco reforco reforco",
        encoding="utf-8",
    )

    snapshot = knowledge_agent._snapshot()

    assert snapshot.chunk_token_counts[0]["reforco"] == 3
    assert snapshot.document_frequency["reforco"] == 1


def test_pdf_pages_are_indexed_with_page_citations_and_persistent_cache(isolated_knowledge_base):
    _markdown_dir, pdf_dir, cache_dir = isolated_knowledge_base
    pdf_path = pdf_dir / "manual.pdf"
    document = canvas.Canvas(str(pdf_path))
    document.drawString(72, 760, "Reforcamento diferencial para comportamento interferente")
    document.showPage()
    document.drawString(72, 760, "Treino de comunicacao funcional com apoio gradual")
    document.showPage()
    document.save()

    status = knowledge_agent.status()
    results = knowledge_agent.search("comunicação funcional", limit=3)

    assert status["arquivos_pdf"] == 1
    assert status["paginas_pdf"] == 2
    assert status["paginas_pdf_com_texto"] == 2
    assert status["alertas_fontes"] == []
    assert list(cache_dir.glob("pdf_*.json"))
    assert results[0]["fonte"] == "pdf/manual.pdf"
    assert results[0]["pagina"] == 2
    assert results[0]["tipo_fonte"] == "pdf"


def test_pdf_without_extractable_text_is_reported(isolated_knowledge_base):
    _markdown_dir, pdf_dir, _cache_dir = isolated_knowledge_base
    pdf_path = pdf_dir / "com_pagina_vazia.pdf"
    document = canvas.Canvas(str(pdf_path))
    document.drawString(72, 760, "Pagina textual")
    document.showPage()
    document.showPage()
    document.save()

    status = knowledge_agent.status()

    assert status["paginas_pdf"] == 2
    assert status["paginas_pdf_com_texto"] == 1
    assert status["alertas_fontes"] == [
        {
            "fonte": "pdf/com_pagina_vazia.pdf",
            "detalhe": "1 pagina(s) sem texto extraivel",
        }
    ]


def test_search_diversifies_sources_when_multiple_documents_match(isolated_knowledge_base):
    markdown_dir, _pdf_dir, _cache_dir = isolated_knowledge_base
    (markdown_dir / "dominante.md").write_text(
        "# A\nreforco reforco reforco\n# B\nreforco reforco\n# C\nreforco\n# D\nreforco",
        encoding="utf-8",
    )
    (markdown_dir / "segunda.md").write_text("# Segunda\nreforco", encoding="utf-8")
    (markdown_dir / "terceira.md").write_text("# Terceira\nreforco", encoding="utf-8")

    results = knowledge_agent.search("reforço", limit=4)
    counts = Counter(item["fonte"] for item in results)

    assert len(results) == 4
    assert counts["dominante.md"] == 2
    assert {"segunda.md", "terceira.md"}.issubset(counts)
