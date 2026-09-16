-- depende: 20260907T1927_featureserver_edicao.sql
-- depende: 20260907T2020_historico_geom_nula.sql
--
-- Conserto de regressão de fusão (achado ao restaurar L2-13-b/L2-04-d, wt/f2fixreplica, 16/09):
-- `tests/api/test_featureserver_edicao.py::test_historico_registra_origem_featureserver` grava um
-- INSERT por `applyEdits` do FeatureServer (`_marcar_origem` faz `set_config('plat.origem',
-- 'featureserver', true)` ANTES da escrita — confirmado ao vivo que `plat.origem_atual()` devolve
-- 'featureserver' nesse ponto da transação) e depois lê `plat.feicao_historico.origem` esperando
-- 'featureserver' na linha do insert — mas toda linha vem 'api' (o DEFAULT da coluna), mesmo vindo do
-- FeatureServer.
--
-- Causa raiz: mesma classe de perda-por-fusão do `camada_preparar` em `20260916T1035` — duas migrações
-- do MESMO dia (07/09) redefiniram `plat.feicao_historico_registrar()` inteira a partir de bases
-- diferentes e nunca se enxergaram:
--   - `20260907T1927_featureserver_edicao.sql` (19:27, item L2-04-d) acrescentou a coluna `origem` e
--     `plat.origem_atual()`, e gravou `origem` nas três operações (INSERT/UPDATE/DELETE);
--   - `20260907T2020_historico_geom_nula.sql` (20:20, item L2-07-b) resolveu separadamente o `to_jsonb(NEW)
--     -> 'geom'` sendo `jsonb null` (não SQL NULL) em camada sem geometria — mas partiu do texto de
--     `20260907T1025_historico_feicao.sql` (a versão ANTES das 19:27), então seu `CREATE OR REPLACE`
--     ficou por cima e apagou a gravação de `origem` sem querer. Migração posterior (`chave_migracao`
--     ordena por nome, e 2020 > 1927) venceu, e é o texto que ficou instalado.
--
-- Esta migração funde as duas: o teste de geometria nula por `jsonb_typeof` (2020) + a coluna/valor de
-- `origem` por `plat.origem_atual()` (1927), sem reabrir nenhuma das duas. Idempotente. Sem BEGIN/COMMIT.
-- Aplicada como postgres.

CREATE OR REPLACE FUNCTION plat.feicao_historico_registrar() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  antes jsonb; depois jsonb; ga text; gd text;
BEGIN
  IF TG_OP = 'DELETE' THEN
    antes := to_jsonb(OLD);
    IF jsonb_typeof(antes -> 'geom') = 'object' THEN ga := ((antes -> 'geom') - 'crs')::text; END IF;
    INSERT INTO plat.feicao_historico
      (tenant_id, schema_dado, tabela_dado, fid, globalid, operacao, versao, atributos_antes, geom_antes,
       usuario_id, origem)
    VALUES (OLD.tenant_id, TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.fid, OLD.globalid, 'apagar', OLD.versao,
            antes - 'geom', ga, plat.usuario_atual(), plat.origem_atual());
    RETURN OLD;
  ELSIF TG_OP = 'UPDATE' THEN
    antes := to_jsonb(OLD); depois := to_jsonb(NEW);
    IF jsonb_typeof(antes -> 'geom') = 'object' THEN ga := ((antes -> 'geom') - 'crs')::text; END IF;
    IF jsonb_typeof(depois -> 'geom') = 'object' THEN gd := ((depois -> 'geom') - 'crs')::text; END IF;
    INSERT INTO plat.feicao_historico
      (tenant_id, schema_dado, tabela_dado, fid, globalid, operacao, versao, atributos_antes, atributos_depois,
       geom_antes, geom_depois, usuario_id, origem)
    VALUES (NEW.tenant_id, TG_TABLE_SCHEMA, TG_TABLE_NAME, NEW.fid, NEW.globalid, 'atualizar', NEW.versao,
            antes - 'geom', depois - 'geom', ga, gd, plat.usuario_atual(), plat.origem_atual());
    RETURN NEW;
  ELSIF TG_OP = 'INSERT' THEN
    depois := to_jsonb(NEW);
    IF jsonb_typeof(depois -> 'geom') = 'object' THEN gd := ((depois -> 'geom') - 'crs')::text; END IF;
    INSERT INTO plat.feicao_historico
      (tenant_id, schema_dado, tabela_dado, fid, globalid, operacao, versao, atributos_depois, geom_depois,
       usuario_id, origem)
    VALUES (NEW.tenant_id, TG_TABLE_SCHEMA, TG_TABLE_NAME, NEW.fid, NEW.globalid, 'inserir', NEW.versao,
            depois - 'geom', gd, plat.usuario_atual(), plat.origem_atual());
    RETURN NEW;
  END IF;
  RETURN NULL;
END $$;
