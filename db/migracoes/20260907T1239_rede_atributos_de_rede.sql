-- 20260907T1239_rede_atributos_de_rede: ATRIBUTOS DE REDE (item L4-01-d-atributos-de-rede). Depende de
-- 20260906T1553 (plat.rede_atributo, plat.rede_tipo_categoria, categoria 'fonte'/'seccionamento'/'transformacao'
-- já semeadas pelo pacote eletrica-br) e 20260906T2000/T2048 (topologia derivada, item L4-01-b).
--
-- Hipótese do item: "atributo de rede" (network attribute, no vocabulário da Esri) é a coluna da topologia que
-- o traçado lê SEM ir à camada de origem: fase (bitmask A/B/C, propagável), tensão nominal, estado do
-- dispositivo (aberto/fechado, com traversabilidade), capacidade, comprimento geodésico, `is_connected` e
-- `subrede`. `plat.rede_atributo` JÁ EXISTE (item L4-01-a) e já declara, por linha, o nome/tipo/campo de
-- origem POR TIPO DE ATIVO de cada atributo importado do pacote (coluna `origem` jsonb, câmera/coluna do
-- Módulo 10 da BDGD) — a extensão aqui é só marcar, em cada linha já existente, se ela é PROPAGÁVEL (a fase é
-- o único exemplo hoje) e se ela APOIA TRAVERSABILIDADE (a posição normal de operação de uma chave, `P_N_OPE`,
-- é o único exemplo hoje); nenhuma tabela nova para isso, é o mesmo catálogo do item anterior, mais completo.
--
-- Três atributos do enunciado não têm coluna de origem na BDGD (são CALCULADOS pela plataforma, não lidos de
-- nenhum módulo): comprimento geodésico (deriva de `ST_Length(geom::geography)`), `is_connected` e `subrede`
-- (derivam do job de conectividade, ver `app/rede_utilidades/atributos.py`). Entram como linhas SINTÉTICAS de
-- `plat.rede_atributo` (uma por grupo aplicável, `tipo_id` nulo = vale para todos os tipos do grupo), com
-- `origem` marcando `"calculado": true` em vez de câmera/coluna — nunca inventando uma fonte que não existe.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

-- a. duas flags no catálogo já existente (cláusula 1 do portão) -----------------------------------------------
ALTER TABLE plat.rede_atributo ADD COLUMN IF NOT EXISTS propagavel boolean NOT NULL DEFAULT false;
ALTER TABLE plat.rede_atributo ADD COLUMN IF NOT EXISTS apoia_traversabilidade boolean NOT NULL DEFAULT false;
-- FK composta (tenant_id, id) para as tabelas novas abaixo referenciarem uma linha específica do catálogo.
ALTER TABLE plat.rede_atributo DROP CONSTRAINT IF EXISTS rede_atributo_tenant_id_key;
ALTER TABLE plat.rede_atributo ADD CONSTRAINT rede_atributo_tenant_id_key UNIQUE (tenant_id, id);

-- b. colunas nativas da plataforma nas camadas de rede (tensão nominal, capacidade, estado do dispositivo) ----
-- estas NÃO substituem o `atributos` jsonb cru importado da BDGD: são o valor NORMALIZADO que o traçado lê sem
-- ir ao jsonb nem à camada de origem — cláusula central do item ("sem ir à camada").
ALTER TABLE plat.rede_feicao_ponto ADD COLUMN IF NOT EXISTS estado_dispositivo text
  CHECK (estado_dispositivo IS NULL OR estado_dispositivo IN ('aberto', 'fechado'));
ALTER TABLE plat.rede_feicao_ponto ADD COLUMN IF NOT EXISTS tensao_nominal_kv numeric CHECK (tensao_nominal_kv IS NULL OR tensao_nominal_kv >= 0);
ALTER TABLE plat.rede_feicao_ponto ADD COLUMN IF NOT EXISTS capacidade_kva numeric CHECK (capacidade_kva IS NULL OR capacidade_kva >= 0);
ALTER TABLE plat.rede_feicao_linha ADD COLUMN IF NOT EXISTS tensao_nominal_kv numeric CHECK (tensao_nominal_kv IS NULL OR tensao_nominal_kv >= 0);
ALTER TABLE plat.rede_feicao_linha ADD COLUMN IF NOT EXISTS capacidade_kva numeric CHECK (capacidade_kva IS NULL OR capacidade_kva >= 0);

-- c. atributos derivados na topologia: fase propagada, is_connected, subrede (cláusulas 3 e 4 do portão) ------
ALTER TABLE plat.rede_topo_no ADD COLUMN IF NOT EXISTS is_connected boolean NOT NULL DEFAULT false;
ALTER TABLE plat.rede_topo_no ADD COLUMN IF NOT EXISTS subrede_codigo text;
ALTER TABLE plat.rede_topo_aresta ADD COLUMN IF NOT EXISTS is_connected boolean NOT NULL DEFAULT false;
ALTER TABLE plat.rede_topo_aresta ADD COLUMN IF NOT EXISTS subrede_codigo text;
ALTER TABLE plat.rede_topo_aresta ADD COLUMN IF NOT EXISTS tensao_nominal_kv numeric;
ALTER TABLE plat.rede_topo_aresta ADD COLUMN IF NOT EXISTS capacidade_kva numeric;
ALTER TABLE plat.rede_topo_aresta ADD COLUMN IF NOT EXISTS fase_propagada smallint
  CHECK (fase_propagada IS NULL OR fase_propagada BETWEEN 0 AND 7);
CREATE INDEX IF NOT EXISTS ix_rede_topo_no_subrede ON plat.rede_topo_no (rede_id, subrede_codigo);
CREATE INDEX IF NOT EXISTS ix_rede_topo_aresta_subrede ON plat.rede_topo_aresta (rede_id, subrede_codigo);

-- d. aresta INTERNA do dispositivo: liga os dois nós-terminal de um dispositivo de dois terminais (chave,
-- religador, disjuntor...) e carrega a traversabilidade do estado atual — a topologia derivada (item anterior)
-- não gerava nenhuma aresta entre os terminais de um MESMO dispositivo (só entre um terminal e o trecho vizinho
-- coincidente); sem isso não há como o traçado nem o job de conectividade atravessarem uma chave FECHADA.
-- Dispositivos com categoria 'transformacao' (o transformador separa duas subredes, nunca conduz por dentro
-- desta aresta) NUNCA ganham esta linha — decisão da função Python que a constrói, não desta migração.
CREATE TABLE IF NOT EXISTS plat.rede_topo_dispositivo_aresta (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         int NOT NULL REFERENCES plat.tenant(id),
  rede_id           uuid NOT NULL,
  origem_id         uuid NOT NULL,
  no_terminal_1_id  uuid NOT NULL,
  no_terminal_2_id  uuid NOT NULL,
  traversavel       boolean NOT NULL DEFAULT true,
  atualizado_em     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_topo_dispositivo_aresta ON plat.rede_topo_dispositivo_aresta (tenant_id, rede_id, origem_id);
CREATE INDEX IF NOT EXISTS ix_rede_topo_dispositivo_aresta_tenant ON plat.rede_topo_dispositivo_aresta (tenant_id);
CREATE INDEX IF NOT EXISTS ix_rede_topo_dispositivo_aresta_rede ON plat.rede_topo_dispositivo_aresta (rede_id);
ALTER TABLE plat.rede_topo_dispositivo_aresta ADD CONSTRAINT rede_topo_dispositivo_aresta_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_topo_dispositivo_aresta ADD CONSTRAINT rede_topo_dispositivo_aresta_tenant_origem_fkey
  FOREIGN KEY (tenant_id, origem_id) REFERENCES plat.rede_feicao_ponto (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_topo_dispositivo_aresta ADD CONSTRAINT rede_topo_dispositivo_aresta_tenant_no1_fkey
  FOREIGN KEY (tenant_id, no_terminal_1_id) REFERENCES plat.rede_topo_no (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_topo_dispositivo_aresta ADD CONSTRAINT rede_topo_dispositivo_aresta_tenant_no2_fkey
  FOREIGN KEY (tenant_id, no_terminal_2_id) REFERENCES plat.rede_topo_no (tenant_id, id) ON DELETE CASCADE;

-- e. regra de substituição: um dispositivo de um TIPO declarado (ex.: chave de transferência) troca o valor
-- de um atributo propagável (hoje só 'fase') de `de_valor` para `para_valor` ao ser atravessado pelo traçado
-- de propagação — registrada por regra, nunca inferida, nunca aplicada em silêncio (cláusula do enunciado).
CREATE TABLE IF NOT EXISTS plat.rede_atributo_substituicao (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        int NOT NULL REFERENCES plat.tenant(id),
  rede_id          uuid NOT NULL,
  tipo_id          uuid NOT NULL,
  atributo_codigo  text NOT NULL CHECK (atributo_codigo ~ '^[a-z0-9][a-z0-9_-]{0,62}$'),
  de_valor         smallint NOT NULL CHECK (de_valor BETWEEN 0 AND 7),
  para_valor       smallint NOT NULL CHECK (para_valor BETWEEN 0 AND 7),
  descricao        text CHECK (descricao IS NULL OR length(descricao) <= 2000),
  ativa            boolean NOT NULL DEFAULT true,
  criado_em        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_atributo_substituicao
  ON plat.rede_atributo_substituicao (rede_id, tipo_id, atributo_codigo, de_valor);
CREATE INDEX IF NOT EXISTS ix_rede_atributo_substituicao_tenant ON plat.rede_atributo_substituicao (tenant_id);
ALTER TABLE plat.rede_atributo_substituicao ADD CONSTRAINT rede_atributo_substituicao_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_atributo_substituicao ADD CONSTRAINT rede_atributo_substituicao_tenant_tipo_fkey
  FOREIGN KEY (tenant_id, tipo_id) REFERENCES plat.rede_tipo (tenant_id, id) ON DELETE CASCADE;

-- f. discrepância: onde a fase PROPAGADA (calculada a partir do controlador) diverge da fase DECLARADA (lida
-- do arquivo/BDGD) — candidata a erro de cadastro, NUNCA corrigida em silêncio (cláusula do enunciado).
CREATE TABLE IF NOT EXISTS plat.rede_atributo_discrepancia (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         int NOT NULL REFERENCES plat.tenant(id),
  rede_id           uuid NOT NULL,
  aresta_id         uuid NOT NULL,
  atributo_codigo   text NOT NULL,
  valor_declarado   smallint,
  valor_propagado   smallint,
  detectada_em      timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_atributo_discrepancia
  ON plat.rede_atributo_discrepancia (tenant_id, rede_id, aresta_id, atributo_codigo);
CREATE INDEX IF NOT EXISTS ix_rede_atributo_discrepancia_tenant ON plat.rede_atributo_discrepancia (tenant_id);
ALTER TABLE plat.rede_atributo_discrepancia ADD CONSTRAINT rede_atributo_discrepancia_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_atributo_discrepancia ADD CONSTRAINT rede_atributo_discrepancia_tenant_aresta_fkey
  FOREIGN KEY (tenant_id, aresta_id) REFERENCES plat.rede_topo_aresta (tenant_id, id) ON DELETE CASCADE;

-- g. sincronização por TRIGGER na edição (cláusula do enunciado: "por trigger na edição e por lote"). A
-- sincronização POR LOTE é a função Python `atributos.sincronizar_topologia_lote` (não cabe em SQL puro: ela
-- também (re)constrói `rede_topo_dispositivo_aresta`, que depende da CONTAGEM de terminais por dispositivo).
-- O trigger cobre a edição de UMA feição já refletida na topologia; não reconstrói estrutura (isso é
-- `habilitar`), só copia o valor do atributo para a linha derivada já existente.
CREATE OR REPLACE FUNCTION plat.tg_rede_atributo_sincronizar_linha() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  UPDATE plat.rede_topo_aresta SET
    fase_bitmask = NEW.fase_bitmask, atributos = NEW.atributos,
    tensao_nominal_kv = NEW.tensao_nominal_kv, capacidade_kva = NEW.capacidade_kva
  WHERE tenant_id = NEW.tenant_id AND origem_id = NEW.id;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS tg_rede_atributo_sincronizar_linha ON plat.rede_feicao_linha;
CREATE TRIGGER tg_rede_atributo_sincronizar_linha AFTER UPDATE ON plat.rede_feicao_linha
  FOR EACH ROW EXECUTE FUNCTION plat.tg_rede_atributo_sincronizar_linha();

CREATE OR REPLACE FUNCTION plat.tg_rede_atributo_sincronizar_ponto() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.estado_dispositivo IS DISTINCT FROM OLD.estado_dispositivo THEN
    UPDATE plat.rede_topo_dispositivo_aresta SET
      traversavel = (NEW.estado_dispositivo IS DISTINCT FROM 'aberto'), atualizado_em = now()
    WHERE tenant_id = NEW.tenant_id AND origem_id = NEW.id;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS tg_rede_atributo_sincronizar_ponto ON plat.rede_feicao_ponto;
CREATE TRIGGER tg_rede_atributo_sincronizar_ponto AFTER UPDATE ON plat.rede_feicao_ponto
  FOR EACH ROW EXECUTE FUNCTION plat.tg_rede_atributo_sincronizar_ponto();

-- h. RLS + GRANT das 3 tabelas novas, mesmo padrão das migrações anteriores da linha.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_topo_dispositivo_aresta', 'rede_atributo_substituicao', 'rede_atributo_discrepancia'] LOOP
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

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('redes/atributos_declarar', 'atributos de rede declarados (propagável/apoia traversabilidade) após importar o pacote'),
  ('redes/atributos_sincronizar', 'atributos sincronizados em lote das feições para a topologia derivada'),
  ('redes/fase_propagar', 'fase propagada do controlador para jusante, com concordância contra o valor declarado'),
  ('redes/conectividade_recalcular', 'is_connected e subrede recalculados por job sobre a topologia atual'),
  ('redes/substituicao_definir', 'regra de substituição de atributo por tipo de dispositivo definida')
ON CONFLICT (nome) DO NOTHING;
