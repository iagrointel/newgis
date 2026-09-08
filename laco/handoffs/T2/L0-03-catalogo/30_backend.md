# T2 · L0-03-catalogo · 30_backend — backend (trilha C)

## Objetivo

Retomar e fechar o backend do catálogo de conteúdo que estava no disco sem commit: migração, `plat.item` com RLS,
versões imutáveis com sha256, relações sem ciclo, compartilhamento em cinco níveis com link por token, busca com
pesos, pastas, categorias, favoritos, lixeira com expurgo, transferência de dono, miniatura e os seis tipos de job —
contra o contrato do ADR 0004, sem mudar rota que o frontend já consumiu no commit 05a41cd, e com a separação de
permissão das migrações 006/012/013 preservada.

## O que fiz

1. **Permissão da 011 (obrigação 1a-1c).** O trabalho no disco já trazia o bloco de grants EXPLÍCITOS por função
   (23 funções do catálogo para `plat_app`, 7 funções de gatilho sem EXECUTE para ninguém) no lugar do
   `GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA plat`, e o sha da 011 já estava re-registrado em
   `plat.versao_migracao`. Confirmei os três pontos antes de qualquer commit: `bash db/migrar.sh` sai 0,
   `venv/bin/ruff check app/catalogo` passa, e a asserção "plat_app sem EXECUTE nas funções do worker" existe em
   `tests/api/catalogo/test_eventos_e_seguranca.py::test_funcoes_do_catalogo_sem_public_e_worker_fechado_a_plat_app`,
   com a mesma lista de `tests/api/jobs/test_jobs_transicoes.py`.
2. **Roteiro de fumaça pela API real** (TestClient com o admin de demo e o de demo2), fora do repositório: 67 passos
   cobrindo tipos, criação, JSON Schema recusando item inválido, listagem, facetas, as 7 ordenações, versões com
   sha256, relações e dependência bloqueando exclusão, proteção bloqueando, cruzado A→B em 3 rotas, compartilhamento,
   link anônimo e revogação, pastas, favoritos, categorias, lote, transferência, lixeira e expurgo. Fechou 0 falha.
   Todas as divergências da primeira rodada eram do roteiro contra o contrato real (ver "Contrato conferido").
3. **Suíte do item**: 249 testes de `tests/api/catalogo` + `tests/unit` passando, 0 falha, com as medidas gravadas.
   A primeira rodada tinha 13 falhas e 6 erros; a lista do que era defeito de produto e do que era defeito de teste
   está na seção "Defeitos achados".
4. **Dez defeitos de produto corrigidos** (dois apontados pelo frontend, três pela fumaça e pela suíte) e **três
   migrações novas** (016, 017, 018), cada uma com o motivo medido no cabeçalho.
5. **Desempenho da leitura com 11 mil itens**: a política de `plat.item` deixou de ser uma função por linha. Busca por
   texto 2.813 → 66,2 ms de p95; lista por tipo 457 → 48,6 ms (portões 200 ms e 100 ms).
6. **OpenAPI regenerado**: 92 caminhos e 123 operações, das quais 36 caminhos e 48 operações do catálogo.
7. **Varredura cruzada A→B inteira** (`tests/api/test_cruzado.py`, gerada do OpenAPI): 124 casos, 0 falha. Ela só
   passou a cobrir as 48 operações do catálogo depois que elas entraram em `docs/openapi.json`, e a primeira
   passagem achou dois defeitos: identidade vazando pelo link anônimo e ordem de checagem na miniatura.
8. **`make check-rapido` inteiro verde**: ruff, varredura de marcadores e 612 testes, 0 falha.
9. **Serviços reiniciados uma vez, às 21:07:36 UTC de 05/09/2026**: `plat-api` e `plat-worker` ativos, `/saude` com
   `migracoes_pendentes: 0` e `ultima_migracao: 018_item_ler_durante_transferencia`, `/conteudo` e
   `/conteudo/lixeira` respondendo 200 e o OpenAPI vivo listando os 36 caminhos do catálogo.
10. Dez commits pequenos, por caminho, sem `git add -A` (nas linhas compartilhadas entraram só os arquivos deste
    item; `tests/medidas/L0-01-repo.json` e `L0-02-tenant-auth.json` ficaram fora, são de outras trilhas).

## Evidência (comando + saída literal)

```
$ bash db/migrar.sh
igual      011_catalogo
...
aplicada   018_item_ler_durante_transferencia (66 ms)
migracoes: aplicadas 1 · reaplicadas 0 · iguais 16 · pendentes 0

$ venv/bin/ruff check app/catalogo app/db.py tests
All checks passed!

$ make sem-marcador
! grep -rnI ... -E -f tests/marcadores.regex app web db docs deploy install.sh Makefile ... *.md
(sem saída: 0 marcadores)

$ flock /home/dev/plataforma/laco/.pytest.lock env PYTHONNOUSERSITE=1 venv/bin/python <fumaça>
OK  GET /api/tipos-item: 200
OK  POST /api/itens (mapa): 201
OK  POST /api/itens dados invalidos -> 422: 422
OK  ordenar=titulo|modificado_em|criado_em|tipo|dono|tamanho_bytes|pontuacao: 200 (7 de 7)
OK  ordenar invalido -> 422: 422
OK  GET versoes: 200        versoes: 2 campos: ['autor','comentario','compactou','criado_em','rotulo','sha256','versao']
OK  GET versao n: 200       sha256 da versao 1 = 8599a0ac51c0be57 len 64
OK  PUT versao (imutavel) -> 405: 405
OK  PUT relacoes de mapa -> 409 relacoes_pelo_tipo: 409
OK  DELETE camada com dependencia -> 409: 409
OK  DELETE protegido -> 409: 409
OK  cruzado B le / patch / apaga item de A -> 404: 404 (3 de 3)
OK  POST link: 201 · anon GET /api/compartilhado/<token>: 200 · DELETE link (revogar): 204
OK  anon com link revogado -> 404/410: 404 · anon com token inexistente -> 404: 404
OK  DELETE pasta nao vazia -> 409: 409
OK  POST /api/lixeira/esvaziar (apagar agora): 202
--- fumaca: 67 passos, 0 falha(s)

$ flock /home/dev/plataforma/laco/.pytest.lock env PYTHONNOUSERSITE=1 PLAT_GRAVAR_MEDIDAS=1 \
    venv/bin/pytest tests/api/catalogo tests/unit -q -p no:randomly
........................................................................ [ 28%]
........................................................................ [ 57%]
........................................................................ [ 86%]
.................................                                        [100%]
(249 testes, 0 falha, 0 erro)

$ cat tests/medidas/L0-03-catalogo.json
  busca_p95_ms = 66.2 ms          (GET /api/itens?q=municipio&limite=50, 20 execuções, corpus 10 mil)
  busca_trgm_p95_ms = 133.3 ms    (GET /api/itens?q=municpio, trigram de reserva, 10 execuções)
  lista_tipo_p95_ms = 48.6 ms     (GET /api/itens?tipo=mapa&limite=50, 20 execuções)
  facetas_p95_ms = 25.8 ms        (GET /api/itens/facetas?tipo=mapa, 10 execuções)
  revogacao_nega_ms = 15.4 ms     (DELETE link + GET /api/compartilhado/<token> -> 404)
  expurgo_s = 0.32 s              (job catalogo.lixeira_expurgar de 1 camada até concluido)
  miniatura_job_s = 0.33 s        (miniatura/gerar de camada com 30 polígonos até concluido)
  usado_por_medio_ms = 11.9 ms    (GET /api/itens/{id}/usado-por, média de 20 chamadas)
  versao_custo_ms = 0.361 ms      (custo do gatilho de versão, 1.000 pares como plat_app)
  pagina_conteudo_ms = 234.9 · primeira_pintura_conteudo_ms = 24 · soma_modulos_kb = 229.6  (do frontend)

$ <EXPLAIN ANALYZE da lista por tipo com 11 mil itens, como plat_app>
antes da 017:  Index Scan ... Filter: pode_ler(id)   Buffers: shared hit=38862   Execution Time: 208.366 ms
depois da 017: Aggregate ... InitPlan 1..6           Buffers: shared hit=4428    Execution Time:  12.566 ms

$ venv/bin/python -c "import json; d=json.load(open('docs/openapi.json')); ..."
paths 92 ops 123 | catalogo paths 36 ops 48

$ make check-rapido
All checks passed!
612 passed, 25 deselected, 5 warnings in 187.06s (0:03:07)

$ flock ... venv/bin/pytest tests/api/test_cruzado.py -q -p no:randomly
........................................................................ [ 58%]
....................................................                     [100%]
(124 casos, 0 falha; EXIT=0)

$ date -u; sudo systemctl restart plat-api plat-worker; systemctl is-active plat-api plat-worker
2026-09-05T21:07:36Z
active
active
$ curl -s <URL>/saude
{"versao":"0.1.0","git_sha":"a5915815a75e","ambiente":"producao","banco":"ok","migracoes_aplicadas":17,
 "migracoes_pendentes":0,"ultima_migracao":"018_item_ler_durante_transferencia",
 "servicos":{"martin":"ausente","titiler":"ausente","garage":"ok","worker":"ok"},
 "fila":{"pendentes":2,"rodando":0,"workers_vivos":1,...}}
$ for p in /api/openapi.json /conteudo /conteudo/lixeira; do curl -o /dev/null -w "%{http_code}" <URL>$p; done
200 200 200
$ curl -s <URL>/api/openapi.json | ...
OpenAPI vivo: caminhos 92 | do catálogo 36

$ git log --oneline | head -10
65a9fc2 Medidas do L0-03-catalogo gravadas pela suíte com o corpus de 11 mil itens
a591581 Link anônimo não entrega identidade nem estado interno; miniatura confere acesso antes do formato (L0-03)
4bde64f Ler a linha durante a transferência de dono (migração 018), achado exposto pela 017
7d91329 Marcador na 016: a varredura do driver casa TODO dentro de TODOS (sha re-registrado)
7d6d94f Leitura de item por linha em vez de função por linha (migração 017) e semente com estatística
61bb480 Apagar usuário depois da transferência (L0-03-j, migração 016) e correção da semente de escala
36317a7 Correções do catálogo achadas na fumaça e nos testes (L0-03): faceta de dono com id, status nenhum como
        IS NULL, itens_incluidos como texto, 422 no núcleo do PUT, espera no pool
d4c592e Testes do catálogo (L0-03): 11 arquivos de API, 3 de unidade, casos cruzados A->B e eventos esperados
3f44ec1 Integração do catálogo com as trilhas A e B (L0-03): routers, páginas, limites, tipos de job, escopo com
        uuid e OpenAPI
76aa929 Catálogo de conteúdo (L0-03, backend): migração 011, modelo plat.item com RLS por pode_ler, ...
```

## Defeitos achados (produto, não teste)

| # | onde | o que acontecia | correção |
|---|---|---|---|
| 1 | `GET /api/itens/facetas` | a faceta de dono devolvia só o login, mas o filtro lateral é `?dono_id=<int>`: dono sem item na página carregada sumia da lista (achado do frontend) | a faceta devolve `{valor: login, id, rotulo: nome, n}`; teste confere a contagem da faceta contra o filtro |
| 2 | `GET /api/itens?status=nenhum` | a faceta contava o NULL como `nenhum` e o filtro comparava `i.status = ANY(...)`: 54 itens na faceta, 0 no filtro (achado do frontend) | o filtro traduz `nenhum` para `IS NULL`, valida o vocabulário (422 fora dele) e aceita a mistura com `obsoleto` |
| 3 | `POST/GET /api/itens/{id}/links` | `itens_incluidos` vinha como o texto do array do PostgreSQL e a resposta saía com uma letra por posição | `ARRAY(...)::text[]`, como já se fazia na resolução do link |
| 4 | núcleo do PUT/PATCH | campo fora do limite conhecido só pelo núcleo (21 categorias) subia `ValidationError` e virava 500 | 422 no mesmo contrato do tratador de `app/erros.py` |
| 5 | `app/db.py` (compartilhado) | `ThreadedConnectionPool` com maxconn 8 estoura `PoolError` na rajada: 20 pedidos simultâneos ao mesmo link derrubavam com 500 os que passassem de 8 | `obter_conexao` espera até 5 s por conexão livre e só então deixa o `PoolError` subir |
| 6 | apagar usuário depois de transferir (016) | `item.criado_por` prendia o usuário: 409 `em_uso` mesmo com todos os itens transferidos | `criado_por`, `modificado_por`, `apagado_por` e `compartilhamento_link.criado_por` passam a `ON DELETE SET NULL`; `dono_id` continua NOT NULL e continua barrando |
| 7 | leitura de `plat.item` com 11 mil itens (017) | a política era `plat.pode_ler(id)`, função chamada uma vez por linha, que relia a tabela pela chave e reavaliava `plat.tem(...)`: 457 ms de p95 na lista e 2.813 ms na busca | o mesmo predicado escrito na própria linha, com o que não depende da linha dentro de `(SELECT ...)`; 12,6 ms no plano, 48,6 e 66,2 ms por HTTP |
| 9 | `GET /api/compartilhado/{token}` anônimo | a resposta trazia o NOME do dono ("Administrador demo2"), o login de quem criou e de quem alterou, favorito, contagem de grupos e de links, proteção, pontuação e versão publicada; `item_json(publico=True)` só tirava `dono.login` e `pode_*` | o público devolve o que descreve o conteúdo: dono só com id, nenhum nome ou login, nenhum contador interno |
| 10 | `POST /api/itens/{id}/miniatura` | decodificava a imagem antes de conferir o acesso: quem não enxerga o item recebia 415 sobre o formato em vez de 404 | o acesso vem primeiro |
| 8 | transferência de dono (018) | com a 017, o PostgreSQL passou a conferir a linha NOVA contra a política de leitura e a transferência parava com 403 `sem_permissao`; antes passava por acidente, porque a função SECURITY DEFINER relia a linha ANTIGA | a política aceita a linha enquanto `plat.transferencia` está ligada, dentro do inquilino; teste novo confere que a variável não atravessa a fronteira de inquilino |

## Contrato conferido contra o frontend (05a41cd e 03a73e0)

Nenhuma rota mudou de caminho, verbo ou corpo. O que a fumaça confirmou, ponto a ponto, é o que o frontend já usa:
`ordenar` + `direcao` separados (as sete chaves de `ORDENAVEIS` em `lista.js` são exatamente as sete de `ORDENACOES`),
`PUT /api/favoritos/{id}`, `POST /api/lixeira/esvaziar {ids}` como "apagar agora" (não existe `DELETE /api/lixeira/{id}`),
`PUT /api/itens/{id}/compartilhamento {acesso, grupos, destaques, aplicar_a_dependencias}`, versão identificada por
`versao` na resposta e por `{n}` no caminho, relações de mapa/cena/app/painel/modelo_amc/rede saindo de `dados`
(o `PUT .../relacoes` responde 409 `relacoes_pelo_tipo`, que é o que o painel mostra).

## Desvios do ADR 0004 (para o frontend)

| ADR | o que ficou diferente | por quê | o que o frontend faz |
|---|---|---|---|
| 15.5 `/admin/categorias` | a página NÃO está registrada em `app/paginas.py` | `web/admin/categorias.html` não existe; rota registrada para arquivo inexistente é casca (P2) | quando a tela existir, é uma linha em `PAGINAS`; peça no próximo turno |
| 13 facetas | `dono` ganhou os campos `id` e `rotulo` (o `valor` segue sendo o login) | o filtro lateral é `?dono_id=<int>` | pode parar de resolver o id pelo objeto `dono` da lista |
| 13 filtro de status | `?status=nenhum` passou a existir de verdade (IS NULL) e valor fora do vocabulário devolve 422 | a faceta já usava `coalesce(..., 'nenhum')` | pode mandar `nenhum` direto, inclusive junto com `obsoleto` |
| 18 numeração | a migração do catálogo é a **011**, não a 006 | 006 a 010 já eram da fila quando a trilha C entrou | nada |
| 11.4 miniatura de camada | é render por Pillow, não captura de mapa | o visualizador é do L2-01 | o painel já mostra a ressalva |
| 3.1 `tipo_item` | continua global (sem `tenant_id`) | leitura registrada pelo arquiteto; nenhum inquilino pede tipo próprio ainda | nada |

## Riscos

1. **`app/db.py` é arquivo compartilhado** e a espera do pool muda o comportamento de TODA a aplicação sob carga: o
   que antes virava 500 agora vira latência de até 5 s. Quem mede latência sob rajada precisa saber disso. A trilha
   que cuida da fundação (L0-01) deveria decidir se `maxconn` 8 é o número certo — não medi carga sustentada.
2. **A 017 mexe na política de leitura de `plat.item`**, que é a peça de segurança mais importante do item. O
   predicado é o mesmo, linha a linha, mas quem confere isso é o adversário, não eu. A 018 amplia a leitura enquanto
   `plat.transferencia` está ligada: o recorte por inquilino continua sendo a primeira condição (teste novo), mas
   dentro da transação da transferência um item privado de outro dono do MESMO inquilino fica legível. A janela é a
   execução da transferência, depois de `planejar` já ter exigido `pode_editar` em cada item.
3. **A escala medida é 11 mil itens** (10 mil em demo, 1 mil em demo2). 50 mil (refutação do L0-03-f) e 100 mil
   (`COTA_ITENS`) não foram medidos.
4. **O corpus `zt-semente` agora sobrevive à sessão de testes** (semeá-lo custa minutos por rodada). Quem quiser o
   banco limpo roda `venv/bin/python -m tests.api.semear_catalogo 0`.
5. O relógio simulado do expurgo (`parametros.agora`) **não serve na prática**: o worker roda na unidade systemd em
   `PLAT_AMBIENTE=producao` e o parâmetro só é aceito em dev. O teste envelhece `apagado_em`. Se alguém quiser o
   caminho do relógio, é decisão de ambiente, não de código.
6. `plat.pasta.dono_id` continua NOT NULL: um usuário que criou pasta e não a transferiu ainda prende a exclusão.
   Não apareceu no teste porque a transferência com `pastas: "unica"` cria a pasta no dono novo. Fica nomeado.
7. A miniatura por Pillow desenha os polígonos, mas o pixel do centro pode cair num vão entre feições: o teste conta
   pixels fora do fundo, não olha um ponto.

## Pendências

- **Testador (40)**: `make check` inteiro e `make medidas` contra a URL real; o e2e do frontend já fechou 2/2 com
  0 erro de console, mas foi antes das migrações 016/017/018 — vale repetir depois do reinício dos serviços.
- **Adversário (50)**: o roteiro do L0-03-e (revogar e reabrir link em 20 clientes, token curto, compartilhar item de
  outro) e, agora, **a 017 e a 018**: comparar cláusula a cláusula o predicado da política com o corpo de
  `plat.pode_ler`, e tentar ler item de outro dono com `plat.transferencia` ligada à força.
- `/admin/categorias` (L0-03-b) e a aba "Uso" do item continuam fora; upload de arquivo (`/api/uploads`) é do L0-04.
- L0-11 deve entregar o cliente de objetos com a assinatura da seção 11.3 do ADR; hoje roda o adaptador local
  (`app/objetos.py`, `PLAT_DADOS_DIR`).
- L0-10 deve acrescentar `plat.historico` por gatilho em `pasta`, `categoria`, `item_grupo`, `compartilhamento_link`.

## Para o próximo papel (testador, 40)

1. `flock /home/dev/plataforma/laco/.pytest.lock make check` — `make check-rapido` (ruff + marcadores + 612 testes)
   já está verde aqui; o que falta é o `e2e` contra a URL real, que o alvo `check` acrescenta.
2. Repita o e2e `tests/e2e/test_conteudo.py` DEPOIS do reinício dos serviços: as migrações 016/017/018 mudaram a
   política de leitura de `plat.item` e a transferência. Esperado: 2 passed, 10 capturas `L0-03_*.png`, 0 erro de
   console.
3. Meça o que ainda não foi medido: 50 mil itens (`venv/bin/python -m tests.api.semear_catalogo 50000 1000`) e a
   lista com "Carregar mais" 200 vezes sem repetir nem pular. Grave `busca_50k_p95_ms` como fronteira, sem portão.
4. Rajada: 20 e 50 pedidos simultâneos numa rota que usa banco, para pôr número na espera do pool (`POOL_ESPERA_S`).
   O que hoje se sabe é que 20 clientes no mesmo link não dão mais 500; não sei o teto.
5. Confira que o corpus `zt-semente` não contamina contagem de nenhum teste seu: ele fica no banco entre rodadas.
6. **Interferência entre trilhas**: numa das rodadas de `make check-rapido` reprovaram 5 testes de identidade
   (`test_eu`, `test_log_acesso`, `test_plataforma`, um caso do cruzado) com "token revogado" e com a contagem de
   itens de B mudando no meio da varredura. Rodados de novo, sozinhos, passaram (EXIT=0), e a rodada seguinte do
   `check-rapido` fechou 612/612. É outra sessão mexendo no banco fora do `flock`, não defeito do catálogo — se
   reaparecer, repita antes de investigar.

## Resumo em 8 linhas

1. O trabalho do disco foi colhido e comitado em sete commits pequenos: migração 011 com grants explícitos por função,
   `app/catalogo` (20 módulos, 3.500 linhas), `app/objetos.py`, integração com as trilhas A e B e 15 arquivos de teste.
2. As três obrigações antes do commit estão cumpridas: grants explícitos na 011, sha re-registrado (`db/migrar.sh`
   sai 0 para todas as trilhas) e ruff limpo em `app/catalogo`.
3. Roteiro de fumaça pela API real com 67 passos e 0 falha: cruzado A→B, link revogado negando, dependência e proteção
   bloqueando exclusão, expurgo da lixeira, busca com pesos, JSON Schema recusando item inválido e versões imutáveis
   com sha256 de 64 caracteres.
4. Suíte do item verde: 249 testes de `tests/api/catalogo` e `tests/unit`, 0 falha, com as medidas gravadas em
   `tests/medidas/L0-03-catalogo.json`.
5. Dez defeitos de produto corrigidos: dois apontados pelo frontend (faceta de dono sem id, `status=nenhum`
   devolvendo 0), um em arquivo compartilhado (`app/db.py`: rajada acima de 8 conexões virava 500) e dois de
   privacidade achados pela varredura cruzada (o link anônimo entregava nome e login de pessoas; a miniatura
   respondia sobre o formato antes de conferir o acesso).
6. Três migrações novas com o motivo medido no cabeçalho: 016 (apagar usuário depois de transferir), 017 (leitura de
   `plat.item` por linha em vez de função por linha) e 018 (a linha nova durante a transferência).
7. Desempenho com 11 mil itens: busca 2.813 → 66,2 ms de p95, lista por tipo 457 → 48,6 ms, plano de 208,4 → 12,6 ms
   e de 38.862 → 4.428 buffers. Portões de 200 ms e 100 ms cumpridos.
8. `make check-rapido` fecha em 612 testes verdes e a varredura cruzada A→B em 124 casos sem falha; os serviços
   foram reiniciados às 21:07:36 UTC e a API viva publica os 36 caminhos do catálogo. Fica para o testador o e2e
   contra a URL real, a escala de 50 mil e o teto da rajada; fica para o adversário conferir cláusula a cláusula as
   políticas das migrações 017 e 018.
