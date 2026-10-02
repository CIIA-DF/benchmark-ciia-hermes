# Hostinger — preparar, aprovar, implantar e reverter

A VPS foi indicada pela coordenação. IP, SSH, domínio, sistema, recursos efetivos, contas e credenciais ainda não foram fornecidos/verificados. Este guia não implica implantação realizada.

## Configurar (Infra, após autorização)

Confirmar dados de acesso por canal privado; inventariar SO/CPU/RAM/disco e firewall. Instalar Git e Docker Engine/Compose conforme documentação oficial do SO. Criar usuário operacional com acesso mínimo, acesso por chave e política de atualizações. Confirmar espaço/retention para backups e destino externo.

Clonar o repositório em diretório dedicado, configurar .env privado com senha nova e permissões restritas. Banco sem porta pública; API fica em loopback. No piloto, usar túnel SSH ou rede privada aprovada. Exposição por domínio exige decisão específica, TLS e autenticação/autorização implementadas antes de dados reais. Não abrir 5432 publicamente.

LLM será endpoint externo com orçamento/chave próprios; não presumir GPU ou modelo incluído na hospedagem. A demo não usa inferência. Credenciais e logs não devem entrar no repositório.

## Aprovar (Coordenação)

Revisar PR main → production com merge commit, CI e aprovação humana. Registrar SHA aprovado, versões/digests das imagens, schema, corpus, requisitos e protocolo. Isso aprova a versão; a janela de implantação precisa ser autorizada separadamente.

## Implantar (operador autorizado)

Começar com diretório de trabalho limpo. Buscar código, conferir SHA em production aprovado e salvar SHA anterior. Fazer backup/restauração de teste antes de mudança com dados. Para evitar misturar alterações locais, parar se git status indicar trabalho pendente.

```sh
git fetch origin
git switch production
git merge --ff-only origin/production
git rev-parse HEAD
docker compose --env-file .env -f infra/compose.yml up -d --build --wait
docker compose --env-file .env -f infra/compose.yml ps
```

Confirmar /health, consultas e versão. Na primeira implantação sintética, carregar o exemplo com `docker compose --env-file .env -f infra/compose.yml exec -T backend python -m scripts.demo --seed-only`. Conferir consulta HTTP e persistência após reinício. Registrar operador/horário/SHA e resultados.

MVP sem autenticação e com create_all só suporta piloto sintético privado. Mudança de schema requer migração explícita, não apenas atualizar container. Agentes/escritas reais ainda não estão disponíveis.

## Rollback

Parar novas execuções, preservar logs seguros e backup atual. Com aprovação, selecionar SHA anterior conhecido em um **worktree de release separado**, por exemplo `git worktree add --detach ../benchmark-rollback SHA_ANTERIOR`. Copiar configuração privada de forma controlada, verificar caminhos e usar o mesmo nome de projeto Compose ciia-benchmark para reutilizar o volume intencionalmente. Não usar reset/force push nem apagar a branch production.

Recriar serviços a partir do commit anterior só é seguro se schema/dados forem compatíveis. Se não forem, restaurar backup validado em banco separado e reconfigurar serviço após avaliação da perda de dados. Não executar down -v. Validar saúde, consulta e artefatos; registrar incidente, versões e regra de repetição das rodadas.

Uma correção no código deve voltar pelo fluxo equipe → main → production. O rollback operacional não reescreve histórico.
