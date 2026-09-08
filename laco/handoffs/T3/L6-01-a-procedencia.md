# Handoff — item L6-01-a-procedencia-acervo (arquiteto + backend, passagem única)

**Objetivo.** Expor o acervo da casa (376 fontes registradas em `acervo.*` no servidor principal,
banco `iagro_sat` — MESMO Postgres que `plat`) como catálogo assinável só-leitura, com licença,
frescor, sha256, comando de reexecução e contagens; sem copiar dado, sem GRANT direto de escrita,
sem publicar fonte sem licença escrita (regra D17). Escopo real construído: `plat.acervo_ficha`
(view) + `GET /api/acervo` + `GET /api/acervo/{fonte_id}` + `POST /api/acervo/{fonte_id}/adicionar`.
O item formal `L6-01-a-procedencia-acervo` do `estado.json` está registrado numa forma mais abstrata
("o conector do acervo preenche o bloco de procedência a partir de acervo.fonte/objeto/endpoint",
com portão "a fixar pelo arquiteto no turno em que o item que a pediu entrar") — este handoff FIXA
o portão executado aqui (parágrafo seguinte) e entrega o mecanismo completo de ficha + adicionar; a
tela de navegação (`L6-01-c-tela-acervo`), a view por CAMADA de dado com RLS por assinatura
(`L6-01-b-view-so-leitura`) e a licença curada em vocabulário fechado (`L6-01-g-licenca-curada`)
continuam pendentes, como itens à parte no backlog.

**Confirmação de pré-requisito (instrução do dono).** `sudo -u postgres psql -d iagro_sat -c '\dn'`
confirma o schema `acervo` no MESMO banco/servidor de `plat` — nenhum bloqueio de servidor
diferente. `\dt acervo.*` e `\d` confirmam as 4 tabelas + 1 view descritas em `acervo/ACERVO.md`:
`acervo.fonte` (376 linhas), `acervo.objeto`, `acervo.camada_arquivo`, `acervo.endpoint`,
`acervo.v_completude` (376 linhas, 1:1 com `fonte`).

## Decisão de arquitetura (motivo, não moda)

`laco/decomposicao/L3L6_CONCEITO.md` B1 decide view `SECURITY INVOKER` com lista branca de colunas
e GRANT só na view para as camadas de DADO (`L6-01-b`, tabelas com geometria e potencial de coluna
sensível) — o motivo lido é disco a 98% e revogação por camada. Este item é mais simples: a ficha é
METADADO DE FONTE (376 linhas, sem geometria, sem coluna identificável de pessoa), então:

- `plat.acervo_ficha` também é `SECURITY INVOKER` (mesma convenção da casa), mas aqui isso exige
  GRANT SELECT direto em `acervo.fonte`/`acervo.v_completude` a `plat_app` — decisão deliberada,
  registrada no comentário da migração 021, porque a alternativa (view `SECURITY DEFINER` por
  omissão, sem grant nenhum no schema `acervo`) teria sido mais conservadora ainda. Nenhuma das
  duas dá GRANT à role `PUBLIC` (a leitura da instrução "sem GRANT em public" — lida como a role
  `PUBLIC`, não o schema `public`, que aqui nem entra: tudo fica em `acervo.*`/`plat.*`).
- Filtro `licenca IS NOT NULL AND btrim(licenca) <> ''` dentro da própria view (regra D17): medido
  hoje, **68 de 376 fontes** têm licença escrita — 308 ficam de fora, e o teste conta esse número.
- `GET /api/acervo/{fonte_id}` devolve 404 tanto para fonte inexistente quanto para fonte sem
  licença — a API nunca confirma a existência de uma fonte que não pode mostrar (mesma regra já
  usada em pastas/categorias de outro inquilino no catálogo).
- `POST /adicionar` cria um item `plat.item` tipo `conexao` (tipo já existia, criado no L0-04-i;
  esquema `1 -> 2` acrescenta o protocolo `"acervo"` ao vocabulário fechado, mesma regra de UPSERT
  do ADR 0004 §3 — versão só sobe se a nova for maior). `dados.parametros.fonte_id` é a referência;
  `dados.url` usa `url_http` (testada por HTTP) → `url` (bruta) → `acervo:<fonte_id>` (sintético,
  para as 9 fontes com licença mas sem nenhuma URL registrada) como último recurso, nunca vazio.
  Nada do dado do acervo é copiado; RLS de `plat.item` (`tenant_id = tenant_atual() AND
  pode_ler(id)`, já existente desde o ADR 0004) garante o isolamento por inquilino sem código novo.

## O que fiz

- `db/migracoes/021_acervo_ficha.sql` (aplicada, `sudo bash db/migrar.sh`): `GRANT USAGE ON SCHEMA
  acervo` + `GRANT SELECT` em `acervo.fonte`/`acervo.v_completude` a `plat_app`; `CREATE OR REPLACE
  VIEW plat.acervo_ficha WITH (security_invoker = true)`; `REVOKE ALL ... FROM PUBLIC` + `GRANT
  SELECT ... TO plat_app`; UPSERT do tipo `conexao` com `"acervo"` no enum de `protocolo`.
- `app/acervo/rotas.py` + `app/acervo/modelos.py`: as 3 rotas descritas acima, registradas em
  `app/main.py` (ver nota de concorrência abaixo). Reaproveita `plat.cota_itens`, `tipos.validar`,
  `item_json`/`item_ou_404`/`registrar_evento`/`jsonb` de `app.catalogo.comum` — nenhuma lógica de
  catálogo duplicada.
- `tests/api/test_acervo.py`: 6 casos — contagem exata de fontes de fora por falta de licença
  (`de_fora > 0`, medido 308), ficha batendo campo a campo com `acervo.fonte`, fonte sem licença
  nunca aparece (nem na ficha nem na lista, mesmo buscando pelo próprio `fonte_id`), fonte
  inexistente 404, `adicionar` cria item no `tenant_id` certo com RLS cruzada A→B confirmada (B
  recebe 404 no item de A), `adicionar` numa fonte sem licença = 404.
- `tests/api/cruzado_casos.py`: 3 casos novos na varredura A→B do L0-02 (campo novo
  `Preparacao.fonte_acervo`, populado em `preparar()` via `GET /api/acervo?limite=1` — o acervo é
  compartilhado, não pertence a A nem a B, então não há "fonte de B" para simular um ataque; o caso
  correto é `proprio=True` como `GET /api/tipos-item`, com `POST /adicionar` limpando o item criado
  via `_apagar_criado(("DELETE", "/api/itens/{id}"))`, igual ao padrão de `POST /api/papeis`).
- `tests/api/eventos_esperados.py`: `("POST", "/api/acervo/{fonte_id}/adicionar"): ["itens/adicionar"]`
  (o mesmo tipo de evento já usado por `POST /api/itens`; nenhum vocabulário novo no banco).
- `docs/PARIDADE.md`: seção "Acervo da casa" com 2 linhas (ficha de procedência; adicionar sem
  copiar), citando o Living Atlas 11.4 como referência Esri, estado `parcial` (mecanismo completo,
  sem tela — L6-01-c —, licença ainda texto livre — L6-01-g), **"testado por" marcado explicitamente
  como "sem adversário independente do turno"** — não usei o vocabulário `feito` porque a
  METODOLOGIA da casa exige adversário separado antes disso, e esta passagem não o rodou.
- `docs/openapi.json` regenerado (`make openapi`) só com as 3 rotas novas — conferido por
  `git diff` que nenhuma outra rota de trilha concorrente entrou no meu diff.

## Evidência (comando + saída literal)

```
$ sudo -u postgres psql -d iagro_sat -c "select count(*) total, count(*) filter (where licenca is not null and licenca <> '') as com_licenca from acervo.fonte;"
 total | com_licenca
-------+-------------
   376 |          68

$ venv/bin/pytest tests/api/test_acervo.py -m "not lento" -q   # sob flock .pytest.lock
......                                                                   [100%]
6 passed

$ venv/bin/pytest tests/api/test_cruzado.py -k acervo -m "not lento" -q   # sob flock .pytest.lock
...                                                                      [100%]
3 passed   # GET /api/acervo, GET /api/acervo/{fonte_id}, POST /api/acervo/{fonte_id}/adicionar
```

## `make check` — verde para o meu escopo; 2 falhas PRÉ-EXISTENTES e EXTERNAS ao item

Corri `flock .pytest.lock make check-rapido` (lint + sem-marcador + teste) na árvore compartilhada
do turno (outras 2-3 trilhas rodando a suíte inteira ao mesmo tempo, confirmado por `ps aux`).
Antes de eu adicionar os 3 casos cruzados e o evento declarado, a suíte reprovava exatamente nos 3
pontos esperados (rotas sem caso cruzado, rota sem evento declarado — ambos meus, corrigidos) mais
um terceiro já presente e não meu (`test_migrar_duas_vezes_nao_insere_linha`, sobre o arquivo de
OUTRA trilha). Depois da correção, rodei a suíte inteira de novo: restaram só 2 falhas, nenhuma
minha, com evidência de causa externa:

1. `test_rota_nao_cruza[GET-/api/itens/{id}]`: o dígest de B mudou ENTRE a chamada e a checagem
   (`5e0e46...` → `8cc9a9...`, 183 → 186 linhas) — outra sessão escreveu no inquilino `demo2`
   durante o teste. Rota pré-existente, não tocada por mim; reprova por corrida entre trilhas na
   mesma base, não por código.
2. `test_migrar_duas_vezes_nao_insere_linha`: `DIVERGENTE 021_arquivos: sha aplicado
   e441d9dc9... , arquivo 27fba31a7...` — o arquivo de outra trilha (`021_arquivos.sql`, hoje
   renomeado por ela para `022_arquivos.sql`) foi editado no disco DEPOIS de aplicado, no meio da
   suíte. Confirmado com `sha256sum` contra `plat.versao_migracao`. Nada meu.

Rodei os dois cenários isolados de novo depois (`-k acervo`) e os 3 casos do meu item passam sempre,
sozinhos ou dentro da suíte inteira. Não tornei a rodar a suíte inteira uma terceira vez porque, no
momento de fechar este handoff, havia 2-3 `make check-rapido` de outras sessões competindo pelo
`flock` (confirmado por `ps aux`) — esperar uma "rodada limpa" nesta janela seria arbitrário, e a
evidência acima já isola a causa como externa ao meu código, não como falha do item.

## Nota de concorrência (transparência, não é frescor de imprecisão)

Este é um repositório de trabalho ÚNICO compartilhado por várias trilhas simultâneas (não há
worktree por trilha). Em algum momento entre eu montar o `app/main.py` (import +
`rotas_acervo.router,` no `ROUTERS`) e commitar, outra trilha (`L0-12`, commit `6f034c3`, "Contrato
de API e limite de corpo por requisição") rodou `git commit` enquanto MINHA versão de `app/main.py`
estava no índice compartilhado (eu tinha usado `git update-index --cacheinfo` para isolar meu hunch
de `main.py` do de uma terceira trilha, `rotas_arquivos`, que editava o mesmo arquivo ao vivo) — o
resultado é que a integração de `rotas_acervo` em `app/main.py` (2 linhas: import +
`rotas_acervo.router,`) acabou dentro do commit `6f034c3`, não do meu `555cb00`. Conferido: (a)
`git show HEAD:app/main.py` já tinha as 2 linhas antes do meu commit; (b) meu commit não reincluiu
`app/main.py`; (c) `git diff --stat 6f034c3` mostra só `app/main.py` afetado por essa mistura, os
outros 9 arquivos do commit deles são só deles. Não reescrevi histórico (a regra da casa proíbe
rebase/amend de commit alheio). Efeito prático: nenhum — o código está correto, testado e commitado
duas vezes por engano, não duplicado nem quebrado. Registro aqui para o gerente decidir se quer
mencionar no ledger do turno.

## Riscos

- Licença ainda é o texto livre de `acervo.fonte.licenca` (32 valores distintos, muitos "dado
  público (licença não declarada na fonte)"), não o vocabulário fechado que `L3L6_CONCEITO.md` B3 e
  o item `L6-01-g-licenca-curada` preveem. A ficha expõe o texto como está; nenhuma tela de cliente
  deve tratar isso como "licença confirmada" antes do L6-01-g rodar.
- `numero_tabelas`/`registros_estimados` vêm de `acervo.fonte.tabelas`/`linhas_est` — são os números
  do REGISTRO da casa (já com a ressalva de estimativa em `ACERVO.md`), não recontados aqui; a
  ficha não roda `COUNT(*)` on-demand (ficaria caro por fonte a cada leitura).
- Sem tela (`L6-01-c`): só API. Sem adversário independente do turno — as 6 + 3 provas são minhas
  mesmas, não de um papel separado; portanto o estado no `PARIDADE.md` é `parcial`, nunca `feito`.
- Não toquei `estado.json` (registro compartilhado do laço, sem lock próprio como o `.pytest.lock`;
  editá-lo ao vivo no meio de outras trilhas escrevendo nele pareceu mais arriscado que deixar para
  o gerente consolidar no fechamento do turno).

## Pendências / para o próximo papel

- `L6-01-c-tela-acervo` (frontend + backend + cartógrafo): tela "Acervo" consumindo estas 3 rotas.
- `L6-01-g-licenca-curada` (dados + pesquisa): tabela `plat.acervo_licenca` com vocabulário fechado
  (B3), substituindo o texto livre hoje exposto.
- `L6-01-b-view-so-leitura` continua sendo o item que resolve leitura de DADO por camada (CAR,
  BDGD, etc.) com RLS por assinatura — este item (`L6-01-a`) não mexeu nisso, só na ficha da fonte.
- Gerente: decidir se quer registrar no ledger a nota de concorrência do `app/main.py` acima.