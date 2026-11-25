# ADR 010 — Consolidação documental das interfaces F/A/I

Data: 31/10/2026. Estado: consolidação local implementada; aprovação conjunta pendente.
Responsável: Backend & Tools. Escopo: bloco D, sem alteração funcional ou publicação.

## Contexto

Referências anteriores misturavam o ledger de etapas com tentativas físicas, omitiam quotas e descreviam erros HTTP anteriores a A0. Relatórios por etapa são evidência histórica, não uma referência única de consumo.

## Decisão local

Adotar a [referência vigente](../02-arquitetura/backend-api-atual.md) para consumo e o [índice de estado](../04-operacoes/backend-estado-atual.md) para implementação, verificação e liberação. Preservar referências antigas com indicação explícita de histórico, sem apagar resultados nem converter propostas em capacidades homologadas.

As 21 operações têm fichas derivadas do OpenAPI, exemplos sintéticos e verificação executável de cobertura/modelos. O OpenAPI continua gerado pelo código. O documento não redefine autenticação, quotas, timeouts ou política de retry.

API `0.3.0`, contrato de saúde `0.3`, projeto `0.2.0`, registro experimental `0.1` e exportação `1` têm escopos diferentes. D documenta os valores atuais; não faz release, bump silencioso nem declara pacote de contratos distribuído independentemente. Futuro versionamento da exportação canônica pertence a E.

ADRs 007 e 008 continuam registrando suas decisões e limites. O histórico de etapas não permite reconstruir contagens físicas retroativas; sem backfill inferido. Revisões Alembic 0001–0009 são descritas sem reescrever migrações; a 0010 (registro experimental, [ADR 011](011-registro-experimental-revisoes.md)) foi acrescentada depois e consta no [índice de estado](../04-operacoes/backend-estado-atual.md).

## Consequências e revisão

Mudanças públicas devem manter fichas, exemplos, OpenAPI e consumidores coerentes. Executar `python -m scripts.validate_api_docs` detecta divergência estrutural; revisão humana continua necessária para significado e exemplos de domínio. Este comando não comprova entrega ao cliente, inferência, desempenho ou PostgreSQL.

Backend, Documentos/RAG, Metodologia, Hermes, LangGraph e Infra revisam seus respectivos contratos. Liberação conjunta permanece pendente; nenhuma decisão deste documento autoriza deploy. Novos indicadores, exportação canônica e homologação ficam em O, E e H, respectivamente.
