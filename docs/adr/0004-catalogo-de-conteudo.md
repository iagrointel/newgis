# ADR 0004 — Catálogo de conteúdo (item L0-03-catalogo e seus 12 filhos L0-03-a … L0-03-l)

Estado: **aceito para construção** (turno T2, trilha de preparação; construção começa quando as trilhas A e B
comitarem `003`/`005` e `004`). Autor: arquiteto. Data: setembro de 2026. Migração deste item: `006_catalogo.sql`.
Código: `app/catalogo/*`, `web/js/catalogo/*`, `web/conteudo*.html`, `web/admin/categorias.html`.

Este ADR é o "Content" do Portal traduzido para a pilha aberta: uma tabela de item para todo tipo de conteúdo, com
registro de tipos, versões imutáveis, dependências declaradas, compartilhamento decidido por uma função usada na RLS,
busca no próprio PostgreSQL, pastas hierárquicas, favoritos, lixeira, proteção, status, transferência de dono,
eventos, miniaturas e limites declarados. Cada decisão traz o motivo (MEDIDO nesta máquina, LIDO em código que já
roda aqui, ou DOCUMENTO oficial com URL testada por HTTP no anexo B) e o custo de mudar depois.

O que este ADR **lê e não redefine**: ADR 0001 (schema `plat`, `plat_app`, RLS `FOR ALL`, migrações imutáveis,
módulos ES, `/saude`), ADR 0002 (grupos `plat.grupo`/`plat.grupo_membro`, papéis de grupo, privilégios
`conteudo.*`/`compartilhar.*`, escopos de token, `plat.evento`/`evento_registrar`, contrato de erro
`{erro, mensagem, detalhe?, req_id}`, paginação `limite/deslocamento` + `total`, teste cruzado A→B), ADR 0003
(fila `plat.job`, decorador `@tarefa`, periódicos do inquilino técnico `plataforma`, convenção de resultado
`{"item_id": …}`), `L0_CONCEITO.md` (D1 UUID, D2 tabela única + registro de tipos com JSON Schema, D3 schema por
inquilino, D7 compartilhamento, D8 busca, D9 dependências, D10 lixeira/proteção/status/versões, D13 Garage, D14
eventos), `L1_CONCEITO.md` (C1 espelho `plat.raster_item`, C2 id estável e objeto por sha256, C12 copiado ×
referenciado), `L2_CONCEITO.md` (C1 documento de mapa por uuid, C2 estilo MapLibre), `L5_CONCEITO.md` (D1 sem
framework, D2 envelope de documento com ULID por nó, D3 `plat.item_versao`) e o handoff `T1/21_esri.md` (seções 2
e 3.2: o que o Portal faz, limites literais, dez irritações da migração).

## 0. O que foi medido antes de decidir (05/09/2026, esta máquina, schema temporário `med0004` apagado no fim)

Corpus sintético: 10.000 itens em 2 inquilinos, 7 tipos, títulos com acento, 3 tags por item, resumo e descrição de
~500 caracteres; 50 grupos, 2.500 itens compartilhados com grupo; 30.000 relações (3 por item); `extent` em 4326.
Comando: `sudo -u postgres psql -d iagro_sat` com o SQL do anexo A por stdin (regra da casa). `p50`/`p95` sobre 30
execuções (20 onde indicado), tempo de `EXECUTE` dentro de plpgsql, banco compartilhado em uso normal (RAM disponível
2 GB no momento, `free -g`).

| medida | valor | o que sustenta |
|---|---|---|
| `array_to_string` é `STABLE` (`pg_proc.provolatile = 's'`); coluna gerada com ela **não compila** (`generation expression is not immutable`) | erro reproduzido | seção 7: a migração cria `plat.tags_texto(text[]) IMMUTABLE` antes da coluna `busca` |
| `to_tsvector(regconfig, text)` `IMMUTABLE`; `unaccent(text)` `STABLE` | `pg_proc` | por isso o `unaccent` entra como **dicionário** da configuração `plat.pt_sem_acento`, não como função na expressão |
| busca `municipio` (sem acento) sobre coluna `tsvector` gerada com pesos, GIN, ordenada por `ts_rank_cd` + `modificado_em`, 50 primeiros | p50 1,93 ms · p95 2,41 ms | D8; portão do L0-03-c pede ≤ 200 ms p95 |
| `Município` (acento, maiúscula) e `municipio` acham o mesmo conjunto | 1.429 = 1.429 | configuração `portuguese` + dicionário `unaccent` |
| só `ts_rank_cd`: item cujo título é exatamente `Município` **não** vem em 1º (empata em 1,0 com "Município leste 7") | reproduzido | seção 7: chave de ordenação `lower(unaccent(titulo)) = termo` antes do rank (irritação 9) |
| com a chave de título exato | 1º = `Município`; p95 2,59 ms | idem |
| reforço de status somado ao rank (`+0,25` autoritativo, `−0,25` obsoleto) | p95 2,71 ms | L0-03-h "autoritativo sobe na busca" |
| trigram `titulo % 'municpio'` (GIN `gin_trgm_ops`, limiar 0,3), 50 primeiros | p50 19,6 ms · p95 20,9 ms · 1.172 acham | D8: trigram como reserva quando o FTS devolve 0 |
| lista por tipo sem busca (índice parcial `tenant_id, tipo, modificado_em DESC WHERE apagado_em IS NULL`) | p95 2,59 ms | portão do L0-03-a pede < 100 ms |
| `count(*)` do mesmo filtro | p95 0,05 ms | `total` na resposta custa nada nesta escala |
| `pode_ler` por `EXISTS` em `item_grupo × grupo_membro` (usuário 7), varrendo 10.000 itens sem cache | p50 2,06 ms · p95 3,17 ms · 2.500 visíveis | D7: sem cache de autorização e mesmo assim barato |
| `pode_ler` + busca + ordenação, 50 primeiros | p95 3,11 ms | idem |
| filtro por `extent && bbox` (GIST) + ordenação | p95 2,93 ms | filtro lateral "localização" |
| página 100 (5.000 itens adiante): `OFFSET 4950` × cursor por chave `(modificado_em, id)` | 2,03 ms × 3,39 ms | seção 13: nesta escala o `OFFSET` **não** perde; o cursor entra por estabilidade de página, não por velocidade |
| `usado_por` profundidade 2 (CTE recursiva, índice em `destino`) | p95 0,97 ms · 12 linhas | portão do L0-03-i pede < 50 ms |
| fecho transitivo de dependentes com corte de ciclo por caminho, 6 níveis | p95 2,82 ms · 839 linhas | ordem de exclusão e detecção de ciclo no gatilho |
| `UPDATE` de título (recalcula `tsvector`, GIN busca, GIN trigram) | média 0,51 ms · máx 6,85 ms | índice na mesma transação custa menos de 7 ms |
| gravação de versão (`to_jsonb(item)` + `digest(sha256)` do pgcrypto) | 0,12 ms por versão | portão do L0-03-l pede ≤ +5 ms por PUT |
| tamanho com 10.000 itens | tabela 37 MB · GIN busca 5,5 MB · GIN trigram 5,5 MB · GIST 704 kB | cota (D16): o catálogo em si é pequeno |
| `jsonschema` 4.26.0 na venv, Draft 2020-12, documento de 60 campos | 0,86 ms por validação; erro devolve o caminho `['campos', 60, 'nome']` | D2: 422 com caminho do campo sem dependência nova |
| bibliotecas na venv | `Pillow` 12.2.0, `pillow_heif` 1.5.0, `markdown` 3.10.2, `markdown-it-py` 3.0.0, `jsonschema` 4.26.0; **ausentes**: `bleach`, `nh3`, cliente S3 | seções 2.4 (descrição), 11 (miniatura), 11.3 (contrato com L0-11) |
| Garage `plataforma-garage` ativo (`systemctl is-active`), `:3900` responde 403 sem assinatura | ativo | D13; a entrega do objeto passa sempre pela API |

O que **não** foi medido e fica declarado: busca com 50 mil itens (o adversário do L0-03-f abre a tela com 50 mil; o
testador semeia e mede), miniatura gerada por job (depende do L0-11 e do renderizador do L2-01), e concorrência de
20 clientes revogando/abrindo o mesmo link (refutação do L0-03-e; é o testador que mede).

## 1. Resumo das decisões (uma linha cada; o detalhe está na seção indicada)

1. **Uma tabela `plat.item`** para todo tipo de conteúdo, `id uuid` gerado no banco, estável para sempre, referência
   entre itens só por uuid (D1, D2) — seção 2.
2. **Registro de tipos `plat.tipo_item`** com família, JSON Schema do campo `dados` (Draft 2020-12, validado no servidor
   com `jsonschema`, 422 com o caminho do campo), módulo do front que abre o tipo; 12 tipos nascem na 006, cada linha
   futura registra o seu por migração (D19) — seção 3.
3. **Descrição em Markdown guardada como texto e convertida no servidor** para HTML por lista de permissão própria
   (sem `bleach`/`nh3` na venv), `<script>` e atributos de evento nunca sobrevivem — seção 2.4.
4. **`plat.item_versao` imutável** (gatilho `AFTER INSERT/UPDATE` grava o retrato do metadado + `dados` com sha256;
   restaurar cria versão nova; 50 versões vivas por item, compactação pelo periódico) — seção 4.
5. **`plat.item_relacao(origem, destino, tipo)`** com vocabulário fechado de 11 tipos, gravada por quem cria o vínculo,
   ciclo recusado no gatilho, `usado_por`/`criado_a_partir_de`, ordem de exclusão calculada, aviso ao sobrescrever
   (D9; o nome `item_relacao` é o do portão congelado do L0-03-i; "dependência" é o conceito) — seção 5.
6. **Compartilhamento em cinco níveis** (`privado`, `grupos`, `inquilino`, `link`, `publico`), combináveis como na
   Esri, decididos por **`plat.pode_ler(uuid)`/`plat.pode_editar(uuid)`** usadas na RLS de `item` e de toda tabela
   dependente; 404 para item sem acesso; link por token ≥ 32 hex, revogável, com validade e contagem, sem cache;
   `publico` só com `tenant.config.auth.compartilhar_publico = true` (D24) — seção 6.
7. **Busca no PostgreSQL**: configuração `plat.pt_sem_acento` (portuguese + unaccent), coluna `busca tsvector`
   gerada `STORED` com pesos A/B/C/D, GIN; trigram no título como reserva; texto livre por `websearch_to_tsquery`
   (nunca `to_tsquery` com texto do usuário); sintaxe por campo por gramática própria; chave de título exato antes do
   rank; reforço de status; filtros laterais inclusive `extent` — seção 7.
8. **Pastas hierárquicas por inquilino** (profundidade ≤ 5, nome único entre irmãs, visíveis a quem vê o item),
   **tags** livres no item, **categorias** do inquilino em árvore de 3 níveis/200 nós com modelos ISO 19115 (19
   categorias temáticas) e INSPIRE (34 temas), **classificação** JSON opcional, **favoritos** por usuário — seção 8.
9. **Lixeira de 30 dias** por exclusão lógica (`apagado_em`), visível só quando a rota da lixeira liga
   `plat.lixeira = on` na transação; expurgo por periódico; **proteção** é campo e o superadmin sempre desliga com
   evento; **status** `autoritativo` (só admin, liga proteção, sobe na busca) e `obsoleto` (dono ou admin, desce) — seção 9.
10. **Transferência de dono** com pré-checagem (`simular=true`) que lista o que vai falhar, arrasta vistas/estilo/
    arquivo de origem, não arrasta mapas que usam a camada, preserva uuid, compartilhamentos e pastas — seção 10.
11. **Eventos**: vocabulário `itens/*`, `pastas/*`, `categorias/*`, `compartilhamento/*`, `favoritos/*`,
    `lixeira/*` em `plat.evento_tipo`; toda rota de escrita grava 1 evento na mesma transação (D14; `plat.evento` é a
    caixa de saída que L0-10 lê e L7-08 entrega) — seção 12.
12. **Miniatura** 600×400 PNG: envio pela API (Pillow, limite de 10 MB e 25 megapixels contra bomba de descompressão)
    ou geração por job `catalogo.miniatura` no worker; objeto no Garage pelo contrato do L0-11, entregue sempre pela
    API com `pode_ler` — seção 11.
13. **Limites** em `app/limites.py` (seção `# --- catálogo (L0-03)`), aplicados por validação e gerados em
    `docs/LIMITES.md` (L0-12) — seção 14.
14. **API** em `/api/itens`, `/api/pastas`, `/api/categorias`, `/api/favoritos`, `/api/lixeira`, `/api/tipos-item`,
    `/api/compartilhado/{token}`, `/api/publico/itens/{id}`; lista com `limite/deslocamento` (D18) **e** `cursor`
    opaco por chave (estabilidade de página com 10 mil itens sendo editados) — seção 13.
15. **Telas**: `/conteudo` (abas Meu conteúdo · Favoritos · Meus grupos · Inquilino · Lixeira; vistas tabela/lista/
    grade; filtros laterais; seleção em massa), `/conteudo/{id}` (Visão geral · Dados · Configurações · Versões · Uso),
    diálogo Compartilhar com árvore de dependências, `/admin/categorias` — seção 15.
16. **Testes obrigatórios** (seção 16) e **paridade** declarada (seção 17).

---

## 2. Modelo `plat.item` (L0-03-a)

### 2.1 DDL normativo (trecho da `006_catalogo.sql`; idempotente; aplicada como `postgres`)

```sql
CREATE TABLE IF NOT EXISTS plat.item (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),          -- D1: opaco, estável, nunca reatribuído
  tenant_id          int NOT NULL REFERENCES plat.tenant(id),
  tipo               text NOT NULL REFERENCES plat.tipo_item(nome),        -- seção 3
  titulo             text NOT NULL CHECK (length(titulo) BETWEEN 1 AND 250),
  resumo             text CHECK (length(resumo) <= 2048),                  -- snippet da Esri, mesmo limite literal
  descricao          text CHECK (length(descricao) <= 65536),              -- Markdown guardado como texto (2.4)
  descricao_html     text,                                                  -- convertido e saneado no servidor (2.4)
  tags               text[] NOT NULL DEFAULT '{}'
                     CHECK (cardinality(tags) <= 50 AND plat.tags_validas(tags)),   -- cada uma 1..128, sem vírgula
  creditos           text CHECK (length(creditos) <= 2048),                -- accessInformation
  termos_de_uso      text CHECK (length(termos_de_uso) <= 65536),          -- licenseInfo (Markdown, mesma conversão)
  dono_id            int NOT NULL REFERENCES plat.usuario(id),
  pasta_id           uuid REFERENCES plat.pasta(id) ON DELETE SET NULL,   -- NULL = raiz
  extent             geometry(Polygon, 4326)
                     CHECK (extent IS NULL OR (ST_XMin(extent) >= -180 AND ST_XMax(extent) <= 180
                                               AND ST_YMin(extent) >= -90 AND ST_YMax(extent) <= 90
                                               AND ST_IsValid(extent))),
  extent_origem      text CHECK (extent_origem IN ('dado','usuario','inquilino')),
  miniatura_chave    text,                                                  -- objeto no Garage (seção 11); NULL = sem
  miniatura_sha256   text,
  dados              jsonb NOT NULL DEFAULT '{}'::jsonb,                   -- validado pelo JSON Schema do tipo
  acesso             text NOT NULL DEFAULT 'privado' CHECK (acesso IN ('privado','inquilino','publico')),  -- seção 6
  status             text CHECK (status IN ('autoritativo','obsoleto')),   -- NULL = sem status
  protegido          boolean NOT NULL DEFAULT false,
  classificacao      jsonb,                                                 -- seção 8.4; validado pelo esquema do inquilino
  categorias         uuid[] NOT NULL DEFAULT '{}' CHECK (cardinality(categorias) <= 20),   -- seção 8.3
  origem             text NOT NULL DEFAULT 'hospedado' CHECK (origem IN ('hospedado','referenciado')),  -- L1 C12 / Esri 2.9
  url                text CHECK (url IS NULL OR (length(url) <= 2048 AND url ~ '^https?://')),  -- item por URL
  tamanho_bytes      bigint NOT NULL DEFAULT 0,                             -- soma dos objetos e da tabela física (cota)
  versao_atual       int NOT NULL DEFAULT 0,                               -- seção 4
  versao_publicada   int,                                                   -- L5 D3; NULL = a atual
  pontuacao          smallint NOT NULL DEFAULT 0 CHECK (pontuacao BETWEEN 0 AND 10),  -- 2.6
  criado_por         int REFERENCES plat.usuario(id),
  criado_em          timestamptz NOT NULL DEFAULT now(),
  modificado_por     int REFERENCES plat.usuario(id),
  modificado_em      timestamptz NOT NULL DEFAULT now(),
  apagado_em         timestamptz,                                           -- lixeira (seção 9)
  apagado_por        int REFERENCES plat.usuario(id),
  busca              tsvector GENERATED ALWAYS AS (
                       setweight(to_tsvector('plat.pt_sem_acento', coalesce(titulo, '')), 'A') ||
                       setweight(to_tsvector('plat.pt_sem_acento', coalesce(plat.tags_texto(tags), '')), 'B') ||
                       setweight(to_tsvector('plat.pt_sem_acento', coalesce(resumo, '')), 'C') ||
                       setweight(to_tsvector('plat.pt_sem_acento', coalesce(descricao, '')), 'D')) STORED
);
CREATE INDEX IF NOT EXISTS ix_item_lista   ON plat.item (tenant_id, tipo, modificado_em DESC, id DESC) WHERE apagado_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_item_dono    ON plat.item (tenant_id, dono_id, modificado_em DESC) WHERE apagado_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_item_pasta   ON plat.item (pasta_id) WHERE apagado_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_item_lixeira ON plat.item (tenant_id, apagado_em) WHERE apagado_em IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_item_busca   ON plat.item USING gin (busca);
CREATE INDEX IF NOT EXISTS ix_item_titulo_trgm ON plat.item USING gin (titulo gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_item_tags    ON plat.item USING gin (tags);
CREATE INDEX IF NOT EXISTS ix_item_categorias ON plat.item USING gin (categorias);
CREATE INDEX IF NOT EXISTS ix_item_extent  ON plat.item USING gist (extent) WHERE extent IS NOT NULL;
```

Funções auxiliares criadas **antes** da tabela (a coluna gerada exige `IMMUTABLE`; MEDIDO na seção 0):

```sql
CREATE OR REPLACE FUNCTION plat.tags_texto(text[]) RETURNS text
  LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT array_to_string($1, ' ') $$;
CREATE OR REPLACE FUNCTION plat.tags_validas(text[]) RETURNS boolean
  LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT coalesce(bool_and(length(t) BETWEEN 1 AND 128 AND t !~ '[,\n\r\t]' AND t = btrim(t)), true) FROM unnest($1) t $$;
```

`tags_texto` é declarada `IMMUTABLE` sobre `array_to_string` (que o catálogo marca `STABLE` por causa de tipos cuja
saída depende de configuração, como datas); para `text[]` a saída não depende de nada e a declaração é correta.
Custo de mudar: nenhum (a função é uma linha).

### 2.2 Regras que valem para qualquer caminho (gatilhos, não código de rota)

| regra | mecanismo | erro |
|---|---|---|
| `id` nunca muda; `PUT` que traga `id`, `tenant_id`, `criado_em`, `criado_por`, `versao_atual`, `tamanho_bytes`, `pontuacao`, `busca` ou `apagado_*` diferentes | `BEFORE UPDATE` `plat.tg_item_imutaveis` | `RAISE 'campo_imutavel'` → `400 campo_nao_editavel {detalhe: {campo}}` |
| `dono_id` só muda pela rota de transferência (seção 10) | mesmo gatilho: `NEW.dono_id <> OLD.dono_id` exige `current_setting('plat.transferencia', true) = 'on'` | `RAISE 'dono_so_por_transferencia'` → `400` |
| `dono_id`, `criado_por`, `modificado_por`, `apagado_por`, `pasta_id`, `categorias[]` do **mesmo inquilino** | `BEFORE INSERT/UPDATE` `plat.tg_item_coerente` (subconsultas em `usuario`, `pasta`, `categoria` filtradas por `tenant_id = NEW.tenant_id`) | `RAISE 'usuario_de_outro_inquilino'` (404, código já mapeado em `app/auth/comum.py`) · `'pasta_de_outro_inquilino'` (404) · `'categoria_de_outro_inquilino'` (404) |
| `dados` válido pelo JSON Schema do tipo | validação em Python **antes** do `INSERT/UPDATE` (seção 3.3); o banco guarda só `jsonb_typeof(dados) = 'object'` como CHECK | `422 dados_invalidos {detalhe: [{campo, erro}]}` |
| `modificado_em`/`modificado_por` sempre atualizados | `BEFORE UPDATE` `plat.tg_item_modificado` (`now()`, `plat.usuario_atual()`), salvo quando só `tamanho_bytes` muda (medição de cota não é edição) | — |
| `protegido = true` impede exclusão lógica | `BEFORE UPDATE OF apagado_em` se `NEW.apagado_em IS NOT NULL AND OLD.protegido` e `current_setting('plat.superadmin', true) <> 'on'` | `RAISE 'item_protegido'` → `409 item_protegido {mensagem: "desligue a proteção na aba Configurações"}` |
| `status = 'autoritativo'` liga `protegido` | `BEFORE UPDATE OF status`: `NEW.protegido := true` | — (regra literal da Esri, E12-configitem) |
| `acesso = 'publico'` exige o inquilino autorizar | `BEFORE INSERT/UPDATE OF acesso`: consulta `tenant.config->'auth'->>'compartilhar_publico'` | `RAISE 'publico_desligado'` → `400 publico_desligado` |
| versão gravada a cada edição de metadado ou `dados` | `AFTER INSERT OR UPDATE OF titulo, resumo, descricao, tags, creditos, termos_de_uso, extent, dados, categorias, classificacao, url` → seção 4 | — |
| pontuação recalculada | mesmo gatilho de versão, antes: `NEW.pontuacao := plat.item_pontuacao(NEW)` (2.6) | — |

Tudo o que é regra de negócio testável fica no banco porque o L2-03 (edição), L2-08 (migração), L5 (construtores),
L6 (conectores) e a CLI escrevem em `item` por caminhos que não passam pelas rotas deste item (L2 C5: "uma porta de
escrita e gatilhos para o que tem de valer por qualquer caminho"). Custo de mudar uma regra: uma migração com
`CREATE OR REPLACE FUNCTION` do gatilho.

### 2.3 Nomes dos campos e a tradução Esri (para o conector L2-08/L6 não inventar mapa)

| REST Esri | `plat.item` | nota |
|---|---|---|
| `id` (32 hex) | `id` (uuid) | conector gera `uuid5(namespace do inquilino, id Esri)` (D1) |
| `title` · `snippet` · `description` · `tags` | `titulo` · `resumo` · `descricao` · `tags` | limite de `snippet` = 2.048, literal |
| `accessInformation` · `licenseInfo` | `creditos` · `termos_de_uso` | |
| `extent` `[[xmin,ymin],[xmax,ymax]]` · `spatialReference` | `extent` (Polygon 4326) | o CRS do dado fica no `dados` do tipo (D4) |
| `type` · `typeKeywords` | `tipo` · `dados.palavras_chave_tipo` (só nos tipos que o conector preenche) | |
| `owner` · `ownerFolder` · `created` · `modified` | `dono_id` · `pasta_id` · `criado_em` · `modificado_em` | datas ISO 8601 UTC, não UNIX ms |
| `access` (private/shared/org/public) | `acesso` + `item_grupo` + `compartilhamento_link` | `shared` = há linhas em `item_grupo` |
| `protected` · `contentStatus` | `protegido` · `status` | |
| `categories` · `properties` · `url` · `size` | `categorias` · `dados` · `url` · `tamanho_bytes` | |
| `scoreCompleteness` | `pontuacao` (0-10) | 2.6 |
| `numViews` · `numComments` · `numRatings` · `avgRating` · `culture` | fora (seção 17) | uso vem de `log_acesso` (aba Uso) |

### 2.4 Descrição e termos de uso: Markdown guardado, HTML gerado e saneado no servidor

Opções: (a) guardar HTML do editor e sanear com `bleach`/`nh3` (ausentes na venv; instalar é do gerente do item e
o guardrail diz "não instalar" nesta preparação); (b) guardar Markdown, converter no navegador com biblioteca vendida
(`marked`, MIT, ~40 kB, regra 3 do ADR 0001) e sanear no navegador; (c) guardar Markdown, converter no servidor com
`markdown` 3.10.2 (presente) e passar o HTML por **lista de permissão própria** sobre `html.parser` da biblioteca
padrão, gravando o resultado em `descricao_html`.

Decisão: **(c)**. Motivo: o texto sai por três caminhos (tela do item, catálogo OGC Records do L0-09-d, exportação)
e só o servidor está em todos; a refutação do L0-03-a ("descrição com `<script>`") tem de ser 4xx ou texto inerte
independentemente do cliente; `markdown` já está na venv e a lista de permissão cabe em ~80 linhas testáveis
(`app/catalogo/texto.py`). Lista de permissão: `p, br, hr, h2, h3, h4, strong, em, del, code, pre, blockquote, ul, ol,
li, a[href], img[src, alt], table, thead, tbody, tr, th, td`; `href`/`src` só `https://`, `http://` ou caminho
relativo que comece por `/api/` (miniaturas e anexos da própria plataforma); qualquer outra tag é removida com o
conteúdo (`script`, `style`, `iframe`, `object`) ou só a tag (`div`, `span`, `font`); atributos `on*`, `style`,
`javascript:` e `data:` nunca passam. Conversão com extensões `tables` e `fenced_code` apenas; `md_in_html` e HTML cru
desligados (o conversor recebe `safe_mode` inexistente na 3.x, por isso o saneador é obrigatório e não opcional).
`descricao` (texto) e `descricao_html` são gravados juntos na mesma transação; `GET` devolve os dois; `PUT` aceita só
`descricao`. Custo de mudar: trocar o saneador por `nh3` quando entrar na venv = 1 função; o dado guardado (Markdown)
não muda.

### 2.5 Extent

Sempre `geometry(Polygon, 4326)` (D4), com origem declarada: `dado` (calculado pela ingestão/L1: `ST_Envelope` do
dado reprojetado), `usuario` (desenhado ou digitado na aba Configurações: `[xmin, ymin, xmax, ymax]`), `inquilino`
(`tenant.config.centro/zoom` convertidos, botão "usar o extent da organização"). Regras: `xmin < xmax` e `ymin <
ymax` (`400 extent_invalido`); extent que cruza o antimeridiano é recusado nesta versão (Brasil não cruza; registrado
como fora). Filtro `bbox` da busca é `extent && ST_MakeEnvelope(...)` (MEDIDO p95 2,93 ms).

### 2.6 Pontuação de informação (0-10)

Um ponto por campo preenchido: `titulo` (sempre), `resumo`, `descricao` (≥ 100 caracteres), `tags` (≥ 3),
`creditos`, `termos_de_uso`, `extent`, `miniatura_chave`, `categorias` (≥ 1), `dados.procedencia.fonte` (L0-09-a
preenche; até lá vale se existir). Função SQL `plat.item_pontuacao(plat.item) RETURNS smallint`, recalculada no
gatilho de versão. A tela mostra "6 de 10" e a lista de sugestões (o que falta). É o `scoreCompleteness` da Esri
sem os pesos secretos dela: os dez campos estão escritos aqui e no MANUAL.

### 2.7 O que é `dados` por família (contrato de uso para as outras linhas)

`dados` é o único lugar em que uma linha futura guarda o que é específico do seu tipo (D19: "item de outra linha que
precise de coluna nova em `item` está errado"). O JSON Schema do tipo (seção 3) valida na API; o que aponta para
dado físico (tabela PostGIS, coleção pgstac, objeto) é referência por nome/uuid dentro de `dados`, nunca cópia.

---

## 3. Registro de tipos `plat.tipo_item` (L0-03-a; D2 e D19)

### 3.1 DDL

```sql
CREATE TABLE IF NOT EXISTS plat.tipo_item (
  nome           text PRIMARY KEY CHECK (nome ~ '^[a-z][a-z0-9_]{1,40}$'),
  familia        text NOT NULL CHECK (familia IN ('camada','raster','mapa','app','painel','formulario','fluxo','rede',
                                                  'arquivo','ferramenta','documento')),
  rotulo         text NOT NULL,                        -- "Camada vetorial" (o que a tela mostra)
  descricao      text NOT NULL,
  esquema        jsonb NOT NULL,                       -- JSON Schema Draft 2020-12 do campo item.dados
  esquema_versao int NOT NULL DEFAULT 1,
  icone          text NOT NULL,                        -- nome do ícone em web/js/catalogo/icones.js (frontend deste item)
  modulo_front   text NOT NULL,                        -- '/static/js/catalogo/tipos/camada_vetorial.js'
  abre_em        text[] NOT NULL DEFAULT '{}',         -- {'mapa','tabela','app'}: botões "Abrir em"
  tem_dado_fisico boolean NOT NULL DEFAULT false,      -- expurgo apaga tabela/objetos (seção 9)
  linha_dona     text NOT NULL,                        -- 'L0-04', 'L1-01', ...: quem completa o esquema
  criado_em      timestamptz NOT NULL DEFAULT now()
);
-- vocabulário da plataforma: sem RLS; plat_app só lê (REVOKE INSERT/UPDATE/DELETE); muda por migração
```

Sem `tenant_id` de propósito: tipo é vocabulário da plataforma, igual a `privilegio` e `evento_tipo`. A hipótese do
L0-03-a diz "tipo_item por inquilino"; a decisão aqui é **um registro global**, porque (a) o módulo do front e o
esquema são código, não dado do inquilino; (b) tipo por inquilino obrigaria o conector, a busca por `tipo:` e a
paridade a lidar com N vocabulários; (c) o que o inquilino personaliza são categorias e classificação (seção 8). O
portão do L0-03-a ("RLS em item, tipo_item por inquilino") é lido como "RLS em `item`; `tipo_item` sem dado de
inquilino", e o adversário do item confere que `tipo_item` não carrega nome de inquilino nem é editável por `plat_app`.
Custo de mudar: acrescentar `tenant_id NULL` (tipo global) e RLS por `tenant_id IS NULL OR tenant_id = tenant_atual()`
em uma migração; nenhuma rota muda.

### 3.2 Os 12 tipos que a 006 registra (esquema mínimo; quem completa e em que linha)

| `nome` | família | esquema mínimo de `dados` na 006 (todos com `additionalProperties: false` nesta versão) | completa em | `abre_em` | dado físico |
|---|---|---|---|---|---|
| `camada_vetorial` | camada | `{schema: string (d_<slug>), tabela: string (c_<uuid16>), geometria: enum[Point…MultiPolygon, nenhuma], srid: int 1..999999, campos: [{nome, tipo, alias?}] ≤ 500, fonte: enum[hospedada, referenciada], edicao?: {habilitada: bool}}` | L0-04 (ingestão), L2-03 (edição), L2-04 (serviços) | mapa, tabela | sim |
| `vista_de_camada` | camada | `{camada_id: uuid, filtro?: objeto CQL2-JSON (L2 C7), campos_ocultos?: [string], extent?: bbox}` | L0-04-j | mapa, tabela | sim (VIEW) |
| `raster` | raster | `{colecao: string, stac_id: string, perfil: enum[visual, cientifico, referencia], origem: enum[copiado, referenciado], srid_nativo: int, bandas?: [{nome, nome_comum?}]}` (L1 C1/C2/C12) | L1-01 | mapa | sim (pgstac + objeto) |
| `mapa` | mapa | `{esquema_versao: int, corpo: objeto}` — o corpo é o documento de mapa do L2 C1 (referências só por uuid) | L2-01, L5-05 | mapa | não |
| `cena` | mapa | idem `mapa` (documento de cena, L2-17) | L2-09/L2-17 | cena | não |
| `estilo` | documento | `{esquema_versao: int, corpo: objeto}` com `corpo` = MapLibre Style Spec + bloco `plat_construtor` (L2 C2) | L2-02, L5-27 | — | não |
| `app` | app | envelope do L5 D2: `{tipo: "app", esquema_versao: int, corpo: objeto}` | L5-01 | app | não |
| `painel` | painel | envelope do L5 D2 com `tipo: "painel"` | L5-03 | app | não |
| `formulario` | formulario | envelope do L5 D2 com `tipo: "formulario"` (+ XLSForm como troca, L5 D8) | L5-04, L2-07 | app | não |
| `fluxo` | fluxo | envelope do L5 D2 com `tipo: "fluxo"` (grafo JSON, L5 D9) | L5-02 | app | não |
| `rede` | rede | `{camadas: {nos: uuid, arestas: uuid, equipamentos?: uuid}, regras_versao: int}` | L4-01 | mapa | sim (tabelas L4) |
| `conexao` | ferramenta | `{protocolo: enum[wms, wfs, wmts, ogc_api, esri_rest, postgres_fdw, s3, http], url: string, credencial_id?: uuid, parametros?: objeto}` — segredo nunca em `dados` (fica no cofre do L0-04-i) | L0-04-i, L6-02 | — | não |
| `arquivo` | arquivo | `{chave: string (Garage), sha256: string, bytes: int, content_type: string, nome_original: string}` | L0-11, L0-04-a | — | sim (objeto) |
| `modelo_amc` | ferramenta | `{esquema_versao: int, fatores: [{camada_id: uuid, criterio: string, peso?: number}] ≤ 50, metodo: enum[soma_ponderada, ahp, topsis]}` | L3-01 | app | não |

São 14 linhas porque `vista_de_camada` e `cena` entram junto (o L2 C1 obriga o L0-03-a a aceitar `cena` e
`vista_de_camada` desde já). Tipos que o L2 C1 também cita (`mapa_base`, `layout`, `notebook`, `parquet`, `selecao`,
`anotacao`) entram pela migração do item que os cria, com o esquema dele: não se registra tipo sem dono.

### 3.3 Onde vive o esquema e como valida

- Fonte de verdade: a **migração** (o JSON do esquema está literal na `006_catalogo.sql` em `INSERT ... ON CONFLICT
  (nome) DO UPDATE SET esquema = EXCLUDED.esquema, esquema_versao = EXCLUDED.esquema_versao, ...`). Um item futuro
  que complete o esquema faz o mesmo `INSERT ... ON CONFLICT DO UPDATE` na sua migração e incrementa `esquema_versao`.
- A API carrega `tipo_item` na partida e a cada 60 s (`app/catalogo/tipos.py`, cache de módulo); `GET /api/tipos-item`
  devolve a lista com o esquema (é daí que o front gera o formulário da aba Dados e o L5-02 gera nós).
- Validação: `jsonschema.Draft202012Validator(esquema).iter_errors(dados)` (MEDIDO 0,86 ms para 60 campos); erro vira
  `422 dados_invalidos` com `detalhe: [{campo: "campos.60.nome", erro: "...", regra: "pattern"}]` (caminho absoluto do
  validador; a refutação do L0-03-a exige "422 com o caminho do campo"). Tipo inexistente = `422 tipo_inexistente`.
- `additionalProperties: false` em todos os esquemas mínimos: campo desconhecido é erro, não silêncio. Uma linha que
  precise de campo novo altera o esquema por migração (regra D19).
- Mudança de esquema **não** migra `dados` existentes automaticamente: o item que muda o esquema entrega a função de
  migração de dado (`app/<linha>/migrar_dados.py`) chamada pela própria migração via job `catalogo.migrar_dados`
  (registrado aqui, seção 11.4, executa uma função registrada por nome sobre todos os itens do tipo, por inquilino,
  com versão gravada em `item_versao`).

### 3.4 Custo de mudar

Trocar de "uma tabela + jsonb" para "uma tabela por tipo": alto (toda rota, a busca, a lixeira, as versões e as
relações são escritas uma vez sobre `item`). Acrescentar tipo: uma migração de uma linha + um módulo ES. Trocar o
validador (`jsonschema` → `fastjsonschema`): uma função em `app/catalogo/tipos.py`.

---

## 4. `plat.item_versao` — imutável, com sha256 (L0-03-l; D10; L5 D3)

### 4.1 DDL

```sql
CREATE TABLE IF NOT EXISTS plat.item_versao (
  item_id      uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  versao       int NOT NULL,
  tenant_id    int NOT NULL,                       -- denormalizado: RLS por comparação direta (ADR 0003 2.1)
  corpo        jsonb NOT NULL,                     -- retrato: metadado editável + dados (nunca busca, nunca tamanho)
  sha256       text NOT NULL,                      -- encode(digest(corpo::text, 'sha256'), 'hex')  (pgcrypto)
  autor_id     int,
  comentario   text CHECK (length(comentario) <= 500),
  rotulo       text CHECK (rotulo IN ('edicao','restauracao','rascunho','publicacao','compactada','migracao')),
  compactou    int NOT NULL DEFAULT 0,             -- quantas versões esta linha resume (0 = original)
  criado_em    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (item_id, versao)
);
CREATE INDEX IF NOT EXISTS ix_item_versao_tenant ON plat.item_versao (tenant_id, criado_em DESC);
-- RLS: FOR SELECT USING (tenant_id = plat.tenant_atual() AND plat.pode_ler(item_id));
--      sem INSERT/UPDATE/DELETE para plat_app: só o gatilho (dono da tabela) e as funções SECURITY DEFINER escrevem
```

### 4.2 Regras

- **Gatilho, não código de rota**: `AFTER INSERT OR UPDATE OF <campos da seção 2.2>` em `item` →
  `plat.tg_item_versao()` faz `UPDATE item SET versao_atual = versao_atual + 1` (via variável de sessão para não
  reentrar) e `INSERT item_versao (corpo = plat.item_retrato(NEW), sha256, autor = plat.usuario_atual(), rotulo =
  coalesce(current_setting('plat.versao_rotulo', true), 'edicao'), comentario = current_setting('plat.versao_comentario',
  true))`. A rota que quer rotular (restaurar, publicar, rascunho do L5) faz `set_config` local antes do `UPDATE`.
  MEDIDO: 0,12 ms por gravação (o portão pede ≤ +5 ms por PUT).
- **Sem `UPDATE`/`DELETE`** em `item_versao` por `plat_app`; a compactação é função `SECURITY DEFINER`
  (`plat.item_versoes_compactar(p_item uuid, p_manter int DEFAULT 50)`) chamada pelo periódico `catalogo.versoes_compactar`
  (diário, 03:40): mantém as 50 mais recentes intactas; das mais antigas, cada bloco de 10 vira **uma** linha (a mais
  recente do bloco, `rotulo = 'compactada'`, `compactou = 10`). Refutação do L0-03-l ("1.000 PUTs em 1 min"): em
  qualquer momento `count(*) ≤ 50 + 1.000/10` entre duas execuções do periódico, e ≤ 50 + ceil(pendentes/10) depois;
  a rota de lista mostra `compactou` para o usuário saber que houve resumo. Se o portão exigir "≤ 50 linhas" em
  todo instante, o `POST /api/itens/{id}` chama a compactação em linha quando `versao_atual % 100 = 0` (custo
  medido no item; decisão registrada aqui como a alternativa).
- **Restaurar** = `POST /api/itens/{id}/versoes/{n}/restaurar`: lê `corpo` da versão `n`, aplica como `PUT` normal
  (passa pela validação do tipo e pelos gatilhos), com `plat.versao_rotulo = 'restauracao'` e comentário
  `"restaurada da versão n"`. Nunca apaga versões (o portão: "restaurar a 2ª gera a 6ª igual à 2ª"; o teste compara
  `sha256` da 6ª com o da 2ª = iguais).
- **Diff** entre duas versões é calculado no servidor por função própria (`app/catalogo/diff.py`, recursiva sobre
  dicionários e listas, saída no formato JSON Patch RFC 6902 `[{op, path, value}]`), sem dependência; o cliente só
  mostra. Motivo: o L5 D3 diz "diff no cliente"; aqui a decisão é servidor porque a aba Versões e a exportação de
  auditoria (L0-10) precisam do mesmo diff, e 40 linhas de Python testadas custam menos que uma biblioteca vendida.
- `versao_publicada` (L5 D3): `POST /api/itens/{id}/versoes/{n}/publicar` aponta; `NULL` = a atual é a publicada.
  Este item só grava o ponteiro; quem lê é o L5 (render do app) e o L2-01 (mapa publicado × rascunho).
- Item de outro inquilino: RLS de `item_versao` devolve 0 linhas → `404`.
- Diff forjado (refutação): o cliente nunca envia diff; envia `corpo` inteiro ou pede restauração por número.

Custo de mudar: corpo > 1 MB (narrativas com mídia) vai para o Garage por sha256 e `corpo` vira ponteiro
`{"chave": ...}` (L5 D3); a API não muda.

---

## 5. `plat.item_relacao` — dependências declaradas (L0-03-i; D9)

### 5.1 DDL

```sql
CREATE TABLE IF NOT EXISTS plat.relacao_tipo (
  nome text PRIMARY KEY, descricao text NOT NULL,
  origem_familias text[] NOT NULL, destino_familias text[] NOT NULL,   -- vocabulário checado no gatilho
  arrasta_dono boolean NOT NULL DEFAULT false,      -- transferência de dono leva o destino junto (seção 10)
  apaga_junto boolean NOT NULL DEFAULT false        -- exclusão do destino em cascata explícita apaga a origem
);
INSERT INTO plat.relacao_tipo VALUES
  ('camada_de_mapa',      'mapa usa camada',                     '{mapa}',            '{camada,raster,rede}', false, false),
  ('dado_de_camada',      'camada aponta para o dado (STAC/arquivo de origem)', '{camada,raster}', '{raster,arquivo}', true, false),
  ('mapa_de_app',         'app/painel usa mapa',                 '{app,painel}',      '{mapa}',               false, false),
  ('vista_de_camada',     'vista deriva da camada primária',     '{camada}',          '{camada}',             true, true),
  ('estilo_de_camada',    'estilo pertence à camada',            '{documento}',       '{camada,raster}',      true, true),
  ('arquivo_de_camada',   'arquivo de origem da camada',         '{arquivo}',         '{camada}',             true, true),
  ('formulario_de_camada','formulário grava na camada',          '{formulario}',      '{camada}',             false, false),
  ('resultado_de_job',    'item produzido por job (proveniência)','{camada,raster,arquivo,documento}', '{camada,raster,arquivo,mapa,ferramenta}', false, false),
  ('anexo_de_item',       'arquivo anexado a item',              '{arquivo}',         '{camada,mapa,app,painel,formulario,fluxo,rede,ferramenta,documento,raster}', true, true),
  ('fator_de_motor',      'modelo AMC usa camada como fator',    '{ferramenta}',      '{camada,raster}',      false, false),
  ('rede_de_camada',      'rede é composta por camadas',         '{rede}',            '{camada}',             true, true)
ON CONFLICT (nome) DO UPDATE SET descricao = EXCLUDED.descricao, origem_familias = EXCLUDED.origem_familias,
  destino_familias = EXCLUDED.destino_familias, arrasta_dono = EXCLUDED.arrasta_dono, apaga_junto = EXCLUDED.apaga_junto;

CREATE TABLE IF NOT EXISTS plat.item_relacao (
  origem     uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,   -- quem USA (mapa)
  destino    uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,   -- quem É USADO (camada)
  tipo       text NOT NULL REFERENCES plat.relacao_tipo(nome),
  tenant_id  int NOT NULL,
  posicao    int,                                   -- ordem da camada no mapa, do fator no modelo (opcional)
  criado_em  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (origem, destino, tipo),
  CHECK (origem <> destino)
);
CREATE INDEX IF NOT EXISTS ix_item_relacao_destino ON plat.item_relacao (destino);
CREATE INDEX IF NOT EXISTS ix_item_relacao_origem  ON plat.item_relacao (origem);
-- RLS: FOR ALL USING (tenant_id = plat.tenant_atual() AND plat.pode_ler(origem)) WITH CHECK (tenant_id = plat.tenant_atual())
```

Semântica fixa: **origem depende de destino**; `usado_por(X)` = origens cujas relações têm `destino = X`;
`criado_a_partir_de(X)` = destinos cujas relações têm `origem = X`. Ordem de exclusão: dependentes (origens) antes.

### 5.2 Gatilho `plat.tg_item_relacao()` (`BEFORE INSERT`)

1. `origem` e `destino` existem, pertencem a `NEW.tenant_id` (= `plat.tenant_atual()`) e não estão na lixeira; senão
   `RAISE 'relacao_com_outro_inquilino'` → `422` (o teste de refutação do item exige 422, não 404, para relação).
2. Famílias de `origem`/`destino` batem com `relacao_tipo` (`RAISE 'relacao_familia_invalida'` → `422`).
3. **Ciclo**: CTE recursiva a partir de `NEW.destino` seguindo `destino → origem`... isto é, verifica se `NEW.origem`
   é alcançável a partir de `NEW.destino` pelas relações existentes (`NEW.destino` depende, direta ou indiretamente, de
   `NEW.origem`); se sim, `RAISE 'relacao_ciclo'` → `409 relacao_ciclo {detalhe: caminho}`. MEDIDO: fecho de 6
   níveis em 2,8 ms p95 sobre 30 mil relações; o gatilho limita a 20 níveis e 10.000 nós visitados (`RAISE
   'relacao_profunda'` → `422`) para o adversário de "100 mil relações no mesmo item" não travar a transação.
4. Teto: 5.000 relações por `origem` e 50.000 por `destino` (`422 limite_relacoes`); um mapa com 5.000 camadas não é
   caso de uso e o teto protege a CTE.

### 5.3 Quem grava

A relação é gravada **por quem cria o vínculo, na mesma transação**: `PUT /api/itens/{mapa}` com `dados.corpo.camadas
= [uuid…]` → o módulo do tipo `mapa` (`app/catalogo/tipos_relacoes.py`, uma função por tipo que extrai os uuids do
`dados`) sincroniza `item_relacao` (insere as novas, apaga as que sumiram, atualiza `posicao`). Este item entrega o
extrator para `mapa`, `vista_de_camada`, `app`, `painel`, `modelo_amc`, `rede`; L1/L2/L5 estendem a mesma tabela de
extratores quando o esquema deles crescer. Nunca se infere lendo JSON na hora da consulta (D9).

### 5.4 Consultas

- `GET /api/itens/{id}/usado-por?profundidade=1..5` (padrão 2): CTE recursiva com corte por caminho; devolve
  `[{item: {id, titulo, tipo, dono, acesso}, tipo_relacao, profundidade, caminho: [uuid]}]`, só itens que `pode_ler`
  (os que não pode aparecem como `{id, oculto: true}` **contados**, para que "apagar" possa dizer "3 itens que você não
  vê dependem desta camada" sem revelar título; o adversário do L0-03-e confere que `oculto` não vaza metadado).
- `GET /api/itens/{id}/criado-a-partir-de`: um nível.
- `GET /api/itens/{id}/ordem-de-exclusao`: fecho de dependentes em ordem topológica (dependentes primeiro), com
  `apaga_junto` marcado; é o que o diálogo "Apagar" mostra e o que `DELETE ... ?cascata=true` executa na ordem.
- Sobrescrita de dado de camada (L0-04-g): antes de aceitar a carga, `usado-por` da camada vira aviso `{"mapas_afetados":
  n, "itens": [...]}` (irritação 7); o uuid da camada e das sublayers não mudam.

Custo de mudar: acrescentar tipo de relação = uma linha em `relacao_tipo` por migração; trocar para grafo externo =
não há motivo medido.

---

## 6. Compartilhamento e a decisão de acesso (L0-03-e, L0-03-d; D7; ADR 0002 4.3)

### 6.1 Níveis e tabelas

| nível | onde se guarda | quem pode ligar | como combina |
|---|---|---|---|
| `privado` | `item.acesso = 'privado'` sem linhas em `item_grupo` | padrão na criação | só dono, `conteudo.ver_tudo`, links |
| `grupos` | `plat.item_grupo(item_id, grupo_id, tenant_id, criado_por, criado_em)` | dono/`editar_tudo` com `compartilhar.grupo`, e só em grupo em que o ator **pode contribuir** (papel de grupo ou `contribuicao = 'todos'`, ADR 0002 4.2) | soma-se a qualquer `acesso` |
| `inquilino` | `item.acesso = 'inquilino'` | `compartilhar.inquilino` | quem tem `conteudo.ver_inquilino` |
| `link` | `plat.compartilhamento_link` (6.2) | `compartilhar.link` | independente do `acesso`; vale para anônimo |
| `publico` | `item.acesso = 'publico'` | `compartilhar.publico` **e** `tenant.config.auth.compartilhar_publico = true` (D24; padrão `false`) | anônimo por `/api/publico/itens/{id}` |

```sql
CREATE TABLE IF NOT EXISTS plat.item_grupo (
  item_id uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  grupo_id uuid NOT NULL REFERENCES plat.grupo(id) ON DELETE CASCADE,     -- apagar grupo remove o compartilhamento (ADR 0002 4.1)
  tenant_id int NOT NULL, criado_por int, criado_em timestamptz NOT NULL DEFAULT now(),
  destaque boolean NOT NULL DEFAULT false,          -- "itens em destaque" do grupo (≤ 24 por grupo, gatilho)
  PRIMARY KEY (item_id, grupo_id));
CREATE INDEX IF NOT EXISTS ix_item_grupo_grupo ON plat.item_grupo (grupo_id);
-- RLS: FOR SELECT USING (tenant_id = plat.tenant_atual() AND (plat.pode_ler(item_id) OR EXISTS membro ativo do grupo));
--      FOR INSERT/DELETE WITH CHECK/USING (tenant_id = plat.tenant_atual() AND plat.pode_editar(item_id))
```

O gatilho `tg_item_grupo` confere: grupo do mesmo inquilino (`grupo_de_outro_inquilino` → 404), ator pode contribuir
no grupo (`RAISE 'sem_contribuicao_no_grupo'` → `403 sem_contribuicao_no_grupo`), teto de 24 destaques.

### 6.2 Link por token

```sql
CREATE TABLE IF NOT EXISTS plat.compartilhamento_link (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  item_id      uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  token_hash   text NOT NULL UNIQUE,               -- sha256 do token; o token (32 bytes → 64 hex) só aparece na criação
  prefixo      text NOT NULL,                      -- 8 primeiros hex, para reconhecer na lista
  nome         text CHECK (length(nome) <= 128),
  criado_por   int NOT NULL REFERENCES plat.usuario(id),
  criado_em    timestamptz NOT NULL DEFAULT now(),
  expira_em    timestamptz,                        -- NULL = não expira; máximo 365 d (limite)
  revogado_em  timestamptz,
  revogado_por int,
  acessos      bigint NOT NULL DEFAULT 0,
  ultimo_acesso_em timestamptz,
  ultimo_ip    text,
  permite_download boolean NOT NULL DEFAULT false  -- L0-04-h decide o que "download" significa por tipo
);
CREATE TABLE IF NOT EXISTS plat.compartilhamento_link_item (    -- dependências incluídas explicitamente no link
  link_id uuid NOT NULL REFERENCES plat.compartilhamento_link(id) ON DELETE CASCADE,
  item_id uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  PRIMARY KEY (link_id, item_id));
CREATE INDEX IF NOT EXISTS ix_link_item ON plat.compartilhamento_link (item_id) WHERE revogado_em IS NULL;
-- RLS: FOR ALL USING (tenant_id = plat.tenant_atual() AND plat.pode_editar(item_id)) — só quem edita o item vê/gere links
```

- Token: `secrets.token_hex(32)` = 64 caracteres hex (refutação: "tem de ser ≥ 32 hex"); no banco só o sha256, como
  `sessao.token_hash` (ADR 0001). URL: `https://<host>/c/<token>` (página) e `GET /api/compartilhado/<token>` (API).
- Resolução anônima: `plat.link_resolver(p_hash text, p_ip text)` `SECURITY DEFINER`, pré-contexto (o hash é o
  segredo): devolve `tenant_id`, `item_id`, `itens_incluidos uuid[]`, `permite_download`, e o motivo quando não vale
  (`revogado`, `expirado`, `inexistente`); incrementa `acessos`/`ultimo_acesso_em`/`ultimo_ip` na mesma chamada. A
  rota então abre o contexto `set_config('plat.tenant_id', tenant)`, `plat.usuario_id = ''` e
  `set_config('plat.link_itens', '<uuid,uuid,...>', true)`; `pode_ler` (6.3) lê essa variável. Nada é cacheado: revogar
  é um `UPDATE` e o próximo pedido já cai em `revogado` (portão: 404 em ≤ 1 s; refutação: 20 clientes simultâneos).
- Códigos: válido `200`; revogado ou inexistente `404 link_invalido` (não confirma existência); expirado `410
  link_expirado` (o portão pede 410 para expirado e 404 para revogado).
- Validade: `expira_em ≤ criado_em + 365 d` (`400 validade_acima_do_maximo`); máximo 100 links por item
  (`422 limite_links`).
- "Elevar ao nível do mapa" (irritação 2): ao criar link para um item com dependências, o diálogo lista a árvore
  (`usado-por` invertido: `criado-a-partir-de` recursivo) com o nível atual de cada uma e caixas "incluir neste
  link"; só as marcadas entram em `compartilhamento_link_item`; o ator precisa `pode_editar` de **cada** uma marcada
  (refutação: "eleva camada de outro dono" → a caixa vem desabilitada e a API devolve `403 sem_edicao_no_item
  {detalhe: [uuid]}`). O mesmo diálogo, para `grupos`/`inquilino`/`publico`, oferece "aplicar o mesmo nível às
  dependências" com a mesma regra; nunca rebaixa e nunca eleva em silêncio.

### 6.3 `plat.pode_ler` e `plat.pode_editar` (o núcleo; usadas na RLS)

```sql
CREATE OR REPLACE FUNCTION plat.pode_ler(p_item uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT EXISTS (
    SELECT 1 FROM plat.item i
    WHERE i.id = p_item
      AND i.tenant_id = plat.tenant_atual()
      AND (i.apagado_em IS NULL OR current_setting('plat.lixeira', true) = 'on')
      AND (
           -- link anônimo: só os itens listados no link desta requisição
           (plat.usuario_atual() IS NULL AND i.id::text = ANY (string_to_array(current_setting('plat.link_itens', true), ',')))
        OR -- público anônimo ou autenticado (o inquilino tem de autorizar; a rota pública confere a config)
           (i.acesso = 'publico' AND plat.tenant_permite_publico(i.tenant_id))
        OR -- usuário autenticado do inquilino
           (plat.usuario_atual() IS NOT NULL AND (
                i.dono_id = plat.usuario_atual()
             OR plat.tem('conteudo.ver_tudo')
             OR (i.acesso = 'inquilino' AND plat.tem('conteudo.ver_inquilino'))
             OR EXISTS (SELECT 1 FROM plat.item_grupo ig JOIN plat.grupo_membro gm
                          ON gm.grupo_id = ig.grupo_id AND gm.usuario_id = plat.usuario_atual() AND gm.estado = 'ativo'
                        WHERE ig.item_id = i.id)))
      )
  )
$$;

CREATE OR REPLACE FUNCTION plat.pode_editar(p_item uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT plat.usuario_atual() IS NOT NULL AND EXISTS (
    SELECT 1 FROM plat.item i
    WHERE i.id = p_item AND i.tenant_id = plat.tenant_atual()
      AND (i.dono_id = plat.usuario_atual()
        OR plat.tem('conteudo.editar_tudo')
        OR EXISTS (SELECT 1 FROM plat.item_grupo ig JOIN plat.grupo g ON g.id = ig.grupo_id AND g.atualizacao_compartilhada
                   JOIN plat.grupo_membro gm ON gm.grupo_id = g.id AND gm.usuario_id = plat.usuario_atual() AND gm.estado = 'ativo'
                   WHERE ig.item_id = i.id)))
$$;
```

Por que `SECURITY DEFINER` aqui: a função lê `item`, `item_grupo`, `grupo` e `grupo_membro`, e essas tabelas têm
políticas que **chamam** `pode_ler`; sem `SECURITY DEFINER` a política recursaria (a `p_grupo_ler` do ADR 0002 lê
`grupo_membro`, e `pode_ler` lê os dois). Como o ADR 0002 seção 12 fixa `REVOKE EXECUTE ... FROM PUBLIC` + `GRANT
... TO plat_app`, a função é chamável só por `plat_app` e checa `tenant_atual()` na primeira linha (achado do
adversário do T1). `STABLE` permite ao planejador chamá-la uma vez por linha, não por acesso; MEDIDO: o mesmo
predicado escrito em linha custou 3,17 ms p95 sobre 10 mil linhas.

O que `pode_ler` **não** faz: não cacheia (D7, "link revogado nega em ≤ 1 s"), não olha `status`, não olha
`classificacao` (L7-12 acrescenta `AND plat.classificacao_permite(i.classificacao)` por `CREATE OR REPLACE`).
`plat.tenant_permite_publico(int)` é SQL STABLE sobre `tenant.config`.

### 6.4 Políticas de RLS de `plat.item`

```sql
ALTER TABLE plat.item ENABLE ROW LEVEL SECURITY;
CREATE POLICY p_item_ler     ON plat.item FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual() AND plat.pode_ler(id));
CREATE POLICY p_item_inserir ON plat.item FOR INSERT TO plat_app WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_atual() IS NOT NULL
                                                                            AND dono_id = plat.usuario_atual() AND plat.tem('conteudo.criar'));
CREATE POLICY p_item_alterar ON plat.item FOR UPDATE TO plat_app USING (tenant_id = plat.tenant_atual() AND plat.pode_editar(id))
                                                                  WITH CHECK (tenant_id = plat.tenant_atual());
CREATE POLICY p_item_apagar  ON plat.item FOR DELETE TO plat_app USING (false);   -- exclusão física só pelo expurgo (função)
```

`DELETE` físico por `plat_app` é proibido: apagar é `UPDATE apagado_em` (seção 9); o expurgo é `SECURITY DEFINER`.
Toda tabela que referencia `item` (`item_versao`, `item_relacao`, `item_grupo`, `compartilhamento_link`, `favorito`,
e, nas linhas seguintes, `raster_item`, tabelas de camada `d_<slug>.c_*`, anexos) usa `plat.pode_ler(item_id)` na
política de leitura e `plat.pode_editar(item_id)` na de escrita: o Martin e o tipg (L2) decidem igual à API porque
decidem pela mesma função (D7).

Superadmin lendo outro inquilino (`X-Plat-Inquilino`, ADR 0002 seção 10): `plat.usuario_atual()` é o superadmin, que
não é dono nem membro; `pode_ler` devolve só `inquilino`/`publico`. Para o console do superadmin ver tudo (L0-07-f),
a rota liga `set_config('plat.superadmin', 'on', true)` e `pode_ler` ganha `OR current_setting('plat.superadmin',
true) = 'on'` — **só** a função de contexto do superadmin do ADR 0002 seção 10 (`plat.plataforma_operador(p_sessao_hash)`, que prova a
sessão pelo hash) liga essa variável; o adversário testa `set_config` direto sem sessão de superadmin (a variável sozinha não basta porque
`tenant_atual()` continua sendo o do contexto e a função de contexto grava evento `inquilinos/leitura_superadmin`).

### 6.5 Rotas de compartilhamento (contrato completo na seção 13)

`GET /api/itens/{id}/compartilhamento` devolve o estado inteiro: `{acesso, grupos: [{id, nome, destaque}], links:
[{id, prefixo, nome, expira_em, revogado_em, acessos, itens_incluidos}], publico_permitido: bool, dependencias:
[{id, titulo, tipo, acesso, grupos: n, pode_editar}]}`; `PUT` do mesmo recurso aplica `{acesso?, grupos?: [uuid],
aplicar_a_dependencias?: [uuid]}` em uma transação (evento `compartilhamento/alterar` com antes/depois). Links têm
rotas próprias (`POST`, `DELETE` = revogar). 404 (não 403) quando o ator não pode ler o item; 403 quando pode ler mas
não pode compartilhar (`sem_permissao`, `sem_contribuicao_no_grupo`, `sem_edicao_no_item`).

Custo de mudar: a decisão é uma função; ACL por usuário (opção c do D7) = uma tabela `item_usuario` e uma cláusula
`OR EXISTS` a mais em `pode_ler`.

---

## 7. Busca (L0-03-c; D8)

### 7.1 Configuração de texto e coluna

```sql
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'pt_sem_acento' AND cfgnamespace = 'plat'::regnamespace) THEN
    CREATE TEXT SEARCH CONFIGURATION plat.pt_sem_acento (COPY = pg_catalog.portuguese);
    ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
      ALTER MAPPING FOR hword, hword_part, word, asciiword, asciihword, hword_asciipart
      WITH unaccent, portuguese_stem;
  END IF;
END $$;
```

`unaccent` entra como **dicionário** (a função `unaccent()` é `STABLE` e não serviria numa coluna gerada; MEDIDO).
A coluna `busca` (seção 2.1) é `GENERATED ... STORED`: o índice GIN é atualizado na mesma transação da edição (D8;
irritação 9 "tags por API não aparecem"; MEDIDO 0,51 ms médio por `UPDATE`). O portão "tags criadas por API aparecem
na busca na mesma requisição seguinte" fica cumprido por construção, não por fila.

### 7.2 O que a busca faz com o texto do usuário (`app/catalogo/busca.py`)

Entrada: `q` (≤ 1.000 caracteres; ≤ 200 termos → `422 busca_complexa`). A gramática própria (analisador descendente,
sem biblioteca) reconhece:

| forma | exemplo | vira |
|---|---|---|
| palavras soltas | `municipio rodovia` | `websearch_to_tsquery('plat.pt_sem_acento', 'municipio rodovia')` (AND implícito) |
| frase | `"setor censitario"` | idem (o `websearch_to_tsquery` trata aspas, `-` e `OR`) |
| operadores | `a OR b`, `NOT c`, `-c`, `(a OR b) c` | parênteses e `NOT` resolvidos pela gramática em uma árvore; cada folha de texto vira `websearch_to_tsquery`; a árvore vira `tsquery` combinado com `&&`, `||`, `!!` |
| campo texto | `titulo:mapa`, `tags:ibge`, `resumo:x`, `descricao:x` | `to_tsvector` da coluna correspondente `@@ websearch_to_tsquery(...)` (título por `busca` com filtro de peso `'A'`) |
| campo exato | `dono:maria`, `tipo:mapa`, `status:autoritativo`, `acesso:inquilino`, `pasta:<uuid ou nome>`, `categoria:<uuid ou caminho>`, `grupo:<uuid>`, `id:<uuid>`, `origem:referenciado` | predicado SQL parametrizado; valor inválido (uuid mal formado, tipo inexistente) = `422 campo_invalido {detalhe: {campo, valor}}` |
| intervalo | `criado:[2026-01-01 TO 2026-03-31]`, `modificado:[2026-08 TO *]` | `criado_em >= a AND criado_em < b + 1 dia`; `*` = aberto; ISO 8601 (não UNIX ms como a Esri) |
| `:` sem campo ou campo desconhecido | `:x`, `foo:bar` | `422 campo_invalido` (refutação) |
| sintaxe tsquery direta | `a & b`, `a:*` | é texto: `websearch_to_tsquery` nunca levanta erro (refutação "tsquery inválida") |

Nunca se chama `to_tsquery` com texto do usuário (D8). `id:` de item que o usuário não pode ler devolve 0 linhas: o
predicado é somado à RLS, não a substitui (refutação: "item privado de outro usuário por `id:`").

### 7.3 Ordenação (o que resolve a irritação 9 e a cláusula de status)

```sql
ORDER BY (lower(unaccent(titulo)) = lower(unaccent(:termo_inteiro))) DESC,          -- 1. título exatamente igual
         ts_rank_cd(busca, :tsquery, 32) + CASE status WHEN 'autoritativo' THEN 0.25 WHEN 'obsoleto' THEN -0.25 ELSE 0 END DESC,
         modificado_em DESC, id DESC
```

MEDIDO: sem a chave 1, o item "Município" empata com "Município leste 7" (rank 1,0 nos dois) e não vem primeiro; com
ela vem, a p95 2,59 ms. O reforço `±0,25` é declarado (o normalizador 32 põe o rank em 0..1; 0,25 é um quarto da
escala: um item autoritativo passa à frente de um comum com rank até 0,25 maior, nunca de um cujo título bate).
`ordenar=` explícito (`titulo`, `modificado_em`, `criado_em`, `tipo`, `dono`, `tamanho_bytes`, `pontuacao`) substitui
o rank; `q` sem `ordenar` = relevância.

### 7.4 Trigram como reserva

Se a consulta FTS devolve 0 linhas e há um único termo de texto com ≥ 4 caracteres, a rota repete com `titulo %
:termo` (`pg_trgm`, limiar 0,3 fixado por `SET LOCAL pg_trgm.similarity_threshold = 0.3`) ordenado por
`similarity` e marca a resposta com `"aproximado": true` (a tela escreve "mostrando resultados parecidos com
'municpio'"). MEDIDO: 20,9 ms p95 sobre 10 mil títulos. Prefixo (`muni`) é resolvido pelo próprio FTS
(`websearch_to_tsquery` não faz prefixo; a gramática acrescenta `:*` ao último termo quando `q` termina sem espaço e
a origem é a caixa de busca ao vivo, parâmetro `prefixo=true`).

### 7.5 Filtros laterais (todos combináveis com `q`; contagens por faceta)

`tipo[]`, `familia[]`, `dono_id[]`, `tags[]` (todas as tags: `tags @> :lista`), `categoria[]` (nó ou qualquer
descendente), `pasta_id`, `status[]`, `acesso[]`, `origem`, `criado_de/ate`, `modificado_de/ate`, `bbox` (`xmin,ymin,
xmax,ymax` em 4326: `extent && envelope`), `favoritos=true`, `meus=true`, `grupo_id`, `lixeira=true` (seção 9).
`GET /api/itens/facetas?<mesmos filtros>` devolve `{tipo: [{valor, n}], tags: [top 30], dono: [...], status, categoria}`
para os painéis laterais (uma consulta por faceta com `GROUP BY`, sobre o mesmo `WHERE`; a tela pede só quando o
painel está aberto).

### 7.6 Escala e medidas que o testador grava (`tests/medidas/L0-03-catalogo.json`)

`busca_p95_ms` (10 mil itens, "municipio"; portão ≤ 200), `busca_trgm_p95_ms`, `lista_tipo_p95_ms` (portão < 100),
`usado_por_p95_ms` (portão < 50), `facetas_p95_ms`. A 50 mil itens (adversário do L0-03-f) o testador repete e grava
`busca_50k_p95_ms` sem portão numérico, como fronteira declarada.

Custo de mudar: motor externo (Meilisearch) = trocar `app/catalogo/busca.py` e manter o mesmo contrato de `q`; a RAM
desta máquina (2-3 GB disponíveis) é o que o descarta hoje, não o desempenho (MEDIDO: 2,4 ms).

---

## 8. Pastas, tags, categorias, classificação e favoritos (L0-03-b, L0-03-k)

### 8.1 Pastas hierárquicas por inquilino

```sql
CREATE TABLE IF NOT EXISTS plat.pasta (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   int NOT NULL REFERENCES plat.tenant(id),
  pai_id      uuid REFERENCES plat.pasta(id) ON DELETE RESTRICT,     -- NULL = raiz
  nome        text NOT NULL CHECK (length(nome) BETWEEN 1 AND 128 AND nome !~ '[/\\]' AND nome = btrim(nome)),
  ancestrais  uuid[] NOT NULL DEFAULT '{}',        -- caminho materializado (raiz primeiro); mantido por gatilho
  profundidade smallint NOT NULL DEFAULT 0 CHECK (profundidade BETWEEN 0 AND 4),   -- ≤ 5 níveis
  dono_id     int NOT NULL REFERENCES plat.usuario(id),
  criado_em   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, pai_id, lower(nome))          -- nome único entre irmãs (raiz: pai_id NULL → índice parcial)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_pasta_raiz ON plat.pasta (tenant_id, lower(nome)) WHERE pai_id IS NULL;
CREATE INDEX IF NOT EXISTS ix_pasta_ancestrais ON plat.pasta USING gin (ancestrais);
-- RLS: FOR SELECT USING (tenant_id = plat.tenant_atual());  escrita: tenant + (dono_id = usuario_atual() OR tem('conteudo.editar_tudo'))
```

Decisões: (a) pasta é **do inquilino e visível a todos** (a Esri: um nível, por membro; irritação 3); quem vê a
pasta vê só os itens que `pode_ler` dentro dela, e a contagem mostrada é a de itens visíveis; (b) profundidade ≤ 5
e nome único entre irmãs (hipótese do item); (c) `ancestrais uuid[]` mantido pelo gatilho `tg_pasta_caminho`
(`BEFORE INSERT/UPDATE OF pai_id`): calcula `ancestrais = pai.ancestrais || pai.id`, `profundidade`, recusa ciclo
(`NEW.id = ANY(pai.ancestrais) OR NEW.id = pai_id` → `RAISE 'pasta_ciclo'` → `409`), recusa 6º nível
(`RAISE 'pasta_profunda'` → `422`), recusa pai de outro inquilino (`404`), e ao mover uma pasta reescreve
`ancestrais` das descendentes (`UPDATE ... WHERE NEW.id = ANY(ancestrais)`, GIN); (d) `ltree` não é usado: a
extensão está disponível e não instalada, o guardrail desta preparação é "não instalar", e `uuid[]` + GIN resolve
"descendentes de X" com `ancestrais @> ARRAY[X]`; custo de mudar para `ltree` = uma coluna a mais; (e) apagar pasta
com item ou subpasta recusa (`409 pasta_nao_vazia {detalhe: {itens: n, pastas: n}}`); a tela oferece "mover conteúdo
para a pasta-mãe e apagar" como segundo passo explícito; (f) `pasta_id` do item é `ON DELETE SET NULL` só para o
expurgo físico da pasta, que nunca acontece com item dentro (gatilho).

### 8.2 Tags

`item.tags text[]` (≤ 50, cada 1..128, sem vírgula/quebra, sem espaço nas pontas; gatilho normaliza espaços
internos duplos). Sem tabela de tags: a faceta `tags` sai de `unnest(tags)` + GIN (`ix_item_tags`); `GET
/api/itens/tags?q=ib` sugere (prefixo, `ILIKE`, 20 resultados). Renomear tag em massa = `POST /api/itens/lote
{acao: "tags", de: "x", para: "y"}` (≤ 100 itens por lote; para o inquilino inteiro, job `catalogo.tags_renomear`).

### 8.3 Categorias do inquilino

```sql
CREATE TABLE IF NOT EXISTS plat.categoria (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id int NOT NULL REFERENCES plat.tenant(id),
  pai_id uuid REFERENCES plat.categoria(id) ON DELETE RESTRICT,
  nome text NOT NULL CHECK (length(nome) BETWEEN 1 AND 100), caminho text NOT NULL,   -- 'Ambiente/Água/Bacias' (gatilho)
  nivel smallint NOT NULL CHECK (nivel BETWEEN 1 AND 3), posicao int NOT NULL DEFAULT 0,
  origem text CHECK (origem IN ('iso19115','inspire','propria')) NOT NULL DEFAULT 'propria', codigo text,  -- código do modelo
  UNIQUE (tenant_id, pai_id, lower(nome)));
-- RLS: leitura por tenant; escrita exige plat.tem('conteudo.categorias'); gatilho: ≤ 200 nós por inquilino, ≤ 3 níveis
```

`item.categorias uuid[]` (≤ 20, gatilho confere inquilino e existência). Modelos importáveis por `POST
/api/categorias/importar {modelo: "iso19115" | "inspire"}` (idempotente por `codigo`): **ISO 19115** = as 19
categorias temáticas de `MD_TopicCategoryCode` (farming, biota, boundaries, climatologyMeteorologyAtmosphere, economy,
elevation, environment, geoscientificInformation, health, imageryBaseMapsEarthCover, intelligenceMilitary,
inlandWaters, location, oceans, planningCadastre, society, structure, transportation, utilitiesCommunication), com
rótulo em português e o código original; **INSPIRE** = os 34 temas dos anexos I (9), II (4) e III (21), em três nós
de topo "Anexo I/II/III". Os dois arquivos vivem em `app/catalogo/modelos_categorias/{iso19115,inspire}.json` com a
URL de origem (anexo B) e são testados por contagem (19 e 34). O limite de 200 nós é o da Esri para categorias de
grupo/membro (2.10 do handoff); o de organização lá é 900 — decisão: 200 como padrão em `tenant.config.catalogo.
categorias_max` (faixa 50..900), porque a árvore aparece inteira no painel lateral e 900 nós não cabem numa tela.

### 8.4 Classificação (esquema por inquilino; L7-12)

`tenant.config.catalogo.classificacao` = `{ativa: bool, obrigatoria: bool, esquema: JSON Schema}`; padrão
`{ativa: false}`. Quando `ativa`, `item.classificacao` é validado contra o esquema (`422 classificacao_invalida`);
quando `obrigatoria`, item novo sem classificação = `422 classificacao_obrigatoria`. Esquema-modelo entregue em
`app/catalogo/modelos_classificacao/sigilo.json`: `{sigilo: enum[publico, interno, restrito, pessoal], base_legal?:
string, retencao_meses?: int}`. Este item só guarda e valida; o que "pessoal" bloqueia (público, exportação) é do L7-12
(gancho: `pode_ler` ganha uma cláusula por `CREATE OR REPLACE`). A Esri diz que "classificação não restringe acesso";
aqui a decisão é a mesma **até** o L7-12, declarado na paridade.

### 8.5 Favoritos

```sql
CREATE TABLE IF NOT EXISTS plat.favorito (
  usuario_id int NOT NULL REFERENCES plat.usuario(id) ON DELETE CASCADE, item_id uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  tenant_id int NOT NULL, criado_em timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (usuario_id, item_id));
-- RLS: FOR ALL USING (tenant_id = plat.tenant_atual() AND usuario_id = plat.usuario_atual()) WITH CHECK (idem AND plat.pode_ler(item_id))
```

`WITH CHECK ... pode_ler` cumpre a refutação "favorita item sem acesso (deve recusar)" no banco: `404
item_inexistente`. Limite 500 favoritos por usuário. A aba "Favoritos" da tela e o seletor de camadas do mapa (L2-01)
leem `GET /api/itens?favoritos=true`. Notificações internas (a outra metade do L0-03-k) são do L0-10 (fonte `evento`);
este ADR só fixa os eventos que as alimentam (seção 12).

---

## 9. Lixeira, proteção e status (L0-03-h; D10)

### 9.1 Exclusão lógica e a variável `plat.lixeira`

- `DELETE /api/itens/{id}` = `UPDATE item SET apagado_em = now(), apagado_por = usuario_atual()`, evento
  `itens/apagar`. A política `p_item_ler` filtra `apagado_em IS NULL` **a menos que** a transação tenha
  `set_config('plat.lixeira', 'on', true)` — só as rotas `/api/lixeira*` ligam. Assim toda consulta do produto (lista,
  busca, mapa, Martin, tipg, conectores) esconde a lixeira por construção (D10), e a tela da lixeira existe sem
  duplicar política.
- Quem vê na lixeira: dono do item ou `conteudo.apagar_tudo` (`pode_ler` já dá isso: dono/`ver_tudo`; a rota da
  lixeira exige ainda `conteudo.criar` ou `apagar_tudo`).
- **Restaurar** (`POST /api/lixeira/{id}/restaurar`): `apagado_em = NULL`; uuid igual; `item_grupo`, links, relações,
  favoritos e versões **nunca foram tocados** (ficaram nas tabelas; as políticas deles apontam para `pode_ler`, que os
  escondia). Restaurar item cujo pai de pasta foi apagado fisicamente vai para a raiz (`pasta_id` já é NULL por `SET
  NULL`); restaurar com nome de pasta duplicado não se aplica (item não tem unicidade de título).
- Dependentes: `DELETE` de item com `usado-por` não vazio = `409 possui_dependentes {detalhe: {ordem: [...]}}`; com
  `?cascata=true` apaga na ordem de exclusão (dependentes primeiro), um evento por item, tudo em uma transação. Item
  com dependente que o ator **não pode editar** = `409` sem cascata possível (`detalhe.ocultos: n`).
- Apagar em massa (`POST /api/itens/lote {acao: "apagar", ids: [≤100]}`) aplica a mesma regra por item e devolve
  `{apagados: n, recusados: [{id, erro}]}`.
- **Expurgo** (`catalogo.lixeira_expurgar`, periódico diário 03:50, tipo registrado aqui, pesado = true porque
  apaga tabela física): `plat.lixeira_expurgar(p_dias int DEFAULT 30) RETURNS TABLE (item_id, tipo, dados)` `SECURITY
  DEFINER` seleciona `apagado_em < now() - p_dias` por inquilino; para cada item o job (a) chama o **destruidor do
  tipo** registrado em `app/catalogo/destruidores.py` (`camada_vetorial` → `DROP TABLE d_<slug>.c_<uuid16>`;
  `raster` → `pgstac` + objetos (L1-01 entrega; até lá o destruidor recusa e o item fica com aviso no log);
  `arquivo` e miniatura → objeto no Garage pelo contrato do L0-11), (b) só depois `plat.item_expurgar(uuid)` (função,
  `DELETE` físico com cascatas: versões, relações, links, favoritos), (c) evento `lixeira/expurgar` no inquilino do
  item, (d) `tenant.uso` recalculado (L0-07-c). Relógio simulado para o teste: `POST /api/jobs {tipo:
  "catalogo.lixeira_expurgar", parametros: {dias: 30, agora: "2026-10-07T00:00:00Z"}}` só em `PLAT_AMBIENTE=dev`
  (o parâmetro `agora` é recusado com 422 em produção).
- `POST /api/lixeira/esvaziar` (dono: os próprios; `apagar_tudo`: do inquilino) enfileira o mesmo job com `dias = 0`
  e `ids` explícitos.
- A lixeira **conta na cota** (D16): `tamanho_bytes` continua somado em `tenant.uso` até o expurgo.
- Tabela física de camada só some no expurgo: protege também o job de importação que falhou no meio (D10).

### 9.2 Proteção

`protegido` é campo (não segredo; irritação 6): `PUT /api/itens/{id} {protegido: false}` por dono ou
`editar_tudo`; com `protegido = true`, `DELETE` = `409 item_protegido` com a instrução. **Superadmin** apaga item
protegido sem desligar (`plat.superadmin = on` no gatilho da seção 2.2) e o evento `itens/apagar` leva
`propriedades.forcado = true` e `propriedades.protegido_em = ...`; admin de inquilino **não** (refutação do item:
"como admin de inquilino deve falhar; como superadmin deve passar com evento"). Proteção em massa: `lote {acao:
"proteger" | "desproteger"}`.

### 9.3 Status

| status | quem liga | efeito |
|---|---|---|
| `autoritativo` | `conteudo.editar_tudo` (admin) | gatilho liga `protegido`; `+0,25` no rank (7.3); selo na lista e no detalhe; a tela "Conteúdo" tem filtro "Autoritativos" |
| `obsoleto` | dono ou `editar_tudo` | `−0,25` no rank; selo "Obsoleto" na lista, no detalhe e (L2-01) no seletor de camadas; recomendação na tela de apagar ("marque como obsoleto antes de apagar", regra Esri) |
| `NULL` | qualquer um dos acima tira | — |

Evento `itens/status` com antes/depois. Trocar o reforço `±0,25` = constante em `app/limites.py`
(`BUSCA_REFORCO_STATUS`), coberta pelo teste de ordenação.

---

## 10. Transferência de dono (L0-03-j)

`POST /api/itens/transferir {ids: [uuid ≤ 100] | usuario_origem_id: int, novo_dono_id: int, simular: bool,
pastas: "manter" | "unica", pasta_unica_nome?: string, adicionar_aos_grupos: bool}`; exige `conteudo.transferir`
(ou dono do item com `conteudo.criar` e o novo dono com `conteudo.criar`: "Reassign content"/"Receive content" da Esri,
aqui reduzidos a esses dois privilégios, declarado na paridade).

Pré-checagem (`simular: true` devolve o plano sem executar; `false` executa **só se** o plano não tiver falhas, salvo
`forcar_parcial: true`):

```json
{"plano": [{"id": "...", "titulo": "...", "acao": "transferir", "arrasta": [{"id": "...", "tipo_relacao": "vista_de_camada"}],
            "falhas": [{"codigo": "novo_dono_fora_do_grupo", "grupo": {"id": "...", "nome": "..."}, "solucao": "adicionar_aos_grupos"}]}],
 "total": 3, "com_falha": 1, "novo_dono": {"id": 9, "login": "joao", "ativo": true}}
```

Regras (E12-manageitems traduzidas, cada uma com código de falha testável):

1. Novo dono ativo e do mesmo inquilino (`404 usuario_inexistente`; `422 novo_dono_inativo`).
2. Novo dono precisa ser membro ativo de **todos** os grupos com que o item está compartilhado e o grupo tem de
   deixá-lo contribuir (`novo_dono_fora_do_grupo`, `novo_dono_sem_contribuicao`); `adicionar_aos_grupos: true` resolve
   a primeira quando o ator é dono/gerente do grupo ou tem `grupos.gerir_todos` (o plano diz qual).
3. Relações com `arrasta_dono = true` (vistas, estilo, arquivo de origem, anexos, dado STAC, camadas da rede) vão
   junto **obrigatoriamente**; transferir só a vista sem a camada primária = `409 vista_sem_camada` (refutação);
   mapas e apps que usam a camada **não** mudam de dono (regra Esri literal).
4. Preserva: uuid, `item_grupo`, links (o link sobrevive: refutação mede que `GET /api/compartilhado/<token>` continua
   200 depois), favoritos de terceiros, versões, relações, `protegido`, `status`.
5. Pastas: `manter` (o item fica na pasta em que está: a pasta é do inquilino, seção 8.1, então nada muda) ou
   `unica` (todos vão para a pasta `de_<login_antigo>` criada na raiz, ou `pasta_unica_nome`). A opção existe
   porque o usuário Esri espera a pergunta (Transfer content); aqui `manter` é o padrão e não perde nada.
6. Executa em uma transação com `set_config('plat.transferencia', 'on', true)` (gatilho da seção 2.2), evento
   `itens/transferir` por item com `{de, para}`; `usuario_origem_id` transfere **tudo** do usuário (é o passo que
   `DELETE /api/usuarios/{id}` do ADR 0002 exige antes de apagar: `409 possui_conteudo` lá aponta para esta rota).
7. Item de outro inquilino: 404 pela RLS; usuário desabilitado: `422`.

Custo de mudar: as regras são funções puras em `app/catalogo/transferencia.py` sobre o plano; a execução é um
`UPDATE` por item.

---

## 11. Miniaturas, objetos e jobs do catálogo (L0-03-g; D13; ADR 0003)

### 11.1 Miniatura enviada (síncrona, na API)

`POST /api/itens/{id}/miniatura` (`multipart/form-data`, campo `arquivo`; exige `pode_editar`): (1) tamanho ≤ 10 MB
antes de ler (`413 miniatura_grande`; `client_max_body_size` do nginx já é 200m); (2) tipo pelos **bytes** (assinatura
PNG/JPEG/GIF; `python-magic` ausente, então `Pillow.Image.open` + `format`), não pelo nome nem pelo `Content-Type`
(`415 formato_nao_aceito`); (3) bomba de descompressão: `Image.MAX_IMAGE_PIXELS = 25_000_000` **e** leitura do
cabeçalho (`im.size`) antes de `im.load()`; acima → `422 imagem_grande {detalhe: {largura, altura, maximo_px}}`
(refutação: PNG de 20.000 × 20.000 = 400 Mpx recusado sem alocar); (4) `ImageOps.exif_transpose` e depois
**descarte de todo metadado** (o PNG de saída é criado de um `Image.new` + `paste`, sem `info`, sem EXIF, sem
`iCCP`; refutação "EXIF com script"); (5) corte central para 3:2 e redução para 600 × 400 (`Image.Resampling.LANCZOS`);
(6) PNG para o objeto `miniatura/<item uuid>/<sha256>.png` no Garage pelo contrato do L0-11 (11.3); (7) `UPDATE item
SET miniatura_chave, miniatura_sha256` (sem versão: miniatura não entra em `item_versao`; a chave antiga é apagada no
expurgo de órfãos do L0-11, nunca sobrescrita); evento `itens/miniatura`. GIF animado: só o primeiro quadro.
`DELETE /api/itens/{id}/miniatura` limpa as duas colunas.

### 11.2 Entrega

`GET /api/itens/{id}/miniatura` → `pode_ler` → entrega do objeto. Decisão sobre o caminho dos bytes: o nginx não
assina SigV4, por isso a API gera uma URL pré-assinada de 60 s para o Garage e devolve `X-Accel-Redirect` para uma
`location /_garage/` marcada `internal` com `proxy_pass` para essa URL; os bytes não passam pelo Python e o navegador
nunca vê o Garage (D13). Esse é o padrão que o L0-11 fixa para todo objeto. Enquanto o L0-11 não entregar o cliente,
a API lê o objeto pelo adaptador da seção 11.3 e devolve os bytes ela mesma (PNG de 600 × 400 ≤ 200 kB; custo medido
no item, não aqui). `Cache-Control: private, max-age=300` e `ETag` = sha256: a miniatura muda de chave quando muda
de conteúdo, logo o cache nunca serve imagem velha (regra do nome por sha256). Sem miniatura: `204` e a tela mostra o
ícone do tipo (refutação "miniatura ausente": nenhum erro de console, nenhum `<img>` quebrado).

### 11.3 Contrato que este ADR **espera** do L0-11 (não constrói)

`app/objetos/cliente.py` com `guardar(classe: str, item_id: uuid, dados: bytes, content_type: str) -> {chave, sha256,
bytes}` (nome `<classe>/<uuid>/<sha256>.<ext>`, nunca sobrescreve: mesma chave = mesmo conteúdo = devolve sem
gravar), `ler(chave) -> bytes | stream`, `url_assinada(chave, segundos) -> str`, `apagar(chave)`, registro em
`plat.arquivo` com RLS. Enquanto o L0-11 não existir, `app/catalogo/miniatura.py` importa um **adaptador local**
`app/catalogo/objetos_local.py` que grava em `PLAT_DADOS_DIR/miniaturas/<tenant>/<classe>/<uuid>/<sha256>.png` com a
mesma assinatura de função; o adaptador é trocado pelo cliente do L0-11 sem mudar chamador (a chave gravada em
`item.miniatura_chave` é a mesma). Isto é um adaptador de armazenamento, não uma casca: grava e lê de verdade, e o
e2e do L0-03-g passa com ele; o L0-11 migra os arquivos para o bucket com um job (`objetos.migrar_local`) que o
próprio L0-11 entrega.

### 11.4 Tipos de job registrados por este item (`app/catalogo/tarefas.py`, importado em `app/jobs/tipos.py`)

| nome | o que faz | pesado | memória | timeout | chave | resultado |
|---|---|---|---|---|---|---|
| `catalogo.miniatura` | gera 600×400 de um item de dado: `camada_vetorial` → render estático das feições (até 5.000, simplificadas por `ST_SimplifyPreserveTopology` a 1/600 do extent) com Pillow `ImageDraw` sobre fundo neutro, extent do item; `raster` → L1-01 substitui (versão 2 do tipo) por tile do TiTiler; `mapa`/`app` → L2-01/L5 substituem (versão 2) por captura headless do MapLibre (L5 A.2 mediu 25 ms) | não | 512 MB | 120 s | `miniatura:<item>` | `{item_id, miniatura_chave}` |
| `catalogo.lixeira_expurgar` | seção 9.1 | sim | 512 MB | 3.600 s | `lixeira_expurgar` | `{expurgados: n, recusados: [...]}` |
| `catalogo.versoes_compactar` | seção 4.2 | não | 256 MB | 1.800 s | `versoes_compactar` | `{itens: n, versoes_removidas: n}` |
| `catalogo.tags_renomear` | tag de/para no inquilino inteiro | não | 256 MB | 600 s | `tags:<tenant>` | `{itens: n}` |
| `catalogo.migrar_dados` | aplica função de migração de `dados` registrada por nome a todos os itens de um tipo (3.3) | não | 512 MB | 3.600 s | `migrar:<tipo>` | `{itens: n, falhas: [...]}` |
| `catalogo.exportar_lista` | CSV/JSON da lista filtrada (> 1.000 itens vira job; ≤ 1.000 é síncrono) | não | 256 MB | 600 s | — | `{arquivo_id}` |

Periódicos acrescentados a `app/catalogo/periodicos.py` (lista `PERIODICOS` própria, somada pela partida do worker
à do `app/jobs/periodicos.py`; **não** se edita o arquivo do L0-05): `("lixeira diária", "50 3 * * *",
"catalogo.lixeira_expurgar", {})`, `("versões diárias", "40 3 * * *", "catalogo.versoes_compactar", {})`. O portão
do L0-03-g ("miniatura de uma camada por job em ≤ 30 s") depende de haver camada (L0-04): o teste usa a camada de
demonstração (L0-13) e, até ela existir, uma tabela semeada pelo próprio teste em `d_demo`.

---

## 12. Eventos (D14; L0-10; caixa de saída)

`plat.evento` (ADR 0002 seção 9.4) **é** a caixa de saída: append-only, por inquilino, particionada por mês, escrita
só por `plat.evento_registrar` na mesma transação da alteração. O L0-10 dá tela, exportação e partição; o L7-08 lê
`evento` por `id` crescente e entrega webhooks; o L0-03-k lê `evento` para as notificações. Este item acrescenta em
`plat.evento_tipo` (migração 006, `ON CONFLICT DO NOTHING`):

`itens/adicionar`, `itens/atualizar` (propriedades: `campos: [nomes]`, `versao`), `itens/apagar` (`forcado`,
`cascata`), `itens/restaurar`, `itens/mover` (`de_pasta`, `para_pasta`), `itens/transferir` (`de`, `para`,
`arrastados: [uuid]`), `itens/status` (`de`, `para`), `itens/proteger`, `itens/desproteger`, `itens/miniatura`,
`itens/versao_restaurar` (`versao`), `itens/versao_publicar`, `itens/dados_migrar`, `compartilhamento/alterar`
(`antes`, `depois`: acesso e grupos), `compartilhamento/link_criar` (`link_id`, `prefixo`, `itens_incluidos`),
`compartilhamento/link_revogar`, `compartilhamento/link_acesso` (**não** é gravado por acesso: seria um evento por
tile; o contador vive em `compartilhamento_link.acessos` e o `log_acesso` tem a linha — o tipo existe para o L7-08
poder assinar "primeiro acesso" quando `acessos` passa de 0 para 1), `pastas/criar`, `pastas/renomear`, `pastas/mover`,
`pastas/apagar`, `categorias/alterar` (árvore inteira antes/depois em `propriedades`, ≤ 200 nós), `categorias/importar`
(`modelo`, `criadas`), `favoritos/adicionar`, `favoritos/remover`, `lixeira/expurgar` (`item_id`, `tipo`,
`bytes_liberados`), `lixeira/esvaziar`.

Regra testável (herdada do L0-10 e já aplicada aqui): `tests/api/eventos_esperados.py` ganha uma entrada por rota de
escrita deste item; o teste percorre o OpenAPI e reprova rota de escrita sem entrada. `alvo_tipo = 'item' | 'pasta' |
'categoria' | 'link'`, `alvo_id = uuid`. `propriedades` nunca carrega token de link, `descricao` inteira (só o nome
dos campos) nem `dados` inteiros (só `versao`). A Esri dispara webhooks por `/items/add`, `/items/update`,
`/items/delete`, `/items/move`, `/items/share`, `/items/unshare`, `/items/reassign` (E11-wh-triggers, lido no handoff
21): a tradução é linha a linha (`compartilhamento/alterar` cobre share e unshare com `antes/depois`).

---

## 13. Contrato de API (todas em `/api/`; erros no formato D18; `S` sessão, `T` token com escopo, `-` anônimo)

### 13.1 Paginação: `limite/deslocamento` (D18) **e** `cursor`

- Toda lista aceita `limite` (padrão 50, máximo 200 para itens — abaixo dos 1.000 gerais porque cada item carrega
  miniatura/dono/contagens) e `deslocamento` (≤ 10.000; acima, `422 deslocamento_alto` com a instrução de usar
  `cursor`), e devolve `{"total": n, "itens": [...], "proximo_cursor": "<opaco>" | null}`.
- `cursor` = base64url de `{"o": "<ordenar>", "v": <último valor>, "id": "<último uuid>", "q": "<sha256 da consulta>"}`;
  com `cursor`, `deslocamento` é ignorado e a consulta usa chave `(valor, id) < (v, id)` no mesmo `ORDER BY`. Cursor
  cuja `q` não bate com os filtros atuais = `400 cursor_invalido`. Motivo: MEDIDO que `OFFSET 4950` (2,0 ms) **não**
  perde para o cursor (3,4 ms) em 10 mil itens; o cursor entra por **estabilidade** (a tela "Conteúdo" rola uma lista
  que outros usuários editam; com `OFFSET`, um item inserido no topo repete ou pula o último da página) e por ser o
  que a lista infinita da vista "grade" precisa; `total` continua vindo (0,05 ms) porque o portão do L0-12 exige.
  Com `q` (relevância), o cursor guarda `(rank, modificado_em, id)`.
- Cabeçalho `Link: <...>; rel="next"` espelha `proximo_cursor` (D18).

### 13.2 Objeto `item` (o que lista e detalhe devolvem; a lista omite `descricao`, `descricao_html`, `dados`, `termos_de_uso`)

```json
{"id": "…", "tipo": "camada_vetorial", "familia": "camada", "titulo": "…", "resumo": "…", "descricao": "…(markdown)",
 "descricao_html": "…", "tags": ["…"], "creditos": "…", "termos_de_uso": "…", "categorias": [{"id": "…", "caminho": "…"}],
 "classificacao": {…} | null, "dono": {"id": 3, "login": "maria", "nome": "Maria"}, "pasta": {"id": "…", "nome": "…", "caminho": ["…"]} | null,
 "extent": [xmin, ymin, xmax, ymax] | null, "extent_origem": "dado", "miniatura": "/api/itens/<id>/miniatura" | null,
 "acesso": "privado|inquilino|publico", "compartilhado_com_grupos": 2, "links_ativos": 1,
 "status": null | "autoritativo" | "obsoleto", "protegido": false, "origem": "hospedado", "url": null,
 "tamanho_bytes": 0, "pontuacao": 6, "versao_atual": 4, "versao_publicada": null,
 "criado_em": "…Z", "criado_por": {"id", "login"}, "modificado_em": "…Z", "modificado_por": {…},
 "apagado_em": null, "favorito": true, "pode_editar": true, "pode_apagar": true, "pode_compartilhar": true,
 "abre_em": ["mapa", "tabela"], "dados": {…}, "usado_por": 3, "criado_a_partir_de": 1}
```

`favorito`, `pode_*` são calculados para o ator (a tela não adivinha botão); `usado_por`/`criado_a_partir_de` são
contagens (o detalhe tem as rotas). `extent` sai como bbox (o Polygon fica no banco).

### 13.3 Rotas

| M | rota | auth | privilégio / regra | corpo ou query | sucesso | erros específicos |
|---|---|---|---|---|---|---|
| GET | `/tipos-item` | S/T | — | | `200 [{nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em, tem_dado_fisico}]` | |
| GET | `/itens` | S/T(`catalogo:ler`) | RLS (`pode_ler`) | `q, prefixo, ordenar, tipo[], familia[], dono_id[], tags[], categoria[], pasta_id, status[], acesso[], origem, criado_de/ate, modificado_de/ate, bbox, favoritos, meus, grupo_id, limite, deslocamento, cursor` | `200 {total, itens, proximo_cursor, aproximado?}` | `422 busca_complexa` · `422 campo_invalido` · `400 cursor_invalido` · `422 deslocamento_alto` |
| GET | `/itens/facetas` | S/T | idem | mesmos filtros | `200 {tipo, familia, tags, dono, status, categoria, acesso}` | |
| GET | `/itens/tags?q` | S/T | idem | | `200 [{tag, n}]` | |
| POST | `/itens` | S/T(`admin:inquilino`) | `conteudo.criar` (+ `conteudo.publicar_*` conforme tipo) | `{tipo, titulo, resumo?, descricao?, tags?, creditos?, termos_de_uso?, pasta_id?, extent?, categorias?, classificacao?, url?, origem?, dados?}` | `201 item` | `422 tipo_inexistente` · `422 dados_invalidos {detalhe: [{campo, erro, regra}]}` · `422 validacao` (resumo > 2.048, 51ª tag, 21ª categoria, extent fora de faixa) · `422 classificacao_obrigatoria` · `413 cota_itens` · `404 pasta_inexistente` |
| GET | `/itens/{id}` | S/T | `pode_ler` | | `200 item` | `404 item_inexistente` |
| PUT | `/itens/{id}` | S/T | `pode_editar` | campos editáveis (2.2); `dados` inteiro | `200 item` (versão nova) | `400 campo_nao_editavel {campo}` · `400 dono_so_por_transferencia` · `422 dados_invalidos` · `404` · `409 versao_conflito` (se o corpo trouxer `versao_atual` diferente da do banco: edição concorrente; sem o campo, último grava) |
| PATCH | `/itens/{id}` | S/T | `pode_editar` | subconjunto de campos (edição em linha da tela) | `200 item` | idem |
| DELETE | `/itens/{id}?cascata` | S/T | `pode_editar` ou `conteudo.apagar_tudo` | | `204` | `409 item_protegido` · `409 possui_dependentes {ordem, ocultos}` · `404` |
| POST | `/itens/lote` | S/T | por item | `{ids[≤100], acao: mover\|apagar\|restaurar\|tags\|categorias\|proteger\|desproteger\|status\|compartilhar, ...}` | `200 {feitos: n, recusados: [{id, erro}]}` | `422 lote_acima_de_100` |
| POST | `/itens/{id}/mover` | S/T | `pode_editar` | `{pasta_id \| null}` | `200 item` | `404 pasta_inexistente` |
| GET | `/itens/{id}/miniatura` | S/T | `pode_ler` | | `200 image/png` · `204` | `404` |
| POST | `/itens/{id}/miniatura` | S | `pode_editar` | multipart `arquivo` | `200 {miniatura, sha256}` | `413 miniatura_grande` · `415 formato_nao_aceito` · `422 imagem_grande` |
| POST | `/itens/{id}/miniatura/gerar` | S/T | `pode_editar` | | `202 {job_id}` | `409 tipo_sem_gerador` |
| DELETE | `/itens/{id}/miniatura` | S/T | `pode_editar` | | `204` | |
| GET | `/itens/{id}/versoes` | S/T | `pode_ler` | `limite, deslocamento` | `200 {total, itens: [{versao, sha256, autor, rotulo, comentario, compactou, criado_em}]}` | `404` |
| GET | `/itens/{id}/versoes/{n}` | S/T | `pode_ler` | `diff_de=<m>` | `200 {versao, corpo, sha256, diff?: [json patch]}` | `404 versao_inexistente` |
| POST | `/itens/{id}/versoes/{n}/restaurar` | S/T | `pode_editar` | `{comentario?}` | `200 item` | `404` · `403` |
| POST | `/itens/{id}/versoes/{n}/publicar` | S/T | `pode_editar` | | `200 item` | |
| GET | `/itens/{id}/usado-por?profundidade` | S/T | `pode_ler` | | `200 [{item, tipo_relacao, profundidade, caminho} \| {id, oculto: true}]` | |
| GET | `/itens/{id}/criado-a-partir-de` | S/T | `pode_ler` | | `200 [...]` | |
| GET | `/itens/{id}/ordem-de-exclusao` | S/T | `pode_ler` | | `200 {ordem: [{id, titulo, tipo, apaga_junto, pode_editar}], ocultos: n}` | |
| PUT | `/itens/{id}/relacoes` | S/T | `pode_editar` (origem) e `pode_ler` (destinos) | `{relacoes: [{destino, tipo, posicao?}]}` (só para tipos sem extrator; os com `dados` são sincronizados no PUT do item) | `200 [...]` | `422 relacao_com_outro_inquilino` · `422 relacao_familia_invalida` · `409 relacao_ciclo {caminho}` · `422 limite_relacoes` |
| GET | `/itens/{id}/compartilhamento` | S/T | `pode_ler` (detalhe completo só `pode_editar`) | | `200 {…6.5}` | `404` |
| PUT | `/itens/{id}/compartilhamento` | S/T | `pode_editar` + `compartilhar.*` conforme nível | `{acesso?, grupos?: [uuid], aplicar_a_dependencias?: [uuid]}` | `200 {…}` | `400 publico_desligado` · `403 sem_contribuicao_no_grupo {grupo}` · `403 sem_edicao_no_item {detalhe: [uuid]}` · `403 sem_permissao` · `404 grupo_inexistente` |
| POST | `/itens/{id}/links` | S | `pode_editar` + `compartilhar.link` | `{nome?, expira_em?, itens_incluidos?: [uuid], permite_download?}` | `201 {token (única vez), id, prefixo, url, expira_em}` | `400 validade_acima_do_maximo` · `422 limite_links` · `403 sem_edicao_no_item` |
| GET | `/itens/{id}/links` | S | `pode_editar` | | `200 [{id, prefixo, nome, criado_por, criado_em, expira_em, revogado_em, acessos, ultimo_acesso_em, itens_incluidos}]` | |
| DELETE | `/itens/{id}/links/{lid}` | S | `pode_editar` | | `204` (revoga; idempotente) | `404` |
| GET | `/compartilhado/{token}` | - | `link_resolver` | | `200 {item, itens_incluidos: [item]}` (contexto só de leitura) | `404 link_invalido` · `410 link_expirado` · `429` |
| GET | `/compartilhado/{token}/itens/{id}` · `/miniatura` | - | item ∈ link | | `200` | `404` |
| GET | `/publico/itens/{id}` · `/miniatura` | - | `acesso = publico` e inquilino autoriza | | `200 item` (sem `dono.login`, sem `pode_*`) | `404` |
| POST | `/itens/transferir` | S/T | `conteudo.transferir` ou dono + destinatário com `conteudo.criar` | seção 10 | `200 {plano, executado: bool, transferidos: n}` | `422 novo_dono_inativo` · `409 vista_sem_camada` · `409 plano_com_falhas` |
| GET | `/pastas?pai_id` · `/pastas/arvore` | S/T | tenant | | `200 [{id, nome, pai_id, profundidade, ancestrais, itens_visiveis, filhas}]` | |
| POST | `/pastas` | S/T | `conteudo.criar` | `{nome, pai_id?}` | `201 pasta` | `409 nome_existente` · `422 pasta_profunda` · `404 pasta_inexistente` |
| PUT | `/pastas/{id}` | S/T | dono ou `editar_tudo` | `{nome?, pai_id?}` | `200 pasta` | `409 pasta_ciclo` · `422 pasta_profunda` · `409 nome_existente` |
| DELETE | `/pastas/{id}` | S/T | dono ou `editar_tudo` | | `204` | `409 pasta_nao_vazia {itens, pastas}` |
| GET | `/categorias` | S/T | tenant | | `200 {arvore: [...], total, maximo}` | |
| PUT | `/categorias` | S/T | `conteudo.categorias` | `{arvore: [{id?, nome, codigo?, filhas: [...]}]}` (árvore inteira; ids preservados; nó removido com itens = 409) | `200 {arvore}` | `422 limite_categorias` · `422 nivel_maximo` · `409 categoria_em_uso {detalhe: [{id, itens}]}` |
| POST | `/categorias/importar` | S/T | `conteudo.categorias` | `{modelo: iso19115\|inspire}` | `200 {criadas: n, existentes: n}` | `422 modelo_inexistente` |
| GET | `/favoritos` | S/T | próprio | | `200 {total, itens}` (= `/itens?favoritos=true`) | |
| PUT | `/favoritos/{item_id}` · DELETE | S/T | `pode_ler` | | `204` | `404` · `422 limite_favoritos` |
| GET | `/lixeira` | S/T | próprio ou `apagar_tudo` | `limite, deslocamento, tipo, apagado_de/ate` | `200 {total, itens: [item + apagado_por + expurga_em]}` | |
| POST | `/lixeira/{id}/restaurar` | S/T | dono ou `apagar_tudo` | | `200 item` | `404` |
| POST | `/lixeira/esvaziar` | S/T | idem | `{ids?: [uuid]}` | `202 {job_id}` | |
| GET | `/conteudo`, `/conteudo/{id}`, `/conteudo/lixeira`, `/c/{token}`, `/admin/categorias` | páginas | | | `web/conteudo.html`, `web/conteudo_item.html`, `web/conteudo_lixeira.html`, `web/compartilhado.html`, `web/admin/categorias.html` | |

Tokens de serviço: `catalogo:ler` cobre todo `GET` desta tabela que exige `pode_ler`; escrita por token exige
`admin:inquilino` (ADR 0002 8.2); `camada:ler:<uuid>` e `tiles:ler:<uuid>` passam a ser validados aqui na criação
do token (o uuid tem de existir e ser legível pelo dono: `422 escopo_item_inexistente`), completando a pendência
do ADR 0002. Toda rota tem `response_model`; `make openapi` regenera `docs/openapi.json` sem diff no `make check`.

---

## 14. Limites (`app/limites.py`, seção `# --- catálogo (L0-03)`; `docs/LIMITES.md` gerado pelo L0-12)

| constante | valor | fonte |
|---|---|---|
| `ITEM_TITULO_MAX` · `ITEM_RESUMO_MAX` · `ITEM_DESCRICAO_MAX` · `ITEM_CREDITOS_MAX` | 250 · 2.048 · 65.536 · 2.048 | resumo = limite literal Esri (E12-configitem) |
| `ITEM_TAGS_MAX` · `TAG_MAX` | 50 · 128 | hipótese do L0-03-b |
| `ITEM_CATEGORIAS_MAX` · `CATEGORIAS_POR_INQUILINO` (padrão, faixa) · `CATEGORIA_NIVEIS` · `CATEGORIA_NOME_MAX` | 20 · 200 (50..900) · 3 · 100 | E12-configitem, E12-manageitems |
| `PASTA_PROFUNDIDADE_MAX` · `PASTA_NOME_MAX` | 5 · 128 | L0-03-b |
| `MINIATURA_BYTES_MAX` · `MINIATURA_PIXELS_MAX` · `MINIATURA_LARGURA` · `MINIATURA_ALTURA` | 10 MB · 25.000.000 · 600 · 400 | E12-configitem; refutação do L0-03-g |
| `LINKS_POR_ITEM` · `LINK_VALIDADE_MAX_DIAS` · `LINK_TOKEN_BYTES` | 100 · 365 · 32 (64 hex) | L0-12; D6 |
| `RELACOES_POR_ORIGEM` · `RELACOES_POR_DESTINO` · `RELACAO_PROFUNDIDADE_MAX` | 5.000 · 50.000 · 20 | 5.2 |
| `VERSOES_VIVAS` · `VERSOES_BLOCO_COMPACTACAO` · `VERSAO_COMENTARIO_MAX` | 50 · 10 · 500 | L0-03-l |
| `FAVORITOS_POR_USUARIO` · `DESTAQUES_POR_GRUPO` | 500 · 24 | E12-owngroups |
| `BUSCA_Q_MAX` · `BUSCA_TERMOS_MAX` · `BUSCA_TRGM_LIMIAR` · `BUSCA_REFORCO_STATUS` | 1.000 · 200 · 0,3 · 0,25 | 7.2, 7.4, 7.3 (MEDIDO) |
| `ITENS_PAGINA_MAX` · `ITENS_DESLOCAMENTO_MAX` · `LOTE_MAX` (reuso) | 200 · 10.000 · 100 | 13.1; ADR 0002 |
| `LIXEIRA_DIAS` | 30 | D10 |
| `COTA_ITENS` (padrão por inquilino, `tenant.config.catalogo.cota_itens`) | 100.000 | D16 (`413 cota_itens`) |
| `USADO_POR_PROFUNDIDADE_MAX` | 5 | 5.4 |

Todos aplicados por validação (pydantic ou CHECK) e conferidos por `tests/unit/test_limites_catalogo.py` (número no
código = número no CHECK da migração, lido do `information_schema`).

---

## 15. Telas (wireframe em texto; estilo = `web/style.css` existente; módulos ES ≤ 60 kB, soma da tela ≤ 400 kB)

### 15.1 `/conteudo` (`web/conteudo.html` + `web/js/catalogo/conteudo.js`, `lista.js`, `filtros.js`, `pastas.js`, `selecao.js`, `busca_sintaxe.js`)

```
┌ barra superior (web/js/base/layout.js) ───────────────────────────────────────── [sino] [conta] ┐
│ Conteúdo   [ Meu conteúdo | Favoritos | Meus grupos | Inquilino | Lixeira ]      [+ Novo item ▾] │
│ [busca: titulo:mapa tags:ibge modificado:[2026-08 TO *] ............] [ajuda da sintaxe]  ordenar ▾ │
├ pastas (árvore, ≤ 5 níveis) ─┬ filtros ──────────────┬ lista ─────────────────────── [tabela|lista|grade] ┤
│ ▸ Raiz (128)                 │ Tipo      [ ] camada 61 │ [ ] [x] Título            Tipo     Dono   Modificado  Acesso │
│   ▾ Ambiente (40)            │           [ ] mapa  22 │ [ ] [mini] Municípios…  camada   maria  há 2 h     inquilino│
│     ▸ Água (12)              │ Dono      [ ] maria 30 │ [ ] [mini] Rodovias …   camada   joao   ontem      grupos 2 │
│   ▸ Transporte (15)          │ Tags      [ ] ibge  44 │ [ ] [ícone] Mapa base…  mapa     maria  05/09      privado  │
│ [+ pasta]                    │ Categoria ▸ ISO…      │ …                                                        │
│                              │ Status    [ ] autorit. │ [selecionados: 3] [mover ▾] [compartilhar] [tags] [apagar] │
│                              │ Data      de ▭ até ▭ │                                                          │
│                              │ Local     [desenhar] │ ← 1 2 3 … →  (cursor; total 128)   selo obsoleto/autorit. │
└──────────────────────────────┴───────────────────────┴───────────────────────────────────────────────────────────┘
```

- Abas = filtros fixos sobre `GET /api/itens`: Meu conteúdo (`meus=true`), Favoritos (`favoritos=true`), Meus
  grupos (`grupo_id` de cada grupo do usuário, seletor), Inquilino (`acesso=inquilino` ou `ver_tudo`), Lixeira
  (`GET /api/lixeira`). Vista tabela/lista/grade é só renderização do mesmo JSON (`lista.js`); preferência guardada
  em `localStorage` com `try/catch`.
- "Novo item ▾": Arquivo (abre o fluxo de upload do L0-04; até lá, cria item tipo `arquivo` via L0-11), URL (cria
  `conexao`/item por `url`), Mapa em branco (`POST /api/itens {tipo: "mapa", dados: documento vazio}`), Pasta.
- Seleção em massa: até 100 (limite visível: "100 de 128 selecionados; refine o filtro"); ações chamam `POST
  /api/itens/lote`; resultado com `recusados` aparece em diálogo com o motivo por item.
- Teclado: `/` foca a busca, `j/k` navegam, `x` seleciona, `Enter` abre, `Esc` limpa; `aria-*` nas vistas.
- Responsivo: abaixo de 900 px as colunas de pastas e filtros viram gavetas; a tabela vira lista.
- Ajuda da sintaxe: painel com a tabela 7.2 e exemplos clicáveis (`busca_sintaxe.js`, também valida no cliente
  para mostrar `campo desconhecido` antes de enviar; o servidor é quem decide).
- 0 itens: estado vazio com "Nenhum item; crie um ou peça acesso" (sem botão inerte: o botão é o mesmo "Novo item").
- 50 mil itens (adversário): a lista pede 50 por vez com cursor; a árvore de pastas mostra contagens do servidor;
  medida `pagina_conteudo_ms` = primeira pintura ≤ 1,5 s com 10 mil (portão).

### 15.2 `/conteudo/{id}` (`web/conteudo_item.html` + `web/js/catalogo/item.js`, `item_dados.js`, `item_compartilhar.js`, `item_versoes.js`, `item_relacoes.js`)

```
┌ ← Conteúdo   [miniatura 300×200]  Municípios do estado           [favorito] [Abrir em ▾ mapa|tabela] [⋯ ▾] ┐
│              camada vetorial · maria · modificado há 2 h · inquilino + 2 grupos · autoritativo  uuid ⧉  URL ⧉ │
│ [ Visão geral | Dados | Configurações | Versões | Uso ]                          pontuação 6/10 [o que falta] │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Visão geral:  Resumo [editar em linha]   Descrição (markdown → html) [editar]   Tags [chips +]                │
│               Créditos [editar]  Termos de uso [editar]  Categorias [escolher]  Classificação [escolher]       │
│               Criado a partir de: arquivo municipios.gpkg      Usado por: 2 mapas, 1 app  [ver árvore]        │
│ Dados:        formulário gerado do JSON Schema do tipo (campos, srid, geometria…) + [tabela de atributos] (L0-04)│
│ Configurações: extent [mapa | digitar | do dado | da organização]  [ ] proteger contra exclusão                  │
│               status (autoritativo — só admin | obsoleto)  pasta [mover]  dono [transferir…]  miniatura [enviar|gerar]│
│ Versões:      lista (versão, autor, data, rótulo, comentário, compactou) [ver diff] [restaurar] [publicar]     │
│ Uso:          acessos por dia (log_acesso do item e dos links) · links ativos e contagem                       │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- Diálogo **Compartilhar** (`item_compartilhar.js`): nível (privado / inquilino / público — este último só aparece se
  o inquilino permite) + grupos (só os em que o ator contribui, com aviso nos demais) + links (criar com validade,
  copiar uma vez, revogar) + **árvore de dependências** com o nível de cada uma e caixa "aplicar este nível" /
  "incluir no link", desabilitada onde `pode_editar = false` com o motivo no `title`. Nada muda até "Aplicar".
- Diálogo **Apagar**: mostra `ordem-de-exclusao`; se houver dependentes, o botão principal é "Cancelar" e o
  secundário "Apagar os N em cascata"; item protegido mostra a instrução; recomenda marcar obsoleto.
- `⋯`: mover, transferir dono, proteger, status, apagar, copiar uuid/URL, exportar (L0-04-h).
- Edição em linha grava por `PATCH`; a lista reflete ao voltar (portão do L0-03-g).

### 15.3 `/conteudo/lixeira` (`web/conteudo_lixeira.html` + `web/js/catalogo/lixeira.js`)

Tabela: título, tipo, apagado por, apagado em, **expurga em** (apagado + 30 d), ações Restaurar / Apagar agora;
"Esvaziar lixeira" com confirmação por texto; filtro por tipo e período.

### 15.4 `/c/{token}` (`web/compartilhado.html` + `web/js/catalogo/compartilhado.js`)

Página anônima: título, resumo, miniatura, itens incluídos, botão "Abrir" (mapa do L2-01 em modo link) e, se
`permite_download`, "Baixar" (L0-04-h). Link revogado/expirado: página com a mensagem e o código (404/410); `noindex`.

### 15.5 `/admin/categorias` (`web/admin/categorias.html` + `web/js/catalogo/categorias.js`)

Árvore editável (3 níveis, 200 nós, contador), arrastar para reordenar/mover (API nativa, L5 D1), importar
ISO 19115 / INSPIRE, contagem de itens por nó, nó em uso não apaga (mostra os itens).

---

## 16. Testes obrigatórios (o testador roda; o adversário repete por conta própria, sem ler os handoffs 30/31)

| arquivo | prova | medida |
|---|---|---|
| `tests/unit/test_busca_sintaxe.py` | 12 consultas por campo → SQL esperado; `:x`, `foo:bar`, 201 termos, `a & b`, `(a OR b) c`, aspas, intervalo com `*` | — |
| `tests/unit/test_texto_saneado.py` | `<script>`, `onerror=`, `javascript:`, `<iframe>`, `data:` em `img`, Markdown com HTML cru: nada sobrevive; tabela e link `https` sobrevivem | — |
| `tests/unit/test_diff_versoes.py` | JSON Patch de 6 casos (add/replace/remove em objeto e lista) | — |
| `tests/unit/test_limites_catalogo.py` | número em `app/limites.py` = CHECK da migração (lido do catálogo do banco) | — |
| `tests/api/test_itens_modelo.py` | POST/GET/PUT/DELETE; uuid não muda em PUT nem em mover; tipo inexistente 422; resumo de 5.000 → 422; descrição com `<script>` → texto inerte em `descricao_html`; extent fora de [−180,180] → 422; PUT trocando `tenant_id`/`dono_id` → 400; `dados` inválido → 422 com `campo`; **10 mil itens semeados**, `GET /api/itens?tipo=` p95 | `lista_tipo_p95_ms` (< 100) |
| `tests/api/test_cruzado.py` (estender `cruzado_casos.py`) | **toda** rota nova deste ADR com caso A→B (0 × 200/201/204/202); inclui `/compartilhado/<token de B>` chamado com sessão de A (deve ser 200: link é anônimo por desenho — o caso prova que a sessão de A não ganha nada além do link) e `/publico/itens/<id de B>` com inquilino B sem `compartilhar_publico` (404) | `rotas_cobertas = rotas_total` |
| `tests/api/test_funcoes_seguras.py` (estender) | `pode_ler`, `pode_editar`, `link_resolver`, `lixeira_expurgar`, `item_expurgar`, `item_versoes_compactar` sem `=X/` em `proacl`; `plat_app` sem INSERT/UPDATE/DELETE em `item_versao`, `tipo_item`, `relacao_tipo`; `set_config('plat.superadmin','on')` sem sessão de superadmin não revela item privado (a política exige `plat.superadmin` **e** `tenant_atual()` do contexto, e a variável só é ligada pela função de contexto) | — |
| `tests/api/test_busca.py` | corpus 10 mil: `municipio` acha `Município` e `municpio` (trigram, `aproximado: true`); título exato em 1º; tag criada por API aparece na requisição seguinte; 12 consultas por campo; `id:` de item privado de outro → 0; autoritativo antes de comum com o mesmo rank; facetas batem com `count` | `busca_p95_ms` (≤ 200), `busca_trgm_p95_ms`, `facetas_p95_ms` |
| `tests/api/test_compartilhamento.py` | privado→grupo→inquilino→link; membro vê, não-membro 404; link 200 anônimo → revogar → 404 em ≤ 1 s (medido) → 20 clientes simultâneos após revogação 0 × 200; expirado 410; token de 64 hex; `publico` com inquilino desligado 400; compartilhar item de outro com o próprio grupo 404/403; "elevar" camada de outro dono 403; contagem de acessos incrementa | `revogacao_nega_ms` (≤ 1.000) |
| `tests/api/test_relacoes.py` | camada→mapa→app; `usado-por` profundidade 2; DELETE sem cascata 409 com lista; com cascata na ordem (evento por item); ciclo 409; outro inquilino 422; vocabulário fora 422; FK `ON DELETE CASCADE` sem órfã; 5.001ª relação 422; grafo 10 mil/30 mil | `usado_por_p95_ms` (< 50) |
| `tests/api/test_pastas_categorias.py` | pasta em pasta, mover 3 em massa, renomear, apagar vazia, apagar com item 409, ciclo por PUT 409, 6º nível 422, nome de 10 mil caracteres 422; 2 categorias + 1 classificação; 21ª categoria 422; importar ISO = 19 de topo; INSPIRE = 34; categoria de outro inquilino 404 | — |
| `tests/api/test_lixeira.py` | apagar → lixeira → restaurar (uuid e compartilhamentos iguais: diff = 0) → apagar → esvaziar; protegido 409; superadmin apaga protegido com evento `forcado`; admin de inquilino não; expurgo com `agora` simulado (+31 d) apaga a tabela física (`pg_class`); restaurar item de outro inquilino 404; camada usada por mapa sem cascata 409 | `expurgo_s` |
| `tests/api/test_transferencia.py` | 3 itens com 1 falha prevista (novo dono fora do grupo) → plano mostra e `adicionar_aos_grupos` resolve; camada leva 2 vistas; só a vista 409; tudo de um usuário + apagar usuário; uuid e compartilhamentos iguais; link sobrevive; para desabilitado 422; outro inquilino 404 | — |
| `tests/api/test_versoes.py` | 5 PUTs = 5 versões com diff correto; restaurar 2ª = 6ª com sha igual; 1.000 PUTs → compactação mantém ≤ 50 + pendentes/10; sem edição não restaura (403); outro inquilino 404; PUT com versão custa ≤ +5 ms (comparação com PUT em coluna sem gatilho medida no mesmo teste) | `versao_custo_ms` |
| `tests/api/test_miniatura.py` | JPEG → PNG 600×400 (dimensões lidas de volta); 11 MB 413; SVG 415; 20.000×20.000 422 sem estouro de RAM (RSS do processo medido antes/depois < +100 MB); EXIF descartado; PUT de outro dono 404; job `catalogo.miniatura` de camada semeada ≤ 30 s | `miniatura_job_s` |
| `tests/api/test_eventos_catalogo.py` | toda rota de escrita deste ADR tem entrada em `eventos_esperados.py` e grava 1 evento; `propriedades` sem token, sem `descricao`, sem `dados` | — |
| `tests/e2e/test_conteudo.py` (`lento`, `e2e`) | 6 capturas (cada aba e cada vista) 0 erro de console; 10 mil itens: primeira pintura; seleção de 50 → mover; filtros tipo+tag+data = API; busca por campo (captura); 0 itens; título de 2.048 caracteres (elipse, sem estouro); miniatura ausente sem `<img>` quebrado | `pagina_conteudo_ms` (≤ 1.500), `soma_modulos_kb` (≤ 400) |
| `tests/e2e/test_conteudo_item.py` (`lento`) | editar título/resumo/tags em linha e ver na lista; enviar miniatura; gerar por job e ver em ≤ 30 s; compartilhar por grupo, inquilino e link; abrir o link em contexto anônimo (200), revogar, reabrir (404); mapa com camada privada mostra o aviso e a opção; apagar com dependentes; lixeira e restaurar; versões e restaurar; transferir com pré-checagem; capturas nomeadas por tela | — |
| `tests/e2e/test_categorias.py` (`lento`) | árvore, importar ISO, arrastar, nó em uso | — |

Capturas em `tests/e2e/capturas/L0-03-catalogo_<tela>.png`. O `make check` inteiro continua obrigatório (P3).

---

## 17. Paridade que este item entrega (linhas para `docs/PARIDADE.md`; "feito" só depois do teste)

| capacidade (Portal 11.4) | nós | estado previsto |
|---|---|---|
| item com tipo (≈150 tipos REST) | `plat.item` + 14 tipos registrados; os demais entram por migração das linhas donas | parcial (declarado) |
| metadado básico + créditos + termos + extent + categorias + ID + pontuação | seção 2 | feito |
| metadado ISO 19139/19115-3/FGDC/INSPIRE com editor e XML | L0-09 (D17) | fora deste item |
| pastas (um nível, por membro) | hierárquicas por inquilino, ≤ 5 níveis | feito (supera; declarado) |
| favoritos | `plat.favorito` + aba | feito |
| tela Conteúdo (abas, vistas, ordenar, filtros inclusive Location) | 15.1 | feito |
| busca simples (título + tags) e avançada (campos, booleana, intervalo) | 7.2 (+ resumo/descrição com peso; trigram) | feito |
| compartilhamento Owner/Organization/Everyone/Groups + Update sharing | 5 níveis; árvore explícita, nunca em silêncio; link por token (a Esri não tem) | feito |
| grupos (visibilidade, entrada, contribuição, shared update, administrativo, papéis, destaques) | ADR 0002 + `item_grupo.destaque` | feito |
| transferência de dono (regras de grupo e dependentes; em massa; Transfer content) | seção 10 com pré-checagem | feito |
| delete protection; status authoritative/deprecated | 9.2, 9.3 | feito |
| lixeira / restauração | 30 dias (Enterprise não tem; Online 14 d) | feito (supera; declarado) |
| histórico de versões do item | `item_versao` (não encontrado na doc Esri) | feito (supera; declarado) |
| dependências (45 tipos REST; ordem de exclusão) | 11 tipos + ordem + ciclo | parcial (vocabulário menor, declarado) |
| hosted × referenced | `origem` no item; semântica no L0-04-i/L1 | parcial |
| limites (500 GB upload, 20 categorias, 900 categorias, 512 grupos, 20 views) | seção 14 (upload é do L0-04) | feito (próprios, declarados) |
| comentários, avaliações por estrela, RSS, Living Atlas, "related terms" na busca | fora | fora (declarado) |
| OpenAPI publicado | `docs/openapi.json` | feito |

---

## 18. Migração `006_catalogo.sql` (ordem normativa; idempotente; sem BEGIN/COMMIT; aplicada como `postgres`)

```
18.1  funções IMMUTABLE: tags_texto, tags_validas; configuração plat.pt_sem_acento (DO $$ IF NOT EXISTS $$)
18.2  tipo_item (+ 14 INSERT ... ON CONFLICT DO UPDATE com o JSON Schema literal); relacao_tipo (+ 11 linhas)
      REVOKE INSERT/UPDATE/DELETE ... FROM plat_app nas duas
18.3  pasta (+ gatilho tg_pasta_caminho; RLS)                      -- antes de item (FK)
18.4  categoria (+ gatilho de teto/nível/caminho; RLS)             -- antes de item (gatilho de coerência)
18.5  item (+ índices; gatilhos tg_item_imutaveis, tg_item_coerente, tg_item_modificado, tg_item_protegido,
      tg_item_status, tg_item_publico; RLS 6.4)                     -- pode_ler ainda não existe: as políticas são criadas em 18.8
18.6  item_versao (+ gatilho tg_item_versao em item; item_retrato(); item_pontuacao(); RLS)
18.7  item_relacao (+ tg_item_relacao com ciclo; RLS), item_grupo (+ tg_item_grupo; RLS), compartilhamento_link,
      compartilhamento_link_item, favorito (RLS)
18.8  pode_ler, pode_editar, tenant_permite_publico, link_resolver (SECURITY DEFINER), e ENTÃO as políticas de
      item e das tabelas de 18.6/18.7 (DROP POLICY IF EXISTS + CREATE POLICY)
18.9  lixeira_expurgar, item_expurgar, item_versoes_compactar, catalogo_uso(tenant) (SECURITY DEFINER)
18.10 evento_tipo: INSERT ... ON CONFLICT DO NOTHING (seção 12)
18.11 tenant.config: nenhum ALTER (chaves novas em config.catalogo lidas com padrão)
18.12 REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA plat FROM PUBLIC; GRANT ... TO plat_app (repetido, idempotente)
```

O que a 006 **não** faz: não cria tabela de camada (L0-04), não cria `plat.arquivo` (L0-11), não cria
`plat.historico` (L0-10), não altera 002-005, não instala extensão (`pgcrypto`, `unaccent`, `pg_trgm`, `postgis`
já estão; `ltree` não é usado). Se a trilha A publicar `005` com nome que colida, a numeração deste item passa a
`007` sem outra mudança (o gerente decide na integração; o conteúdo é o mesmo).

Custo de reverter: `DROP` das tabelas novas e da configuração de busca; nada em 002-005 muda.

---

## 19. Consequências e o que custa mudar

| decisão | custo de reverter |
|---|---|
| uma tabela `item` + `dados jsonb` por tipo | alto: toda rota, busca, lixeira, versões, relações escritas uma vez sobre ela |
| `tipo_item` global (sem inquilino) | baixo: coluna `tenant_id NULL` + política, uma migração |
| Markdown guardado + saneador próprio | baixo: trocar saneador por `nh3` = 1 função; o dado não muda |
| versão por gatilho | nenhum (é a garantia de "qualquer caminho"); desligar = `DROP TRIGGER` |
| `item_relacao` com vocabulário em tabela | baixo: linha nova por migração |
| `pode_ler`/`pode_editar` na RLS | médio: a função é uma, as políticas apontam para ela; ACL por usuário = uma cláusula |
| FTS no PostgreSQL | baixo enquanto ≤ 100 mil itens (MEDIDO 2,4 ms em 10 mil); motor externo = trocar `busca.py` |
| pastas por inquilino com `uuid[]` | baixo: `ltree` = coluna a mais quando instalar for permitido |
| lixeira por `plat.lixeira = on` | baixo: uma variável e uma cláusula |
| cursor + deslocamento | nenhum: os dois coexistem |
| adaptador local de objetos até o L0-11 | baixo: mesmo contrato; job de migração do L0-11 move os arquivos |
| miniatura de camada por Pillow (versão 1 do job) | nenhum: L2-01 registra versão 2 do mesmo tipo com MapLibre headless |

---

## Anexo A — medições (SQL por stdin, `sudo -u postgres psql -d iagro_sat -v ON_ERROR_STOP=1`, 05/09/2026 ≈ 15:00 UTC; schema `med0004` apagado no fim, `pg_namespace` = 0)

Roteiro: `plataforma/laco/handoffs/T2/preparacao/L0-03-catalogo/medida_0004.sql` (cópia do scratchpad). Saídas
literais (p50/p95 em ms, 30 execuções; 20 no `pode_ler` varrendo tudo; 10 no fecho transitivo):

```
 itens | relacoes | compart_grupo
 10000 |    30000 |          2500
--- FTS: municipio (sem acento) … 50 primeiros            p50 1.93  p95 2.4115  linhas 50
--- FTS: só ts_rank_cd: título exatamente Município em 1º?  Município leste 7 | Município centro 14 | Município sul 21  (r = 1 nos três)
--- FTS: com chave de título exato                         Município | Município leste 7 | Município centro 14 ; p50 2.48 p95 2.59
--- reforço de status ±0,25                                 p50 2.51  p95 2.7055
--- filtro por bbox (GIST) + tipo                           p50 2.38  p95 2.9315
--- OFFSET 4950 × cursor (modificado_em, id)                p50 1.95 p95 2.0255  ×  p50 3.31 p95 3.3875
--- "Município" × "municipio"                               1429 = 1429
--- trigram titulo % 'municpio' (limiar 0,3)                p50 19.555 p95 20.8705 ; acha 1172
--- lista por tipo, 50 primeiros por modificado_em          p50 1.75  p95 2.5875
--- count(*) do mesmo filtro                                p50 0.03  p95 0.0455
--- pode_ler por EXISTS (usuário 7), 10 mil linhas          p50 2.055 p95 3.17   visíveis 2500
--- pode_ler + busca + ordenação                            p50 2.57  p95 3.1105
--- usado_por profundidade 2                                p50 0.91  p95 0.9655 ; 12 linhas
--- fecho transitivo 6 níveis com corte de ciclo            p50 2.305 p95 2.824  ; 839 linhas
--- UPDATE de título (tsvector + 2 GIN)                     update_media_ms=0.513 update_max_ms=6.849
--- versão (to_jsonb + digest sha256)                       versao_media_ms=0.120
--- tamanho                                                 item 37 MB · gin_busca 5544 kB · gin_trgm 5488 kB · gist_extent 704 kB
--- erro reproduzido antes da correção                      ERROR: generation expression is not immutable (array_to_string em coluna gerada)
--- pg_proc.provolatile                                     array_to_string s · to_tsvector(regconfig,text) i · unaccent s · similarity i
```

Python (venv do repositório): `jsonschema 4.26.0`, 1.000 validações de documento com 60 campos = 0,858 s
(0,86 ms/doc); erro com caminho `['campos', 60, 'nome']`. `pip list`: Pillow 12.2.0, pillow_heif 1.5.0, Markdown
3.10.2, markdown-it-py 3.0.0; `bleach`, `nh3`, cliente S3: ausentes. `systemctl is-active plataforma-garage` =
active; `curl :3900/` = 403. `free -g`: 23 GB, 2 GB disponíveis no momento; disco `/` e `/mnt/pgdata` a 98 %.

## Anexo B — URLs testadas (`curl -sIL -m 12` com User-Agent de navegador, 05/09/2026 15:08 UTC; todas HTTP 200)

Esri 11.4 (`https://enterprise.arcgis.com/en/portal/11.4/`): `use/item-details.htm`, `use/configure-item-details.htm`,
`use/move-items.htm`, `use/content-categories.htm`, `use/search.htm`, `use/create-groups.htm`, `use/share-items.htm`,
`use/supported-items.htm`, `use/delete-items.htm`, `use/hosted-web-layers.htm`, `administer/windows/manage-items.htm`,
`administer/windows/configure-classification-schema.htm`. Esri 12.1/latest (`https://doc.esri.com/en/arcgis-enterprise/latest/`):
`create/advanced-search.html`, `share/limit-usage-of-secure-services.html`, `administer/migrate-group-content.html`.
REST (`https://developers.arcgis.com/rest/users-groups-and-items/`): `items-and-item-types/`, `create-folder/`,
`search-reference/`, `recycle-bin-reference/`, `protect/`, `relationship-types/`, `related-items/`, `reassign-item/`,
`notifications/`. Base de conhecimento: KB 000031852 (itens apagados) e KB 000024210 (member must not own items).
PostgreSQL 16: `textsearch-controls`, `textsearch-tables`, `unaccent`, `pgtrgm`, `sql-createtable` (colunas geradas),
`ddl-rowsecurity`, `pgcrypto`. Outras: JSON Schema 2020-12 validation, python-jsonschema, Python-Markdown, Pillow
`Image` (MAX_IMAGE_PIXELS), RFC 6902 (JSON Patch), INSPIRE Themes (34), ISO 19115 `MD_TopicCategoryCode.xml` (19),
MapLibre Style Spec.
