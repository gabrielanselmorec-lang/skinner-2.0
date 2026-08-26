# Base de conhecimento em PDF

O assistente clínico indexa duas classes de fonte:

- arquivos Markdown em `dados_clinica/base_conhecimento_md`;
- arquivos PDF nos diretórios configurados localmente.

Neste computador, os diretórios de PDF ficam em
`dados_clinica/base_conhecimento_pdf_dirs.txt`, um caminho por linha. Esse arquivo
é local e não é versionado, pois pode conter caminhos específicos da máquina.
Como alternativa, use `SKINNER_KNOWLEDGE_PDF_DIR` para um diretório ou
`SKINNER_KNOWLEDGE_PDF_DIRS` para vários diretórios separados por `;` no Windows.

## Pré-indexação

Execute a indexação antes de iniciar a API quando adicionar ou substituir livros:

```powershell
.\.venv\Scripts\python.exe -m app.services.knowledge_index_cli
```

Também é possível informar uma fonte sem editar a configuração local:

```powershell
.\.venv\Scripts\python.exe -m app.services.knowledge_index_cli `
  --pdf-dir "C:\caminho\para\os\pdfs"
```

O texto extraído fica em `dados_clinica/.knowledge_cache`. O diretório é ignorado
pelo Git e cada PDF é reprocessado automaticamente apenas quando seu tamanho ou
data de modificação muda. O índice Markdown também é mantido em memória e
invalidado quando uma fonte muda.

## Diagnóstico

`GET /api/conhecimento/status` informa arquivos, páginas, trechos indexados e
alertas de extração. Resultados de busca provenientes de PDF incluem o número da
página usado na citação.

PDFs compostos somente por imagens precisam de OCR prévio. Eles aparecem nos
alertas como páginas sem texto extraível; o sistema não os trata silenciosamente
como fontes válidas.

## Validação da coleção local em 03/08/2026

- 26 PDFs e 10.619 páginas auditadas;
- 20.348.362 caracteres extraídos;
- nenhum arquivo criptografado, corrompido ou com erro fatal de extração;
- 10.245 páginas com texto significativo (pelo menos 20 caracteres);
- 374 páginas sem texto significativo, normalmente capas e páginas ilustradas.

Dois arquivos são integralmente digitalizações sem camada de texto e precisam de
OCR para entrar nas buscas: `Biblioteca - SKINNER B.F. Ciência e comportamento
humano.pdf` (255 páginas) e `introdução ao comp verbal.pdf` (10 páginas).

Com a coleção completa, a montagem inicial do índice em um novo processo levou
aproximadamente 46 segundos. No mesmo processo, consultas subsequentes ficaram
entre 0,17 e 0,19 segundo no ensaio local. Esses tempos variam conforme a máquina.
