# ADR — limite de taxa em três camadas (item L7-03-b-rate-limit-abuso)

Data: 2026-09-07. Trilha `il703bratel`, worktree `/home/dev/plataforma/wt/il703bratel`.

## Contexto

O item pede defesa contra abuso de volume em três camadas independentes — nginx por IP, API por
inquilino/plano, fail2ban sobre 401/429 repetidos — mais uma cláusula herdada do item L7-03 (auth):
a restrição por IP não pode confiar em `X-Forwarded-For` forjado. `L0-02-tenant-auth` está `parcial`
(P3 do laço inteiro pendente, não deste item) e `L1-02-tiles-token` está `entregue` mas **não
mesclado** nesta base (ramos `wt/tiles`/`wt/tilestok`, ver `laco/handoffs/T4/L1-02-tiles-token.md`) —
`app/imagens/` não existe neste worktree.

## Decisão 1 — camada 2 em Postgres, com janela DESLIZANTE (não fixa), reusando o desenho de
`plat.redefinicao_solicitar` (migração 047)

Uma linha por pedido em `plat.limite_taxa_pedido` (chave, escopo, criado_em) e `COUNT(*)` sobre os
últimos N segundos, dentro de `plat.limite_taxa_verificar` (SECURITY DEFINER, migração
`20260907T1444_limite_taxa.sql`). Alternativas descartadas:

- **Memória do processo**: `plat-api` sobe com `--workers 2` (`deploy/plat-api.service`); um
  atacante distribuído entre os dois workers dobraria a cota de graça, e a hipótese do item já
  deixava isso em aberto ("Postgres OU memória por worker").
- **Janela FIXA** (bucket por minuto-relógio): permite rajada dobrada na borda do minuto (N no
  segundo 59 + N no segundo 1 do minuto seguinte = 2N em 2 s). A deslizante não tem esse buraco.
- **Redis/outro serviço**: nada disso roda nesta máquina hoje: subir um novo daemon para um contador
  que o Postgres já resolve, com um padrão já testado no próprio repositório, não se paga.

Custo aceito: uma consulta extra por requisição autenticada (medido — ver §9.4 do
`docs/SEGURANCA.md`) e uma tabela que cresce; a faxina oportunista (1 em 200 chamadas apaga linhas
com mais de 1 dia) evita um job periódico novo.

**Correção pós-adversário (mesma passagem, antes de marcar o item):** a 1ª versão desta função
afirmava, no próprio comentário, que fazer o `SELECT count()` e o `INSERT` "dentro da mesma
transação curta" bastava para nunca abrir corrida — **errado**. Sob `READ COMMITTED` (padrão do
Postgres), duas transações concorrentes fazem o MESMO `SELECT count()` (nenhuma enxerga o `INSERT`
da outra até o commit dela) e as duas passam pelo `IF n >= p_max`. O adversário do turno mediu isso
de verdade: pool de 2 conexões furou um teto de 20 para 21 em 2 de 3 rodadas; pool de 8 furou para
23 em 1 de 5. Conserto: `pg_advisory_xact_lock(hashtextextended(chave || '|' || escopo, 0))` logo no
início da função — trava transacional (liberada sozinha no fim da transação, a mesma transação curta
de `with db.db()`) só para a MESMA `(chave, escopo)`; chaves diferentes nunca se bloqueiam entre si.
Reproduzido depois do conserto: `tests/api/test_limite_taxa.py::
test_concorrencia_real_nunca_fura_o_teto` — 5 rodadas de 200 chamadas verdadeiramente concorrentes
(thread pool) contra o mesmo par `(chave, escopo)`, teto sempre EXATAMENTE respeitado nas 5.

## Decisão 2 — a chave é o INQUILINO (`tenant:<id>`), nunca o IP

A hipótese do item fala em "API por token/inquilino"; a chave escolhida foi `tenant:<id>` (o plano
pertence ao inquilino, não a um token isolado — um token comprometido não deveria por si só definir
o teto de todo o resto do inquilino, mas fatiar por token também deixaria a refutação "1 IP com 50
tokens" indefesa na camada 2, e ELA JÁ TEM DEFESA: é a camada 1, por IP). Efeito nas duas metades da
refutação do item:

- **50 IPs contra o mesmo token**: todos caem na MESMA `chave` — o teto aparece exatamente onde
  apareceria sem forjar IP nenhum. Provado em `tests/api/test_limite_taxa.py::
  test_50_ips_forjados_contra_o_mesmo_token_a_camada_de_inquilino_segura` (o cabeçalho
  `X-Forwarded-For` rotaciona a cada pedido e não devolve cota nenhuma).
- **1 IP contra 50 tokens (de 50 inquilinos)**: cada inquilino tem SUA cota — a camada 2 não segura
  isso sozinha, e não deveria: é o desenho, não um buraco. Quem segura é a camada 1 (nginx por IP,
  `zone=plat_api`), que não sabe o que é um token e por isso não pode ser contornada criando mais
  tokens. Provado por fora do pytest, com nginx real — `scripts/bench_limite_taxa.sh` (abaixo).

## Decisão 3 — X-Forwarded-For: nada de novo em Python, o que já existe já resolve

`deploy/plat-api.service` já sobe o uvicorn com `--proxy-headers --forwarded-allow-ips 127.0.0.1`
(de um item anterior — não tocado aqui). Isso faz o `ProxyHeadersMiddleware` do uvicorn só confiar
no cabeçalho `X-Forwarded-For` quando o PEER TCP imediato é `127.0.0.1` (o nginx local); de qualquer
outro peer, o valor do cabeçalho é ignorado e `request.client.host` fica com o endereço real do
socket. `app/auth/sessao.py::ip_de()` já lê só `request.client.host` — nunca um cabeçalho — então
todo código que já usava `ip_de()` (restrição de token por IP, bloqueio de login, log de acesso)
já herda a defesa sem mudança nenhuma. O item aqui **prova** isso (não inventa mecanismo novo):

1. `scripts/bench_limite_taxa.sh` sobe a API real com a mesma flag do systemd e manda, direto na
   porta do uvicorn (sem nginx no meio), um `X-Forwarded-For` forjado; como o peer é `127.0.0.1`
   MESMO sem passar pelo nginx (o teste roda local), a única forma de isolar "peer não confiável" de
   "peer confiável" sem mentir para si mesmo é usar um endereço de loopback DIFERENTE de
   `127.0.0.1` como "atacante" (`127.0.0.9` — todo o bloco `127.0.0.0/8` é loopback no Linux, então
   `curl --interface 127.0.0.9` funciona sem configurar nada, e nenhum outro serviço da casa depende
   desse endereço específico: um teste que efetivamente bane esse IP não pode quebrar nada real).
2. Camada 1 (nginx `limit_req`) usa `$binary_remote_addr`, nunca um cabeçalho — não há trust a
   configurar ali; é seguro por padrão contra XFF forjado (só ficaria vulnerável com
   `ngx_http_realip_module` + `set_real_ip_from` apontando para uma faixa que inclua o atacante, o
   que este vhost não declara).
3. Camada 3 (fail2ban) lê `$remote_addr` do log combined do nginx — mesma garantia do item 2.

## Decisão 4 — fail2ban: arquivo dedicado, nunca o journal nem o log compartilhado da casa

`jail.d/nginx-limit.conf` (já na máquina, de outro produto) roda com `backend = systemd` e
`journalmatch = _SYSTEMD_UNIT=nginx.service + _COMM=nginx` — leria todo o nginx da casa, de todo
produto, se eu reaproveitasse aquele desenho. A jail `plat` (`deploy/fail2ban/jail.d/plat.conf`) usa
`backend = auto` (arquivo) sobre um `access_log` DEDICADO do vhost do plat
(`/var/log/nginx/plat_access.log`, `deploy/nginx.conf`) — nunca o `access.log` genérico da máquina,
compartilhado com outros produtos, e nunca o log de outro produto. `banaction` herdado do `[DEFAULT]`
da casa (`nftables`) — mesma ação que `sshd`/`nginx-limit-req` já usam, nada novo para auditar.

## Decisão 5 — nginx: `location /api/` e `location /tiles/` novas, camada 1

`deploy/nginx.conf` ganhou duas `location` novas com `limit_req` (zonas `plat_api`/`plat_tiles`,
`install.sh` grava as zonas em `plat_limites.conf`, mesmo padrão do `plat_login` já existente do
L0-02). `/tiles/` já é citado no vhost de PRODUÇÃO hoje (visto ao ler
`/etc/nginx/sites-enabled/plat.iagrointel.com`), mas o TEMPLATE deste repositório (`deploy/nginx.conf`)
não tinha essa `location` — ela chegou por fora, provavelmente por um `install.sh` de um ramo
ainda não mesclado (`wt/tilestok`, ver `laco/handoffs/T4/L1-02-tiles-token.md`, que também mexe em
`deploy/nginx.conf`/`install.sh` para o cache do ladrilho). Esta trilha acrescenta a `location`
básica com `limit_req` ao TEMPLATE (para que a fiação exista quando os dois ramos se juntarem) sem
tentar reproduzir o `proxy_cache`/`auth_request` daquele item — isso pertence ao L1-02, não a este.
`limit_req` roda ANTES de qualquer `proxy_cache` que a rota venha a declarar (fases distintas do
nginx): uma rajada acima do limite nunca chega ao `proxy_pass`, logo nunca invalida nem escreve
cache — provado com um backend real desta trilha em `docs/SEGURANCA.md §9.3`.

## O que ficou de fora (nomeado)

- **"Tile acima do limite do plano" fim a fim por HTTP**: não há rota de ladrilho nesta base
  (`L1-02-tiles-token` não mesclado). O MECANISMO da camada 2 é genérico por escopo (`api`/`tiles`)
  e testado unitariamente com o escopo `tiles` (`tests/api/test_limite_taxa.py::
  test_escopos_diferentes_da_mesma_chave_sao_contadores_independentes`), mas nenhum teste bate numa
  URL `/tiles/...` ou `/svc/.../raster` de verdade, porque essa rota não existe para bater. Registrado
  como cláusula **pendente**, não fingida — ver `marcar_item.py` no fim do turno.
- **`banaction` real contra um atacante de verdade**: por segurança operacional desta máquina
  compartilhada, o teste usa `127.0.0.9` (loopback, nunca usado por nenhum outro serviço) como
  "atacante" em vez de um IP de produção — ver Decisão 3, item 1. O jail instalado em produção usa
  a ação real (`nftables`, herdada do `[DEFAULT]`), sem dry-run: só o TESTE evita o endereço real.
- **Limite diferenciado por PLANO nomeado** (Bronze/Prata/Ouro, item L7-09-b): o mecanismo já lê
  `tenant.config.limites.*`; a UI/rotina que traduz "plano X" para esses números é do L7-09-b, fora
  de escopo aqui (o portão deste item fala em "limite do plano", não em nomear planos).

## Fontes

- RFC 6585 (429 Too Many Requests, `Retry-After`).
- Documentação do nginx: `ngx_http_limit_req_module`, `ngx_http_realip_module` (não usado — decisão 3).
- `man fail2ban-jail.conf` / `man fail2ban-regex` (instalados nesta máquina).
- `laco/handoffs/T4/L1-02-tiles-token.md` (o que a trilha vizinha já construiu e ainda não mesclou).
