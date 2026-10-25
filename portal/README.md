# Portal e chat local

Next.js 14/React 18 conforme package-lock.json. O portal apresenta documentação
em /team e o chat experimental em /chat. Não há upload de documentos nesta etapa.

Na raiz, prepare a configuração privada e inicie a API e o worker em terminais separados:

```powershell
uv run --locked python -m scripts.chat setup
uv run --locked python -m scripts.chat serve
uv run --locked python -m scripts.chat worker
```

Nesta pasta:

```powershell
npm ci
npm run dev -- --hostname 127.0.0.1
```

Abra http://127.0.0.1:3000/chat. Sem login no piloto: um UUID local identifica
conversas para análise, sem conceder permissões ou comprovar identidade.
O proxy guarda credenciais no servidor e bloqueia hosts remotos. Textos e eventos
ficam no banco. Somente o marcador e a última conversa ficam no navegador.

Verificação: npm run lint, npx tsc --noEmit e npm run build (sem dev simultâneo).
O diretório de guias node_modules/next/dist/docs citado por AGENTS.md não existe
na versão 14 instalada; consulte a documentação oficial dessa versão para APIs.

[Operação](../docs/04-operacoes/chat.md) · [PRD](../docs/02-arquitetura/backend-prd.md) ·
[Contratos](../contracts/README.md) ·
[Route Handlers Next.js 14](https://nextjs.org/docs/14/app/building-your-application/routing/route-handlers).
