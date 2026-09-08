# SDK JavaScript `plat`

Análise / beta privado. SDK para a plataforma SIG (item `L7-08-c-sdk-js`), irmão do SDK Python (`sdk/python`):
mesmo modelo de objetos, mesmos nomes, mesma tradução de erro. Um único arquivo, módulo ES, sem dependência
(só `fetch`), servido pela própria instalação em `/static/sdk/plat.js` (o arquivo de verdade é
`web/sdk/plat.js`; `sdk/js/plat.js` é o mesmo arquivo, publicado aqui para quem consome o repositório).

```html
<script type="module">
  import { Plataforma } from '/static/sdk/plat.js';

  // 1) primeira vez: login + criação de um token de serviço (sessão só para emitir o token)
  const p = await Plataforma.entrar(location.origin, 'SEU-INQUILINO', 'usuario', 'senha');

  // 2) uso normal, com o token já emitido
  const p2 = new Plataforma(location.origin, 'plat_...');

  const pagina = await p2.itens.listar({ limite: 20 });
  for await (const item of p2.itens.todos({ tipo: 'camada_vetorial' })) console.log(item.id, item.titulo);
  const job = await p2.jobs.esperar(algumJobId, { tempoLimiteMs: 120000 });
</script>
```

Em Node >= 18 o mesmo arquivo funciona (`import { Plataforma } from './sdk/js/plat.js'`); `entrar()` guarda o
cookie de sessão à mão para que `.tokens` continue funcionando.

## O que existe

- `Plataforma(url, token)` — `.eu()`, `.itens` (`listar`, `todos`, `obter`, `criar`, `atualizar`, `apagar`,
  `mover`, `facetas`, `compartilhamento`, `compartilhar`), `.camadas` e `.mapas` (visões por `tipo` sobre
  `/api/itens`; `/api/camadas` e `/api/mapas` não existem), `.jobs` (`listar`, `obter`, `tipos`, `criar`,
  `esperar`), `.tokens` (`listar`, `criar`, `revogar`, `renovar`, `log` — só com sessão: no navegador, a da
  página ou a de `entrar()`), `.sair()`.
- Retentativa embutida em 429/502/503/504 e erro de rede (espera 0,5 s, 1 s, 2 s); nunca em 4xx do próprio pedido.
- `ErroPlataforma` no vocabulário RFC 9457 (`status`, `tipo`, `titulo`, `detalhe`, `instancia` = `req_id`),
  traduzido do contrato real da API (`{"erro","mensagem","detalhe","req_id"}`), com `toProblemDetails()`.
- **Bearer nunca junto com o cookie**: pedidos por token vão com `credentials: 'omit'`; a API responde 400
  `autenticacao_ambigua` quando recebe os dois — regra medida no e2e, não suposta.
- `.maplibre` (o SDK não importa o MapLibre; recebe o objeto ou o mapa):
  - `transformRequest` — opção do `new maplibregl.Map({...})`: põe o Bearer (sem cookie) só em `/api` e `/ogc`
    da própria plataforma;
  - `fonte(item)` — `source` pronta: PMTiles do item (`vector`, `pmtiles://`) ou a extensão do item como
    GeoJSON; item sem extensão nem endereço = `ErroPlataforma item_sem_geometria`, nunca fonte vazia;
  - `camada(item)` — `layer` correspondente; `enquadrar(mapa, item)` — `fitBounds` na extensão;
  - `catalogo({bbox, tipo, q, limit})` — o catálogo OGC API Records como GeoJSON autenticado;
  - `estilo(mapaItem, {basemapUrl, itens})` — estilo MapLibre versão 8 de um item `mapa` (respeita
    `dados.corpo.estilo` quando é um estilo completo; senão fundo + mapa-base PMTiles + extensão dos itens).

## O que NÃO existe ainda (e por que o SDK não finge)

A API não tem rota de feições por camada nem de tiles dinâmicos (FeatureServer real = `L2-04`, parcial).
`fonte(item)` devolve o que EXISTE (extensão, PMTiles estático, catálogo); quando a rota de feições entrar, o
mesmo método passa a devolver a fonte de feições sem mudar a assinatura. Não há CORS na API: o SDK no navegador
é same-origin (as páginas de exemplo são servidas pela instalação); de outra origem, use Node ou o SDK Python.

## Exemplos (10, e são os testes)

`web/sdk/exemplos/NN_x.html` (+ `NN_x.js`), abertos em `/static/sdk/exemplos/NN_x.html`: formulário
(inquilino, login, senha) para rodar à mão, e `window.exemplo.main(url, inquilino, login, senha)` para o e2e
(`tests/e2e/test_sdk_js.py`), o MESMO código. Cada página tem CSP `default-src 'none'` na própria `<meta>` e
registra violações em `window.exemplo.violacoes`; o e2e exige a lista vazia e 0 erro de console.

| nº | exemplo | prova |
|---|---|---|
| 01 | login e primeiro token | `entrar()`, `eu()`, `sair()` revoga o token |
| 02 | listar itens | `listar()`, `todos()` sem ler cursor, `facetas()` |
| 03 | criar, atualizar e apagar | `mapas.criar()`, `atualizar()` PATCH, `apagar()` |
| 04 | paginação | 7 itens, páginas de 3, `todos()` entrega os 7 |
| 05 | tokens de serviço | criar com `catalogo:ler`, log, revogar, mensagem exata do token revogado (401 `token_revogado`) |
| 06 | jobs | `jobs.criar('prova.progresso')`, `esperar()` até `concluido` (worker real) |
| 07 | compartilhamento | `compartilhar(acesso: 'inquilino')` e `compartilhamento()` |
| 08 | erros e escopo | 404 e 403 `escopo_insuficiente` como Problem Details |
| 09 | mapa: fonte/camada/enquadrar | extensão do item sobre o mapa-base PMTiles local; captura conferida |
| 10 | mapa: estilo/catálogo | `estilo(mapa)` com 2 camadas hospedadas + `catalogo({bbox})` via `transformRequest` |

Testes de unidade sem rede: `node --test tests/sdk_js/plat.test.mjs` (13), corridos pelo `make check` via
`tests/unit/test_sdk_js.py`. Medidas em `tests/medidas/L7-08-c-sdk-js.json`.
