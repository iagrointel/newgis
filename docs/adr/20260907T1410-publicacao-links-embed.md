# ADR 20260907T1410 — publicação de documento de construtor (links e embed)

Item `L5-14-publicacao-links-embed`. Depende de `L5-05-documento-versoes` (grafo versionado, `versao_publicada`)
e `L1-02-tiles-token` (token de serviço escopado por camada, `restricao.referer`).

## 1. O que muda

Publicar um documento de construtor (`app`/`painel`) passa a significar três coisas ao mesmo tempo, numa
única chamada (`POST /api/itens/{id}/publicacao`):

1. Apontar `plat.item.versao_publicada` para a versão escolhida (mecanismo que já existia em
   `POST /api/itens/{id}/versoes/{n}/publicar` — aqui reaproveitado, não duplicado).
2. Reservar uma URL fixa `/p/<inquilino>/<slug>` (tabela nova `plat.item_publicacao`).
3. Emitir um token de serviço PRÓPRIO da publicação (`plat.token_servico`, mesma tabela do L0-02/L1-02),
   com escopo calculado automaticamente = as camadas citadas pelo documento (fecho de
   `plat.item_relacao` até a família `camada`, `app/catalogo/publicacao.py::camadas_citadas`), e com
   `restricao.referer` = a lista de domínios de incorporação escolhida pelo publicador.

Nenhum mecanismo de autorização novo nasce aqui: tudo é composição do que já existe (RLS +
`plat.pode_editar`, `plat.compartilhamento_link`/`link_resolver` para acesso anônimo, `token_servico` +
`escopos`/`restricao` para escopo de dado). O item novo é a ORQUESTRAÇÃO — calcular o escopo certo e gravar
a URL — não uma segunda forma de autenticar.

## 2. Acesso à página `/p/`

- `item.acesso = 'publico'` (e o inquilino permite): aberto para qualquer visitante.
- Qualquer outro `acesso`: exige `?link=<token>` de um `plat.compartilhamento_link` já existente do item
  (o mesmo link que abre `/c/<token>` hoje) — não um segundo tipo de link. Sessão de inquilino autenticada
  para ver `/p/` fica FORA do escopo desta rodada (a navegação autenticada já usa os endpoints normais do
  item; `/p/` é a vitrine anônima). Ver "o que ficou de fora" no handoff do turno.

## 3. Por que o token da publicação guarda o VALOR em texto, não só o hash

Todo outro token de serviço da casa guarda só `sha256(valor)` — o valor é um segredo que só o dono viu uma
vez. O token da publicação é diferente por natureza: ele PRECISA estar no HTML/JS servido a qualquer
visitante anônimo da página pública para que o navegador dele chame `/api/camadas/...`/`/api/tiles/...`.
Não há como "esconder" esse valor do visitante — ele É o cliente. A propriedade que protege não é o sigilo
do valor (como uma chave publicável de gateway de pagamento), é:

- **escopo**: só as camadas citadas pelo documento, nunca `admin:inquilino` nem `camada:editar`;
- **restrição de domínio**: `restricao.referer` fecha o token à lista de domínios do app (a mesma checagem
  de `Origin`/`Referer` de `app/auth/sessao.py::_checar_restricao`, sem código novo);
- **revogação**: republicar gera um token NOVO e revoga o antigo na mesma transação; despublicar revoga.

`item_publicacao.token_valor` fica em texto exatamente PORQUE ele não é mais secreto do que o próprio HTML
público que o contém — continuar hasheando essa cópia não protegeria nada e impediria a página de
funcionar (não dá para reconstituir o valor a partir do hash para servir de novo a cada visita).

## 4. Cabeçalho de iframe: exceção por rota, não regra global

O item pede que `/p/` funcione embutido só nos domínios da lista do app. Isso é `Content-Security-Policy:
frame-ancestors 'self' <dominios>`, calculado por app e enviado SÓ pela rota `GET /p/{inquilino}/{slug}`
(`app/catalogo/rotas_publicacao.py::pagina_publicada`). Isto não depende nem colide com um cabeçalho
`X-Frame-Options`/CSP GLOBAL que outro item da casa (L7-03-e-cabecalhos-csp-tls) venha a instalar no
middleware para o resto da API — quando esse item chegar, a exceção correta é a MESMA rota escapar do
padrão geral (`frame-ancestors` explícito nesta resposta prevalece sobre `X-Frame-Options` herdado, e os
navegadores modernos ignoram `X-Frame-Options` quando `frame-ancestors` está presente).

## 5. Exportação estática

`GET /api/itens/{id}/publicacao/exportacao` devolve um HTML autocontido (sem `<script src>` externo, sem
`fetch`): título, grafo de nós/ligações e metadado das camadas citadas (nome, tipo, acesso) embutidos como
`<script type="application/json">`. Abre de `file://` com o MESMO conteúdo por construção (não há chamada
de rede para falhar). Não inclui geometria/feição — a exportação é do DOCUMENTO (o que o construtor
desenhou), não um espelho do banco geográfico; isso fica dito no próprio HTML exportado.

## 6a. Achado de ambiente (não deste item, mas custou tempo real): e2e de trilha precisa de nginx próprio

`venv/bin/python -m uvicorn app.main:app --port 8266` sozinho NÃO serve `/static/*` (a app nunca serviu
estático — comentário em `app/main.py`; só o L7-31/homologação lembra disso em `docs/HOMOLOGACAO.md`). Um
e2e de trilha que aponte `--base-url http://127.0.0.1:8266` direto ao uvicorn carrega a casca HTML mas
`/static/js/...` volta `404` e a tela fica muda — não é erro de aplicação, é ausência de proxy. Contorno
usado aqui: um nginx efêmero (`worker_processes 1`, `pid` e config em `/tmp`, sem tocar `/etc/nginx`)
escutando **outra porta** (8267), `location /static/ { alias .../web/; }` e `location / { proxy_pass
http://127.0.0.1:8266; }` — mesmo desenho de `deploy/nginx_homolog.conf`, sem os cabeçalhos de segurança
(irrelevante para o teste). `--base-url http://127.0.0.1:8267` no pytest. Vale para qualquer item que
precise de e2e numa trilha sem subir o `make homolog` inteiro.

## 6. O que ficou fora desta rodada (honesto)

- Geração de miniatura por captura headless (Chromium) no publish: a hipótese menciona, o portão de
  pronto NÃO exige (nenhuma cláusula fala de miniatura/tempo de captura). O item já tem miniatura própria
  (`app/catalogo/miniatura.py`) e não foi tocado.
- Acesso a `/p/` por sessão de inquilino/grupo autenticado (só público e link-com-token nesta rodada).
- Exportação "para o hub e para o appliance" (distribuição do pacote estático) — o endpoint devolve o
  arquivo; automatizar o envio para outro sistema é integração de outro item.
