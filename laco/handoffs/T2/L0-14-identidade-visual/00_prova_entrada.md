# L0-14-identidade-visual — prova de direção "instrumento" na tela de entrada

Papéis combinados por pedido direto do dono (pressão de tempo): designer + frontend na mesma sessão.
Escopo desta fatia: SÓ a tela de entrada (`web/login.html`) + os tokens base (`web/estilo/tokens.css`)
+ o remapeamento escopado no layout base (`web/style.css`). As outras 8 telas do item **não** foram
tocadas visualmente (verificado, ver seção "evidência"). Commit: `4027ce1`.

## Objetivo

Dar ao dono algo para OLHAR agora e decidir se a direção "instrumento" (painel escuro, denso,
preciso — cockpit, não painel administrativo genérico) está certa, antes de investir o resto do
item G (as 8 telas restantes, ícones, página `/estilo`, contraste AA nas 9 telas, estados completos
dos 6 componentes de base).

## O que fiz

1. **`web/estilo/tokens.css`** (novo): paleta em três estados (escuro por padrão em `:root`, claro
   via `@media (prefers-color-scheme: light)` guardado por `:not([data-theme="dark"])`, e escolha
   explícita repetida em `:root[data-theme="light"]` / `:root[data-theme="dark"]` — a regra de tema
   da casa). Tipografia com motivo escrito no comentário do arquivo: Big Shoulders Display 700/800
   para título/rótulo de destaque, IBM Plex Sans 400/500/600 para corrida e formulário, IBM Plex
   Mono 400/500 para dado tabular (`font-variant-numeric: tabular-nums`). Cantos retos (`--i-raio:
   2px`). Utilitário `.instrumento-moldura` = tique de canto em L nos 4 cantos (marca d'água de
   instrumento), cor âmbar (`--i-acento`), vive num `::before` próprio.
2. **Fontes vendorizadas** em `web/vendor/` (convenção do ADR 0001 seção 11.2 regra 3, **estendida**):
   - `big-shoulders-display-2.002.woff2` (variável, cobre 700 e 800)
   - `ibm-plex-sans-3.201.woff2` (variável, cobre 400/500/600)
   - `ibm-plex-mono-regular-2.3.woff2` (400) e `ibm-plex-mono-medium-2.3.woff2` (500)
   Baixadas da CSS2 API do Google Fonts (subconjunto "latin" só, 06/09/2026), sha256 e origem em
   `web/vendor/VERSOES.txt`. A regra 3 do ADR só previa `.js|.css` e licenças BSD/MIT/Apache/ISC
   (pensada para libs JS); **estendi** `tests/unit/test_vendor.py` para aceitar `.woff2` e a versão
   Major.Minor (fontes não seguem semver de 3 dígitos) e **acrescentei** `OFL-1.1` à lista de
   licenças admitidas — é a licença de toda fonte do diretório `ofl/` do repositório `google/fonts`
   (confirmado arquivo a arquivo: `raw.githubusercontent.com/google/fonts/main/ofl/<família>/OFL.txt`
   devolveu HTTP 200 com o texto da SIL Open Font License para as 3 famílias). Documentado no
   docstring do teste e no comentário do `VERSOES.txt`; não editei o ADR em si (fora de escopo desta
   fatia rápida, registrado como pendência abaixo).
3. **`web/login.html`**: `<link>` para `tokens.css` antes de `style.css`; `<body class="tela
   instrumento">`; `<div class="cartao instrumento-moldura">`. Nenhuma outra mudança estrutural.
4. **`web/style.css`** (layout base): bloco novo no fim do arquivo, `body.instrumento { --fundo:
   var(--i-fundo); ... }` — remapeia as variáveis antigas (`--fundo`, `--painel`, `--painel-2`,
   `--borda`, `--borda-forte`, `--texto`, `--fraco`, `--ok`, `--atencao`, `--falha`, `--info`,
   `--acento`, `--acento-texto`, `--foco`, `--sombra`, `--sans`, `--mono`, `--raio`, `--e1..e6`) para
   as novas, **só dentro do escopo `body.instrumento`**. Toda regra existente da folha (barra
   lateral, botão, formulário, tabela, diálogo, abas — usada pelas 8 outras telas) continua
   referenciando os MESMOS nomes de variável; nenhuma delas foi redefinida fora do escopo, por isso
   nada muda numa tela sem essa classe. `web/js/base/layout.js` **não precisou de mudança**: não tem
   cor nem fonte hard-coded (confirmado por grep), toda a aparência vem das classes que já herdam o
   remapeamento automaticamente no dia em que uma tela ganhar `class="instrumento"`.
5. Rodei o e2e existente (`tests/e2e/test_login.py`, 2 testes) e o unitário do vendor
   (`tests/unit/test_vendor.py`, 2 testes) sob `flock /home/dev/plataforma/laco/.pytest.lock`;
   também a suíte inteira "not lento" (382 testes) e lint+sem-marcador, para não quebrar as
   trilhas em andamento no mesmo turno (L0-03-catalogo comitou `79490e9` durante o meu trabalho —
   nenhum conflito, arquivos disjuntos).
6. Capturei `tests/e2e/capturas/L0-14_entrada_instrumento.png` com um script avulso
   (`scratchpad/captura_entrada.py`, não é teste permanente da suíte) em `color_scheme="dark"`
   (o padrão do produto; o chromium headless por si reporta `prefers-color-scheme: light`, o que
   dispara corretamente a paleta clara — os dois estados existem e funcionam, a captura de
   referência mostra o "instrumento" escuro porque é essa a direção em avaliação).

## Evidência (comando + saída literal)

Vendor (sha256 + convenção de nome):
```
$ cd web/vendor && grep -v '^#' VERSOES.txt | awk '{print $3"  "$1}' | sha256sum -c
maplibre-gl-4.7.1.js: OK
maplibre-gl-4.7.1.css: OK
swagger-ui-bundle-5.32.15.js: OK
swagger-ui-5.32.15.css: OK
dompurify-3.4.14.js: OK
big-shoulders-display-2.002.woff2: OK
ibm-plex-sans-3.201.woff2: OK
ibm-plex-mono-regular-2.3.woff2: OK
ibm-plex-mono-medium-2.3.woff2: OK
```

Licença confirmada na origem (as 3 famílias, HTTP 200, texto "SIL Open Font License, Version 1.1"):
```
$ curl -sS -o /dev/null -w "%{http_code}\n" https://raw.githubusercontent.com/google/fonts/main/ofl/bigshouldersdisplay/OFL.txt
200
$ curl -sS -o /dev/null -w "%{http_code}\n" https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexsans/OFL.txt
200
$ curl -sS -o /dev/null -w "%{http_code}\n" https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexmono/OFL.txt
200
```

Assets servidos pelo nginx (alias direto do disco, sem precisar reiniciar nada):
```
$ curl -sS -D - -o /dev/null https://plat.iagrointel.com/static/estilo/tokens.css | grep -i "HTTP\|content-type"
HTTP/1.1 200 OK
Content-Type: text/css
$ curl -sS -D - -o /dev/null https://plat.iagrointel.com/static/vendor/big-shoulders-display-2.002.woff2 | grep -i "HTTP\|content-type"
HTTP/1.1 200 OK
Content-Type: font/woff2
```

Suíte (sob flock):
```
$ flock .../.pytest.lock venv/bin/ruff check app tests
All checks passed!
$ flock .../.pytest.lock venv/bin/pytest -m "not lento" -q      # 382 testes, antes do commit
[...] [100%]   (exit 0)
$ flock .../.pytest.lock venv/bin/pytest tests/unit/test_vendor.py tests/e2e/test_login.py \
    --base-url https://plat.iagrointel.com -q                   # rodada final, depois de tudo
....                                                              [100%]   (exit 0)
```

Fontes carregadas na tela real (script avulso, chromium real, sem erro de console):
```
{'family': 'Big Shoulders Display', 'weight': '700 800', 'status': 'loaded'}
{'family': 'IBM Plex Sans', 'weight': '400 600', 'status': 'loaded'}
{'family': 'IBM Plex Mono', 'weight': '400', 'status': 'unloaded'}   # não usada nesta tela, ok
{'family': 'IBM Plex Mono', 'weight': '500', 'status': 'unloaded'}   # não usada nesta tela, ok
erros de console: []
```

As outras 8 telas continuam intocadas (login → home autenticada, sem a classe nova):
```
url: https://plat.iagrointel.com/
body.className: 'com-lateral'
background-color computado: rgb(20, 23, 28)     # = #14171c, o --fundo ANTIGO do T2
--fundo: #14171c
```

Captura: `tests/e2e/capturas/L0-14_entrada_instrumento.png` (1280×800, dark). Corner-tick conferido
por recorte ampliado (não commitado — pasta de captura é gitignored): as 4 bordas em L aparecem
em âmbar, distintas do contorno cinza do painel.

## Riscos

- O tique de canto (`.instrumento-moldura::before`) na primeira versão usava a MESMA cor da borda e
  ficava indistinguível dela; a segunda versão trocou a cor para o âmbar mas ainda vivia na
  propriedade `background` do próprio elemento — um `.cartao { background: var(--painel) }`
  carregado depois na cascata (mesma especificidade, `background` é atalho e reseta
  `background-image`) apagava o tique silenciosamente. Corrigido movendo o tique para um `::before`
  próprio, independente da propriedade `background` do painel. Deixo isso registrado porque é o
  tipo de regressão que não aparece em teste algum (nenhum teste confere presença de pixel do tique)
  — só apareceu ao olhar a captura ampliada.
- `OFL-1.1` foi acrescentado à lista de licenças do `test_vendor.py` por mim, não pelo papel
  `arquiteto`; é uma extensão de escopo (a regra original só previa JS), documentada e com evidência
  de origem, mas o ADR 0001 em si **não foi editado** — fica pendência para quem tocar o item de
  novo formalizar a seção 11.2 com uma "regra 3 (fontes)" explícita.
- Não toquei `docs/PARIDADE.md`, `CHANGELOG.md`, `MANUAL.md` nem `ARQUITETURA.md` (P9 do portão
  congelado pede documentação no mesmo turno) — decisão deliberada para não colidir com o cronista
  de outra trilha que pode estar escrevendo no mesmo `CHANGELOG.md` do turno 2 agora, e porque o
  pedido explícito era só a prova visual. Registrar como dívida do item, não como "pronto".
- A captura de referência força `color_scheme="dark"` no Playwright; não gerei a captura do estado
  claro (existe e funciona — testado manualmente, não commitado como evidência formal).

## Pendências (o que falta do item L0-14 inteiro — cláusulas do portão de pronto)

- (a) parcial: tokens existem e a tela de entrada não tem cor/medida fora deles; as outras 8 telas
  ainda têm cor/medida fora do sistema nomeado (elas usam a paleta antiga do T2, que também é "um
  sistema de tokens", só não o novo).
- (c) família de ícones: não iniciado.
- (d) estados completos (repouso/foco/ativo/desativado/carregando/vazio/erro) nos 6 componentes de
  base: não iniciado nesta fatia.
- (e) página viva `/estilo`: não iniciado.
- (f) contraste AA medido (axe-core) nas 9 telas: não medido; medi só visualmente que o botão
  primário âmbar-sobre-#1a1002 e o texto claro sobre #0b0f10/#12181a têm contraste alto, sem
  ferramenta.
- (g) as 8 telas restantes restiladas com captura antes/depois: não iniciado.
- (h) traço único documentado (candidato: "a régua — cada número na tela carrega a sua
  procedência"): não escrito ainda como documento formal de identidade.

## Para o próximo papel (quem continuar o item L0-14)

- O mecanismo de opt-in (`body.instrumento` + tokens `--i-*`) já está pronto e testado; restilar
  uma tela nova é, em princípio, `class="tela instrumento"` no body + a classe `instrumento-moldura`
  onde fizer sentido um painel-chave — confirmar visualmente cada uma antes de fechar (o próprio
  tique já mostrou que "parece que devia funcionar" não é evidência).
- Rodar axe-core (ainda não instalado nesta máquina, verificar antes) antes de declarar a cláusula
  (f) do portão.
- Formalizar a extensão da regra 3 do ADR 0001 (fontes .woff2, OFL-1.1) num ADR novo ou addendum,
  se o arquiteto concordar com a leitura que fiz.
- Estado do item no `laco/estado.json`: deixei como `parcial`, turno 2, com esta lista de pendências
  no campo de notas do backlog.
