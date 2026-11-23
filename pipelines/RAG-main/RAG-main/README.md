# Pipeline RAG — processos SEI

Ingestão (RAG-01) e parsing (RAG-02) dos PDFs exportados do SEI-GDF. Cada PDF de
processo contém vários documentos internos (ofícios, despachos, atas...); o número
do **processo** é diferente do número **SEI de cada documento**, e o pipeline mantém
essa distinção.

```text
app/data/raw/*.pdf
  -> loader.py  (RAG-01) -> app/data/processed/<nome>.paginas.jsonl     uma página por linha
  -> parser.py  (RAG-02) -> app/data/processed/<nome>.documentos.jsonl  um documento por linha
                         -> app/data/reports/relatorio_ingestao.json   qualidade e alertas
```

## Instalação

Python 3.12.

```sh
pip install -r requirements.txt
```

## Execução

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

Os PDFs e as saídas contêm dados pessoais e não são versionados (`.gitignore`).
Os testes de integração são pulados quando os PDFs não estão em `app/data/raw/`.
