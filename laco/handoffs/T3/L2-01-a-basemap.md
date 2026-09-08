# L2-01-a-basemap-local-pmtiles — turno 3 (sessão única: arquiteto+backend+frontend)

**Objetivo.** Primeiro mapa real do produto: mapa-base local em MapLibre GL JS servindo PMTiles pelo
próprio nginx, sem serviço de tiles dinâmico e sem chave de terceiro, na tela `/mapa`.

**Portão fixado** (o item nasceu com portão em aberto, "a fixar pelo arquiteto"): registrado em
`laco/estado.json` antes de construir — MapLibre + `pmtiles-4.5.0.js` lendo PMTiles local (Range
HTTP, gzip off) servido do nginx, recorte OSM ODbL 1.0 ≤ 50 MB com proveniência escrita, tela cheia
com navegação/escala/coordenadas do cursor/seletor de camada base (uma opção), e2e provando 206 +
canvas desenhado (mais de 50 cores distintas na captura) + 0 erro de console.

## O que fiz

1. **Dado**: recorte de Guarulhos-SP (bbox `-46.62,-23.53,-46.42,-23.38`) extraído com `ogr2ogr`
   (streaming, GDAL) do `.pbf` regional já presente na casa (`/home/dev/cbre/osm/area_estudo.osm.pbf`,
   sem novo download) em 4 camadas (estradas/edificações/cobertura/lugares), ladrilhado com
   `tippecanoe -zg --drop-densest-as-needed --extend-zooms-if-still-dropping -L nome:arquivo` (uma
   `-L` por camada). Resultado: `web/dados/basemap/guarulhos.pmtiles` (18,3 MiB, zoom 0-14),
   proveniência completa em `web/dados/basemap/PROVENIENCIA.md` (fonte, bbox, comando, sha256).
2. **Vendor**: `web/vendor/pmtiles-4.5.0.js` (novo, `npm pack pmtiles@4.5.0`, BSD-3-Clause, sha256
   em VERSOES.txt). MapLibre 4.7.1 já estava vendorizado (outra trilha).
3. **Backend**: `/mapa` → `mapa.html` em `app/paginas.py`. `deploy/nginx.conf` (template +
   `/etc/nginx/sites-enabled/plat.iagrointel.com`, ambos): location regex nova
   `^/static/dados/basemap/(?<arquivo_pmtiles>[^/]+\.pmtiles)$` com `gzip off` (obrigatório para
   Range) antes do `/static/` genérico.
4. **Frontend**: `web/mapa.html` + `web/mapa.css` + `web/js/mapa/{mapa.js,estilo.js}`. Tela cheia,
   já com `class="instrumento"` (primeira tela NOVA a nascer no sistema visual novo, não a antiga
   paleta azul). Nav em `layout.js`, i18n em `pt-BR.json`.
5. **Testes**: `tests/e2e/test_mapa.py` — Range 206/Content-Range sem gzip; captura do `#mapa` com
   `PIL.Image.getcolors()` > 50 cores distintas; controles existem e reagem (clique no `+` muda a
   leitura de coordenadas); `tela.verificar()` (0 erro de console, 0 resposta ≥400 inesperada).
6. Corrigi um regression próprio em `tests/unit/test_instalador.py` (contagem de `location` no
   nginx.conf subiu de 4 para 5 com o meu bloco novo).
7. Documentação: `MANUAL.md` §13, `CHANGELOG.md` (nova entrada de turno), `ARQUITETURA.md` (§11 e
   §13 atualizadas), `laco/gera_painel.py` (frase em FUNCOES do item).

## Evidência (comando + saída literal)

```
$ curl -s -D - -o /dev/null -r 0-99 https://plat.iagrointel.com/static/dados/basemap/guarulhos.pmtiles
HTTP/1.1 206 Partial Content
Content-Range: bytes 0-99/19181534

$ flock .pytest.lock venv/bin/pytest -q -m lento tests/e2e/test_mapa.py --base-url https://plat.iagrointel.com
..                                                                       [100%]

$ flock .pytest.lock make check-rapido   (suíte inteira, não só o item)
742 passed, 28 deselected, 5 warnings in 195.74s
```

Captura: `tests/e2e/capturas/L2-01-a-basemap-local-pmtiles_mapa.png` (verificada visualmente —
mapa legível: vias por classe, água/cobertura, edificações, atribuição ODbL, painéis de camada base
e coordenadas, zoom/escala).

## Dois achados corrigidos ANTES de publicar (a verificação visual pegou os dois; o e2e sozinho não pegaria nenhum)

1. **tippecanoe `-l` repetido funde as camadas.** Rodei `-l estradas -L estradas:… -l edificacoes -L …`
   (um `-l` "por precaução" antes de cada `-L`). O manual do tippecanoe diz o contrário do que eu
   supunha: com `-l`, múltiplos arquivos de entrada são fundidos numa ÚNICA camada nomeada, mesmo
   com `-L` individual. Resultado: as 4 camadas viraram uma só chamada `lugares` (o último `-l` da
   linha), confirmado decodificando um tile real (`tippecanoe-decode` + `pmtiles` python — a camada
   `lugares` continha LineString e Polygon, não só Point). O estilo desenha `lugares` como `circle`;
   o `CircleBucket` do MapLibre desenha um círculo em CADA VÉRTICE de qualquer geometria, não só em
   pontos — o mapa saía coberto de bolinhas âmbar (visualmente denso, mas **passava** no teste "mais
   de 50 cores distintas", porque o artefato também produz muitas cores). Corrigido: só `-L`, nunca
   `-l`. Documentado em `PROVENIENCIA.md`.
2. **Painel com `var(--texto)` sobre fundo fixo escuro.** O canvas do MapLibre é cartografia de cor
   FIXA (não segue tema claro/escuro do produto — decisão de estilo.js). Os painéis sobrepostos
   usavam `color: var(--texto)` (que SEGUE o tema) sobre `background: rgba(18,24,26,.86)` fixo. Em
   preferência de sistema clara, `--texto` vira escuro (`#12181a` do tokens.css) — texto invisível
   sobre o próprio fundo (medido: `getComputedStyle` devolvia a mesma cor para `color` e
   `background-color`). Corrigido com uma paleta fixa `--mapa-*` (mesmos hex de `estilo.js`),
   independente do tema; conferido nos dois `color_scheme` do playwright.

## Incidente próprio (registrado, não escondido)

A primeira extração usou `osmium extract` com RAM disponível já abaixo do guardrail de 4 GB do
laço (medido 3,1 GB antes de rodar). O processo foi morto pelo OOM killer, que na mesma varredura
também matou um backend do Postgres — cluster travado 14 min em `deactivating` (Result: oom-kill),
mesmo padrão do incidente de 30/08 já documentado na memória da casa. Remediado com o procedimento
já conhecido: `sudo pg_ctlcluster 16 main stop -m immediate --skip-systemctl-redirect`; banco voltou
consistente (23 migrações, 0 perdidas) em ~40 s; `plat-worker` e `plat-api` reconectaram sozinhos.
Extração refeita com `ogr2ogr` (streaming, pico de RSS medido ~500 MB por chamada) — sem repetir o
erro. Lição para o próximo item que tocar dado geoespacial grande: preferir ferramentas GDAL/ogr2ogr
(disco, streaming) a ferramentas que constroem índice em RAM (osmium, e provavelmente outras).

## Riscos / pendências

- `web/dados/basemap/` fica FORA de `web/vendor/` (que só tem bibliotecas de terceiro versionadas);
  é dado, não código — sem `make vendor` cobrindo. Se crescer (mais de uma base), talvez precise de
  um manifesto próprio (tipo `VERSOES.txt`) para dado, não só para JS/CSS/fonte.
- Cores do estilo do mapa (`estilo.js`) e as cores fixas do chrome (`mapa.css`) são cópias manuais
  da paleta de `tokens.css`; **não há hoje um passo de build que as gere automaticamente** — uma
  mudança de paleta em `tokens.css` não se propaga sozinha (documentado nos dois arquivos).
- `laco/gera_painel.py` ainda sai com código 2 (PAINEL.md não regenerado) por 4 itens de OUTRAS
  trilhas sem frase em `FUNCOES` (`L0-02-a-login-sessao`, `L0-05-a-fila-postgres`,
  `L7-03-f-dependencias-cve-log-correcoes`, `L7-03-b-antivirus-anexos`) — não mexi nesses, não é
  meu item; quem fechou cada um precisa escrever a frase.
- Rótulo de texto no mapa (nome de rua/bairro) fica para `L2-02-e-simbolos-sprites-glifos` (servidor
  de glifos). Camada `lugares` está no tileset mas não é desenhada como texto.
- `git_sha` de `/saude` ainda mostra o commit anterior (só atualiza no próximo `install.sh`); o
  processo em produção JÁ roda o código novo (confirmado pelo e2e contra a URL pública), a rota
  `/mapa` respondeu 200 depois do `systemctl restart plat-api` que dei durante o turno.

## Para o próximo papel / próximo item

`L2-01-mapa-web` é o item grande de verdade (camadas do catálogo do inquilino por Martin/RLS,
raster, legenda, popup, busca de endereço/coordenada, impressão) — ainda não instalei Martin
(`plat-martin`, 8151, porta reservada, serviço inexistente); essa é a próxima trilha bloqueante
dele. `L2-02-e-simbolos-sprites-glifos` destrava rótulo de texto no mapa-base já existente.
