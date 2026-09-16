-- depende: 20260908T1934_regras_atributo_rede.sql
-- depende: 20260906T2126_rede_modelo_elementos.sql
--
-- Conserto de colisão de nome nunca fechada: duas features diferentes criaram uma tabela chamada
-- plat.rede_regra — 20260906T2126 (regra de CONECTIVIDADE do modelo de elementos: rede_id/tipo/
-- de_tipo_id/para_tipo_id, todos NOT NULL) e 20260908T1934 (regra de ATRIBUTO, item
-- L4-29-regras-de-atributo-de-rede: perfil/nome/alvo_tipo/expressao/atributo_alvo, tenant-wide,
-- sem noção de rede_id nem de tipo de elemento). A entrega de 10/09 que fundiu os dois ramos
-- documentou a colisão e uniu as colunas com ALTER TABLE ADD COLUMN IF NOT EXISTS (aditivo,
-- correto), mas isso só acrescenta coluna — nunca solta um NOT NULL nem repõe CHECK/UNIQUE que
-- não sejam coluna. Resultado: toda chamada de app/rede/regras.py::criar_regra (que nunca teve
-- rede_id, tipo, de_tipo_id nem para_tipo_id — não fazem sentido para uma regra de atributo)
-- batia em NotNullViolation em rede_id assim que tentava gravar (achado em
-- tests/api/rede/test_regras_atributo.py, 8 dos 18 testes).
--
-- Conserto: solta NOT NULL das 4 colunas que só a regra de conectividade usa (o CHECK
-- rede_regra_tipo_check e as FKs de tipo continuam valendo quando a linha É de conectividade —
-- NULL passa em CHECK e em FK, então nenhuma regra de conectividade existente perde validação).
-- Repõe os dois constraints do desenho original de regra de atributo que a união nunca trouxe de
-- volta (não são coluna, então ADD COLUMN IF NOT EXISTS não os alcança): o CHECK
-- perfil='calculo' <=> atributo_alvo preenchido, e o UNIQUE (tenant_id, perfil, nome) — os dois
-- também passam em NULL para linha de conectividade (perfil NULL nas existentes).

ALTER TABLE plat.rede_regra ALTER COLUMN rede_id DROP NOT NULL;
ALTER TABLE plat.rede_regra ALTER COLUMN tipo DROP NOT NULL;
ALTER TABLE plat.rede_regra ALTER COLUMN de_tipo_id DROP NOT NULL;
ALTER TABLE plat.rede_regra ALTER COLUMN para_tipo_id DROP NOT NULL;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conrelid = 'plat.rede_regra'::regclass
      AND conname = 'rede_regra_calculo_tem_atributo_alvo_check'
  ) THEN
    ALTER TABLE plat.rede_regra ADD CONSTRAINT rede_regra_calculo_tem_atributo_alvo_check
      CHECK ((perfil = 'calculo') = (atributo_alvo IS NOT NULL));
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conrelid = 'plat.rede_regra'::regclass
      AND conname = 'rede_regra_tenant_perfil_nome_key'
  ) THEN
    ALTER TABLE plat.rede_regra ADD CONSTRAINT rede_regra_tenant_perfil_nome_key
      UNIQUE (tenant_id, perfil, nome);
  END IF;
END $$;
