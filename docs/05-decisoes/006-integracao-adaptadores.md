# ADR 006 — integração por fábrica explícita e homologação real

Data: 24/10/2026. Estado: infraestrutura local implementada; agentes pendentes.
Responsáveis pela revisão: Backend, Hermes, LangGraph, Infra e Metodologia.

## Contexto e decisão

O backend fornece ferramentas comuns; as equipes implementam seus executores.
O repositório e a versão oficial de Hermes continuam pendentes. Não instalar
pacotes por suposição nem escrever um substituto e apresentá-lo como Hermes.

O worker recebe --executor e --adapter modulo:funcao. A fábrica fornecida pela
equipe retorna objeto com AgentAdapter.stream. O cliente comum oferece as seis
tools e injeta contexto/token da reserva. O simulador tem identificação própria.

## Alternativas e consequências

Evitar imports fixos para arquivos ainda inexistentes permite entregar a integração
antes dos runtimes. A fábrica é configuração administrativa de código local
confiável, nunca argumento enviado pelo usuário ou LLM.

Não declarar executor pronto apenas por habilitá-lo na configuração. Sua equipe
deve registrar versão, modelo, endpoint, limites e passar os cenários de
[homologação](../04-operacoes/integracao-agentes.md). Enquanto isso,
o piloto com agentes reais permanece pendente, mesmo com testes sintéticos aprovados.
