-- Item L4-04-c-unificar-subrede: uma tabela só de subrede.
-- depende: 20260907T2031_rede_controlador_de_subrede.sql
-- depende: 20260907T2243_rede_subrede_resumo.sql
--
-- Duas tabelas descreviam o MESMO conceito por caminhos diferentes (ADR 20260907T2200):
--
--   * `plat.rede_subrede` (item L4-04-a): a subrede DERIVADA do controlador — tier, estado limpa/suja,
--     linha agregada, resumo. É o que o traçado calcula a partir da rede que está no chão.
--   * `plat.rede_subrede_bdgd` (item L4-01-c): a hierarquia que o ARQUIVO da BDGD declara — nível 1
--     subestação, 2 alimentador (CTMT), 3 transformador (UNTRMT), com `pai_id` e `codigo_externo`.
--
-- Aqui as duas viram uma só, com uma coluna `origem` que diz de onde a linha veio. A DERIVADA é a
-- canônica (`origem='controlador'`): é ela que tem tier, ciclo de vida e elementos. A do arquivo entra
-- como ORIGEM DECLARADA (`origem='bdgd'`, `estado='declarada'`): não tem tier nem ciclo de vida, tem
-- nível, código do arquivo e pai. `equivalente_id` liga a linha declarada à derivada correspondente
-- quando a reconciliação encontra o par — e fica NULL quando não encontra, que é o número que importa.
--
-- Os `id` das linhas do arquivo são PRESERVADOS na migração: `plat.rede_no.subrede_id` e
-- `plat.rede_aresta.subrede_id` continuam apontando para a mesma linha, agora na tabela unificada, sem
-- reescrever uma única referência.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

-- 1. colunas da origem declarada -------------------------------------------------------------------
ALTER TABLE plat.rede_subrede ADD COLUMN IF NOT EXISTS origem text NOT NULL DEFAULT 'controlador';
ALTER TABLE plat.rede_subrede ADD COLUMN IF NOT EXISTS nivel smallint;
ALTER TABLE plat.rede_subrede ADD COLUMN IF NOT EXISTS codigo_externo text;
ALTER TABLE plat.rede_subrede ADD COLUMN IF NOT EXISTS pai_id uuid;
ALTER TABLE plat.rede_subrede ADD COLUMN IF NOT EXISTS controlador_no_id uuid;
ALTER TABLE plat.rede_subrede ADD COLUMN IF NOT EXISTS equivalente_id uuid;
ALTER TABLE plat.rede_subrede ADD COLUMN IF NOT EXISTS atributos jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE plat.rede_subrede ALTER COLUMN tier_id DROP NOT NULL;

ALTER TABLE plat.rede_subrede DROP CONSTRAINT IF EXISTS rede_subrede_origem;
ALTER TABLE plat.rede_subrede ADD CONSTRAINT rede_subrede_origem
  CHECK (origem IN ('controlador', 'bdgd'));
-- a forma da linha depende da origem: derivada tem tier e ciclo de vida; declarada tem nível e código.
ALTER TABLE plat.rede_subrede DROP CONSTRAINT IF EXISTS rede_subrede_forma_da_origem;
ALTER TABLE plat.rede_subrede ADD CONSTRAINT rede_subrede_forma_da_origem CHECK (
  (origem = 'controlador' AND tier_id IS NOT NULL AND nivel IS NULL AND pai_id IS NULL
   AND equivalente_id IS NULL AND estado IN ('limpa', 'suja')) OR
  (origem = 'bdgd' AND tier_id IS NULL AND nivel BETWEEN 1 AND 4 AND codigo_externo IS NOT NULL
   AND estado = 'declarada'));
ALTER TABLE plat.rede_subrede DROP CONSTRAINT IF EXISTS rede_subrede_estado_check;
ALTER TABLE plat.rede_subrede ADD CONSTRAINT rede_subrede_estado_check
  CHECK (estado IN ('limpa', 'suja', 'declarada'));
ALTER TABLE plat.rede_subrede DROP CONSTRAINT IF EXISTS rede_subrede_atributos_objeto;
ALTER TABLE plat.rede_subrede ADD CONSTRAINT rede_subrede_atributos_objeto
  CHECK (jsonb_typeof(atributos) = 'object');

-- o nome é único dentro do tier SÓ para a subrede derivada (a declarada não tem tier); a do arquivo é
-- única por (rede, nível, código), exatamente a chave que a tabela antiga tinha.
DROP INDEX IF EXISTS plat.ux_rede_subrede;
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_subrede
  ON plat.rede_subrede (rede_id, tier_id, nome) WHERE origem = 'controlador';
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_subrede_declarada
  ON plat.rede_subrede (rede_id, nivel, codigo_externo) WHERE origem = 'bdgd';
CREATE INDEX IF NOT EXISTS ix_rede_subrede_pai ON plat.rede_subrede (pai_id);
CREATE INDEX IF NOT EXISTS ix_rede_subrede_equivalente ON plat.rede_subrede (equivalente_id);

-- 2. os dados da tabela antiga, com o MESMO id ------------------------------------------------------
DO $mig$
BEGIN
  IF to_regclass('plat.rede_subrede_bdgd') IS NULL THEN
    RETURN;
  END IF;
  -- o gatilho de nível ainda não existe na tabela nova: a ordem por nível garante que todo pai já
  -- entrou quando o filho chega, e o gatilho criado adiante passa a valer para a escrita nova.
  INSERT INTO plat.rede_subrede (id, tenant_id, rede_id, tier_id, nome, estado, origem, nivel,
                                 codigo_externo, pai_id, controlador_no_id, atributos, criado_em)
  SELECT b.id, b.tenant_id, b.rede_id, NULL, coalesce(nullif(btrim(b.nome), ''), b.codigo_externo),
         'declarada', 'bdgd', b.nivel, b.codigo_externo, b.pai_id, b.controlador_no_id, b.atributos,
         b.criado_em
    FROM plat.rede_subrede_bdgd b ORDER BY b.nivel
  ON CONFLICT (id) DO NOTHING;

  ALTER TABLE plat.rede_no DROP CONSTRAINT IF EXISTS rede_no_tenant_subrede_bdgd_fkey;
  ALTER TABLE plat.rede_no ADD CONSTRAINT rede_no_tenant_subrede_fkey
    FOREIGN KEY (tenant_id, subrede_id) REFERENCES plat.rede_subrede (tenant_id, id) ON DELETE SET NULL;
  ALTER TABLE plat.rede_aresta DROP CONSTRAINT IF EXISTS rede_aresta_tenant_subrede_bdgd_fkey;
  ALTER TABLE plat.rede_aresta ADD CONSTRAINT rede_aresta_tenant_subrede_fkey
    FOREIGN KEY (tenant_id, subrede_id) REFERENCES plat.rede_subrede (tenant_id, id) ON DELETE SET NULL;

  DROP TABLE plat.rede_subrede_bdgd;
  DROP FUNCTION IF EXISTS plat.rede_subrede_bdgd_validar();
END
$mig$;

-- 3. chaves da própria tabela unificada -------------------------------------------------------------
ALTER TABLE plat.rede_subrede DROP CONSTRAINT IF EXISTS rede_subrede_tenant_pai_fkey;
-- NO ACTION e não RESTRICT: apagar a REDE inteira apaga pai e filho no mesmo comando, e RESTRICT é
-- verificado linha a linha (barraria a exclusão da rede); NO ACTION confere no fim do comando, então
-- continua impedindo deixar filho órfão e deixa a exclusão em cascata da rede passar.
ALTER TABLE plat.rede_subrede ADD CONSTRAINT rede_subrede_tenant_pai_fkey
  FOREIGN KEY (tenant_id, pai_id) REFERENCES plat.rede_subrede (tenant_id, id) ON DELETE NO ACTION;
ALTER TABLE plat.rede_subrede DROP CONSTRAINT IF EXISTS rede_subrede_tenant_equivalente_fkey;
ALTER TABLE plat.rede_subrede ADD CONSTRAINT rede_subrede_tenant_equivalente_fkey
  FOREIGN KEY (tenant_id, equivalente_id) REFERENCES plat.rede_subrede (tenant_id, id) ON DELETE SET NULL;
ALTER TABLE plat.rede_subrede DROP CONSTRAINT IF EXISTS rede_subrede_tenant_controlador_no_fkey;
ALTER TABLE plat.rede_subrede ADD CONSTRAINT rede_subrede_tenant_controlador_no_fkey
  FOREIGN KEY (tenant_id, controlador_no_id) REFERENCES plat.rede_no (tenant_id, id) ON DELETE SET NULL;

-- 4. o gatilho de nível da hierarquia declarada, agora na tabela unificada --------------------------
-- Mesmas regras e MESMOS nomes de exceção da função antiga (`subrede_nivel_invertido`,
-- `subrede_sem_pai`, `subrede_pai_fora_da_rede`, `subrede_controlador_fora_da_rede`): quem trata o erro
-- continua tratando o mesmo. Só vale para a linha declarada; a derivada não tem nível nem pai.
CREATE OR REPLACE FUNCTION plat.rede_subrede_validar() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
  v_pai_nivel smallint;
  v_pai_rede uuid;
  v_pai_origem text;
  v_no_rede uuid;
  v_eq record;
BEGIN
  IF NEW.origem = 'bdgd' THEN
    IF NEW.pai_id IS NOT NULL THEN
      SELECT nivel, rede_id, origem INTO v_pai_nivel, v_pai_rede, v_pai_origem
        FROM plat.rede_subrede WHERE tenant_id = NEW.tenant_id AND id = NEW.pai_id;
      IF NOT FOUND OR v_pai_rede <> NEW.rede_id OR v_pai_origem <> 'bdgd' THEN
        RAISE EXCEPTION 'subrede_pai_fora_da_rede: o pai precisa ser subrede declarada da mesma rede';
      END IF;
      IF v_pai_nivel <> NEW.nivel - 1 THEN
        RAISE EXCEPTION 'subrede_nivel_invertido: subrede de nível % exige pai de nível % (veio %)',
          NEW.nivel, NEW.nivel - 1, v_pai_nivel;
      END IF;
    ELSIF NEW.nivel <> 1 THEN
      RAISE EXCEPTION 'subrede_sem_pai: só a subestação (nível 1) fica sem pai';
    END IF;
    IF NEW.controlador_no_id IS NOT NULL THEN
      SELECT rede_id INTO v_no_rede FROM plat.rede_no
       WHERE tenant_id = NEW.tenant_id AND id = NEW.controlador_no_id;
      IF NOT FOUND OR v_no_rede <> NEW.rede_id THEN
        RAISE EXCEPTION 'subrede_controlador_fora_da_rede: o controlador precisa ser nó da mesma rede';
      END IF;
    END IF;
    IF NEW.equivalente_id IS NOT NULL THEN
      SELECT rede_id, origem INTO v_eq FROM plat.rede_subrede
       WHERE tenant_id = NEW.tenant_id AND id = NEW.equivalente_id;
      IF NOT FOUND OR v_eq.rede_id <> NEW.rede_id OR v_eq.origem <> 'controlador' THEN
        RAISE EXCEPTION 'subrede_equivalente_invalida: o equivalente precisa ser subrede derivada da mesma rede';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END;
$fn$;
DROP TRIGGER IF EXISTS tg_rede_subrede_bdgd_validar ON plat.rede_subrede;
DROP TRIGGER IF EXISTS tg_rede_subrede_validar ON plat.rede_subrede;
CREATE TRIGGER tg_rede_subrede_validar BEFORE INSERT OR UPDATE ON plat.rede_subrede
  FOR EACH ROW EXECUTE FUNCTION plat.rede_subrede_validar();

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('redes/subredes_reconciliar',
   'hierarquia declarada pelo arquivo reconciliada com a subrede derivada do controlador')
ON CONFLICT (nome) DO NOTHING;
