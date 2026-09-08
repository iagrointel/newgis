-- depende: 20260907T1025_historico_feicao.sql
-- Conserto (achado do item L2-07-b): o gatilho de histórico quebrava em toda linha com geometria NULA —
-- `to_jsonb(NEW) -> 'geom'` é o jsonb `null` (não SQL NULL), o teste `IS NOT NULL` passava e `null - 'crs'`
-- levanta "cannot delete from scalar". Camadas de formulário sem geopoint e tabelas filhas de repetição têm
-- geom nula em toda linha. Só o teste de tipo muda (jsonb_typeof = 'object'); o resto é idêntico à 20260907T1025.
CREATE OR REPLACE FUNCTION plat.feicao_historico_registrar() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  antes jsonb; depois jsonb; ga text; gd text;
BEGIN
  IF TG_OP = 'DELETE' THEN
    antes := to_jsonb(OLD);
    IF jsonb_typeof(antes -> 'geom') = 'object' THEN ga := ((antes -> 'geom') - 'crs')::text; END IF;
    INSERT INTO plat.feicao_historico
      (tenant_id, schema_dado, tabela_dado, fid, globalid, operacao, versao, atributos_antes, geom_antes,
       usuario_id)
    VALUES (OLD.tenant_id, TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.fid, OLD.globalid, 'apagar', OLD.versao,
            antes - 'geom', ga, plat.usuario_atual());
    RETURN OLD;
  ELSIF TG_OP = 'UPDATE' THEN
    antes := to_jsonb(OLD); depois := to_jsonb(NEW);
    IF jsonb_typeof(antes -> 'geom') = 'object' THEN ga := ((antes -> 'geom') - 'crs')::text; END IF;
    IF jsonb_typeof(depois -> 'geom') = 'object' THEN gd := ((depois -> 'geom') - 'crs')::text; END IF;
    INSERT INTO plat.feicao_historico
      (tenant_id, schema_dado, tabela_dado, fid, globalid, operacao, versao, atributos_antes, atributos_depois,
       geom_antes, geom_depois, usuario_id)
    VALUES (NEW.tenant_id, TG_TABLE_SCHEMA, TG_TABLE_NAME, NEW.fid, NEW.globalid, 'atualizar', NEW.versao,
            antes - 'geom', depois - 'geom', ga, gd, plat.usuario_atual());
    RETURN NEW;
  ELSIF TG_OP = 'INSERT' THEN
    depois := to_jsonb(NEW);
    IF jsonb_typeof(depois -> 'geom') = 'object' THEN gd := ((depois -> 'geom') - 'crs')::text; END IF;
    INSERT INTO plat.feicao_historico
      (tenant_id, schema_dado, tabela_dado, fid, globalid, operacao, versao, atributos_depois, geom_depois,
       usuario_id)
    VALUES (NEW.tenant_id, TG_TABLE_SCHEMA, TG_TABLE_NAME, NEW.fid, NEW.globalid, 'inserir', NEW.versao,
            depois - 'geom', gd, plat.usuario_atual());
    RETURN NEW;
  END IF;
  RETURN NULL;
END $$;
