# ADR — PWA de campo (`/campo/`): shell servido pela própria API, nunca por `/static/`

Estado: aceito (item L2-07-a-pwa-instalavel-cache, turno T3, setembro de 2026). Nome de arquivo por
carimbo de tempo (mesma regra do ADR 0014, já estendida a ADR pelo adendo de 06/09 — dois números `0018`
colidiram no mesmo minuto).

## 1. Contexto

O ADR 0001 seção 4.3 é explícito: o nginx serve `web/` em `/static/` direto do disco; a API
DELIBERADAMENTE não monta `StaticFiles` (ver `handoffs/T1/20_arquitetura.md` linha 265, "NÃO montar
StaticFiles em /static"). Isso funciona em produção e em homologação, onde sempre há um nginx na frente.
Não existe nginx por trilha isolada (`laco/trilha_ambiente.sh` só sobe o schema/DSN; `PLAT_URL_PUBLICA`
da trilha é um domínio `.invalido` que não resolve). Toda página HTML do repositório (`/mapa`, `/entrar`
etc.) referencia `/static/js/...`, `/static/vendor/...`; sem nginx, essas páginas carregam o HTML mas o
JS/CSS 404, e a tela nunca marca `data-pronto`. Confirmado rodando `tests/e2e/test_login.py` puro contra
`uvicorn` sem nginx: timeout esperando `body[data-pronto='1']`.

## 2. Decisão

O shell do PWA de campo (`index.html`, `campo.css`, `app.js`, `idb.js`, os dois ícones, o
`manifest.webmanifest` e o `sw.js`) é servido por rotas PRÓPRIAS em `app/campo/rotas.py`, sob o
prefixo `/campo/*` — nunca em `/static/campo/`. Consequência: o item inteiro (manifest, ícone,
service worker, offline) é testável com só `venv/bin/python -m uvicorn app.main:app --port <porta>`,
sem depender de nenhum nginx, em qualquer trilha isolada. Em produção o nginx pode continuar
proxeando essas rotas para a API sem mudança nenhuma (elas já respondem pela API hoje).

Isso NÃO reabre a discussão do ADR 0001: o resto do produto (telas administrativas, `/mapa`, vendor,
i18n) continua 100% em `/static/`, sem StaticFiles. É uma exceção pontual, documentada, só para os
arquivos que o item `L2-07-a` precisa servir para ser testável fora de um domínio com nginx.

## 3. Cache do shell: versão por arquivo, não por git sha

`web/campo/VERSAO_SHELL` guarda só a versão do shell (uma linha). `app/campo/rotas.py::versao_shell()`
lê esse arquivo A CADA resposta (sem cache em processo) — trocar a versão não exige reiniciar o
servidor nem fazer um commit. `campo/sw.js` embute essa versão no nome do cache
(`campo-shell-<versão>`); o `activate` apaga qualquer cache `campo-shell-*` que não seja o atual.
Usar o git sha do repositório inteiro (`app/versao.py::git_sha_curto`) foi descartado: (a) muda a cada
commit de QUALQUER item, não só do shell de campo, invalidando o cache por nada; (b) quebra em
worktree sem `PLAT_GIT_SHA` no ambiente (achado nesta mesma sessão: `.git` de um worktree é um
arquivo-ponteiro, não uma pasta, e `_sha_do_git()` não sabe seguir `gitdir: <caminho>` — `git_sha()`
levanta `RuntimeError` sem a variável).

## 4. Token de campo reaproveita o token de serviço genérico (L0-02-d)

`POST /api/campo/sessao` não cria tabela nova: insere em `plat.token_servico` com escopo fixo
`campo:usar` (já reservado no vocabulário de `app/auth/escopos.py`) e `CAMPO_TOKEN_DIAS=30`, sem
escolha do chamador — é só uma emissão de conveniência sobre a mesma infraestrutura de
`POST /api/tokens`. Revogação, expiração e o código de erro (`token_revogado`/`token_expirado`) são os
mesmos de qualquer token de serviço; `GET /api/campo/mapas` some quando o inquilino do escopo não bate
(RLS de `plat.item`), então dois inquilinos no mesmo navegador nunca compartilham dado — desde que o
app confira a sessão ativa contra o `tenant_slug` salvo localmente antes de reusar um token do
IndexedDB (ver `web/campo/app.js::obterSessaoAtual`; sem essa checagem, IndexedDB é isolado por ORIGEM,
não por inquilino, e um logout+login de outro inquilino no mesmo navegador reaproveitava o token
velho — achado e corrigido durante o teste de isolamento).

## 5. `credentials: 'omit'` na chamada autenticada por token

`app/auth/sessao.py::resolver` rejeita com 400 `autenticacao_ambigua` uma requisição que chega com
cookie de sessão E cabeçalho `Authorization` ao mesmo tempo (defesa contra confused-deputy). Como o
PWA de campo roda na MESMA origem da app principal, um `fetch()` teria o cookie anexado por padrão
mesmo enviando o `Authorization: Bearer`. `sincronizarMapas()` usa `credentials: 'omit'` de propósito:
o campo fala SEMPRE pelo token, nunca pelo cookie, mesmo quando o mesmo navegador também tem uma
sessão da app principal aberta.
