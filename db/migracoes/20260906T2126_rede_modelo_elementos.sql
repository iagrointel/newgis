-- 20260906T2126_rede_modelo_elementos: MODELO DE ELEMENTOS da rede de utilidades (item L4-01-modelo-rede;
-- ADR docs/adr/20260906T2126-modelo-de-elementos-da-rede.md). Depende de 20260906T1553 (catálogo do pacote:
-- plat.rede, plat.rede_tipo, plat.rede_regra) e de 20260906T1815 (FK composta por inquilino).
-- depende: 20260906T1553_rede_pacote_de_ativos.sql
-- depende: 20260906T1815_rede_fk_por_inquilino.sql
--
-- O que este modelo é e o que não é (evita duplicar os irmãos da família):
--   * L4-01-a guarda o CATÁLOGO (o que pode existir na rede: tipos, regras, terminais).
--   * L4-01-b deriva um ÍNDICE de topologia de camadas de feição editáveis, por coincidência geométrica.
--   * Este item guarda a REDE DE NEGÓCIO: nós (junção/dispositivo/fonte/consumidor) e arestas (trecho)
--     com a conectividade EXPLÍCITA que a fonte declara (na BDGD: PN_CON/PAC nomeados), hierarquia de
--     subredes (subestação -> alimentador -> transformador), estado de manobra (aberto/fechado) e a
--     auditoria da importação. É sobre este grafo que o pgRouting corre.
--
-- Cláusula "pgRouting instalado": o pacote apt postgresql-16-pgrouting é pré-requisito de máquina
-- (instalado em 06/09, versão 4.0.1; a lista deploy/pacotes_apt.txt é do item L7-14 e fica com ele).
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
--
-- Achado deste item (06-07/09/2026, laço de fechamento): a extensão é um objeto ÚNICO por BANCO —
-- "CREATE EXTENSION IF NOT EXISTS" é no-op se ela já existir em QUALQUER schema, mesmo pedindo outro
-- `WITH SCHEMA`. Com várias trilhas compartilhando o mesmo banco (`laco/trilha_ambiente.sh`), a
-- PRIMEIRA trilha a rodar esta migração "ganha" o schema, e todas as outras — cuja consulta é
-- reescrita para o schema DELAS por `CursorSchemaAmbiente` — chamavam `<schema_da_trilha>.pgr_dijkstra`
-- e batiam em UndefinedFunction (medido: extensão ficou em `plat_til401modelo`, outra trilha do MESMO
-- item, enquanto esta rodava como `plat_tf401m`). A extensão fica em `public` (schema que a
-- reescrita NUNCA toca — sempre o mesmo nome literal em toda trilha/homolog/produção), e a função de
-- menor caminho chama `public.pgr_dijkstra` explicitamente, nunca `plat.pgr_dijkstra` reescrito.
CREATE EXTENSION IF NOT EXISTS pgrouting WITH SCHEMA public;

-- -----------------------------------------------------------------------------------------------
-- nó da rede: junção (ponto de conexão anônimo ou nomeado), dispositivo (transformador, chave),
-- fonte (subestação) ou consumidor (unidade consumidora). `seq` é a chave inteira estável que o
-- pgRouting exige (ele não aceita uuid); `codigo_externo` guarda o identificador da fonte
-- (COD_ID / PAC / PN_CON na BDGD) e deduplica o ponto de conexão dentro da rede.
CREATE TABLE IF NOT EXISTS plat.rede_no (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  seq            bigint GENERATED ALWAYS AS IDENTITY,
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  rede_id        uuid NOT NULL,
  papel          text NOT NULL CHECK (papel IN ('juncao', 'dispositivo', 'fonte', 'consumidor')),
  tipo_id        uuid,                       -- plat.rede_tipo; NULL só para junção sem tipo de ativo
  codigo_externo text,                       -- identificador na fonte; NULL = nó criado à mão
  estado         text NOT NULL DEFAULT 'na' CHECK (estado IN ('aberto', 'fechado', 'na')),
  subrede_id     uuid,                       -- subrede imediata (a mais próxima do elemento)
  geom           geometry(Point, 4326),
  atributos      jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(atributos) = 'object'),
  criado_em      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, seq),
  UNIQUE (rede_id, papel, codigo_externo)    -- NULL não colide: nó manual nunca trava importação
);
CREATE INDEX IF NOT EXISTS ix_rede_no_tenant ON plat.rede_no (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_no_rede ON plat.rede_no (rede_id);
CREATE INDEX IF NOT EXISTS ix_rede_no_geom ON plat.rede_no USING gist (geom);
CREATE INDEX IF NOT EXISTS ix_rede_no_subrede ON plat.rede_no (subrede_id);
ALTER TABLE plat.rede_no ADD CONSTRAINT rede_no_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_no ADD CONSTRAINT rede_no_tenant_tipo_fkey
  FOREIGN KEY (tenant_id, tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE RESTRICT;

-- hierarquia de subredes: nível 1 subestação, nível 2 alimentador, nível 3 transformador (a baixa
-- tensão que ele alimenta). `pai_id` aponta a subrede imediatamente acima; o gatilho exige nível
-- exatamente um a menos no pai, o que torna ciclo impossível (uma volta exigiria nível constante).
CREATE TABLE IF NOT EXISTS plat.rede_subrede_bdgd (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        int NOT NULL REFERENCES plat.tenant(id),
  rede_id          uuid NOT NULL,
  nivel            smallint NOT NULL CHECK (nivel BETWEEN 1 AND 4),
  codigo_externo   text NOT NULL,            -- COD_ID da SUB / do CTMT / do UNTRMT na fonte
  nome             text,
  controlador_no_id uuid,                    -- nó que alimenta a subrede (a fonte, o transformador)
  pai_id           uuid,
  atributos        jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(atributos) = 'object'),
  criado_em        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (rede_id, nivel, codigo_externo)
);
CREATE INDEX IF NOT EXISTS ix_rede_subrede_bdgd_tenant ON plat.rede_subrede_bdgd (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_subrede_bdgd_rede ON plat.rede_subrede_bdgd (rede_id);
CREATE INDEX IF NOT EXISTS ix_rede_subrede_bdgd_pai ON plat.rede_subrede_bdgd (pai_id);
ALTER TABLE plat.rede_subrede_bdgd ADD CONSTRAINT rede_subrede_bdgd_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_subrede_bdgd ADD CONSTRAINT rede_subrede_bdgd_tenant_pai_fkey
  FOREIGN KEY (tenant_id, pai_id) REFERENCES plat.rede_subrede_bdgd (tenant_id, id) ON DELETE RESTRICT;
ALTER TABLE plat.rede_subrede_bdgd ADD CONSTRAINT rede_subrede_bdgd_tenant_controlador_fkey
  FOREIGN KEY (tenant_id, controlador_no_id) REFERENCES plat.rede_no (tenant_id, id) ON DELETE SET NULL;

ALTER TABLE plat.rede_no ADD CONSTRAINT rede_no_tenant_subrede_bdgd_fkey
  FOREIGN KEY (tenant_id, subrede_id) REFERENCES plat.rede_subrede_bdgd (tenant_id, id) ON DELETE SET NULL;

-- aresta: trecho/condutor entre dois nós. `no_origem_seq`/`no_destino_seq` são a cópia inteira das
-- pontas que o pgRouting consome (preenchida pelo gatilho, nunca pela aplicação); `comprimento_m`
-- NULL é o ramal de ligação sem geometria da BDGD (declarado, não erro). Estado de manobra não fica
-- na aresta: quem abre/fecha é o dispositivo (nó), e a função de menor caminho exclui as arestas que
-- tocam nó 'aberto'.
CREATE TABLE IF NOT EXISTS plat.rede_aresta (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  seq            bigint GENERATED ALWAYS AS IDENTITY,
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  rede_id        uuid NOT NULL,
  tipo_id        uuid NOT NULL,
  codigo_externo text,
  no_origem_id   uuid NOT NULL,
  no_destino_id  uuid NOT NULL,
  no_origem_seq  bigint NOT NULL,
  no_destino_seq bigint NOT NULL,
  comprimento_m  double precision CHECK (comprimento_m IS NULL OR comprimento_m >= 0),
  fase           text,                          -- FAS_CON da fonte (ABC, BN, ...), como veio
  subrede_id     uuid,
  geom           geometry(LineString, 4326),
  atributos      jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(atributos) = 'object'),
  criado_em      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, seq),
  UNIQUE (rede_id, codigo_externo)
);
CREATE INDEX IF NOT EXISTS ix_rede_aresta_tenant ON plat.rede_aresta (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_aresta_rede ON plat.rede_aresta (rede_id);
CREATE INDEX IF NOT EXISTS ix_rede_aresta_origem ON plat.rede_aresta (no_origem_id);
CREATE INDEX IF NOT EXISTS ix_rede_aresta_destino ON plat.rede_aresta (no_destino_id);
CREATE INDEX IF NOT EXISTS ix_rede_aresta_geom ON plat.rede_aresta USING gist (geom);
CREATE INDEX IF NOT EXISTS ix_rede_aresta_subrede ON plat.rede_aresta (subrede_id);
ALTER TABLE plat.rede_aresta ADD CONSTRAINT rede_aresta_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_aresta ADD CONSTRAINT rede_aresta_tenant_tipo_fkey
  FOREIGN KEY (tenant_id, tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE RESTRICT;
ALTER TABLE plat.rede_aresta ADD CONSTRAINT rede_aresta_tenant_no_origem_fkey
  FOREIGN KEY (tenant_id, no_origem_id) REFERENCES plat.rede_no (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_aresta ADD CONSTRAINT rede_aresta_tenant_no_destino_fkey
  FOREIGN KEY (tenant_id, no_destino_id) REFERENCES plat.rede_no (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_aresta ADD CONSTRAINT rede_aresta_tenant_subrede_bdgd_fkey
  FOREIGN KEY (tenant_id, subrede_id) REFERENCES plat.rede_subrede_bdgd (tenant_id, id) ON DELETE SET NULL;

-- associação explícita entre um nó de ativo (dispositivo/fonte/consumidor) e a rede: conectividade
-- (com a junção onde se liga, ou com outro nó de ativo), contenção ou fixação. O gatilho valida a
-- regra correspondente no catálogo do pacote (plat.rede_regra) ANTES de gravar — fora do catálogo,
-- a escrita falha na hora, não na auditoria.
CREATE TABLE IF NOT EXISTS plat.rede_associacao (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  rede_id      uuid NOT NULL,
  tipo         text NOT NULL CHECK (tipo IN ('conectividade', 'contencao', 'fixacao')),
  de_no_id     uuid NOT NULL,                 -- o ativo (dispositivo/fonte/consumidor)
  para_no_id   uuid,                          -- a junção (conectividade) ou o outro ativo
  para_aresta_id uuid,                        -- o trecho (forma junction-edge direta)
  origem       text NOT NULL DEFAULT 'explicita' CHECK (origem IN ('explicita', 'importacao')),
  criado_em    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  CHECK (num_nonnulls(para_no_id, para_aresta_id) = 1)  -- exatamente um alvo: nó ou aresta
);
CREATE INDEX IF NOT EXISTS ix_rede_associacao_tenant ON plat.rede_associacao (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_associacao_rede ON plat.rede_associacao (rede_id);
CREATE INDEX IF NOT EXISTS ix_rede_associacao_de ON plat.rede_associacao (de_no_id);
CREATE INDEX IF NOT EXISTS ix_rede_associacao_para ON plat.rede_associacao (para_no_id);
ALTER TABLE plat.rede_associacao ADD CONSTRAINT rede_associacao_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_associacao ADD CONSTRAINT rede_associacao_tenant_de_fkey
  FOREIGN KEY (tenant_id, de_no_id) REFERENCES plat.rede_no (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_associacao ADD CONSTRAINT rede_associacao_tenant_para_fkey
  FOREIGN KEY (tenant_id, para_no_id) REFERENCES plat.rede_no (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_associacao ADD CONSTRAINT rede_associacao_tenant_aresta_fkey
  FOREIGN KEY (tenant_id, para_aresta_id) REFERENCES plat.rede_aresta (tenant_id, id) ON DELETE CASCADE;

-- auditoria da importação de uma fonte (BDGD neste item): o que o arquivo declarava, o que entrou,
-- e os desvios explicados (junção sem geometria, trecho sem ponto de conexão, associação que o
-- catálogo de regras não cobre). É o registro que a refutação lê.
CREATE TABLE IF NOT EXISTS plat.rede_importacao (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  rede_id       uuid NOT NULL,
  fonte         text NOT NULL CHECK (fonte IN ('bdgd')),
  caminho       text NOT NULL,
  distribuidora text,
  sha256        text,
  estado        text NOT NULL DEFAULT 'rodando' CHECK (estado IN ('rodando', 'concluida', 'falhou')),
  contagens     jsonb,                        -- {camada: {arquivo: n, inserido: n}} por camada
  desvios       jsonb,                        -- {tipo: {quantidade, explicacao, exemplos}}
  erro          text,
  job_id        uuid,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  concluido_em  timestamptz,
  UNIQUE (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS ix_rede_importacao_tenant ON plat.rede_importacao (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_importacao_rede ON plat.rede_importacao (rede_id);
ALTER TABLE plat.rede_importacao ADD CONSTRAINT rede_importacao_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;

-- -----------------------------------------------------------------------------------------------
-- gatilho da subrede: pai da mesma rede com nível exatamente um a menos; controlador é nó da mesma
-- rede. O nível estrito torna ciclo impossível por construção.
CREATE OR REPLACE FUNCTION plat.rede_subrede_bdgd_validar() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
  v_pai_nivel smallint;
  v_pai_rede uuid;
  v_no_rede uuid;
BEGIN
  IF NEW.pai_id IS NOT NULL THEN
    SELECT nivel, rede_id INTO v_pai_nivel, v_pai_rede FROM plat.rede_subrede_bdgd
     WHERE tenant_id = NEW.tenant_id AND id = NEW.pai_id;
    IF NOT FOUND OR v_pai_rede <> NEW.rede_id THEN
      RAISE EXCEPTION 'subrede_pai_fora_da_rede: o pai precisa ser subrede da mesma rede';
    END IF;
    IF v_pai_nivel <> NEW.nivel - 1 THEN
      RAISE EXCEPTION 'subrede_nivel_invertido: subrede de nível % exige pai de nível % (veio %)',
        NEW.nivel, NEW.nivel - 1, v_pai_nivel;
    END IF;
  ELSIF NEW.nivel <> 1 THEN
    RAISE EXCEPTION 'subrede_sem_pai: só a subestação (nível 1) fica sem pai';
  END IF;
  IF NEW.controlador_no_id IS NOT NULL THEN
    SELECT rede_id INTO v_no_rede FROM plat.rede_no WHERE tenant_id = NEW.tenant_id AND id = NEW.controlador_no_id;
    IF NOT FOUND OR v_no_rede <> NEW.rede_id THEN
      RAISE EXCEPTION 'subrede_controlador_fora_da_rede: o controlador precisa ser nó da mesma rede';
    END IF;
  END IF;
  RETURN NEW;
END;
$fn$;
DROP TRIGGER IF EXISTS tg_rede_subrede_bdgd_validar ON plat.rede_subrede;
CREATE TRIGGER tg_rede_subrede_bdgd_validar BEFORE INSERT OR UPDATE ON plat.rede_subrede_bdgd
  FOR EACH ROW EXECUTE FUNCTION plat.rede_subrede_bdgd_validar();

-- gatilho da aresta: as duas pontas são nós da mesma rede e os seqs inteiros (pgRouting) são
-- copiados aqui — a aplicação nunca preenche `no_origem_seq`/`no_destino_seq` à mão.
CREATE OR REPLACE FUNCTION plat.rede_aresta_validar() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
  v_o record;
  v_d record;
BEGIN
  SELECT rede_id, seq INTO v_o FROM plat.rede_no WHERE tenant_id = NEW.tenant_id AND id = NEW.no_origem_id;
  IF NOT FOUND OR v_o.rede_id <> NEW.rede_id THEN
    RAISE EXCEPTION 'aresta_no_origem_fora_da_rede: o nó de origem precisa ser da mesma rede';
  END IF;
  SELECT rede_id, seq INTO v_d FROM plat.rede_no WHERE tenant_id = NEW.tenant_id AND id = NEW.no_destino_id;
  IF NOT FOUND OR v_d.rede_id <> NEW.rede_id THEN
    RAISE EXCEPTION 'aresta_no_destino_fora_da_rede: o nó de destino precisa ser da mesma rede';
  END IF;
  NEW.no_origem_seq := v_o.seq;
  NEW.no_destino_seq := v_d.seq;
  RETURN NEW;
END;
$fn$;
DROP TRIGGER IF EXISTS tg_rede_aresta_validar ON plat.rede_aresta;
CREATE TRIGGER tg_rede_aresta_validar BEFORE INSERT OR UPDATE ON plat.rede_aresta
  FOR EACH ROW EXECUTE FUNCTION plat.rede_aresta_validar();

-- gatilho da associação: a regra de conectividade (ou contenção/fixação) tem de existir no catálogo
-- do pacote ANTES da escrita. Conectividade com junção: a junção é anônima (sem tipo de ativo), então
-- a regra é conferida contra os tipos das arestas que nela incidem — basta UMA aresta incidente com
-- regra para o tipo do ativo. Conectividade com outro ativo ou com trecho direto: regra entre os dois
-- tipos, em qualquer direção (a direção declarada no pacote é documental; a Esri também valida o par).
CREATE OR REPLACE FUNCTION plat.rede_associacao_validar() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
  v_de record;
  v_para record;
  v_tipo_regra text;
  v_ok boolean;
BEGIN
  SELECT rede_id, papel, tipo_id INTO v_de FROM plat.rede_no
   WHERE tenant_id = NEW.tenant_id AND id = NEW.de_no_id;
  IF NOT FOUND OR v_de.rede_id <> NEW.rede_id THEN
    RAISE EXCEPTION 'associacao_de_fora_da_rede: o nó de origem precisa ser da mesma rede';
  END IF;
  IF v_de.tipo_id IS NULL THEN
    RAISE EXCEPTION 'associacao_sem_tipo: o nó de origem da associação precisa ter tipo de ativo (junção anônima não inicia associação)';
  END IF;

  v_tipo_regra := CASE NEW.tipo
    WHEN 'conectividade' THEN NULL  -- decidido abaixo pela forma do alvo
    WHEN 'contencao' THEN 'contencao'
    WHEN 'fixacao' THEN 'fixacao_estrutural'
  END;

  IF NEW.para_aresta_id IS NOT NULL THEN
    -- forma junction-edge direta: regra entre o tipo da aresta e o tipo do ativo
    SELECT rede_id, tipo_id INTO v_para FROM plat.rede_aresta
     WHERE tenant_id = NEW.tenant_id AND id = NEW.para_aresta_id;
    IF NOT FOUND OR v_para.rede_id <> NEW.rede_id THEN
      RAISE EXCEPTION 'associacao_aresta_fora_da_rede: a aresta alvo precisa ser da mesma rede';
    END IF;
    SELECT EXISTS (
      SELECT 1 FROM plat.rede_regra r
       WHERE r.rede_id = NEW.rede_id AND r.tipo = COALESCE(v_tipo_regra, 'conectividade_no_trecho')
         AND ((r.de_tipo_id = v_para.tipo_id AND r.para_tipo_id = v_de.tipo_id)
           OR (r.de_tipo_id = v_de.tipo_id AND r.para_tipo_id = v_para.tipo_id))
    ) INTO v_ok;
    IF NOT v_ok THEN
      RAISE EXCEPTION 'associacao_sem_regra: o catálogo não tem regra de % entre o tipo do ativo e o tipo da aresta',
        COALESCE(v_tipo_regra, 'conectividade_no_trecho');
    END IF;
    RETURN NEW;
  END IF;

  SELECT rede_id, papel, tipo_id INTO v_para FROM plat.rede_no
   WHERE tenant_id = NEW.tenant_id AND id = NEW.para_no_id;
  IF NOT FOUND OR v_para.rede_id <> NEW.rede_id THEN
    RAISE EXCEPTION 'associacao_para_fora_da_rede: o nó alvo precisa ser da mesma rede';
  END IF;
  IF NEW.de_no_id = NEW.para_no_id THEN
    RAISE EXCEPTION 'associacao_reflexiva: a associação não pode ligar o nó a ele mesmo';
  END IF;

  IF NEW.tipo = 'conectividade' AND v_para.tipo_id IS NULL THEN
    -- alvo é junção anônima: a regra é conferida contra os tipos das arestas que nela incidem
    SELECT EXISTS (
      SELECT 1 FROM plat.rede_aresta a
       JOIN plat.rede_regra r ON r.rede_id = NEW.rede_id AND r.tipo = 'conectividade_no_trecho'
         AND ((r.de_tipo_id = a.tipo_id AND r.para_tipo_id = v_de.tipo_id)
           OR (r.de_tipo_id = v_de.tipo_id AND r.para_tipo_id = a.tipo_id))
       WHERE a.tenant_id = NEW.tenant_id AND a.rede_id = NEW.rede_id
         AND (a.no_origem_id = NEW.para_no_id OR a.no_destino_id = NEW.para_no_id)
    ) INTO v_ok;
    IF NOT v_ok THEN
      RAISE EXCEPTION 'associacao_sem_regra: nenhuma aresta incidente na junção tem regra de conectividade com o tipo do ativo';
    END IF;
  ELSE
    -- ativo-ativo (conectividade_entre_nos) ou contenção/fixação entre tipos
    SELECT EXISTS (
      SELECT 1 FROM plat.rede_regra r
       WHERE r.rede_id = NEW.rede_id AND r.tipo = COALESCE(v_tipo_regra, 'conectividade_entre_nos')
         AND ((r.de_tipo_id = v_para.tipo_id AND r.para_tipo_id = v_de.tipo_id)
           OR (r.de_tipo_id = v_de.tipo_id AND r.para_tipo_id = v_para.tipo_id))
    ) INTO v_ok;
    IF NOT v_ok THEN
      RAISE EXCEPTION 'associacao_sem_regra: o catálogo não tem regra de % entre os dois tipos de ativo',
        COALESCE(v_tipo_regra, 'conectividade_entre_nos');
    END IF;
  END IF;
  RETURN NEW;
END;
$fn$;
DROP TRIGGER IF EXISTS tg_rede_associacao_validar ON plat.rede_associacao;
CREATE TRIGGER tg_rede_associacao_validar BEFORE INSERT OR UPDATE ON plat.rede_associacao
  FOR EACH ROW EXECUTE FUNCTION plat.rede_associacao_validar();

-- -----------------------------------------------------------------------------------------------
-- menor caminho sobre o grafo da rede (pgRouting), respeitando o estado de manobra: aresta que toca
-- nó 'aberto' não entra no grafo. Custo = comprimento geodésico em metros; o ramal sem geometria da
-- BDGD (comprimento NULL) entra com custo 0 e é contado em `ramais_sem_custo` do resultado, para que
-- um caminho barato demais nunca pareça medição. Devolve jsonb com o caminho de nós e arestas.
CREATE OR REPLACE FUNCTION plat.rede_menor_caminho(p_rede uuid, p_de uuid, p_para uuid)
RETURNS jsonb
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
  v_de_seq bigint;
  v_para_seq bigint;
  v_grafo text;
  v_custo double precision := 0;
  v_sem_custo int := 0;
  v_arestas jsonb := '[]'::jsonb;
  v_n int := 0;
BEGIN
  SELECT seq INTO v_de_seq FROM plat.rede_no WHERE id = p_de AND rede_id = p_rede;
  SELECT seq INTO v_para_seq FROM plat.rede_no WHERE id = p_para AND rede_id = p_rede;
  IF v_de_seq IS NULL OR v_para_seq IS NULL THEN
    RAISE EXCEPTION 'menor_caminho_no_fora_da_rede: origem e destino precisam ser nós da mesma rede';
  END IF;

  -- o SQL do grafo vai como texto (o pgRouting executa a consulta no servidor): rede filtrada pelo
  -- literal da função, nó 'aberto' exclui toda aresta que o toca, ramal sem geometria custa 0 e é
  -- contado à parte abaixo, para que um caminho barato demais nunca pareça medição.
  v_grafo := format(
    'SELECT a.seq AS id, a.no_origem_seq AS source, a.no_destino_seq AS target, '
    'COALESCE(a.comprimento_m, 0)::float8 AS cost, COALESCE(a.comprimento_m, 0)::float8 AS reverse_cost '
    'FROM plat.rede_aresta a WHERE a.rede_id = %L::uuid '
    'AND NOT EXISTS (SELECT 1 FROM plat.rede_no n WHERE n.rede_id = a.rede_id AND n.estado = ''aberto'' '
    '  AND (n.id = a.no_origem_id OR n.id = a.no_destino_id))', p_rede);

  WITH dij AS (
    SELECT d.node, d.edge, d.seq AS ordem FROM public.pgr_dijkstra(v_grafo, v_de_seq, v_para_seq, directed := false) d
  )
  SELECT count(*),
         COALESCE(sum(COALESCE(a.comprimento_m, 0)) FILTER (WHERE a.seq IS NOT NULL), 0),
         COALESCE(sum((a.comprimento_m IS NULL)::int) FILTER (WHERE a.seq IS NOT NULL), 0),
         COALESCE(jsonb_agg(jsonb_build_object('ordem', dij.ordem, 'no_seq', dij.node, 'aresta_seq', dij.edge,
                            'custo_aresta_m', a.comprimento_m) ORDER BY dij.ordem)
                  FILTER (WHERE dij.edge > 0), '[]'::jsonb)
    INTO v_n, v_custo, v_sem_custo, v_arestas
    FROM dij LEFT JOIN plat.rede_aresta a ON a.rede_id = p_rede AND a.seq = dij.edge;

  IF v_n = 0 THEN
    RETURN jsonb_build_object('encontrado', false, 'custo_m', NULL, 'ramais_sem_custo', 0, 'arestas', '[]'::jsonb);
  END IF;
  RETURN jsonb_build_object('encontrado', true, 'custo_m', v_custo, 'ramais_sem_custo', v_sem_custo,
                            'arestas', v_arestas);
END;
$fn$;

-- RLS: o mesmo padrão do catálogo da rede (20260906T1553). Leitura pelo inquilino; escrita exige
-- `rede.editar` avaliado na aplicação, com a política de linha como última defesa.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_no', 'rede_aresta', 'rede_subrede_bdgd', 'rede_associacao', 'rede_importacao'] LOOP
    EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_ler ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_ler ON plat.%I FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_inserir ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_inserir ON plat.%I FOR INSERT TO plat_app '
                   'WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_do_inquilino())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_alterar ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_alterar ON plat.%I FOR UPDATE TO plat_app '
                   'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_apagar ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_apagar ON plat.%I FOR DELETE TO plat_app USING (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON plat.%I TO plat_app', t);
  END LOOP;
END $$;

GRANT EXECUTE ON FUNCTION plat.rede_menor_caminho(uuid, uuid, uuid) TO plat_app;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('redes/importar_bdgd', 'rede montada a partir da BDGD (distribuidora, contagens conferidas, desvios)')
ON CONFLICT (nome) DO NOTHING;
