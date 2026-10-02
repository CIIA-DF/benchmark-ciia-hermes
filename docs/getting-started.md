# Primeiro exemplo

Instale Git e [uv](https://docs.astral.sh/uv/getting-started/installation/). Python 3.12 é fixado pelo projeto; `uv sync` pode obtê-lo sem usar Python global. Docker Compose v2 é opcional para PostgreSQL. Não é necessária chave de LLM.

```sh
git clone https://github.com/CIIA-DF/benchmark-ciia-hermes.git
cd benchmark-ciia-hermes
uv sync --locked
uv run --locked python -m scripts.dev demo
uv run --locked python -m scripts.dev check
```

Selecione sua branch pelo [guia Git](git-workflow.md). Se a branch remota ainda não existir, a coordenação precisa ativá-la.

A demo lê os JSONs fictícios de `examples/`, calcula SHA-256, gera chunks por página e grava `data/demo.db`. Outra conexão consulta a API com o cliente ASGI do FastAPI. A saída traz run_id, processo, versões, texto, documento, página e offsets. A segunda execução imprime `Chunks novos persistidos: 0` e continua retornando dados: não duplica a ingestão.

## API HTTP local

Depois da demo, execute:

```sh
uv run --locked python -m scripts.dev serve
```

Em outro terminal:

```sh
uv run --locked python -m scripts.demo --url http://127.0.0.1:8000
uv run --locked python -m agents.smoke --adapter langgraph
```

Abra `http://127.0.0.1:8000/docs` para contratos e `http://127.0.0.1:8000/health` para saúde. O smoke testa apenas a interface HTTP, sem executar agente ou LLM. Ctrl+C encerra a API.

## PostgreSQL com Docker Compose

Copie `.env.example` para `.env`: `cp .env.example .env` no Linux/WSL ou `Copy-Item .env.example .env` no PowerShell. Defina `POSTGRES_PASSWORD`. Para gerar senha hexadecimal compatível com a URL: `uv run python -c "import secrets; print(secrets.token_hex(24))"`. Não publique o valor.

```sh
uv run --locked python -m scripts.dev up
uv run --locked python -m scripts.dev demo-compose
uv run --locked python -m scripts.dev down
```

`up` constrói e aguarda healthchecks. `demo-compose` ingere dentro do container e consulta por HTTP, persistindo no PostgreSQL. `down` preserva o volume. Não use `down -v`: apaga os dados. Banco sem porta publicada; API somente em `127.0.0.1`.

Compose define DATABASE_URL para PostgreSQL. A demo local usa SQLite, exceto se DATABASE_URL estiver definida no terminal. O Python não carrega `.env` automaticamente. Não execute API local e container simultaneamente na porta 8000.

## Comandos

| Make | PowerShell, Linux ou macOS |
| --- | --- |
| `make setup` | `uv sync --locked` |
| `make up` | `uv run --locked python -m scripts.dev up` |
| `make down` | `uv run --locked python -m scripts.dev down` |
| `make demo` | `uv run --locked python -m scripts.dev demo` |
| `make demo-compose` | `uv run --locked python -m scripts.dev demo-compose` |
| `make check` | `uv run --locked python -m scripts.dev check` |
| `make test-backend` | `uv run --locked python -m scripts.dev test-backend` |
| `make test-documents` | `uv run --locked python -m scripts.dev test-documents` |
| `make test-integration` | `uv run --locked python -m scripts.dev test-integration` |

Execute na raiz. `check` faz lint, formato, links/YAML e testes. Formate só os arquivos da tarefa com `uv run ruff format caminho.py`.

Se uv não for reconhecido, reabra o terminal após instalar. Sem Docker, use a demo local. Senha diferente de volume existente exige procedimento administrativo, não apagar volume. Veja [operação](runbooks/operations.md). Falha de lock exige revisar se os arquivos estão sincronizados antes de atualizar dependências.
