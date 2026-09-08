# Handoff — item L6-02-a-modelo-conexao-e-seguranca (arquiteto + backend, passagem única)

**Objetivo.** Modelo genérico de CONEXÃO externa (WMS/WMTS/WFS/OGC API/ArcGIS REST/STAC/GeoParquet/
PMTiles/postgres_fdw/s3/http — só o MODELO e a defesa de segurança; os 15 conectores concretos são
itens futuros): `plat.conexao` (tenant_id+RLS, tipo, URL, credenciais cifradas, modo referenciada/
copiada), validador de URL contra SSRF, teste de saúde (`POST /api/conexoes/{id}/testar`).

## Decisão de arquitetura

`laco/decomposicao/L3L6_CONCEITO.md` B6/B7: `plat.conexao` com tipo fechado + config JSONB + credencial
cifrada + saúde; SSRF fechado por resolução do host (nunca lista de hosts) com pinagem de IP na conexão
real. Achado ao ler o código antes de escrever: a migração 021 (item entregue L6-01-a-procedencia-acervo)
já tinha criado um `tipo_item` de catálogo chamado `conexao` (protocolo `acervo` usado hoje) — é objeto
DIFERENTE do que este item constrói: aquele guarda `dados` num JSONB que a API do catálogo DEVOLVE inteiro
(`GET /api/itens/{id}`), nunca lugar seguro para credencial; `plat.conexao` (esta migração) tem rotas
próprias que nunca expõem `credencial_cifrada`. Reconciliar os dois fica para quando o primeiro conector
concreto ligar um item de catálogo a uma linha de `plat.conexao`.

Cifra: AES-GCM em Python (`app/conexao/credencial.py`), mesmo padrão já usado em `app/auth/totp.py` e
`app/auth/ldap.py` — nunca `pgp_sym_encrypt` (a chave passaria pelo SQL de cada chamada, visível em log
de consulta lenta). Defesa de SSRF (`app/conexao/seguranca.py`): resolve o host com timeout numa thread
(`socket.getaddrinfo` não tem timeout nativo), recusa qualquer IP resolvido privado/loopback/link-local/
CGNAT/reservado/multicast, e conecta PINADO no IP já validado — um `_BackendPinado` (subclasse de
`httpcore.SyncBackend`) troca só o alvo do `connect_tcp`, deixando o TLS (`start_tls`) verificar o
hostname ORIGINAL (conferido na fonte instalada de `httpcore`, não suposto) — fecha DNS-rebinding sem
reimplementar TLS. Redirecionamento nunca é automático: cada `Location` é revalidado do zero.

## O que fiz

- `db/migracoes/030_conexao.sql` (renumerada de 028 por colisão com a trilha concorrente —
  `028_documento_grafo.sql`; aplicada via `sudo bash db/migrar.sh`, registrada em
  `plat.versao_migracao`): `plat.conexao` (tenant_id+RLS, mesmo padrão de `plat.pasta` — políticas por
  dono/`conteudo.editar_tudo`), `plat.tg_conexao_atualizado_em`, evento_tipo `conexoes/criar|editar|
  apagar|testar`.
- `app/conexao/credencial.py`: `cifrar`/`decifrar` AES-GCM, prefixo `encconexao:v1:`.
- `app/conexao/seguranca.py`: `validar_url` (recusa esquema fora http/https, host ausente, userinfo,
  IP bloqueado — 8 categorias), `_BackendPinado`, `cliente_pinado`, `buscar_seguro` (segue
  redirecionamento revalidando hop a hop, até 5 saltos, corpo limitado a 1 MiB).
- `app/conexao/modelos.py` + `app/conexao/rotas.py`: `GET/POST /api/conexoes`, `GET/PATCH/DELETE
  /api/conexoes/{id}`, `POST /api/conexoes/{id}/testar`. Nenhuma rota faz `SELECT credencial_cifrada`
  para responder; o teste de saúde decifra só em memória.
- `app/limites.py`: seção `CONEXAO_*` (tipos, timeouts, limite de bytes, redirecionamentos).
- `app/main.py`: router registrado (edição aditiva; o arquivo já estava sendo tocado por outra
  trilha — `MM app/main.py` no git status — só acrescentei 1 import + 1 linha na lista `ROUTERS`).
- `docs/adr/0012-registro-do-acervo-e-conexao-externa.md` (Parte 2), `docs/PARIDADE.md`, `MANUAL.md`
  §18.2, `ARQUITETURA.md` §15, `CHANGELOG.md`.
- `tests/unit/test_conexao_seguranca.py` (26 testes: os 8 casos do portão + DNS rebinding + loop de
  redirecionamento + pinagem provada com monkeypatch de `getaddrinfo`).
- `tests/api/test_conexoes.py` (13 testes: CRUD, RLS cruzada A→B, unicidade de nome por inquilino,
  tamanho de `config`, credencial nunca na resposta nem no log — `caplog`).
- `tests/api/cruzado_casos.py`: as 6 rotas novas de `/api/conexoes` NÃO apareciam no teste cruzado A→B
  gerado do OpenAPI (`test_cobertura_100_por_cento` falhava com elas em "faltando") — acrescentado
  `conexao_b` (conexão de B criada com URL pública real, IBGE) em `Preparacao`/`preparar`/`desfazer`/
  `marcas_de_b`, e os 6 `CASOS` correspondentes.

## Evidência (comando + saída literal)

Os 8 casos do portão, um a um (`app/conexao/seguranca.py` em REPL):
```
RECUSA  http://127.0.0.1:8150/ -> ip_bloqueado:loopback:127.0.0.1
RECUSA  http://169.254.169.254/latest/meta-data/ -> ip_bloqueado:link_local:169.254.169.254
RECUSA  http://10.1.2.3/ -> ip_bloqueado:privado:10.1.2.3
RECUSA  http://172.16.5.5/ -> ip_bloqueado:privado:172.16.5.5
RECUSA  http://192.168.0.1/ -> ip_bloqueado:privado:192.168.0.1
RECUSA  file:///etc/passwd -> esquema_nao_permitido
RECUSA  http://user:pass@servicodados.ibge.gov.br/ -> userinfo_na_url
RECUSA  http://localhost/ -> ip_bloqueado:loopback:127.0.0.1
RECUSA  http://[::1]/ -> ip_bloqueado:loopback:::1
RECUSA  http://100.64.0.1/ -> ip_bloqueado:privado:100.64.0.1
```

URL pública normal aceita e testável (IBGE, dado aberto federal):
```
validada URLValidada(url='https://servicodados.ibge.gov.br/...', esquema='https', host='servicodados.ibge.gov.br', porta=443, ips=('170.84.40.205',))
busca ResultadoBusca(ok=True, status=200, mensagem='http_200', url_final='...', latencia_ms=68, saltos=0)
```

Redirecionamento de host PÚBLICO real (216.238.123.14, IP desta máquina — nunca loopback) para
`169.254.169.254`:
```
ResultadoBusca(ok=False, status=None, mensagem='url_insegura:ip_bloqueado:link_local:169.254.169.254', url_final='http://169.254.169.254/latest/meta-data/', latencia_ms=4, saltos=1)
```
(aceitou o hop 0 — host público de verdade — e recusou só o hop 1, prova de que o redirecionamento
nunca é seguido cegamente.)

Bypasses clássicos de SSRF, todos recusados (resolução via `getaddrinfo` normaliza antes do `ipaddress`
checar): `::ffff:127.0.0.1` (IPv4-mapped-IPv6), `0177.0.0.1` (octal), `2130706433` (decimal), `127.1`
(forma curta) — todos viraram `ip_bloqueado:loopback:127.0.0.1` ou equivalente.

Loop de redirecionamento (host público real redirecionando para si mesmo indefinidamente):
```
ResultadoBusca(ok=False, status=None, mensagem='redirecionamentos_demais', url_final='...', latencia_ms=10, saltos=5)
```

Suíte (sob `flock laco/.pytest.lock`):
```
tests/unit/test_conexao_seguranca.py: 26 passed in 1.29s
tests/api/test_conexoes.py: 13 passed
tests/api/test_cruzado.py -k conexoes: 6 passed  (as 6 rotas novas, cross-tenant A→B)
tests/api/test_cruzado.py::test_cobertura_100_por_cento: ainda FALHA globalmente, mas o "faltando"
  não cita mais nenhuma rota /api/conexoes — só rotas de outra trilha (/api/importacoes, /ogc/records,
  /api/itens/{id}/metadado.xml), responsabilidade dela, não deste item.
```

`make sem-marcador` e `docs/gerar_limites.py --check` verdes para toda a árvore.

## Riscos

Achado: `httpx.HTTPTransport.__new__` + substituição direta de `_pool` usa um atributo "privado" da
biblioteca (`_pool`) — funciona e foi conferido na fonte instalada (httpx 0.138.0/httpcore 1.0.9), mas
quebra se a versão pinada mudar sem reconferir. `app/conexao/rotas.py::testar` decifra a credencial
mesmo quando `PLAT_SECRET` mudou (silenciosamente testa sem credencial em vez de derrubar a rota) —
decisão deliberada (nunca quebrar o teste de saúde por causa de rotação de segredo), documentada no
código. Full-suite (`pytest -m "not lento"`) rodada uma vez mostrou 36 failed/165 errors em subsistemas
totalmente alheios (login, sessão, LDAP, ingestão de outra trilha) — reproduzidos em ISOLAMENTO
(`test_eu.py`, `test_sessao.py`, `test_plataforma.py`, `test_log_acesso.py`, todos os 6 casos de
`conexoes` em `test_cruzado.py`) e todos passaram limpos; atribuído a interferência/estado transitório
de outras trilhas escrevendo na mesma árvore compartilhada no mesmo instante, não a este item.

## Pendências

Os 15 conectores concretos (L6-02-b em diante) — cada um lê `plat.conexao.config` com JSON Schema
próprio e de fato busca/traduz o serviço externo; materialização "copiada" com agendamento (hoje só o
campo `modo` existe); reconciliação com o `tipo_item` de catálogo `conexao`.

## Para o próximo papel

O primeiro conector concreto (provavelmente WMS ou OGC API Features) usa `app.conexao.seguranca.
buscar_seguro`/`validar_url` para QUALQUER chamada ao serviço de terceiro — nunca reimplementar a
defesa de SSRF em outro lugar. `plat.conexao.tipo` já tem o vocabulário fechado; falta o `config`
schema por tipo (JSON Schema, mesmo padrão de `app/catalogo/tipos.py`).

## Resumo (8 linhas)

`plat.conexao` (migração 030) + `app/conexao/*`: modelo de conexão externa com credencial AES-GCM e
defesa de SSRF por resolução+pinagem de IP (nunca lista de host). Os 8 casos do portão passam: IP
privado/loopback/link-local/CGNAT recusados, `file://` recusado, userinfo recusado, redirecionamento
para IP interno recusado no salto (não no hop público real), DNS-rebinding fechado (conexão pinada
nunca resolve de novo). URL pública real (IBGE) aceita e testável via `POST /api/conexoes/{id}/testar`.
39 testes próprios (26 unit + 13 API) + 6 casos novos no teste cruzado A→B do catálogo (gap real achado
e corrigido: as rotas não apareciam lá). Migração 030 (renumerada de 028 por colisão); ADR 0012.

**Commit:** `9df2cff` (enterprise repo).
