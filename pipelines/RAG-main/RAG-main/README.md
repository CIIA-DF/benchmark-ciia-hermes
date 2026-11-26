# Pipeline RAG — processos SEI

Pipeline de ingestão e recuperação de evidências dos PDFs exportados do SEI-GDF. Cada PDF de
processo contém vários documentos internos (ofícios, despachos, atas...); o número
do **processo** é diferente do número **SEI de cada documento**, e o pipeline mantém
essa distinção.

```text
app/data/raw/*.pdf
  -> loader.py  (RAG-01) -> app/data/processed/<nome>.paginas.jsonl     uma página por linha
  -> parser.py  (RAG-02) -> app/data/processed/<nome>.documentos.jsonl  um documento por linha
                         -> app/data/reports/relatorio_ingestao.json   qualidade e alertas
  -> chunking.py -> corpus.chunks.jsonl
  -> embeddings.py -> indexing.py -> PostgreSQL + pgvector

pergunta -> busca vetorial + busca lexical -> RRF -> reranking opcional -> evidências
```

## Componentes

- `app/ingestion/` reaproveita o loader, o parser e os diagnósticos existentes. O chunking usa `paginas[].texto_limpo` e os offsets do tokenizador do modelo. Cada chunk fica dentro de um documento e registra as páginas que contribuíram com texto.
- `app/db/` define processos, documentos, chunks, vetores e perfil do índice. O PostgreSQL mantém os relacionamentos, o índice HNSW para cosseno e o índice GIN para busca textual em português.
- `app/retrieval/` contém a busca vetorial, a busca lexical com prioridade para identificadores SEI exatos, a fusão por posições (RRF) e o reranking por cross-encoder. Filtros estruturados restringem as duas buscas antes do Top-K.
- `app/api/` e `app/schemas/` expõem os contratos FastAPI/Pydantic. O endpoint entrega trechos e suas origens para Tools. A geração da resposta fica a cargo dos agentes.
- `app/data/` contém as entradas, os JSONLs derivados e os relatórios locais. `scripts/` inicializa o banco, orquestra o índice e executa avaliações.

Organização adaptada do [Hybrid RAG Engine](https://github.com/suneet91/hybrid-rag-engine).

## Instalação e execução completa

Execute os comandos a partir desta pasta, `pipelines/RAG-main/RAG-main`. Use Python 3.12 e `uv`.

```powershell
uv sync --locked --extra models
Copy-Item .env.example .env
# Edite .env e preencha RAG_POSTGRES_PASSWORD com uma senha local.
docker compose up -d --wait db
uv run --locked python -m scripts.init_db
uv run --locked --extra models python -m scripts.build_index
uv run --locked --extra models uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8010 --no-access-log
```

O Compose do benchmark usa uma imagem PostgreSQL sem pgvector e um volume próprio. Este Compose provisiona um banco RAG separado com pgvector 0.8.2, porta local 5433 e volume persistente. Para reaproveitar uma instância autorizada, use `RAG_DATABASE_URL` com o driver `postgresql+psycopg`, um banco dedicado e a extensão pgvector 0.8 ou posterior no schema `public`. A inicialização cria a extensão se a conta tiver a permissão necessária. A API é experimental, sem autenticação, e deve escutar somente em loopback para o operador local autorizado.

O build usa os PDFs de `app/data/raw/` por padrão e aceita caminhos explícitos. Cada execução cria uma pasta `build-*` em `app/data/processed/`, com JSONLs por etapa, e outra em `app/data/reports/`, com diagnósticos e métricas do build. Os caminhos `--processed` e `--reports` permitem escolher diretórios privados alternativos.

```sh
# Só extração, parsing e diagnósticos, sem pacotes de modelos ou banco.
uv run --locked python -m scripts.build_index --prepare-only caminho/processo.pdf

# Reaproveita a saída integral do parser em vez de ler o PDF novamente.
uv run --locked --extra models python -m scripts.build_index --jsonl "caminho/processo.documentos.jsonl"
```

Reexecutar o build reutiliza embeddings dos chunks com IDs idênticos. Uma correção no conteúdo atualiza documentos e substitui os chunks obsoletos da exportação identificada por processo e nome do arquivo, em uma transação. Forneça JSONLs integrais. Renomear um PDF cria outra origem e a remoção da exportação anterior é administrativa. O ID interno do documento distingue blocos pelo arquivo e pela página inicial, inclusive quando o ID SEI está ausente ou aparece em mais de um bloco.

### Configuração

| Variáveis | Padrão e efeito |
| --- | --- |
| `RAG_CHUNK_TOKENS`, `RAG_CHUNK_OVERLAP` | 500 e 75 tokens. O limite deve caber na janela do modelo. |
| `RAG_EMBEDDING_MODEL`, `RAG_EMBEDDING_REVISION`, `RAG_EMBEDDING_DIMENSIONS` | BGE-M3, revisão fixa, 1024 dimensões. Modelos externos à lista configurada exigem revisão SHA e dimensão. |
| `RAG_EMBEDDING_BATCH_SIZE` | 4 textos por lote em CPU. |
| `RAG_RETRIEVAL_MODE`, `RAG_CANDIDATE_K`, `RAG_TOP_K`, `RAG_RRF_K` | `hybrid`, 20 candidatos por busca, 5 resultados e constante RRF 60. |
| `RAG_RERANK_ENABLED`, `RAG_RERANK_MODEL`, `RAG_RERANK_REVISION` | Reranking disponível por opção, com BGE-Reranker-v2-M3 e revisão fixa. `false` converte `hybrid_rerank` em `hybrid`. |
| `RAG_RERANK_CANDIDATE_K`, `RAG_RERANK_BATCH_SIZE`, `RAG_RERANK_MAX_TOKENS` | Até 20 candidatos por padrão, pares em lotes de 2 e janela de 768 tokens. |

Documentos e consultas usam o mesmo modelo de embeddings normalizados. A primeira execução baixa os pesos públicos e usa o cache do Hugging Face nas seguintes. Com o cache preenchido, `HF_HUB_OFFLINE=1` permite execução offline. Em máquinas com menos memória, reduza os lotes e mantenha o modo híbrido sem reranking. A alternativa multilíngue `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` usa 384 dimensões. Para ela, configure `RAG_CHUNK_TOKENS=120` e `RAG_CHUNK_OVERLAP=20`. Trocar modelo, revisão, dimensão ou parâmetros de chunking exige construir o índice completo em um novo banco dedicado.

### Contrato experimental para Tools

Abra `http://127.0.0.1:8010/docs` para consultar o OpenAPI. O contrato `POST /api/query` é independente das rotas `/tools/*` do benchmark. A equipe de Backend/Tools deve revisar o consumo desse contrato antes de ligar os adaptadores Hermes e LangGraph.

```powershell
Invoke-RestMethod http://127.0.0.1:8010/health
$consulta = @{
    question = 'Quais despachos registram encaminhamentos entre unidades?'
    mode = 'hybrid'
    top_k = 5
}
# Para restringir a consulta, acrescente processo_sei e/ou documento_sei_id à tabela acima.
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8010/api/query `
    -ContentType 'application/json' -Body ($consulta | ConvertTo-Json)
```

Os modos são `dense`, `hybrid` e `hybrid_rerank`. A resposta contém o modo efetivo, o perfil de embeddings e `results` em ordem de relevância. Cada item traz texto, ID do chunk, processo, tipo e ID SEI quando extraído, nome do PDF, intervalo de páginas e páginas que contribuíram com texto. As pontuações `vector_score`, `keyword_score`, `rrf_score` e `rerank_score` ficam `null` quando indisponíveis. O campo `exact_identifier_match` indica correspondência lexical por identificador. O Top-K de saída aceita de 1 a 100 e aumenta a lista de candidatos quando necessário.

O healthcheck verifica a conexão e a compatibilidade do perfil registrado. Entrada inválida retorna 422. Banco, perfil ou modelo indisponível retorna 503. Uma busca sem resultados retorna 200 com lista vazia e indica apenas a cobertura da exportação indexada.

## Execução das etapas existentes

A partir desta pasta (onde está este README):

```sh
python -m app.ingestion.loader                       # todos os PDFs de app/data/raw/
python -m app.ingestion.loader caminho/processo.pdf  # ou PDFs específicos
python -m app.ingestion.parser                       # todos os *.paginas.jsonl
python -m app.ingestion.diagnostic                   # refaz o relatório sem reprocessar
python -m pytest                                     # testes
```

Reexecutar sobrescreve as saídas, sem duplicar registros. Um PDF com problema
(inexistente, inválido, protegido, vazio) é registrado e não interrompe os demais.
Quem já usa `pip install -r requirements.txt` pode continuar executando a ingestão, o parsing e os testes. Use a instalação travada com `--extra models` para executar a inferência local.

## Saída do loader (`*.paginas.jsonl`)

| Campo | Descrição |
|---|---|
| `arquivo_origem`, `processo_sei`, `pagina`, `total_paginas` | origem da página (página começa em 1) |
| `texto` | texto extraído, sem alterações |
| `rodape` | rodapé SEI: `rotulo`, `documento_sei_id`, `processo_sei`, `pagina` (ou `null`) |
| `cobertura_imagens` | fração da página ocupada por imagens |
| `flags` | `sem_texto`, `sem_rodape`, `rodape_pagina_divergente`, `erro_extracao` |

O processo vem dos rodapés e é conferido com o nome do arquivo; divergências viram aviso.

## Saída do parser (`*.documentos.jsonl`)

| Campo | Descrição | Origem |
|---|---|---|
| `documento_sei_id`, `rotulo`, `tipo_documento` | ID SEI e tipo do documento | rodapé |
| `numero_documento` | ex.: `98/2024 - UNDF/REIT/CEINTER` | cabeçalho, só do mesmo tipo |
| `assunto` | texto após "Assunto:", juntando linhas quebradas | cabeçalho |
| `data_documento` | ex.: `2024-05-07`, de "Brasília-DF, 07 de maio de 2024" | cabeçalho |
| `data_assinatura` | data da primeira assinatura eletrônica | corpo |
| `unidade` | sigla emissora, ex.: `UNDF/REIT/CEINTER` | número ou cabeçalho |
| `pagina_inicio`, `pagina_fim`, `total_paginas` | intervalo no PDF | rodapé |
| `alertas` | casos para revisão humana | parser |
| `paginas` | `pagina`, `pagina_no_documento`, `texto_bruto`, `texto_limpo`, `flags` | |

Metadado não encontrado fica `null`: nada é inventado. `texto_limpo` remove a moldura
do SEI (rodapé, endereço, código verificador) e normaliza ligaduras, mantendo as
assinaturas.

Alertas: `sem_id_sei` (documento sem rodapé), `paginas_sem_rodape` (páginas atribuídas
ao documento anterior), `numero_nao_confirmado` (rótulo tem número que o cabeçalho
não confirma), `id_repetido` (mesmo documento em blocos separados).

## Dados

Mantenha PDFs e derivados em armazenamento local autorizado. O `.gitignore` protege novos arquivos de dados. A branch já contém PDFs e JSONs legados rastreados pelo Git. As regras de ignore não os retiram do índice do Git.

## Testes e avaliação

```sh
uv run --locked python -m pytest
```

Os novos testes usam PDFs e textos sintéticos. Os testes existentes que dependem dos PDFs são pulados quando eles estão ausentes. Para executar os testes SQL e de API, defina `RAG_TEST_DATABASE_URL` para um PostgreSQL local descartável com pgvector e permissão para criar schemas. Cada teste de integração usa um schema temporário. Os testes de ranking e de API usam encoders determinísticos e dispensam o download de pesos.

```sh
uv run --locked python -m scripts.evaluate scripts/queries.example.jsonl --unit documento_sei_id
```

O avaliador executa as mesmas perguntas nos três modos, com Top-K padrão de 5. Gera latência mediana e p95 por modo, perfil do modelo e referências recuperadas em `app/data/reports/evaluation.json`. A primeira consulta pode incluir carregamento do modelo. Para pontuar uma consulta, preencha `relevant_ids` com os IDs revisados por uma pessoa. O relatório calcula Recall@K, Hit Rate@K, MRR@K e nDCG@K apenas para perguntas anotadas. Na unidade documento, o Top-K ainda conta posições de chunks e cada documento relevante contribui uma vez. Os exemplos fornecidos ficam sem rótulos até conferência no PDF.

### Validação local inicial

Com PostgreSQL 16.14, pgvector 0.8.2 e BGE-M3 em CPU, o build processou as duas exportações locais. Foram 273 páginas, 49 documentos e 358 chunks com vetores de 1.024 dimensões. O primeiro build, com os pesos já em cache, levou 443 segundos. A reexecução com os JSONLs levou 17 segundos e reutilizou os 358 vetores.

As três perguntas de exemplo foram executadas em cada processo com a API aquecida. Cada consulta recebeu cinco trechos. A conferência automática comparou os IDs e as páginas com o JSONL do índice e checou uma consulta por ID SEI em cada processo.

| Modo | Consultas | Latência mediana | p95 |
| --- | ---: | ---: | ---: |
| `dense` | 6 | 103 ms | 134 ms |
| `hybrid` | 6 | 104 ms | 119 ms |
| `hybrid_rerank` | 6 | 20,74 s | 22,49 s |

As latências são observações dessa amostra em CPU. A comparação de relevância aguarda a validação humana das perguntas e dos documentos esperados. A alternativa MiniLM foi verificada em uma inferência local de 384 dimensões.

## Limites e evolução

- Páginas sem texto extraível ficam sinalizadas pelo pipeline de diagnóstico. Implementar OCR e revisar a segmentação de blocos com alertas são próximos passos.
- Um único perfil de embeddings por banco mantém consultas e vetores compatíveis. Para evolução de schema, preparar migrações e registrar a versão da exportação no contrato.
- A busca vetorial usa HNSW, que é aproximado. Medir a cobertura da busca com filtros à medida que o corpus crescer.
- Anotar as consultas de avaliação com páginas de referência e repetir as medições com a API aquecida antes de comparar modos.
- Revisar o contrato com Backend/Tools e implementar autenticação e autorização por processo antes de uso compartilhado.
