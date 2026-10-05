# Desenvolver com Codex ou Claude Code

IA é opcional; testes, revisão e responsabilidade são os mesmos. A preparação consultou OpenAI Docs e a documentação oficial do Claude Code.

## Iniciar e conferir instruções

Abra a raiz, rode `git status --short --branch` e confirme equipe/escopo. Peça: “Leia AGENTS.md, docs/architecture.md, contracts/README.md e docs/teams/backend.md. Informe regras recebidas e comandos de verificação antes de editar”. Troque o guia. Não forneça documentos reais ou segredos.

AGENTS.md é a fonte compartilhada. Codex carrega instruções por hierarquia de diretórios, incluindo possíveis arquivos pessoais e overrides. Confira os caminhos mostrados no contexto da sessão e peça a lista de regras; a resposta do modelo ajuda a conferir, mas não prova enforcement. [Guia oficial AGENTS.md](https://developers.openai.com/codex/guides/agents-md).

CLAUDE.md contém `@AGENTS.md`, import oficialmente suportado. No Claude Code, confira `/context` (arquivos de memória) e `/memory`. A descoberta depende da ferramenta e versão; o import evita manter duas cópias. Guias por componente são leitura explícita para ambas. [Memória/imports](https://code.claude.com/docs/en/memory).

Quando regras mudarem, revise o diff, inicie uma nova sessão na raiz e confira carregamento, tarefa, branch e verificações atuais. Memória anterior não substitui arquivos versionados. Não use /init para duplicar regras sem revisão.

## Tarefa delimitada

Forneça problema, equipe, arquivos permitidos, entradas/saídas, dependências, aceite e teste.

Investigação: “Backend: investigue por que a busca retornou outro processo. Não edite. Mostre causa e reprodução”.
Implementação: “Corrija só filtro e teste de regressão; preserve contrato v0.1”.
Revisão: “Revise o diff buscando vazamento entre processos, quebra de contrato e testes insuficientes; não edite”.

## Prompts por equipe

| Equipe | Exemplo |
| --- | --- |
| Documentos | “Teste offsets/páginas com tabela sintética; verifique se todos os caracteres relevantes são recuperáveis.” |
| Backend | “Teste ler_documento com ID pertencente a outro processo; corrija apenas se o isolamento falhar.” |
| Hermes | “Investigue extensão de ferramentas na URL/versão aprovadas; cite APIs reais antes de implementar.” |
| LangGraph | “Desenhe estado e encerramento do ciclo dinâmico com ToolClient, sem sequência fixa de ferramentas.” |
| Infra | “Execute Compose com dados fictícios, reinicie e comprove persistência; registre limitações sem implantar.” |
| Metodologia | “Escreva duas tarefas de desenvolvimento com evidências e rubrica; não gere resultados experimentais.” |

## Conferir a entrega

Leia git diff e git status; execute demo, testes pertinentes e `uv run --locked python -m scripts.dev check`. Verifique se o relato corresponde aos comandos efetivamente executados. Contratos/ferramentas exigem revisão dos consumidores. Não aceite remoção de checks, APIs inventadas ou declaração de persistência sem confirmação.

Markdown orienta comportamento. Permissões, isolamento, CI, revisão humana e proteções impõem controles técnicos. Tarefa local não requer credenciais de implantação.
