# ADR 20260908T1210 — site do inquilino: páginas públicas renderizadas no servidor

Item `L5-20-sites-paginas-publicas`. Depende de `L5-08-editor-arrasto` (o editor), `L5-05-documento-versoes`
(o envelope do documento e a versão publicada), `L5-14-publicacao-links-embed` (a vitrine anônima `/p/`,
reaproveitada pelos cartões que incorporam) e `L0-03-catalogo` (item, compartilhamento, busca).

## 1. O que muda

Um SITE é um item de tipo `site` (família nova `site`) cujo documento é o MESMO envelope de app/painel:
`corpo.nos`, lista plana, aninhamento por `pai`. Isso é o essencial da decisão: nenhum modelo de documento
novo, nenhum editor novo, nenhuma linguagem nova. A tela `/sites` monta o documento com `criarEditor()` do
L5-08 e a paleta `web/js/editor/paleta_site.js`; o servidor grava por `PATCH /api/itens/{id}` como qualquer
outro documento.

O que é próprio do site:

1. **Regras de montagem** (`app/catalogo/site.py::validar_documento`, 422 `site_invalido`): `pagina` só na
   raiz, `secao` dentro de página, cartão dentro de seção, `cabecalho`/`menu`/`rodape` na raiz (pertencem ao
   site inteiro), caminho de página único, no máximo uma página inicial, e a validação por cartão (imagem só
   do próprio servidor, incorporado só `https`, destino de botão interno ou `https`, texto obrigatório,
   texto alternativo obrigatório). JSON Schema não expressa nenhuma dessas: todas precisam olhar a lista
   inteira ou cruzar tipo de pai com tipo de filho.
2. **Publicação por inquilino**, não por item: `plat.site_publicado` tem `tenant_id` como chave primária, e a
   URL é `/s/<inquilino>/` (forma fixada em L5_CONCEITO D10). Publicar um segundo site no mesmo inquilino é
   `409 site_em_uso` — quem troca de site retira o anterior do ar primeiro. A alternativa (vários sites por
   inquilino, com slug) foi rejeitada porque a URL do D10 não tem lugar para o slug e mudar a forma da URL
   depois custa redirecionamento para sempre.
3. **Renderização no servidor** (`app/catalogo/site_render.py`): a página sai HTML completo; o `curl` lê o
   texto. Nenhum cartão depende de script — a galeria e a busca são formulários `GET` respondidos já
   filtrados pelo servidor, a estatística é contagem feita no pedido, o mapa e o aplicativo são `<iframe>`
   com link equivalente ao lado.

## 2. Por que não Jinja2

O L5_CONCEITO D24 sugeria Jinja2. Não foi usado: a casa já monta HTML no servidor com `html.escape` +
f-string (`app/catalogo/publicacao.py::exportacao_estatica`), o volume aqui é de nove cartões, e Jinja2 seria
dependência nova (escada do Ponytail: parar no degrau que resolve). O custo dessa escolha é conhecido e
aceito: quem escrever o décimo cartão escreve string em Python, não template. Se um dia a página do site
ganhar herança de layout e blocos, a troca é local — todo o HTML nasce em um módulo só.

O que ISSO obriga: todo texto vindo do documento passa por `html.escape`. Não existe caminho em que HTML
escrito pelo autor do site chegue interpretado ao visitante — o cartão de texto quebra parágrafo em linha
em branco e escapa o resto. Markdown (negrito, link) fica para o cartão de texto rico, com `markdown-it` +
DOMPurify, item de outra rodada.

## 3. O que a página anônima pode ler

A página do site não tem sessão. Toda leitura passa por função `SECURITY DEFINER` da migração
`20260908T1134_site_paginas_publicas.sql` (+ `20260908T1159_site_publicacao_slug.sql`), e todas filtram
`acesso = 'publico'` **e** `plat.tenant_permite_publico(tenant)` — a mesma dupla de
`plat.tenant_publico_itens`, que é a definição de "compartilhado com todos" nesta plataforma:

| função | serve a | devolve |
|---|---|---|
| `site_resolver(slug)` | achar o site do inquilino | item, versão publicada, `indexavel`, nome/cor/logotipo |
| `site_corpo(item, versao)` | ler a versão publicada (nunca o rascunho) | corpo do documento |
| `site_itens_publicos(tenant, tipos, busca, limite)` | galeria e busca | só item público |
| `site_estatisticas(tenant)` | cartão de números | contagem por família, só do que é público |
| `site_item_publico(tenant, item)` | cartão que cita item por uuid | zero linha se o item não é público |
| `site_publicacao_slug(tenant, item)` | `/p/<inquilino>/<slug>` do cartão de mapa | slug, só de item público publicado |

Consequência medida (`tests/api/catalogo/test_site.py`): o cartão que aponta para um item que deixou de ser
público não mostra o item — mostra que o conteúdo não está compartilhado com todos. O adversário procura o
item privado por tipo (filtro da galeria), por busca do título exato e pelo uuid: nenhuma das três o traz.

Por que função `SECURITY DEFINER` e não `contexto_anonimo`: o contexto anônimo do L0-03 abre uma lista
FECHADA de ids (é feito para link com token). A galeria não conhece os ids de antemão — ela é uma consulta.

## 4. Indexação: `noindex` por padrão

`site_publicado.indexavel` nasce falso. A página manda `X-Robots-Tag` e `<meta name="robots">` com
`noindex, nofollow`; com a opção ligada, `index, follow`. A tela `/sites` mostra o aviso ao lado da caixa —
ligar indexação é decisão consciente do dono do site, nunca herança silenciosa.

Isto obriga uma exceção no nginx (`deploy/nginx.conf`): o `add_header X-Robots-Tag "noindex, nofollow"
always` do bloco `server` ACRESCENTA (não substitui) e chegaria ao visitante junto do `index, follow` da
aplicação. Por isso `/s/` ganha um `location` próprio que repete os cabeçalhos de segurança MENOS o
`X-Robots-Tag` — nesse caminho quem decide é a aplicação, que é a única que sabe se o site é indexável.

## 5. Política de conteúdo da página pública

`default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-src 'self' <origens>;
base-uri 'none'; form-action 'self'`. As origens de `frame-src` são as dos cartões `incorporado` DAQUELA
página — uma página sem quadro externo não autoriza a origem que outra página usa. `X-Frame-Options: DENY`
continua valendo para `/s/` (site público não precisa ser emoldurado por terceiro; quem precisa é `/p/`).

## 6. Acessibilidade

A página nasce com marco semântico (`header`/`nav`/`main`/`footer`), atalho para o conteúdo, um `h1` por
página, `h2` por seção, `h3` por cartão, `alt` obrigatório em imagem, `title` obrigatório em quadro, rótulo
em todo campo de formulário e `aria-current` na página do menu. A cor da marca do inquilino entra só como
fundo, e a cor do texto sobre ela é escolhida NO SERVIDOR pelo contraste (WCAG 1.4.3,
`site_render.cor_do_texto`): um inquilino de cor clara não fica com texto branco sobre fundo claro.

Medida (`tests/medidas/L5-20-sites-paginas-publicas.json`): auditoria axe-core 4.12.1 — o motor que o
Lighthouse usa na categoria de acessibilidade — nas etiquetas WCAG 2.0/2.1 A e AA, ponderada por impacto,
= 100 de 100, 0 violação `critical`/`serious`. **Não é o binário do Lighthouse**: ele não está instalado
nesta máquina e instalá-lo seria dependência npm nova com o disco a 98 %. A medida diz isso no campo
`comando`, e o handoff registra a cláusula como cumprida por equivalência declarada, não por identidade.
