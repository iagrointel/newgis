-- Conferência do trecho de CÓPIA da migração 20260908T0152 (item L4-04-c-unificar-subrede).
--
-- A migração roda numa base onde `plat.rede_subrede_bdgd` está vazia (o aplicador reconstrói o schema do
-- zero), então a cópia de DADOS não seria exercida por nenhuma suíte. Aqui ela é: a tabela antiga é
-- recriada com a forma que tinha, recebe linhas de nível 1, 2 e 3, uma delas referenciada por um
-- `rede_no`, e o MESMO comando de cópia da migração roda em cima. No fim a transação é DESFEITA — nada
-- fica na base.
--
-- Como rodar (o schema vem do ambiente da trilha; em produção seria `plat`):
--   sudo -u postgres psql -d iagro_sat -v ON_ERROR_STOP=1 \
--     -v esquema=$PLAT_SCHEMA -f tests/dados/verifica_migracao_subrede_unificada.sql
--
-- Saída esperada: três linhas `ok`. Qualquer `RAISE EXCEPTION` reprova.

\set ON_ERROR_STOP on
BEGIN;
SET LOCAL search_path TO :esquema, public;

CREATE TABLE rede_subrede_bdgd (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        int NOT NULL,
  rede_id          uuid NOT NULL,
  nivel            smallint NOT NULL CHECK (nivel BETWEEN 1 AND 4),
  codigo_externo   text NOT NULL,
  nome             text,
  controlador_no_id uuid,
  pai_id           uuid,
  atributos        jsonb NOT NULL DEFAULT '{}'::jsonb,
  criado_em        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id),
  UNIQUE (rede_id, nivel, codigo_externo)
);

DO $verifica$
DECLARE
  v_tenant int;
  v_usuario int;
  v_rede uuid;
  v_n1 uuid; v_n2 uuid; v_n3 uuid;
  v_no uuid;
  v_copiadas int;
  v_no_resolve int;
BEGIN
  SELECT t.id INTO v_tenant FROM tenant t ORDER BY t.id LIMIT 1;
  IF v_tenant IS NULL THEN
    RAISE EXCEPTION 'base sem inquilino: rode o semeador antes';
  END IF;
  SELECT u.id INTO v_usuario FROM usuario u WHERE u.tenant_id = v_tenant ORDER BY u.id LIMIT 1;
  INSERT INTO rede (tenant_id, nome, disciplina, dono_id)
    VALUES (v_tenant, 'zt-verifica-migracao', 'eletrica', v_usuario) RETURNING id INTO v_rede;

  INSERT INTO rede_subrede_bdgd (tenant_id, rede_id, nivel, codigo_externo, nome)
    VALUES (v_tenant, v_rede, 1, 'zt-sub', 'Subestação de teste') RETURNING id INTO v_n1;
  INSERT INTO rede_subrede_bdgd (tenant_id, rede_id, nivel, codigo_externo, nome, pai_id)
    VALUES (v_tenant, v_rede, 2, 'zt-ctmt', NULL, v_n1) RETURNING id INTO v_n2;
  INSERT INTO rede_subrede_bdgd (tenant_id, rede_id, nivel, codigo_externo, pai_id)
    VALUES (v_tenant, v_rede, 3, 'zt-trafo', v_n2) RETURNING id INTO v_n3;

  -- devolve o estado de ANTES da migração: a referência de `rede_no` apontava a tabela antiga
  ALTER TABLE rede_no DROP CONSTRAINT rede_no_tenant_subrede_fkey;
  ALTER TABLE rede_no ADD CONSTRAINT rede_no_tenant_subrede_bdgd_fkey
    FOREIGN KEY (tenant_id, subrede_id) REFERENCES rede_subrede_bdgd (tenant_id, id)
    ON DELETE SET NULL (subrede_id);
  INSERT INTO rede_no (tenant_id, rede_id, papel, subrede_id)
    VALUES (v_tenant, v_rede, 'juncao', v_n2) RETURNING id INTO v_no;

  -- o MESMO comando de cópia da migração
  INSERT INTO rede_subrede (id, tenant_id, rede_id, tier_id, nome, estado, origem, nivel,
                            codigo_externo, pai_id, controlador_no_id, atributos, criado_em)
  SELECT b.id, b.tenant_id, b.rede_id, NULL, coalesce(nullif(btrim(b.nome), ''), b.codigo_externo),
         'declarada', 'bdgd', b.nivel, b.codigo_externo, b.pai_id, b.controlador_no_id, b.atributos,
         b.criado_em
    FROM rede_subrede_bdgd b ORDER BY b.nivel
  ON CONFLICT (id) DO NOTHING;

  -- e o MESMO repontamento da migração
  ALTER TABLE rede_no DROP CONSTRAINT rede_no_tenant_subrede_bdgd_fkey;
  ALTER TABLE rede_no ADD CONSTRAINT rede_no_tenant_subrede_fkey
    FOREIGN KEY (tenant_id, subrede_id) REFERENCES rede_subrede (tenant_id, id)
    ON DELETE SET NULL (subrede_id);

  SELECT count(*) INTO v_copiadas FROM rede_subrede
   WHERE rede_id = v_rede AND origem = 'bdgd' AND id IN (v_n1, v_n2, v_n3);
  IF v_copiadas <> 3 THEN
    RAISE EXCEPTION 'a cópia não preservou os três id: % de 3', v_copiadas;
  END IF;
  RAISE NOTICE 'ok: 3 linhas copiadas com o mesmo id';

  PERFORM 1 FROM rede_subrede WHERE id = v_n2 AND pai_id = v_n1 AND nome = 'zt-ctmt';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'pai_id ou nome (coalesce do código) não sobreviveram à cópia';
  END IF;
  RAISE NOTICE 'ok: hierarquia e nome preservados (nome nulo vira o código do arquivo)';

  SELECT count(*) INTO v_no_resolve FROM rede_no n JOIN rede_subrede s ON s.id = n.subrede_id
   WHERE n.id = v_no AND s.origem = 'bdgd';
  IF v_no_resolve <> 1 THEN
    RAISE EXCEPTION 'a referência de rede_no.subrede_id deixou de resolver depois da cópia';
  END IF;
  RAISE NOTICE 'ok: rede_no.subrede_id continua resolvendo, sem reescrever a referência';
END
$verifica$;

ROLLBACK;
