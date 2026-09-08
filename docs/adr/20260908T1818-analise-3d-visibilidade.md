# ADR 20260908T1818 — análise 3D: visada, bacia visual, perfil e sombra (item L2-09-d-analise-3d-visibilidade)

Contexto: o item pede as quatro análises de terreno que o Scene Viewer da Esri oferece de forma
interativa — linha de visada, viewshed, perfil de elevação e sombra — com o portão medido (obstrução
a ≤ 30 m, viewshed byte a byte contra o `gdal_viewshed` direto, perfil conferido com
`rasterio.sample`, sombra a ≤ 5 % da fórmula, e2e com captura de cada, paridade ESCRITA contra o
Scene Viewer). Fora do item: corte de malha (slice) e análise de malha integrada.

## Decisão

**Terreno inline no corpo do pedido.** `app/analise3d/terreno.py` define `Terreno` (srid, x0, y0,
celula_m, alturas) — a grade viaja no JSON da requisição, sem upload de arquivo nesta passagem. O
srid é validado contra a faixa de UTM sul de SIRGAS 2000 em metros (srid fora → 422
`srid_invalido`); a casa não reprojeta (transformação de grade é problema da fonte, não da análise).
O sha256 da grade canônica entra em toda `procedencia` — o mesmo terreno serializado sempre produz
o mesmo hash, e é ele que amarra as duas metades da comparação byte a byte do viewshed.

**Viewshed é o binário, não uma reimplementação.** `app/analise3d/vista.py` escreve o GeoTIFF da
grade, chama o `gdal_viewshed` instalado e devolve os bytes que ele escreveu (base64) mais a linha
de comando usada. A resposta NÃO normaliza nada: se o binário recorta o raster para a janela do
`-md`, as dimensões da resposta são as do raster recortado (`tests/unit/…viewshed.py::test_md_corta_
o_raster_a_janela_do_binario`). A paridade da cláusula 2 é assim por construção — o teste roda a
MESMA linha de comando de novo, num diretório novo, e exige igualdade byte a byte, em relevo suave
E íngreme (cone de 200 m com sigma 30 m). O PNG pintado (verde visível / vermelho invisível sobre
o relevo sombreado) é apenas leitura, nunca a prova.

**Visada é varredura própria, com o erro declarado.** A linha de visada amostra a reta com passo
declarado (`passo_m`, teto de amostras → 422 `amostras_acima_do_teto`) e devolve o CENTRO do
primeiro passo em que o terreno ultrapassa a reta como ponto de obstrução — erro máximo da ordem
do passo, declarado na `procedencia` e medido contra varredura densa independente de passo 0,25 m
(medido: 2,75 m ≤ 30 m). O ponto vem com `z_terreno_m > z_linha_m` e com a soma das distâncias aos
dois extremos igual à distância total. Refutações explícitas (o adversário do item): observador
abaixo do terreno → 422 `ponto_abaixo_do_terreno` (o binário do gdal sozinho não recusaria); alvo
fora da grade ou a 200 km → 422 `ponto_fora_do_terreno`; observador e alvo coincidentes → 422
`visada_nula`.

**Perfil conferido contra a leitura independente.** `app/analise3d/perfil.py` amostra a linha em
n_amostras equidistantes por interpolação bilinear e calcula ganho, perda, declividade máxima e
extremos; a cláusula 3 reconstrói as MESMAS posições e compara com `rasterio.sample` sobre o
GeoTIFF escrito pela casa (medido: 20/20 amostras iguais).

**Sombra = prisma + posição solar NOAA.** `app/analise3d/sol.py` implementa a posição solar pelo
algoritmo da NOAA (declinação aparente, equação do tempo, refração de Saemundsson) e
`app/analise3d/sombra.py` projeta um prisma vertical de base poligonal sobre superfície plana —
comprimento = altura / tan(elevação), na direção oposta ao azimute. A cláusula 4 confere o
comprimento contra a fórmula (medido: desvio 0,268 % ≤ 5 %, às 12:06−03:00 de 21/12 — meio-dia
solar verdadeiro em −46,6° de longitude — com Sol a > 87°). A aproximação fica na resposta
(`APROXIMACAO_SOMBRA`): o relevo não curva a sombra e a estrutura da base não projeta sombra
própria. Sol abaixo do horizonte → 422 `sol_abaixo_do_horizonte`; data sem fuso → 422
`data_sem_fuso`. A nota honesta em relação à Esri: no AGOL o terreno global não projeta sombra
(só objetos 3D) — a nossa sombra é de sólido também, não de relevo.

**Salvar item reusa a rota do catálogo, sem caminho paralelo.** `salvar_item` presente → a rota
chama `app.catalogo.rotas_itens.criar` com tipo `analise_3d`: mesma cota, mesmo JSON Schema, mesmo
evento `itens/adicionar`, mesma RLS. O privilégio `conteudo.criar` é exigido aqui igual à rota
direta (403 `sem_privilegio` com `detalhe.exigido`), para não existir caminho de criar item sem o
privilégio dele. O viewshed salvo guarda o RESUMO (contagens, sha256 do raster, comando) — o
GeoTIFF base64 não cabe em `dados`; o sha256 permite reproduzir o raster byte a byte com o mesmo
comando. O corpo aceita token com escopo `analise3d:usar` (novo, em `app/auth/escopos.py`); token
sem o escopo → 403 `escopo_insuficiente`; sessão e Bearer juntos → 400 `autenticacao_ambigua`
(comportamento existente, não desta passagem).

**Página `/analise3d` e e2e.** `web/analise3d.html` + `web/js/analise3d/painel.js` geram um terreno
de exemplo determinístico (60×60 células de 20 m, morro + vale) e expõem as quatro análises por
botões; o painel de saída marca `data-analise` com o nome da análise — é o que o e2e espera
(`tests/e2e/test_analise3d.py`, captura de CADA análise em `tests/e2e/capturas/`). O e2e precisa de
front TLS: a app não serve `/static/` e exige `PLAT_URL_PUBLICA` em https (o Origin da escrita tem
de ser igual à URL pública); a receita uvicorn+nginx da trilha com certificado autoassinado fica no
handoff do item. Um defeito real de front foi achado e consertado nesta bancada:
`perfilSvg` em `web/js/analise3d/painel.js` chamava `.map()` da segunda série sem guardá-la — toda
análise de perfil quebrava com "reading 'map' of undefined" (a API respondia 200 correto).

**Fora desta versão** (paridade escrita na seção "Análise 3D" de `docs/PARIDADE.md`): corte de
malha (slice) e análise de malha integrada; observador/velho interativo arrastável na tela; sombra
do próprio relevo; perfil com perfis de CAMADA (só terreno).

## Por que inline e não upload

O upload de terreno (Cloud Optimized GeoTIFF de dezenas de MB) já existe como caminho geral do
produto (`L0-04-a-upload-arquivo`) e o acoplamento entre item e análise fica melhor com o terreno
como referência de item própria — não decidida nesta passagem. Inline tira a dependência da ordem:
as análises são computáveis e testáveis hoje, com a grade pequena de teste; o terreno grande entra
quando o item de camada de terreno do catálogo existir. Custo: payloads limitados a grades pequenas
(o teto de corpo da API e o limite de jobs já protegem), declarado na paridade.
