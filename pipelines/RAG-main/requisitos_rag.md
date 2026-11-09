# Requisitos do Pipeline RAG — Projeto SEI

## Objetivo

Desenvolver um pipeline de recuperação de informações que processe os PDFs dos processos SEI, identifique os documentos administrativos contidos neles, indexe o conteúdo e entregue trechos relevantes para a equipe de **Tools**, responsável pela integração com os agentes **Hermes** e **LangGraph**.

A primeira versão deve ser **simples, funcional, rastreável e reproduzível**. Depois de concluída, a equipe pode comparar diferentes estratégias de recuperação e aprimorar o pipeline com base em métricas.

**Referência arquitetural:** [hybrid-rag-engine](https://github.com/suneet91/hybrid-rag-engine) — usar como referência para a organização dos módulos, adaptando o processamento à estrutura dos documentos SEI.

**Tecnologias propostas:** Python 3.12, PyMuPDF, regex, JSONL, Hugging Face Tokenizers, sentence-transformers, BAAI/bge-m3, PostgreSQL, pgvector, PostgreSQL Full-Text Search, RRF, BAAI/bge-reranker-v2-m3, FastAPI, Pydantic, pandas e pytest.

**Arquivos de teste:**
- Processo `04030-00001001/2024-23` — PDF com 61 páginas.
- Processo `04030-00001179/2025-55` — PDF com 212 páginas.

> **Importante:** cada PDF exportado do SEI contém **vários documentos internos** (ofícios, despachos, atas, notas jurídicas etc.). O número do processo **não** é o mesmo que o número SEI de cada documento. Precisamos manter essa distinção ao longo de todo o pipeline.

## Estrutura de pastas

Organização baseada nos módulos do repositório de referência, com adaptações para o parsing de processos SEI:

```text
pipelines/
└── rag-main/
    ├── app/
    │   ├── ingestion/
    │   │   ├── loader.py          # RAG-01: ingestão dos PDFs
    │   │   ├── parser.py          # RAG-02: documentos internos SEI
    │   │   ├── chunking.py        # RAG-03: limpeza e chunks
    │   │   ├── embeddings.py      # RAG-04: embeddings
    │   │   └── indexing.py        # RAG-05: persistência/indexação
    │   ├── db/
    │   │   ├── models.py          # RAG-05: modelos do banco
    │   │   └── session.py         # RAG-05: conexão
    │   ├── retrieval/
    │   │   ├── vector_search.py   # RAG-06: busca semântica
    │   │   ├── keyword_search.py  # RAG-06: busca lexical
    │   │   ├── fusion.py          # RAG-07: RRF
    │   │   └── rerank.py          # RAG-08: reranking
    │   ├── api/
    │   │   └── routes/
    │   │       └── query.py       # RAG-09: endpoint
    │   ├── schemas/
    │   │   └── query.py           # RAG-09: contratos Pydantic
    │   ├── config.py
    │   └── main.py
    ├── scripts/
    │   └── init_db.sql
    └── tests/
        └── evaluation/           # RAG-10: avaliação
```

Os demais arquivos auxiliares, como `__init__.py`, README, testes unitários e configurações do projeto, permanecem conforme a estrutura adotada no repositório.

## Fluxo geral

```text
Preparação da base
PDFs SEI
  -> Ingestão de páginas
  -> Parsing e identificação dos documentos internos
  -> Limpeza e chunking
  -> Embeddings
  -> PostgreSQL + pgvector

Consulta
Pergunta
  -> Busca semântica + busca lexical (+ filtros exatos)
  -> Fusão RRF
  -> Reranking
  -> Top-K chunks + texto + fontes + metadados
  -> Equipe de Tools -> Hermes / LangGraph
```

---

## RAG-01 — Ingestão dos documentos

**Objetivo:** ler os PDFs dos processos SEI e extrair seu conteúdo por página, com informações de origem.

**Tecnologias:** Python 3.12, PyMuPDF (`fitz`), `re`, `json`/JSONL e pytest.

**Local:** `pipelines/rag-main/app/ingestion/loader.py`.

### Requisitos

1. Criar um script que receba o caminho de um arquivo PDF como argumento, sem depender de nomes fixos.
2. Abrir o PDF com PyMuPDF e validar se o arquivo existe e pode ser lido.
3. Percorrer todas as páginas e extrair o texto de cada uma, mantendo a separação por página.
4. Preservar o nome do PDF de origem e o número da página (contagem começando em 1).
5. Identificar o número do **processo** SEI a partir do nome do arquivo e/ou de padrões no conteúdo, validando eventuais divergências; não confundir um processo citado no texto com o processo do arquivo.
6. Registrar páginas sem texto extraível e falhas de extração; não inventar texto quando ele não puder ser obtido.
7. Salvar a saída em **JSONL**, com um registro por página e campos consistentes.
8. Permitir reexecutar a extração sem acumular registros duplicados na saída.
9. Executar o script nos dois PDFs disponibilizados e conferir amostras do texto extraído com os originais.

**Entregáveis:** `loader.py`, dois JSONLs, instruções de execução no README, testes básicos e resumo do total de páginas processadas e problemas encontrados.

**Critério de conclusão:** cada página processada pode ser localizada no PDF original, com seu texto e metadados correspondentes.

**Fora do escopo:** separação completa dos documentos internos, chunking, embeddings e banco de dados.

## RAG-02 — Parsing e identificação dos documentos SEI

**Objetivo:** identificar os documentos administrativos que compõem cada processo e registrar seus limites e metadados.

**Tecnologias:** Python, regex e PyMuPDF.

**Local:** `pipelines/rag-main/app/ingestion/parser.py`.

### Requisitos

1. Ler a saída estruturada da ingestão.
2. Detectar inícios e finais dos documentos internos de cada processo, usando cabeçalhos, rodapés, identificadores e outros padrões do SEI.
3. Reconhecer, quando possível, tipos como ofício, memorando, despacho, ata, nota jurídica, edital e anexos.
4. Extrair o **número SEI do documento**, distinto do número do processo.
5. Registrar o intervalo de páginas e preservar a sequência de leitura de documentos que ocupem várias páginas.
6. Extrair metadados disponíveis: tipo, identificação, título/assunto, data e unidade, quando houver dados confiáveis.
7. Identificar ambiguidades e possíveis erros de segmentação; registrar esses casos para revisão, sem atribuir um ID fictício.
8. Manter o conteúdo original e a relação entre arquivo, processo, documento e página.
9. Testar manualmente limites de documentos dos dois processos, inclusive documentos de várias páginas.

**Entregáveis:** `parser.py`, documentos estruturados em JSONL, exemplos validados e testes de identificação.

**Critério de conclusão:** é possível localizar um documento pelo número SEI e recuperar seu texto e páginas de origem; casos incertos são sinalizados.

## RAG-03 — Limpeza textual e chunking

**Objetivo:** preparar os textos e separá-los em trechos adequados para indexação.

**Tecnologias:** Python e tokenizador compatível com o modelo escolhido (por exemplo, Hugging Face Tokenizers).

**Local:** `pipelines/rag-main/app/ingestion/chunking.py`.

### Requisitos

1. Receber documentos já individualizados pelo parser.
2. Aplicar limpeza leve de espaços e ruídos recorrentes, sem apagar datas, números SEI, títulos ou conteúdo relevante.
3. Dividir o texto em chunks por tokens; usar como **configuração inicial para teste** cerca de **500 tokens**, com **75 tokens de overlap**.
4. Respeitar, quando possível, títulos, seções e parágrafos.
5. **Nunca misturar textos de documentos SEI diferentes no mesmo chunk.**
6. Preservar `process_id`, `document_id`, arquivo de origem e intervalo de páginas de cada chunk.
7. Gerar identificadores únicos e reproduzíveis para os chunks.
8. Exportar os chunks em JSONL.
9. Inspecionar uma amostra manual para identificar cortes inadequados, excesso de rodapés ou perda de contexto.

**Entregáveis:** `chunking.py`, JSONL de chunks e testes de tamanho, identificação e rastreabilidade.

**Critério de conclusão:** todos os chunks válidos têm origem verificável e respeitam os limites documentais.

## RAG-04 — Geração de embeddings

**Objetivo:** gerar vetores semânticos dos chunks para permitir consultas por similaridade.

**Tecnologias:** Python, sentence-transformers e, inicialmente, `BAAI/bge-m3`.

**Local:** `pipelines/rag-main/app/ingestion/embeddings.py`.

### Requisitos

1. Carregar um modelo de embeddings multilíngue compatível com textos em português.
2. Receber os chunks e produzir um embedding para cada um.
3. Processar lotes (`batches`) para controlar consumo de RAM/VRAM.
4. Verificar que todos os embeddings possuem a dimensão esperada para o modelo selecionado.
5. Preservar associação entre vetor, `chunk_id`, conteúdo e metadados.
6. Registrar falhas e permitir retomar processamento sem recalcular chunks inalterados.
7. Registrar nome e versão do modelo, parâmetros e tempo de processamento para reprodução dos experimentos.
8. Verificar desempenho e consumo de recursos no ambiente disponível.

**Entregáveis:** rotina de embeddings, configuração e resultados associados aos chunks.

**Critério de conclusão:** cada chunk válido tem um vetor correspondente e os parâmetros usados são conhecidos.

## RAG-05 — Indexação no PostgreSQL

**Objetivo:** armazenar os dados processados em estrutura consultável para as buscas.

**Tecnologias:** PostgreSQL, pgvector, SQLAlchemy e Docker Compose.

**Local:** `pipelines/rag-main/app/ingestion/indexing.py`, com modelos em `pipelines/rag-main/app/db/models.py` e conexão em `pipelines/rag-main/app/db/session.py`.

### Requisitos

1. Configurar o PostgreSQL e habilitar pgvector.
2. Modelar registros de **processos**, **documentos** e **chunks**, mantendo os relacionamentos entre eles.
3. Armazenar texto, metadados e embedding de cada chunk.
4. Configurar a dimensão do campo vetorial de acordo com o modelo de embeddings.
5. Criar índices apropriados para metadados e busca vetorial, conforme volume e desempenho observados.
6. Inserir os dados a partir das saídas das etapas anteriores.
7. Garantir que reprocessar um arquivo não crie registros duplicados.
8. Permitir filtros por número de processo, número SEI do documento e outros metadados disponíveis.
9. Testar consultas que recuperem os dados e suas referências de origem.

**Entregáveis:** esquema/migrações, script de indexação e configuração local do banco.

**Critério de conclusão:** os chunks e seus vetores estão persistidos, podem ser consultados e mantêm vínculo correto com os documentos.

## RAG-06 — Retrieval semântico e lexical

**Objetivo:** implementar dois mecanismos independentes de recuperação de trechos relevantes.

**Tecnologias:** Python, pgvector e PostgreSQL Full-Text Search.

**Local:** `pipelines/rag-main/app/retrieval/vector_search.py` (semântica) e `pipelines/rag-main/app/retrieval/keyword_search.py` (lexical).

### Requisitos

1. Criar uma função de busca que receba consulta textual e filtros opcionais.
2. Gerar embeddings da pergunta usando o mesmo modelo usado na indexação.
3. Implementar **busca semântica** por similaridade vetorial.
4. Implementar **busca lexical** usando os recursos de full-text search do PostgreSQL.
5. Permitir executar e testar cada busca isoladamente.
6. Retornar identificadores dos chunks, textos, metadados e pontuações/posições de cada estratégia.
7. Permitir configurar o número de resultados retornados.
8. Implementar filtros por processo e documento, conforme permissões aplicáveis.
9. Prever consulta exata para identificadores SEI e números de processo, sem depender de embeddings.
10. Testar perguntas reais sobre ambos os processos e inspecionar os resultados.

**Entregáveis:** buscas semântica e lexical funcionais, com testes e exemplos de consultas.

**Critério de conclusão:** as duas estratégias retornam candidatos rastreáveis e podem ser avaliadas separadamente.

## RAG-07 — Busca híbrida com RRF

**Objetivo:** combinar os resultados das buscas semântica e lexical em um ranking único.

**Tecnologias:** Python e Reciprocal Rank Fusion (RRF).

**Local:** `pipelines/rag-main/app/retrieval/fusion.py`.

### Requisitos

1. Receber listas ordenadas das duas estratégias de busca.
2. Implementar a fusão por **RRF**, combinando posições nos rankings em vez de somar scores em escalas diferentes.
3. Remover duplicações pelo identificador do chunk.
4. Produzir um ranking único, preservando origem e metadados dos candidatos.
5. Permitir configurar parâmetros da fusão e quantidade de candidatos, inicialmente **20**.
6. Testar consultas com termos exatos, números de processos e perguntas abertas.
7. Comparar qualitativamente e quantitativamente a busca híbrida com as buscas isoladas.

**Entregáveis:** `fusion.py`, testes da função RRF e exemplos de ranking combinado.

**Critério de conclusão:** a fusão retorna uma lista ordenada e sem chunks duplicados.

## RAG-08 — Reranking

**Objetivo:** refinar a ordenação dos candidatos para selecionar os trechos mais relevantes.

**Tecnologias:** Python, sentence-transformers e, inicialmente, `BAAI/bge-reranker-v2-m3` (verificar suporte e consumo de recursos).

**Local:** `pipelines/rag-main/app/retrieval/rerank.py`.

### Requisitos

1. Carregar o modelo de reranking selecionado.
2. Receber a pergunta e os candidatos fornecidos pela busca híbrida.
3. Avaliar os pares pergunta–chunk e produzir novas pontuações de relevância.
4. Reordenar candidatos conforme essas pontuações.
5. Retornar inicialmente os **cinco melhores chunks (Top 5)**.
6. Preservar texto, IDs, páginas, documento SEI e processo de cada candidato.
7. Medir latência e consumo de recursos.
8. Comparar a qualidade dos resultados com e sem reranking usando as mesmas perguntas.

**Entregáveis:** `rerank.py`, testes e comparativo inicial de resultados.

**Critério de conclusão:** o sistema fornece um Top 5 rastreável, e conseguimos medir o efeito do reranker.

## RAG-09 — Interface de consulta para a equipe de Tools

**Objetivo:** disponibilizar a recuperação por um contrato simples e estável, sem acoplar o RAG a um agente específico.

**Tecnologias:** Python, FastAPI e Pydantic.

**Local:** `pipelines/rag-main/app/api/routes/query.py`, com schemas em `pipelines/rag-main/app/schemas/query.py`.

### Requisitos

1. Criar endpoint ou função padronizada para consultar o pipeline.
2. Aceitar pergunta, filtros autorizados e `top_k` como parâmetros.
3. Executar busca semântica, busca lexical, fusão e reranking.
4. Retornar JSON com chunks, textos, números SEI, processos, páginas e scores, quando disponíveis.
5. Validar entradas e tratar falhas sem esconder erros relevantes.
6. Respeitar as regras de acesso aos documentos; os filtros e permissões devem ser aplicados **antes de retornar resultados** e, quando necessário, antes da busca.
7. Documentar o contrato e fornecer exemplos de requisição/resposta para a equipe de Tools.
8. Permitir que Hermes e LangGraph consumam o **mesmo mecanismo de recuperação**, para comparação experimental controlada.

**Entregáveis:** interface documentada e exemplos de integração.

**Critério de conclusão:** a equipe de Tools consegue enviar uma consulta e receber evidências recuperadas sem depender de detalhes internos do RAG.

## RAG-10 — Avaliação e validação

**Objetivo:** medir a qualidade da recuperação e justificar melhorias com resultados reproduzíveis.

**Tecnologias:** Python, pandas, pytest e métricas implementadas em Python (ou scikit-learn quando aplicável).

**Local:** `pipelines/rag-main/tests/evaluation/` (testes e scripts de avaliação).

### Requisitos

1. Construir um conjunto inicial de **20 a 30 perguntas** sobre os PDFs SEI.
2. Registrar manualmente quais documentos ou chunks são relevantes para cada pergunta (*ground truth*).
3. Incluir perguntas sobre datas, atos administrativos, assuntos gerais, números SEI e versões de documentos.
4. Calcular métricas como **Recall@K**, **MRR** e **nDCG@K**, observando a unidade de relevância usada (documento ou chunk).
5. Medir latência das consultas e, quando relevante, do reranking.
6. Executar testes equivalentes com três configurações:
   - Somente busca semântica (*dense retrieval*);
   - Busca híbrida com RRF;
   - Busca híbrida com RRF e reranking.
7. Registrar parâmetros, modelos e versões utilizados em cada experimento.
8. Investigar falhas: documento errado, confusão entre versões, falta de trechos relevantes e erros de parsing.
9. Produzir um relatório conciso com tabelas comparativas, limitações e próximos ajustes.

**Entregáveis:** conjunto de questões anotadas, scripts de avaliação e relatório comparativo.

**Critério de conclusão:** qualquer integrante consegue reproduzir os experimentos e verificar as métricas.

> **Observação:** o conjunto de perguntas pode começar a ser preparado desde a RAG-01. Não é necessário esperar a RAG-10 para coletar os exemplos e respostas de referência.

---

## Requisitos transversais

- **Rastreabilidade:** cada resultado deve apontar para processo, documento SEI e página(s) de origem.
- **Modularidade:** ingestão, parsing, chunking, embeddings, indexação, recuperação e reranking devem ser componentes separados.
- **Reprodutibilidade:** registrar parâmetros, modelos e versões, mantendo exemplos e testes reproduzíveis.
- **Idempotência:** reprocessar PDFs não pode duplicar registros nem corromper a base.
- **Tratamento de falhas:** não preencher dados ausentes com valores inventados; registrar incertezas e erros.
- **Segurança:** trabalhar em ambiente autorizado, com controle de acesso adequado. Não publicar PDFs ou saídas de processos restritos em repositórios públicos.
- **Validação:** incluir testes e exemplos verificáveis em cada PR.
- **Documentação:** manter README com instruções de execução e descrição de entradas/saídas.
- **Comparação entre agentes:** Hermes e LangGraph devem utilizar o mesmo corpus, o mesmo pipeline RAG e configurações equivalentes durante os experimentos.

## Organização das entregas

| Task | Etapa | Entrega principal |
|---|---|---|
| RAG-01 | Ingestão | PDF → texto por página em JSONL |
| RAG-02 | Parsing SEI | Páginas → documentos individualizados |
| RAG-03 | Chunking | Documentos → trechos rastreáveis |
| RAG-04 | Embeddings | Chunks → vetores |
| RAG-05 | Indexação | Dados → PostgreSQL + pgvector |
| RAG-06 | Retrieval | Pergunta → resultados lexicais e semânticos |
| RAG-07 | RRF | Dois rankings → candidatos combinados |
| RAG-08 | Reranking | Candidatos → Top 5 |
| RAG-09 | Integração | API/contrato → equipe de Tools |
| RAG-10 | Avaliação | Experimentos → métricas e relatório |

**Fluxo sugerido de trabalho:** uma task por vez, uma PR por etapa, com os três integrantes acompanhando o desenvolvimento e revisando juntos as entregas.

## Resultado final esperado

Um pipeline RAG que receba documentos SEI, extraia e estruture seu conteúdo, identifique a origem de cada trecho, gere embeddings, indexe os dados no PostgreSQL, recupere resultados usando busca híbrida com RRF, refine a ordenação com reranking e entregue trechos e metadados por interface padronizada à equipe de Tools.
