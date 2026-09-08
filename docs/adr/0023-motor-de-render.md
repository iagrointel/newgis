# ADR 0023 — Motor de render no servidor (item L2-12-a-motor-render-servidor)

## Contexto

Impressão de layout (L2-12), miniatura, relatório (L5-29), WMS `GetMap` (L2-04-i) e exportação MapServer
(L2-04-f) precisam, todas, da mesma coisa: transformar um mapa em PNG/PDF de servidor, sem depender do
navegador de quem pediu. `google-chrome` do sistema quebra nesta máquina (regra da casa, `AUDITORIA_*` de
outras frentes); o chromium instalado pelo `playwright install chromium` funciona (medido no L5-29:
WebGL por SwiftShader, 350 ms para 2.000 polígonos).

## Decisão

Um único serviço, `plat-render` (unidade própria, porta 8154 em produção — nesta trilha ele mora dentro do
mesmo `app.main` por comodidade de teste, mas o processo alvo é isolado), mantém um **pool de N páginas do
chromium quentes** (`app/render/motor.py::Motor`), com:

1. **Fila com teto** (`PLAT_RENDER_FILA_MAX`, padrão 20): acima disso, `429 fila_cheia` — nunca uma fila sem
   fundo que derrube a máquina compartilhada.
2. **Teto de tempo único** (`PLAT_RENDER_TIMEOUT_S`, padrão 30) cobrindo fila **+** execução — um pedido que
   espera 25 s na fila só tem 5 s de render, não 30 s do zero.
3. **Isolamento de rede**: cada contexto do chromium intercepta toda requisição e só deixa passar
   `127.0.0.1`/`::1`/`localhost` (e o host de `PLAT_URL_PUBLICA` em produção) — uma página com um estilo
   malicioso apontando para fora nunca sai da máquina.
4. **Token interno de curta duração** (`app/render/token.py`): HMAC sobre `PLAT_SECRET`, TTL cortado a
   60 s mesmo se alguém pedir mais, mais bloqueio por host (`request.client.host` tem de ser loopback). Não é
   uma sessão — não abre `plat.sessao`, não tem cookie.
5. **WYSIWYG de verdade**: a página headless (`web/render_mapa.html` + `web/js/mapa/render_entrada.js`)
   importa o MESMO `web/js/mapa/estilo.js` do visualizador interativo (`web/js/mapa/mapa.js`) — não uma
   cópia, o mesmo arquivo. O sinal de pronto é `map.once('idle')` (tiles carregadas e desenhadas), não
   `'load'`.

## Fronteira honesta (declarada aqui, não descoberta pelo adversário)

`POST /api/render/mapa` com um `mapa_id` cujo documento tem camadas devolve **501**, não um PNG fingindo
desenhar algo. Compor as camadas de um documento de mapa dentro da página de render depende de
`app/mapas/documento.py::completo()` resolver URLs de tile de verdade, e essas dependem de servidor de tiles
vetoriais (L2-01-b) e raster (L1-02) que **não existem nesta máquina** (mesmo `MOTIVO_TILES_VETOR`/
`MOTIVO_TILES_RASTER` já declarados naquele módulo). O motor genérico (pool/fila/token/isolamento/PNG/PDF)
está pronto para qualquer página; a composição de camada é item futuro que herda o motor sem mudá-lo.

Injeção do documento resolvido na página: para o caminho SEM camada (mapa-base local), a página não faz
nenhuma chamada de rede além do próprio `/render/mapa` + `/static/...` — não há sessão nem cookie envolvidos.
O mecanismo de token interno (item 4 acima) existe e está testado (`tests/api/test_render.py`,
`tests/unit/test_render_token.py`) para o dia em que uma página de render precisar chamar uma rota da própria
API durante a janela do pedido (ex.: composição de camada, quando existir).

## Definição operacional de "frio" e "quente"

O portão pede p95 de 50 renders "quente" ≤ 1 s e "frio" ≤ 3 s. Não existe uma única definição óbvia (frio
de PROCESSO? de PÁGINA? de CACHE do chromium?). Esta implementação define: os primeiros `tamanho_pool`
renders de um `Motor` recém-`iniciar()`-ado são frio (primeira navegação real de cada página, pool ainda
não aquecido); os seguintes são quente. Medido em `tests/unit/test_motor_render.py::
test_frio_e_quente_p95_da_demo_1024x768`, gravado em `tests/medidas/L2-12-a-motor-render-servidor.json`.

## Fora do escopo desta ADR

MemoryMax da unidade systemd (`deploy/plat-render.service`) é um VALOR NOMINAL baseado no tamanho do pool
(2 páginas) — não foi medido sob carga real de produção (o ambiente de trilha não tem a unidade systemd
isolada, só o processo dentro de `app.main`). O handoff do item nomeia isso como pendência para o adversário.
