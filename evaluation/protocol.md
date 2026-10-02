# Protocolo inicial — proposta, ainda não aprovado para coleta

Pergunta: sob mesmo corpus, ferramentas, modelo e orçamento comparável, como as duas implementações diferem em sucesso verificável, fundamentação, latência, uso de ferramentas e custo?

## Congelar antes de medir

Registrar corpus/hash/manifesto, requisitos validados e versões, commit do código, uv.lock, versão exata de Hermes e LangGraph, prompt(s) e hashes, parâmetros do modelo, endpoint/modelo exato, orçamento de tokens/chamadas/tempo, ambiente e protocolo. Versões do harness de desenvolvimento e dos adaptadores precisam estar ligadas aos commits; uso de Codex/Claude Code no desenvolvimento não é o agente avaliado.

Mudanças de prompt, biblioteca, ferramenta, corpus, recuperação ou harness alteram a condição experimental. Antes das rodadas finais, congelar essas versões e reservar tarefas finais sem usá-las para depurar. Se corrigir após freeze, registrar motivo/versão e regra de reexecução comparável para ambos; não selecionar somente rodadas favoráveis.

Os PDFs contêm propostas de 360 e 1.080 execuções/múltiplos modelos. A coordenação deve conciliar volume, endpoint e orçamento. Nenhum desses totais é resultado realizado ou decisão final neste protocolo.

## Desenho

Mesmas tarefas e snapshots para ambos; orçamentos comparáveis de tokens/chamadas/tempo. Definir ordem aleatória/contrabalanceada, repetições, sementes quando suportadas e regras para timeout/erro/indisponibilidade. Reiniciar estado e isolar artefatos de escrita por run_id, evitando contaminar rodadas seguintes. Registrar diferenças inerentes de prompts internos/políticas, sem fingir equivalência que o executor não permite.

Unidade de análise primária proposta: tarefa/processo, com comparação pareada entre implementações. Repetições da mesma tarefa são medidas correlacionadas, não observações independentes. Definir previamente agregação por tarefa ou análise hierárquica/intervalos por clusters. Tamanho amostral e teste estatístico exigem revisão metodológica antes da coleta.

Desenvolvimento: exemplos sintéticos versionados. Avaliação final: tarefas reservadas em armazenamento aprovado, separadas do conjunto usado para ajustar agentes. Não incluir documentos reais no Git.

## Rubricas e métricas propostas

Primária: sucesso verificado da tarefa (todos os critérios críticos, fontes válidas e ações realmente persistidas).
Secundárias: fundamentação factual, chamadas indevidas, latência, consumo/custo e falhas por categoria. Caminhos alternativos válidos são aceitos; não exigir ordem fixa de ferramentas.

Rubrica inicial por tarefa: referência correta (0/1), resposta sustentada (0/1), completude/limitações reconhecidas (0/1), escrita autorizada e confirmada quando aplicável (0/1 ou não aplicável). Um requisito crítico falho impede sucesso global. Versão final, pesos e critérios de divergência precisam ser aprovados antes da coleta.

Para respostas: avaliadores com executor oculto, dois avaliadores numa amostra definida previamente, registro de discordâncias e adjudicação. Avaliador LLM, se adotado, requer validação; não substitui a prova independente.

## Registro por execução

ExperimentRun inclui run_id, task_id, split/repetition, executor, corpus/requisitos, commits/versões do harness e adaptador, modelo e endpoint_id (sem chave), prompt_sha256, parâmetros, início/latência, tool_calls com ID/nome/duração/status/artefato, tokens e custo quando disponíveis, sucesso declarado e verificado.

Guardar prompts efetivos e respostas completas apenas no armazenamento privado aprovado, ligados por hashes ao registro. Tokens/custo não informados ficam null, nunca zero. Definir fonte de preços/data/moeda e separar estimativa de custo medido. Registrar orçamento e interrupções, inclusive falhas.

Escrita exige conferir banco/artefato por leitor independente e comparar conteúdo/hash/ID. Recibo HTTP ou alegação do agente sozinhos não bastam. Hoje escrita e persistência de ExperimentRun não estão implementadas: este documento define requisitos futuros.

## Analisar e publicar

Relatar todas as execuções previstas, exclusões justificadas, falhas, diferenças com incerteza e análise de erros. Custo por sucesso só existe quando há sucessos; definir previamente convenção para zero sucessos. Conclusões valem para as implementações/versões avaliadas, não para todos os agentes possíveis.

Cronograma proposto: outubro integração/piloto, novembro congelamento/coleta/análise, dezembro revisão e entrega até 10/12/2026. Marcos dependem de decisões e evidências; nenhum está declarado concluído. Artigo: introdução, relacionados, corpus, implementações, protocolo, resultados reais, discussão e limitações.
