# Relatorio de Melhorias do Projeto Skinner

## Visao Geral

O projeto e um sistema Python local com FastAPI, Streamlit, banco Postgres/Supabase, integracao com bHave e assistente clinico com IA/RAG. Ele ja roda localmente e tem uma base funcional importante, mas hoje concentra muita logica em poucos arquivos, versiona dados sensiveis e ainda nao tem uma estrategia clara de testes e migracoes.

Este relatorio lista melhorias recomendadas em duas frentes:

- qualidade e manutencao do codigo;
- forma de trabalhar com o Codex no projeto.

## Pontos Prioritarios de Codigo

### 1. Separar o dashboard em modulos menores

O arquivo `app/web/dashboard.py` tem quase 2000 linhas e mistura varias responsabilidades:

- interface Streamlit;
- regras clinicas do PEI;
- geracao de DOCX;
- graficos;
- chamadas HTTP para a API;
- formatacao de tabelas;
- integracao com IA.

Isso torna qualquer alteracao mais arriscada, porque uma regra pequena pode afetar a tela, o documento gerado ou os graficos.

Sugestao de separacao:

- `app/web/api_client.py`: chamadas HTTP para a API;
- `app/services/pei_rules.py`: regras puras do PEI;
- `app/services/pei_docx.py`: geracao de documento Word;
- `app/services/pei_charts.py`: graficos do PEI;
- `app/web/dashboard.py`: apenas renderizacao Streamlit.

### 2. Criar testes para regras clinicas criticas

Atualmente nao ha pasta de testes do projeto fora da `.venv`. Regras clinicas importantes estao sendo alteradas diretamente sem teste automatizado.

Prioridade inicial de testes:

- `periodo_aplicacao_programa`;
- `filtrar_periodo_pei`;
- `resumo_alvos_programa`;
- `status_por_independencia`;
- parser de DOCX em `app/services/docx_parser.py`.

Exemplo de casos importantes para testar no PEI:

- objetivo novo dentro do periodo deve iniciar na primeira aplicacao real;
- objetivo encerrado antes do fim deve terminar na ultima aplicacao real;
- objetivo sem aplicacao no periodo nao deve aparecer;
- alvos do PEI devem respeitar o mesmo recorte de datas da pre-visualizacao e do DOCX.

### 3. Usar Alembic de verdade para o banco

O projeto tem Alembic configurado, mas a migration inicial esta vazia. Ao mesmo tempo, a API cria e altera tabelas diretamente em runtime com `CREATE TABLE IF NOT EXISTS` e `ALTER TABLE`.

Isso funciona em curto prazo, mas dificulta:

- reproduzir ambiente do zero;
- entender historico do schema;
- revisar mudancas de banco;
- evitar diferencas entre maquinas.

Sugestao:

- criar migrations Alembic reais para todas as tabelas;
- remover criacao/alteracao de schema de dentro da API;
- documentar o comando de migracao, por exemplo:

```powershell
alembic upgrade head
```

### 4. Melhorar tratamento de erros no Streamlit

O dashboard ainda possui alguns `except:` genericos que escondem o erro real. Isso pode fazer o usuario ver apenas uma mensagem simples como "API nao esta respondendo", mesmo quando o problema e dependencia faltando, credencial invalida, erro no banco ou formato de dado inesperado.

Sugestao:

- trocar `except:` por excecoes especificas;
- exibir mensagens mais uteis para o usuario;
- registrar detalhes tecnicos em log;
- evitar que logs mostrem dados clinicos ou credenciais.

### 5. Remover dados clinicos e logs do Git

O repositorio atualmente rastreia arquivos em `dados_clinica/` com nomes de pacientes e tambem arquivos em `logs/`.

Isso e um risco importante por envolver dados clinicos e historico operacional.

Sugestao:

- remover planilhas reais de pacientes do Git;
- manter apenas arquivos anonimizados de exemplo;
- remover logs versionados;
- atualizar `.gitignore`.

Exemplo de entradas recomendadas:

```gitignore
logs/
dados_clinica/*.xlsx
raw_data/
*.log
.env
```

Se a base de conhecimento em Markdown tiver material protegido por direitos autorais ou conteudo sensivel, avaliar tambem se ela deve continuar no repositorio.

### 6. Fixar versoes das dependencias

O arquivo `requirements.txt` lista os pacotes, mas nao fixa versoes. Isso pode fazer o projeto funcionar em uma maquina e quebrar em outra, caso algum pacote atualize com mudanca incompatível.

Sugestao:

- criar um `requirements.lock.txt` com versoes testadas;
- ou migrar para `pyproject.toml`;
- documentar a versao recomendada do Python.

Exemplo:

```text
fastapi==...
streamlit==...
pandas==...
sqlalchemy==...
```

### 7. Rodar localmente de forma mais segura

O comando com `--host 0.0.0.0` deixa a API acessivel em todas as interfaces de rede da maquina, incluindo rede local.

Para uso local, prefira:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

E para o Streamlit:

```powershell
..\..\.venv\Scripts\python.exe -m streamlit run dashboard.py --server.address 127.0.0.1 --server.headless true
```

Assim o sistema fica acessivel apenas no proprio computador.

## Pontos Positivos do Projeto

- Existe uma camada de seguranca em `app/security.py`, com sanitizacao, validacao de ambiente, limite de payload e protecao de caminho.
- A API ja usa Pydantic para validar payloads de avaliacoes.
- O assistente clinico tem fallback entre provedores de IA.
- O fluxo local com API + Streamlit e simples de executar.
- O modulo ABLLS-R ja esta bem isolado em `app/web/ablls_view.py`.

## Como Trabalhar Melhor Com o Codex

### 1. Fazer pedidos pequenos e verificaveis

Evitar prompts grandes que pedem varias mudancas ao mesmo tempo.

Exemplo bom:

```text
Altere apenas a regra de periodo do PEI. Nao mexa na UI. Adicione testes para:
1. objetivo novo;
2. objetivo encerrado;
3. objetivo sem aplicacao no periodo.
Depois rode os testes.
```

### 2. Sempre pedir validacao

Incluir no prompt:

```text
Depois rode py_compile e os testes. Se nao houver teste para essa regra, crie um teste minimo.
```

### 3. Trabalhar por branch e Pull Request

Sugestao de branches:

- `codex/ajuste-periodo-pei`;
- `codex/testes-pei`;
- `codex/refatorar-pei-service`;
- `codex/remover-dados-sensiveis`;
- `codex/alembic-migrations`.

Cada branch deve ter uma mudanca clara e revisavel.

### 4. Dar exemplos clinicos concretos

Para regras de PEI, sempre passar cenarios com datas e resultado esperado.

Exemplo:

```text
Periodo selecionado: 01/07/2026 a 30/09/2026.
Objetivo A tem aplicacoes em 10/07 e 05/08.
Resultado esperado no PEI: 10/07/2026 a 05/08/2026.

Objetivo B tem aplicacoes em 15/08, 01/09 e 30/09.
Resultado esperado no PEI: 15/08/2026 a 30/09/2026.
```

Isso reduz ambiguidade e melhora muito a qualidade da alteracao.

### 5. Nao colar segredos nos prompts

Quando precisar configurar ambiente, preferir:

```text
Crie um .env.example com os nomes das variaveis, mas sem valores reais.
```

E manter os valores reais apenas no `.env` local.

### 6. Antes de grandes refatoracoes, pedir mapeamento

Bom fluxo:

```text
Liste quais funcoes puras do dashboard podem ser extraidas sem mudar comportamento.
```

Depois:

```text
Extraia apenas essas funcoes para app/services/pei_rules.py e mantenha a interface atual funcionando.
```

## Proxima Ordem Recomendada

1. Remover dados clinicos reais e logs do Git.
2. Criar testes unitarios para as regras do PEI.
3. Separar as regras do PEI para um modulo proprio.
4. Mover geracao de DOCX para um modulo proprio.
5. Criar migrations Alembic reais.
6. Fixar versoes das dependencias.
7. Melhorar tratamento de erro no Streamlit.

Essa ordem reduz risco operacional primeiro e depois melhora a manutencao do codigo.
