# Ataque G2 — catálogo de conteúdo (L0-03-a..l) — laudo do adversário independente

Data: 06/09/2026. Base própria: schema `plat_tadv2` (criado por `laco/trilha_ambiente.sh adv2`),
worktree `/home/dev/plataforma/wt/adv2` (ramo `wt/adv2`), sincronizado com a árvore de trabalho de
`/home/dev/plataforma/enterprise` no commit `90ab545` **mais as 20 alterações e os 30 arquivos não
comitados que estavam no disco** — é esse o código que os itens dizem ter entregue. Nada foi rodado
contra o schema `plat` de produção; nenhum serviço foi reiniciado.

## (a) Veredito item a item

| item | veredito | por quê (achado curto) |
|---|---|---|
| L0-03-a-modelo-item | **NÃO REFUTADO** | os cinco ataques prescritos deram 4xx com mensagem |
| L0-03-b-pastas-tags-categorias-classificacao | **NÃO REFUTADO** | ciclo 409, 6º nível 422, nome de 10 mil 422, categoria alheia 404, 21ª categoria 422 |
| L0-03-c-busca | **NÃO REFUTADO** | sintaxe inválida 422, 250 termos 422, `id:` de item alheio devolve 0 |
| L0-03-d-grupos | **NÃO REFUTADO** | os quatro ataques prescritos falharam (403/404/409) |
| L0-03-e-compartilhamento | **REFUTADO** | a miniatura servida pelo link sai com `Cache-Control: private, max-age=300`; depois de revogar, o cliente que já baixou continua servindo do cache por 5 min (G2-6) |
| L0-03-f-tela-conteudo | **REFUTADO** | estrela de favorito inerte: grava no servidor e a linha continua `aria-pressed="false"`; o e2e do próprio repositório para nesse passo (G2-9) |
| L0-03-g-detalhe-item-miniatura | **NÃO REFUTADO** | bomba 20.000×20.000 recusada (422), formato fora 415, corpo de 14 MB 413, item de outro dono 403/404 |
| L0-03-h-lixeira-protecao-status | **REFUTADO** | `POST /api/lixeira/esvaziar` com id que não resolve enfileira `ids: []`, a tarefa converte `[]`→`NULL` e o expurgo varre a lixeira INTEIRA do inquilino (G2-4) |
| L0-03-i-dependencias | **NÃO REFUTADO** | ciclo 409 com caminho, cascata 409 com ordem, item de outro inquilino recusado, tetos 5.000/50.000 no gatilho |
| L0-03-j-transferencia-dono | **REFUTADO** | evento `itens/transferir` gravado para item que a RLS impediu de atualizar: o dono não mudou e a auditoria diz que mudou (G2-5) |
| L0-03-k-favoritos-notificacoes | **REFUTADO** | notificação interna NÃO EXISTE (nenhuma rota, tabela, migração ou código); favorito com estado errado na tela (G2-7, G2-9) |
| L0-03-l-versoes-item | **REFUTADO** | `plat.item_versoes_compactar` apaga versões de item de OUTRO inquilino (G2-1/G2-2); a compactação deixa 146 linhas depois de 1.000 PUTs, contra o teto de 50 da refutação (G2-3) |

6 de 12 refutados. Nove achados viraram teste `xfail(strict=True)` em
`tests/api/catalogo/test_adversario_g2.py` (8) e `tests/e2e/test_adversario_g2_conteudo.py` (1):
enquanto o defeito existir são xfail; no dia em que alguém consertar, viram XPASS e a suíte reprova.

```
$ set -a; source /home/dev/plataforma/laco/var/trilha/adv2.env; set +a
$ venv/bin/pytest tests/api/catalogo/test_adversario_g2.py tests/e2e/test_adversario_g2_conteudo.py \
    -q --base-url https://127.0.0.1:8158
xxxxxxxxx                                                                [100%]
```

## (b) Suposições transversais — o que caiu e o que aguentou

O grupo inteiro se apoia em seis suposições. Ataquei-as antes de olhar item por item; três caíram e
derrubaram, sozinhas, quatro dos seis itens refutados.

### T1 — "o isolamento por inquilino é da RLS, e toda função SECURITY DEFINER compara `tenant_atual()`" — **CAIU**
A migração `011_catalogo.sql` faz isso em `item_lixeira`, `lixeira_expurgar`, `item_expurgar` e
`itens_com_versoes_acima` (todas comparam `plat.tenant_atual()` ou exigem o inquilino técnico). Duas
funções da mesma família não fazem: `plat.item_versoes_compactar(uuid,int)` e, por consequência, a
tarefa `catalogo.versoes_compactar`, que aceita `item_id` livre. Medido: no contexto do inquilino A,
a função apagou 2 linhas de `plat.item_versao` de um item do inquilino B; e o `POST /api/jobs` do
admin de A com `item_id` de B foi aceito com 201. É a única passagem cruzada de inquilino que achei
em todo o grupo — mas é destrutiva e chega pela API.

### T2 — "lista vazia significa nada a fazer" — **CAIU**
`POST /api/lixeira/esvaziar` filtra os ids pela RLS, chega a `alvo = []` e enfileira
`{"dias": 0, "ids": []}`. A tarefa faz `[str(x) for x in ids] if ids else None`; `[]` é falso, vira
`NULL`, e `plat.lixeira_expurgar(0, now(), NULL)` devolve **toda** a lixeira do inquilino. Pedir o
expurgo de um item que nem existe apaga tudo o que estava na lixeira. O mesmo `if ids else None`
aparece em `catalogo.exportar_lista` (ali o efeito é exportar tudo em vez de nada — sem perda).

### T3 — "escrita e evento andam juntos; se a RLS barra, alguém levanta erro" — **CAIU**
`UPDATE ... WHERE id = ...` sob RLS que não casa não é erro: afeta zero linhas e segue. A
transferência de dono usa isso em dois lugares (`executar`, laço `for iid in alvo`) e grava o evento
depois, sem olhar `rowcount`. Resultado medido: `itens/transferir` com `{"de": 9, "para": 2}` para
uma vista cujo dono continuou sendo o 9. A API respondeu 200 e o plano prometia o arrasto. Vale para
qualquer leitor da trilha de auditoria: o evento não prova que a linha mudou.

### T4 — "quem não enxerga recebe 404, nunca 403" — **AGUENTOU**
Medido em item, versões, lixeira, favoritos, links, grupos e transferência, nos dois eixos (outro
inquilino e outro usuário do mesmo inquilino): sempre 404 quando não lê, 403 `sem_edicao_no_item`
só quando lê e não edita. `plat.pode_ler`/`plat.pode_editar` são a única porta e estão nas políticas
de `item`, `item_versao`, `item_relacao`, `item_grupo`, `compartilhamento_link*` e `favorito`.

### T5 — "toda entrada é validada antes de tocar no banco" — **AGUENTOU**
Tipo inexistente 422 `tipo_inexistente`; resumo de 5.000 caracteres 422; `<script>` some do
`descricao_html` (`"\n<p>e <img /></p>"`); extent fora de [-180,180] 422; `PUT` com `tenant_id`,
`dono` ou `dono_id` 400 `campo_nao_editavel`; ciclo de pasta 409; 6º nível 422 `pasta_profunda`;
nome de pasta com 10 mil caracteres 422; 21ª categoria 422; categoria de outro inquilino 404; ciclo
de relação 409 com o caminho; PNG de 20.000×20.000 422 `imagem_grande`; BMP 415; corpo de 14 MB 413.

### T6 — "o que sai por link não é cacheável" — **CAIU (parcial)**
`/api/compartilhado/{token}` e `/api/compartilhado/{token}/itens/{id}` saem `no-store,
must-revalidate`. A terceira rota do mesmo link, a miniatura, cai em `miniatura.entregar` e sai
`private, max-age=300`. O servidor devolve 404 depois da revogação (medi), mas o cliente que já
baixou não pergunta de novo por 5 minutos. Não há `proxy_cache` no `deploy/nginx.conf`, então o
vazamento é do navegador de quem tinha o link, não de um cache compartilhado.

### T7 — "toda função do schema `plat` tem REVOKE de PUBLIC" (regra da migração 011) — **CAIU**
13 funções do schema `plat` de PRODUÇÃO têm `proacl` com `=X` (EXECUTE para PUBLIC), 6 delas
SECURITY DEFINER: `convite_aceitar`, `convite_resolver`, `redefinicao_contexto`,
`redefinicao_resolver`, `redefinicao_solicitar`, `uploads_expirar_candidatos`. As migrações novas
(030 conexão, 046 uploads, 047 convites/redefinição) não repetiram o padrão de REVOKE da 011. Não é
escalada por si (só papéis que já conectam podem chamar), mas é a regra do repositório quebrada — e
o teste que a guarda, `tests/api/catalogo/test_eventos_e_seguranca.py::test_funcoes_do_catalogo_sem_public_e_worker_fechado_a_plat_app`,
está VERMELHO no master.

## (c) Um bloco por achado, com comando e saída real

Preparação comum:
```
bash /home/dev/plataforma/laco/trilha_ambiente.sh adv2
cd /home/dev/plataforma/wt/adv2
set -a; source /home/dev/plataforma/laco/var/trilha/adv2.env; set +a
```

### G2-1 e G2-2 — versões de outro inquilino apagadas pela fila (L0-03-l, T1) — GRAVE
```
ADV2 | versoes do item de B antes: 4
ADV2 | POST /api/jobs (A, item de B) -> 201 {"id":"016050b7-...","tipo":"catalogo.versoes_compactar","estado":"pendente",...}
ADV2 | item_versoes_compactar(item de B) no contexto de A -> removidas: 2
```
Código: `db/migracoes/011_catalogo.sql` linha 815, `CREATE FUNCTION plat.item_versoes_compactar
(p_item uuid, p_manter int) ... SECURITY DEFINER` — nenhuma comparação com `plat.tenant_atual()`, ao
contrário das quatro funções vizinhas. `app/catalogo/tarefas.py::catalogo_versoes_compactar` passa
`item_id` do parâmetro direto. `perfil_minimo="admin"`: qualquer admin de qualquer inquilino.
Teste: `test_g2_1_...`, `test_g2_2_...`.
Nota de fronteira: não há worker vivo na trilha, então provei os dois elos separados — a fila aceita
o pedido (201) e a função executa o estrago (2 linhas). O elo do meio (o worker chamando a função) é
uma linha de código lida, não medida.

### G2-3 — compactação não segura as 50 linhas (L0-03-l)
```
ADV2 | 1000 PUTs em 20.2 s; versoes: 1001
ADV2 | passada 1: removeu 855, sobraram 146 linhas (portao: <= 50)
ADV2 | passada 2: removeu 86, sobraram 60 linhas
ADV2 | passada 3: removeu 9, sobraram 51 linhas
ADV2 | passada 4: removeu 0, sobraram 51 linhas
```
Com 200 PUTs sobram 66. O periódico roda **uma** passada por dia (`app/catalogo/periodicos.py`,
`40 3 * * *`), logo o item fica dias acima do teto. A conta é estrutural: guardar as 50 mais recentes
e resumir o resto em blocos de 10 dá 50 + (N−50)/10 linhas, nunca ≤ 50 em uma passada.
Teste: `test_g2_3_...` (200 PUTs, para não custar 20 s por rodada).

### G2-4 — esvaziar a lixeira de um item apaga a lixeira toda (L0-03-h, T2) — GRAVE
```
ADV2 | lixeira de A: 2
ADV2 | job criado com parametros: {"ids": [], "dias": 0, "agora": null}
ADV2 | candidatos que o worker acharia com ids=NULL (dias=0): 2
ADV2 | candidatos com a lista literal: 0
```
`app/catalogo/rotas_lixeira.py::esvaziar` → `servico.criar(..., {"dias": 0, "ids": alvo})` com
`alvo = []`; `app/catalogo/tarefas.py::catalogo_lixeira_expurgar` → `[str(x) for x in ids] if ids
else None`. O expurgo é físico (`destruidores.destruir` + `plat.item_expurgar`), não tem volta.
Teste: `test_g2_4_...`, que roda a MESMA linha da tarefa sobre os parâmetros que o job recebeu.

### G2-5 — evento de transferência que não aconteceu (L0-03-j, T3)
```
ADV2 | plano: [... "arrasta": [{"id": "90608cf9-...", "tipo_relacao": "vista_de_camada", "dono_id": 9}] ...]
ADV2 | executar: 200
ADV2 | dono da camada depois: admin
ADV2 | dono da VISTA depois: ztfab78659      <- não mudou
ADV2 | eventos: {"tipo": "itens/transferir", "alvo_id": "90608cf9-...",
                 "propriedades": {"de": 9, "para": 2, "arrastado_por": "e246e8de-..."}}
```
Montagem: camada do editor 1 e vista do editor 2, ambas com acesso `inquilino`; o editor 1 transfere
a camada. `_arrastados` enxerga a vista (pode ler), o `UPDATE` não a altera (não pode editar) e o
evento é gravado assim mesmo. Dois efeitos: a auditoria mente e o arrasto prometido pelo plano não
acontece, sem nenhum aviso ao usuário. Teste: `test_g2_5_...`.

### G2-6 — miniatura do link revogado fica no cache do cliente (L0-03-e, T6)
```
ADV2 | miniatura por link -> 200 cache-control: private, max-age=300 etag: "8cf12faf..."
ADV2 | json por link -> cache-control: no-store, must-revalidate
ADV2 | miniatura apos revogar -> 404      (no servidor)
```
`app/catalogo/rotas_compartilhamento.py::compartilhado_miniatura` devolve `miniatura.entregar(...)`
sem passar pelo `SEM_CACHE` que as outras duas rotas do link usam. Teste: `test_g2_6_...`.
O resto do portão do item AGUENTOU e eu confirmei: token de 64 hex, `len` conferido antes do hash,
só o `sha256` no banco, 404 para revogado, 410 para expirado, 400 para público com o inquilino
desligado, contagem de acessos, 20 clientes simultâneos sem nenhum 200 depois da revogação,
`itens_incluidos` limitado a dependência que o ator edita, e "elevar ao nível do mapa" recusando
camada de outro dono com 403.

### G2-7 — notificação interna não existe (L0-03-k) — METADE DO ITEM
```
$ grep -rn "notificac" --include=*.py app/ ; grep -rl "notific" web/ ; grep -rn "notificacao" db/migracoes/*.sql
(vazio nos três)
ADV2 | GET /api/notificacoes -> 404
ADV2 | GET /api/eu/notificacoes -> 404
```
`docs/adr/0004` linha 982 diz "o L0-03-k lê `evento` para as notificações" — no futuro. Não há sino,
não há lida/não lida, não há dedup por chave, não há expurgo de 90 dias, não há a medida "sino
consulta ≤ 20 ms". Favoritos existem e funcionam (aba, limite de 500, RLS `WITH CHECK pode_ler`
recusando favoritar item sem acesso com 404, favorito some da lista quando o acesso é retirado).
Teste: `test_g2_7_...`.

### G2-8 — funções do `plat` com EXECUTE para PUBLIC (transversal T7)
```
$ sudo -u postgres psql -d iagro_sat -c "SELECT n.nspname, p.proname, p.prosecdef FROM pg_proc p
    JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='plat'
    AND (p.proacl IS NULL OR EXISTS (SELECT 1 FROM unnest(p.proacl) a WHERE a::text LIKE '=%'))"
 plat | amc_execucao_guarda        | f
 plat | amc_materializado_guarda   | f
 plat | amc_modelo_guarda          | f
 plat | amc_versao_imutavel        | f
 plat | convite_aceitar            | t
 plat | convite_resolver           | t
 plat | redefinicao_contexto       | t
 plat | redefinicao_marcar_usada   | f
 plat | redefinicao_resolver       | t
 plat | redefinicao_solicitar      | t
 plat | tg_conexao_atualizado_em   | f
 plat | upload_reservado_bytes     | f
 plat | uploads_expirar_candidatos | t
(13 linhas)
```
Teste: `test_g2_8_...` (roda no schema da trilha, onde o mesmo defeito aparece em 9 funções).

### G2-9 — estrela de favorito mostra o contrário do que o servidor guardou (L0-03-f, L0-03-k)
```
ADV2 | aria-pressed: false
ADV2 | REQ ('PUT', '/api/favoritos/7d7e5b11-...', 204)
ADV2 | REQ ('GET', '/api/itens?limite=50&meus=true', 200)
ADV2 | servidor tem o favorito? True
ADV2 | apos 2o clique, servidor tem? True       <- o 2o clique manda PUT de novo, não DELETE
ADV2 | aria-pressed apos 2o clique: true
```
Sequência: abrir Conteúdo (11.005 itens), abrir filtros, marcar uma faceta, limpar, clicar na
estrela. O `GET /api/itens` de "limpar filtros" ainda está em voo; sua resposta chega depois do
`PUT` e repinta a linha com o estado velho. Quem clica vê a estrela apagada, clica de novo e manda
outro `PUT` — a tela nunca desfavorita nesse estado. O e2e do próprio repositório para exatamente
aí (`tests/e2e/test_conteudo.py:181`, duas execuções de duas). Sem controle de tempo a corrida sai
em 2 de 3 execuções; o teste que deixo segura a resposta do `GET /api/itens` por 2 s com
`page.route` e reproduz 3 de 3.

## (d) Fronteira honesta — o que NÃO foi provado

1. **Sem worker.** Nenhum `plat-worker` roda na trilha (`/saude` = `workers_vivos: 0`), e o brief
   proíbe subir/reiniciar unidades. Ficaram sem medida: a geração de miniatura por job em ≤ 30 s
   (L0-03-g), o expurgo periódico com relógio simulado apagando a tabela física (L0-03-h) e a
   execução real do job de compactação cruzando inquilino (G2-1: provei a fila e a função, não o
   worker no meio). Os dois testes do repositório que dependem disso deram ERROR por isso.
2. **Medidas de desempenho não repetidas.** `busca_p95_ms` (< 200 ms), `GET /api/itens` p95 < 100 ms
   com 10 mil itens, `pagina_conteudo_ms` ≤ 1,5 s, "sino ≤ 20 ms" (inexistente) e "PUT com versão
   ≤ +5 ms" não foram remedidos por mim: a máquina está com disco a 91 %, 2-3 GB de RAM livre e
   outras trilhas rodando, e número de tempo medido assim não serve de refutação. O que medi de
   tempo: 1.000 PUTs em 20,2 s (a refutação do L0-03-l pede "em 1 min" — cabe).
3. **Tela em condição extrema.** A refutação do L0-03-f pede 0 item, 50 mil itens, nome de item de
   2.048 caracteres e miniatura ausente. Medi com 11.005 itens e com miniatura ausente. **50 mil
   itens não foram semeados** (disco). E o "nome de 2.048 caracteres" é impossível de produzir: o
   `CHECK (length(titulo) BETWEEN 1 AND 250)` da migração 011 recusa antes — a cláusula da refutação
   é insatisfazível como está escrita, não é um defeito da tela.
4. **Harness de navegador não é a produção.** O `/static` é servido pelo nginx em produção e a
   aplicação não o monta; para rodar o playwright subi `tests/e2e/adv2_servidor.py` (a mesma app com
   `StaticFiles` montado) em `https://127.0.0.1:8158` com certificado autoassinado, porque
   `checar_escrita_sob_cookie` compara o `Origin` com `PLAT_URL_PUBLICA` literal e recusa 403 em
   http. As capturas e as medidas de primeira pintura do portão continuam sendo do time que
   construiu; eu só usei o navegador para o achado G2-9.
5. **Suíte inteira do catálogo: ordem importa.** `pytest tests/api/catalogo` (rodada única, 11 mil
   itens semeados) deu 5 falhas + 2 erros; rodando cada arquivo sozinho, 3 dessas falhas passam
   (`test_versoes`, `test_transferencia`, `test_relacoes` — as duas primeiras morrem com
   `401 sessao_expirada` em cliente de fixture de sessão). Registro como observação, não como
   veredito: pode ser acoplamento entre testes da própria suíte, e não consegui isolar a causa sem
   mexer em arquivo de outro time. As duas que se sustentam sozinhas são a do G2-8 e a de
   `test_documento::test_integridade...` (esta última é do item L5-05, fora deste grupo).
6. **Não olhei** paridade documental (`docs/PARIDADE.md` contra a doc 11.4 da Esri), i18n, nem o que
   os portões chamam de "captura": comparar imagem de tela com a doc do concorrente não é medida que
   eu consiga reproduzir com comando e saída.

## Como reproduzir tudo

```
bash /home/dev/plataforma/laco/trilha_ambiente.sh adv2
cd /home/dev/plataforma/wt/adv2 && ln -sfn /home/dev/plataforma/enterprise/venv venv
set -a; source /home/dev/plataforma/laco/var/trilha/adv2.env; set +a
venv/bin/pytest tests/api/catalogo/test_adversario_g2.py -q -rx          # 8 xfail = 8 achados vivos
# para o achado de tela (G2-9):
venv/bin/python -m uvicorn tests.e2e.adv2_servidor:app --host 127.0.0.1 --port 8158 \
  --ssl-keyfile k.pem --ssl-certfile c.pem   # certificado autoassinado de CN=127.0.0.1
PLAT_URL_PUBLICA=https://127.0.0.1:8158 venv/bin/pytest tests/e2e/test_adversario_g2_conteudo.py \
  -q -rx --base-url https://127.0.0.1:8158
sudo -u postgres psql -d iagro_sat -c 'DROP SCHEMA plat_tadv2 CASCADE; DROP SCHEMA plat_trabalho_tadv2 CASCADE'
```
