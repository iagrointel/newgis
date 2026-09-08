# SDK JavaScript `plat` e ajudantes MapLibre (item L7-08-c-sdk-js)

Data: 08/09/2026. Estado: aceito. Par: ADR `20260907T1541-sdk-python.md` (L7-08-b; o modelo de objetos e a
tradução de erro são os mesmos), `laco/decomposicao/L7_CONCEITO.md`.

## Contexto

O SDK Python cobre quem automatiza de fora. Falta o lado do navegador: uma página do cliente (ou um app do
construtor) que fala com a API e põe o dado no MapLibre sem reescrever transporte, paginação, erro e
autenticação a cada vez — o papel que o ArcGIS Maps SDK for JavaScript faz na Esri. A API não emite CORS, e o
appliance não tem internet (L7-11-b): o SDK tem de ser servido pela própria instalação e não pode puxar nada de
fora.

## Decisão

1. **Um arquivo, módulo ES, sem dependência** (`web/sdk/plat.js`, servido em `/static/sdk/plat.js`; publicado
   também como `sdk/js/plat.js`, mesmo arquivo). Só `fetch`. Sem gerador: a API tem 196 operações e o SDK JS
   escrito à mão cobre o MESMO subconjunto ergonômico do Python (`itens`, `camadas`, `mapas`, `jobs`, `tokens`,
   `eu`); quem precisa de uma rota fora dele usa `fetch` com `transformRequest`/`Bearer` — o SDK não esconde
   a API.
2. **Mesmo modelo do Python**: `Plataforma(url, token)`, `entrar()`, `todos()` por cursor, retentativa em
   429/502/503/504, `ErroPlataforma` RFC 9457. Diferenças só onde a linguagem obriga: `todos()` é gerador
   assíncrono; `jobs.esperar()` levanta `ErroPlataforma tempo_esgotado` (JS não tem `TimeoutError` padrão).
3. **Bearer nunca junto com o cookie**: pedidos por token vão com `credentials: 'omit'` (fetch e
   `transformRequest` do MapLibre). Medido no e2e: com os dois, a API responde 400 `autenticacao_ambigua`.
   A sessão (cookie HttpOnly, invisível ao script) continua viva para `.tokens` depois de `entrar()`.
4. **Ajudantes MapLibre não importam o MapLibre**: recebem o mapa ou devolvem JSON (`fonte`, `camada`, `estilo`,
   `catalogo`, `transformRequest`, `enquadrar`). `fonte(item)` devolve o que EXISTE hoje — extensão do item como
   GeoJSON, PMTiles do item, catálogo OGC API Records autenticado — e recusa item sem geometria com erro, nunca
   com fonte vazia. Quando o FeatureServer real (L2-04) entrar, o mesmo método passa a devolver feições.
5. **10 exemplos HTML com CSP `default-src 'none'` na própria página**, sem script inline, sem eval, e SÃO o e2e:
   o teste chama `window.exemplo.main(...)`, o mesmo código do formulário. A página registra
   `securitypolicyviolation`; o e2e exige a lista vazia e prova que a CSP bloqueia um script inline injetado.

## Consequências

- Same-origin: de outra origem o navegador não chega à API (sem CORS, decisão da API, não do SDK); é dito no
  README. Node >= 18 funciona com o mesmo arquivo (cookie de sessão reenviado à mão).
- `docs/PARIDADE.md` tem `merge=ours` na fila: a seção "SDK JavaScript" deste ramo precisa ser reaplicada
  pelo gerente ao fechar o lote (a do SDK Python já se perdeu na junção deste worktree, ver handoff).
- Não há lint de JavaScript no repositório (`make lint` é ruff); o SDK e os exemplos são conferidos por
  `node --check`, pelos 13 testes de unidade em Node e pelo e2e.
