# T2 · L0-03-catalogo · 31_frontend — frontend (trilha C)

## Objetivo

Construir, contra o contrato do ADR 0004 (seções 13, 15, 16) e o upload do ADR 0005 (seção 3), a tela "Conteúdo" com
lista/grade, busca por campo, filtros, pastas, seleção em massa, painel do item (metadado editável, dados por JSON
Schema, configurações, versões, relações, compartilhamento com grupos e link por token), lixeira, favoritos,
transferência de dono e criação de item (arquivo por upload, conexão por URL, mapa em branco, outro tipo), reusando
a base de `web/js/base/` sem duplicar, com e2e playwright em `tests/e2e/test_conteudo.py` (capturas `L0-03_*.png`,
0 erro de console, medida `primeira_pintura_conteudo_ms`), tocando só `web/` e `tests/e2e/` (+ `pt-BR.json` e
`layout.js` por acréscimo).

## O que fiz

1. Li SKILL, item + 12 filhos no estado, `20_arquitetura.md`, ADR 0004 (seções 2-16), ADR 0005 seção 3, a base
   (`api/estado/i18n/dom/layout/componentes`), `31_frontend.md` do L0-02, L5_CONCEITO D1-D5/D23 e, quando o backend
   começou a comitar `app/catalogo/*`, os modelos e rotas reais (ver "Contrato conferido").
2. `web/js/catalogo/` (17 módulos, maior = `item.js` 30,3 kB, todos ≤ 60 kB; soma carregada pela tela MEDIDA
   227,4 kB ≤ 400): `api.js` (único lugar com URL; `ErroApi`; chave repetida para arrays; `PATCH`; corpo bruto só para
   parte de upload), `contexto.js` (loja da base), `lista.js` (tabela | lista | grade sobre o mesmo JSON, cursor
   "Carregar mais" sem perder seleção, favoritar, j/k/x/Enter), `filtros.js` (facetas de `/api/itens/facetas`, chips,
   datas, origem, bbox), `pastas.js` (árvore ≤ 5, criar/renomear/apagar com `pasta_nao_vazia`), `selecao.js` (lote:
   mover, compartilhar, tags, proteger/desproteger, status, transferir, apagar; na lixeira restaurar/apagar agora),
   `busca_sintaxe.js` (gramática 7.2 validada no cliente: campo desconhecido, `:` sem campo, intervalo, uuid, aspas,
   parênteses, 200 termos/1.000 caracteres) + ajuda com exemplos clicáveis, `item.js` (cabeçalho, pontuação 0-10 com
   "o que falta", abas Visão geral / Dados / Configurações / Versões / Relações / Compartilhamento, edição em linha por
   `PATCH`, menu ⋯ mover/transferir/proteger/obsoleto/autoritativo/copiar uuid-URL/apagar com `ordem-de-exclusao`,
   cascata explícita e instrução do protegido), `item_dados.js` (JSON Schema → `<plat-formulario>`: string/enum/
   número/booleano/lista/JSON; validador local type/required/enum/min/max/pattern/maxItems/additionalProperties;
   erro do servidor ligado ao campo pelo caminho), `item_compartilhar.js` (nível, grupos em que contribui, árvore de
   dependências com "aplicar este nível" desabilitada onde `pode_editar=false`, links: criar/copiar uma vez/revogar),
   `item_versoes.js` (lista, diff JSON Patch, restaurar, publicar), `item_relacoes.js`, `item_transferir.js`
   (pré-checagem `simular:true`, falhas com solução, parcial explícito), `lixeira.js` (`<plat-tabela>` +
   `<plat-paginacao>`, expurga em, esvaziar com texto), `novo.js` (Arquivo = upload retomável do ADR 0005: `POST
   /api/uploads` → `PUT partes/{n}` octet-stream com 3 tentativas → `concluir` → abre o item; **só aparece quando
   `/api/openapi.json` lista `/api/uploads`**, senão o menu não mostra botão inerte; Conexão por URL; Mapa em branco;
   Outro tipo com formulário do esquema; Pasta), `compartilhado.js` (página anônima `/c/<token>`: 404/410 com código),
   `formato.js`, `icones.js` (SVG por DOM, sem HTML em string), `tipos/{arquivo,conexao,mapa}.js`.
3. Páginas: `web/conteudo.html` (+ `conteudo_item.html`, `conteudo_lixeira.html` iguais, nomes da seção 15 do ADR;
   o backend já registrou as 4 rotas em `app/paginas.py`), `web/compartilhado.html`, `web/conteudo.css` (só o que
   `style.css` não tem; gavetas `<details>` abaixo de 900 px). DOMPurify carregado nas duas páginas; `descricao_html`
   passa por `htmlSeguro()` de novo no cliente (L5 D23).
4. `layout.js`: uma linha em `TELAS` (`/conteudo`, `nav.conteudo`, sem privilégio: ver conteúdo é de todo perfil).
   `pt-BR.json`: +364 chaves `catalogo.*` + `nav.conteudo`/`nav.conteudo_desc` (363 → 727; verificador de chave
   usada × dicionário: 0 faltando, inclusive as dinâmicas `acesso_*`, `vista_*`, `familia_*`, `rel_*`, `falha_*`).
5. Bancada LOCAL fora do repositório (`scratchpad/bancada/bancada.py`: serve `web/` e simula a API da seção 13 +
   uploads em memória, 120 itens semeados, título de 2.048 caracteres, item apagado, `descricao_html`). Achou e
   corrigiu antes do backend: editor de tags dentro de `<plat-formulario>` (o `render()` do componente apaga os
   filhos), esperas do e2e por um `ok` velho do `<plat-aviso>` (limpar antes de esperar), reload da lixeira sem esperar
   a linha certa. Fumaça (`smoke.py`) percorre vistas, cursor, busca, filtros, pastas, lote, abas, painel com as 6
   abas, diff, link criar/revogar, transferência simulada, apagar, upload por partes e `/c/<token>` inválido: 0 erro
   de console além dos 4xx declarados.
6. Contrato conferido contra `app/catalogo/*` do backend (comitado durante o turno) e ajustado: `ordenar` +
   `direcao` separados (não `campo:dir`); lote `{acao:"tags", tags:[…], de, para}`; `status:"nenhum"` para limpar;
   miniatura por `POST` JSON `{conteudo: base64, nome}` (não multipart: CSRF sob cookie exige `application/json`);
   pastas `/api/pastas/arvore` aninhada com `filhas` (o front aceita aninhada ou plana); transferência com
   `simular/forcar_parcial/adicionar_aos_grupos/pastas`; links `{nome, expira_em, itens_incluidos, permite_download}`.
7. e2e `tests/e2e/test_conteudo.py` (2 testes, marcadores `lento`+`e2e`, salta enquanto o OpenAPI da URL não lista
   `/api/itens`, `/api/tipos-item`, `/api/pastas`, `/api/lixeira`): fluxo completo criar pasta → criar mapa pela tela →
   editar título e tags em linha (lista reflete) → compartilhar com o inquilino → link por token: anônimo 200 →
   revogar → 404 → busca por campo (`titulo:… tipo:mapa`), `foo:bar` recusado no cliente, lista vazia → favoritar →
   aba Favoritos e Inquilino → mover para a pasta → apagar → lixeira → restaurar (mesmo uuid, acesso preservado) →
   apagar → apagar agora; 10 capturas `L0-03_{lista,grade,vista_lista,detalhe,compartilhar,busca,vazio,favoritos,
   inquilino,lixeira}.png`; `verificar()` = 0 erro de console; medidas `pagina_conteudo_ms`,
   `primeira_pintura_conteudo_ms` (FCP da Performance API), `soma_modulos_kb` (recursos `/static/js/` decodificados).
   Segundo teste: nenhuma chave crua em `/conteudo`, `/conteudo/lixeira` e nas 6 abas do painel (mesma regra do
   `test_i18n_cru`). `apoio_catalogo.py` = `TelaCatalogo` com captura `L0-03_<tela>.png` e medidas do item.
8. Três commits só com `web/` e `tests/e2e/` (41c1dd9, a06ca71, 05a41cd).
9. **Fechamento do turno contra a URL real** (o backend publicou o catálogo às 18:03 UTC): rodei o e2e dentro do
   `flock` contra `https://plat.iagrointel.com`, gravei as 10 capturas e as três medidas com `PLAT_GRAVAR_MEDIDAS=1`,
   e sondei um a um os pontos que a bancada não podia confirmar (facetas, cursor, `expurga_em`, `ordem-de-exclusao`,
   `usado-por`, árvore de pastas, os 8 exemplos da ajuda de busca, `ordenar`/`direcao`, `origem`).
10. Dois defeitos que só a API viva mostra, corrigidos no front e cobertos por e2e (detalhe em "Contra a URL real"):
    faceta de **dono** devolve o login e `?dono_id` exige inteiro; faceta de **categoria** devolve o caminho em
    `valor` (o uuid vem em `id`) e `?categoria` exige uuid. Commit 03a73e0, só `web/js/catalogo/filtros.js` e
    `tests/e2e/test_conteudo.py`.

## Evidência (comando + saída literal)

```
$ for f in web/js/catalogo/*.js web/js/catalogo/tipos/*.js; do node --input-type=module --check < $f; done; echo SINTAXE_OK
SINTAXE_OK
$ ! grep -rnI --exclude-dir=vendor -E -f tests/marcadores.regex web tests/e2e && echo MARCADORES_OK
MARCADORES_OK          (a 1ª rodada casou o ATRIBUTO html "placeholder" em 3 inputs: trocado por title)
$ venv/bin/ruff check tests/e2e
All checks passed!
$ python3 -c "import json;print(len(json.load(open('web/js/i18n/pt-BR.json'))))"
727                    (verificador chave usada × dicionário: faltando: [])
$ wc -c web/js/catalogo/*.js | sort -n | tail -2
 30268 web/js/catalogo/item.js
172477 total          (17 módulos; maior 30,3 kB ≤ 60 kB)

$ PYTHONNOUSERSITE=1 venv/bin/python scratchpad/bancada/smoke.py        (bancada local :8890, 120 itens)
conteudo pronto … carregar mais ok; linhas 100 … busca titulo: 23 … filtro tipo: 45 chips 1 … pasta: 24
lote botões 9 … lote tags: 2 feitos … abas ok; lixeira linhas 1 … painel abas ok … link http://127.0.0.1:8890/c/…
plano 1 item(ns), 0 com falha, novo dono maria … gerar: este tipo não gera miniatura por job; envie uma imagem
outro tipo (erros de esquema esperados): 2 … menu novo: ['Arquivo (enviar)', 'Conexão por URL', 'Mapa em branco', 'Outro tipo…', 'Nova pasta']
upload item: teste.geojson … compartilhado 404: este link não existe ou foi revogado (404)
ERROS: 4   (409 miniatura/gerar em tipo sem gerador e 404 de /c/nao-existe: os dois provocados de propósito)

$ flock /home/dev/plataforma/laco/.pytest.lock env PYTHONNOUSERSITE=1 venv/bin/pytest tests/e2e/test_conteudo.py -m lento --base-url http://127.0.0.1:8890 -q
..                                                                       [100%]      (2 passed)
$ ls tests/e2e/capturas | grep L0-03 | tr '\n' ' '
L0-03_busca.png L0-03_compartilhar.png L0-03_detalhe.png L0-03_favoritos.png L0-03_grade.png L0-03_inquilino.png L0-03_lista.png L0-03_lixeira.png L0-03_vazio.png L0-03_vista_lista.png

$ PYTHONNOUSERSITE=1 venv/bin/python scratchpad/bancada/medir.py http://127.0.0.1:8890 admin x demo   (3 cargas, 50 itens de 120)
pagina_conteudo_ms=97.1 primeira_pintura_conteudo_ms=24 soma_modulos_kb=227.4 modulos=33 itens=50
pagina_conteudo_ms=88.5 primeira_pintura_conteudo_ms=16 soma_modulos_kb=227.4 modulos=33 itens=50
pagina_conteudo_ms=96.9 primeira_pintura_conteudo_ms=16 soma_modulos_kb=227.4 modulos=33 itens=50
(número da BANCADA em loopback, sem banco: serve para o orçamento de módulos, NÃO para o portão de 1,5 s com 10 mil itens)

$ curl -s https://plat.iagrointel.com/api/openapi.json | python3 -c "...len(paths), '/api/itens' in paths"
55 False    (às 17:56 UTC; vigia de 55 min em curso — ver seção "Contra a URL real")
```

### Fechamento contra a URL real (20:0x-20:14 UTC)

```
$ curl -s https://plat.iagrointel.com/api/openapi.json | python3 -c "... len(paths); rotas do catálogo"
total paths: 92
/api/itens True · /api/tipos-item True · /api/pastas True · /api/lixeira True · /api/uploads False

$ systemctl show plat-api -p ActiveEnterTimestamp -p NRestarts
NRestarts=0
ActiveEnterTimestamp=Sat 2026-09-05 18:03:37 UTC        (nenhuma rodada precisou ser repetida por reinício)

$ curl -s .../api/itens/facetas | python3 -c "print(json.load(sys.stdin)['dono'])"
[{'valor': 'admin', 'n': 141}, {'valor': 'zt37dbdd64', 'n': 8}, {'valor': 'ztd6cf51a6', 'n': 8}, {'valor': 'ztf9d8cfc2', 'n': 8}]
$ curl -s ".../api/itens?limite=1&dono_id=admin"
{"erro":"campo_invalido","mensagem":"dono_id exige inteiro","detalhe":{"campo":"dono_id"},"req_id":"f15cc18b3b254492"}
$ curl -s ".../api/itens?limite=1&dono_id=1"
dono_id=1 -> total 141                                   (achado 1: a faceta mostra o login, o filtro quer o id)

$ curl -s .../api/itens/facetas | python3 -c "print(json.load(sys.stdin)['categoria'])"
[{'id': 'e7bdf6a9-88e7-4bf8-9461-09ffcd588e24', 'valor': 'zt Tema 2fa6eb', 'n': 1}, ...]
$ curl -s ".../api/itens?limite=1&categoria=zt%20Tema%20f10ed0"
422 {"erro":"campo_invalido","mensagem":"categoria exige uuid","detalhe":{"campo":"categoria","valor":"zt Tema f10ed0"}}
$ curl -s ".../api/itens?limite=1&categoria=f973be05-2475-4569-b583-a55202c7422b"
200 {"total":1,...}                                      (achado 2: o filtro quer o `id`, não o caminho)

$ for s in nenhum obsoleto autoritativo; do curl -s ".../api/itens?limite=1&status=$s"; done
status=nenhum -> 0     status=obsoleto -> 2     status=autoritativo -> 0     (achado 3, do backend: faceta conta 'nenhum' por coalesce, filtro compara i.status = ANY)

$ python3 - <<'EOF'   # os 8 exemplos da ajuda de busca contra a API viva
200 | titulo:municipio            200 | tags:ibge tipo:camada_vetorial      200 | "setor censitario"
200 | rodovia OR ferrovia         200 | municipio -limite                   200 | modificado:[2026-08 TO *]
200 | dono:maria status:autoritativo                200 | criado:[2026-01-01 TO 2026-03-31] acesso:inquilino
EOF

$ curl -s .../api/itens/<id>/ordem-de-exclusao ; curl -s .../api/itens/<id>/usado-por
{"ordem":[],"ocultos":0}                                 []
$ curl -s ".../api/itens?limite=2" | chaves da resposta
['total', 'itens', 'proximo_cursor', 'aproximado']        (lixeira acrescenta 'expurga_em' em cada item)

$ flock /home/dev/plataforma/laco/.pytest.lock env PYTHONNOUSERSITE=1 PLAT_GRAVAR_MEDIDAS=1 venv/bin/python -m pytest tests/e2e/test_conteudo.py -v --durations=3 --base-url https://plat.iagrointel.com
tests/e2e/test_conteudo.py ..                                            [100%]
5.59s call     tests/e2e/test_conteudo.py::test_conteudo_fluxo_completo[chromium]
1.19s call     tests/e2e/test_conteudo.py::test_conteudo_sem_chave_crua[chromium]
============================== 2 passed in 7.42s ===============================

$ git checkout -- web/js/catalogo/filtros.js   # prova de que o conserto é o que segura
$ flock ... pytest tests/e2e/test_conteudo.py::test_conteudo_fluxo_completo -q --base-url https://plat.iagrointel.com
E  playwright._impl._errors.TimeoutError: Page.wait_for_selector: Timeout 15000ms exceeded.
E    - waiting for locator("#lista tr[data-id='a2cbcb0f-6a28-48d7-afc7-c8987edffdd4']") to be visible
FAILED tests/e2e/test_conteudo.py::test_conteudo_fluxo_completo[chromium]     (com o filtros.js de 05a41cd)

$ cat tests/medidas/L0-03-catalogo.json | medidas
{'pagina_conteudo_ms': 234.9, 'primeira_pintura_conteudo_ms': 24, 'soma_modulos_kb': 229.6}  2026-09-05T20:14:22Z
$ ls -l tests/e2e/capturas | grep -c L0-03
10                                                        (todas reescritas às 20:14 contra a URL real)
$ ! grep -rnI --exclude-dir=vendor -E -f tests/marcadores.regex web tests/e2e && echo MARCADORES_OK
MARCADORES_OK
$ venv/bin/ruff check tests/e2e ; node --input-type=module --check < web/js/catalogo/filtros.js
All checks passed!   SINTAXE_OK
$ git log --oneline -1
03a73e0 Conteúdo (L0-03, frontend) contra a API viva: faceta de dono e de categoria devolvem rótulo, o filtro exige id — normaliza antes de desenhar; e2e cobre o ida-e-volta da faceta

$ git log --oneline | head -3
05a41cd Conteúdo (L0-03, frontend): contrato do backend (ordenar+direcao, lote tags, status nenhum, miniatura em JSON), …
a06ca71 e2e da tela Conteúdo (L0-03-catalogo): fluxo criar-editar-compartilhar-link-busca-favoritar-mover-apagar-restaurar …
41c1dd9 Tela Conteúdo (L0-03-catalogo, frontend): lista/grade com cursor, busca por campo, filtros, pastas, seleção em massa, …
$ git status --short -- web tests/e2e
(vazio)
```

## Contra a URL real (https://plat.iagrointel.com)

O `/api/openapi.json` da URL interna passou a listar as rotas do ADR 0004 (92 caminhos; `/api/itens`,
`/api/tipos-item`, `/api/pastas`, `/api/lixeira` presentes, `/api/uploads` ainda não). `plat-api` entrou em serviço às
18:03:37 UTC e **não reiniciou durante nenhuma das rodadas** (`NRestarts=0`), então nenhuma rodada precisou ser
repetida por reinício. O e2e passou 2/2 contra a URL real, com 10 capturas `L0-03_*.png` novas e 0 erro de console.

**Achado 1 — faceta de dono (corrigido no front, registrado para o backend).** `GET /api/itens/facetas` devolve o
dono pelo login (`{"valor": "admin", "n": 141}`), mas `GET /api/itens?dono_id=` exige inteiro e recusa o login com
422 `dono_id exige inteiro`. Quem clicasse a faceta de dono recebia 422 em vez de filtro. O front agora resolve o
login pelo `dono {id, login, nome}` que a própria lista já traz, aceita `id` na faceta caso o backend passe a
mandá-lo, e omite o dono cujo id ainda não apareceu na lista — em vez de mandar um valor que o servidor recusa.
Pedido ao backend: devolver o id do dono na faceta (`{"valor": <dono_id>, "rotulo": "<login>"}` ou um campo `id`,
como já é feito em `categoria`); com isso o front deixa de precisar resolver e nenhum dono some da faceta.

**Achado 2 — faceta de categoria (defeito do front, corrigido).** A faceta traz `{"id": "<uuid>", "valor":
"<caminho>"}` e o filtro `?categoria` exige uuid (422 `categoria exige uuid`); o front mandava o caminho. Agora usa o
`id` como valor do filtro e o caminho como rótulo, tanto nos quadrados quanto nos chips.

**Achado 3 — status "nenhum" (é do backend, sem contorno no front).** A faceta conta `status: nenhum` (54 itens
naquele momento) porque agrupa por `coalesce(i.status, 'nenhum')`, mas o filtro compara `i.status = ANY(...)` e o
"nenhum" está gravado como NULL: `?status=nenhum` devolve `total 0`. Não existe valor que o front possa mandar para
dizer "sem status"; ou a faceta deixa de oferecer o balde, ou o filtro traduz `nenhum` para `IS NULL`. **Não mexi no
backend.**

**Contrato confirmado contra a API viva** (era o risco 1 deste handoff, agora fechado): `dono` no item e na árvore de
pastas vem `{id, login, nome}`; `proximo_cursor` é opaco em base64 e volta junto de `total`/`aproximado`;
`expurga_em` existe só nos itens da lixeira; `/ordem-de-exclusao` devolve `{"ordem": [...], "ocultos": n}`;
`/usado-por` devolve lista; `/api/pastas/arvore` vem aninhada com `filhas`; os 8 exemplos da ajuda de busca devolvem
200; `ordenar` aceita titulo/tipo/dono/modificado_em/criado_em/tamanho_bytes/pontuacao com `direcao` asc|desc (e
recusa `relevancia`, que o front não manda); `origem` aceita hospedado|referenciado, que são exatamente as duas
opções do seletor.

## Riscos

1. **FECHADO no fechamento do turno**: tudo foi reprovado ou confirmado contra a API viva (seção "Contra a URL
   real"). O que era suposição virou medida: `dono` nas facetas vem só com o login (achado 1, corrigido),
   `proximo_cursor`/`aproximado`/`expurga_em`/`ordem-de-exclusao`/`usado-por`/árvore de pastas vieram na forma que o
   front já aceitava. Fica de pé um risco menor: se um dono tiver itens nas contagens da faceta mas nenhum item na
   página carregada, o front não sabe o id dele e omite a linha da faceta — some enquanto o backend não devolver o id.
9. **Não confirmado contra a API viva**: transferência de dono real (só a pré-checagem `simular`), miniatura por job,
   restauração de versão com diff grande, lote acima de 100 itens e o portão de 1,5 s com 10 mil itens semeados. O
   e2e cobre o caminho principal; esses pontos são do roteiro à mão do testador.
10. **status "nenhum"** (achado 3): enquanto o backend não decidir, a faceta oferece um balde que filtra 0. O front
   mostra o que o servidor manda; não há valor que ele possa mandar para dizer "sem status".
2. Upload de arquivo (ADR 0005) está construído mas **escondido até `/api/uploads` existir no OpenAPI** (L0-04);
   nenhum botão inerte, mas o e2e não cobre o upload contra a API real (só na bancada, 1 parte).
3. `Abrir em…` (mapa/tabela) mostra aviso de que o visualizador é de outra linha (L2-01); é informação, não ação.
   `/admin/categorias` (seção 15.5) NÃO foi construída neste turno: o painel mostra categorias, não as edita.
   Miniatura por job (`/miniatura/gerar`) sonda o item por 60 s; sem camada (L0-04) devolve `tipo_sem_gerador`.
4. `test_i18n_cru.py` (da trilha A) não percorre `/conteudo`; o `test_conteudo_sem_chave_crua` cobre isso, mas só
   roda quando o catálogo existir na URL. Chaves dinâmicas (`catalogo.acesso_${v}`) têm todos os valores do CHECK do
   banco no dicionário; um valor novo no banco apareceria cru (o e2e pega).
5. A vista tabela é própria (não `<plat-tabela>`), como a de Tarefas: precisa acrescentar linhas por cursor sem perder
   a seleção e ordenar pelo cabeçalho; o restante (lixeira, versões, links, itens incluídos) usa `<plat-tabela>`.
6. Chromium com `locale pt-BR` mostra `<input type=date>` como `mm/dd/yyyy` nas capturas (formato do navegador, não
   do produto).
7. Regra que custou um ciclo: `<plat-formulario>` apaga os filhos ao conectar (`render()`); não serve de contêiner.
8. **Convivência (aviso do gerente):** os scripts `smoke.py` e `medir.py` (playwright fora do pytest, contra a
   bancada) rodaram sem `flock` e invalidaram 3 rodadas de medição de outra trilha; os `pytest` estiveram sempre no
   `flock`. Regra a partir daqui: qualquer playwright, inclusive na bancada, dentro de
   `flock /home/dev/plataforma/laco/.pytest.lock …`.

## Pendências

- Testador (40): `make check` inteiro e `make medidas` na URL real. O arquivo `tests/medidas/L0-03-catalogo.json`
  **já existe na árvore, gerado por mim contra a URL real** (pagina_conteudo_ms 234,9 · primeira_pintura_conteudo_ms
  24 · soma_modulos_kb 229,6, em 2026-09-05T20:14Z) mas **não foi comitado**: pelo hábito do turno (commit 5fe53c0) a
  pasta `tests/medidas/` entra no commit do testador, e o meu escopo era `web/` e `tests/e2e/`. O portão de 1,5 s
  exige os 10 mil itens semeados (`tests/api/semear_catalogo.py`, do backend) — nenhuma dessas medidas o prova.
- Backend: confirmar `/api/uploads` (L0-04) e, até lá, a criação de item `arquivo` fica fora da tela por desenho.
- **Backend (registrado, não mexi): (a)** devolver o id do dono em `/api/itens/facetas` (`{"valor": <dono_id>,
  "rotulo": "<login>"}` ou campo `id`, como já é feito em `categoria`), senão o dono sem item na página some da
  faceta; **(b)** decidir o `status: "nenhum"` — ou a faceta deixa de contar o balde, ou `?status=nenhum` passa a
  significar `i.status IS NULL` (hoje a faceta conta 54 e o filtro devolve 0).
- `/admin/categorias` (L0-03-b) e "Uso" do item (log_acesso por item) ficam para o próximo turno da trilha.

## Para o próximo papel (testador, 40)

1. `flock /home/dev/plataforma/laco/.pytest.lock make check` e, com o catálogo publicado,
   `flock … env PLAT_GRAVAR_MEDIDAS=1 venv/bin/pytest tests/e2e/test_conteudo.py -m lento --base-url https://plat.iagrointel.com`.
   Esperado: 2 passed, 10 capturas `L0-03_*.png` novas, 0 erro de console (`Tela.verificar()`; o único 4xx declarado é
   o 404 do link revogado e do item apagado).
2. Roteiro à mão além do e2e: 10 mil itens → "Carregar mais" 200 vezes sem repetir/pular (cursor); seleção de 50 →
   mover (lote); filtros tipo+tag+data = `GET /api/itens` com os mesmos parâmetros (o chip mostra o que foi enviado);
   título de 2.048 caracteres (elipse, `title` inteiro); item sem miniatura (ícone do tipo, nenhum `<img>` quebrado);
   0 itens (estado vazio com o mesmo botão "Novo item"); teclado `/`, `j/k`, `x`, `Enter`, `Esc`; largura < 900 px.
3. Painel: editar em linha em cada campo, `Dados` com esquema inválido (422 ligado ao campo), `Configurações`
   (extent, proteção → DELETE 409 com instrução, status autoritativo só admin, miniatura JPEG → PNG 600×400, gerar
   por job em camada), `Versões` (diff, restaurar cria versão nova), `Compartilhamento` (grupo sem contribuição
   desabilitado com motivo; dependência com `pode_editar=false` desabilitada), transferência com falha prevista.
4. Se `ordem-de-exclusao`/`usado-por`/facetas vierem com forma diferente da medida hoje, o erro aparece no painel
   (`<plat-aviso>` de erro), nunca no console: é o sinal para me chamar de volta.
5. O e2e já rodou 2/2 contra `https://plat.iagrointel.com` (20:14 UTC, commit 03a73e0) com as 10 capturas e as três
   medidas gravadas; `tests/medidas/L0-03-catalogo.json` está na árvore **sem commit**, esperando o commit do
   testador. Refaça a rodada antes de gravar: outras trilhas semeiam e apagam itens no mesmo inquilino demo.
6. Ao clicar uma faceta, confira o parâmetro que sai (`dono_id` inteiro, `categoria` uuid) — foi exatamente aí que a
   tela mandava o rótulo e levava 422; o e2e agora cobre esse ida-e-volta, mas só com um dono e uma categoria.
7. Dois pontos que dependem do backend estão nas Pendências (id do dono na faceta e o `status: "nenhum"` que filtra
   0). Enquanto não forem decididos, o comportamento da tela é o descrito, não um defeito novo.

## Resumo em 8 linhas

1. Tela `/conteudo` completa em 17 módulos ES (`web/js/catalogo/`, soma carregada 227,4 kB ≤ 400; maior 30,3 kB ≤ 60) sobre a base existente; + `/c/<token>` anônima.
2. Lista/grade/tabela com cursor "Carregar mais", busca com sintaxe por campo validada no cliente e ajuda, facetas, pastas ≤ 5 níveis, seleção em massa ≤ 100 com resultado por item.
3. Painel do item com 6 abas: metadado em linha (`PATCH`), dados por JSON Schema (`PUT` + `versao_atual`), configurações (extent, proteção, status, pasta, dono, miniatura), versões com diff/restaurar/publicar, relações, compartilhamento (nível, grupos, dependências, links revogáveis).
4. Lixeira com restaurar/apagar agora/esvaziar por texto; favoritos; transferência com pré-checagem; criar item (upload retomável do ADR 0005 só com `/api/uploads` publicado, conexão, mapa, outro tipo, pasta).
5. `TELAS` ganhou `/conteudo`; `pt-BR.json` +364 chaves, 0 chave faltando; 0 marcador; sintaxe de todos os módulos OK.
6. e2e `test_conteudo.py` (fluxo completo + chave crua) passou 2/2 **contra a URL real** (`https://plat.iagrointel.com`, dentro do `flock`), com 10 capturas `L0-03_*.png` reescritas e 0 erro de console; medidas gravadas: primeira pintura 24 ms, página 234,9 ms, módulos 229,6 kB.
7. A API viva mostrou dois defeitos que a bancada não podia mostrar, ambos na volta da faceta para o filtro: dono vem como login e `?dono_id` exige inteiro (422); categoria vem como caminho e `?categoria` exige uuid (422). Corrigidos em `filtros.js` e cobertos por e2e — com o arquivo anterior o mesmo teste falha.
8. Fora deste turno: `/admin/categorias`, aba "Uso", upload contra a API real (L0-04) e duas decisões do backend (id do dono na faceta; `status: "nenhum"` conta 54 e filtra 0); commits 41c1dd9, a06ca71, 05a41cd e 03a73e0, só em `web/` e `tests/e2e/`.
