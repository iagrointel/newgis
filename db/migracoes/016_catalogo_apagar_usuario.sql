-- 016_catalogo_apagar_usuario (achado do teste de transferência do L0-03-j): depois de transferir TODOS os itens
-- de um usuário, apagá-lo ainda falhava com 409 em_uso (item_criado_por_fkey). criado_por, modificado_por e
-- apagado_por são rastro histórico, não posse: passam a ON DELETE SET NULL. dono_id continua NOT NULL e continua
-- barrando a exclusão — é para isso que existe a transferência. O mesmo vale para quem criou um link.
-- tg_item_antes é reescrita porque a ON DELETE SET NULL chega como UPDATE e batia em campo_imutavel: criado_por
-- segue imutável, salvo quando o valor novo é NULL (só a chave estrangeira produz isso). Idempotente.
ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_criado_por_fkey;
ALTER TABLE plat.item ADD CONSTRAINT item_criado_por_fkey
  FOREIGN KEY (criado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;
ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_modificado_por_fkey;
ALTER TABLE plat.item ADD CONSTRAINT item_modificado_por_fkey
  FOREIGN KEY (modificado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;
ALTER TABLE plat.item DROP CONSTRAINT IF EXISTS item_apagado_por_fkey;
ALTER TABLE plat.item ADD CONSTRAINT item_apagado_por_fkey
  FOREIGN KEY (apagado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;
ALTER TABLE plat.compartilhamento_link ALTER COLUMN criado_por DROP NOT NULL;
ALTER TABLE plat.compartilhamento_link DROP CONSTRAINT IF EXISTS compartilhamento_link_criado_por_fkey;
ALTER TABLE plat.compartilhamento_link ADD CONSTRAINT compartilhamento_link_criado_por_fkey
  FOREIGN KEY (criado_por) REFERENCES plat.usuario(id) ON DELETE SET NULL;

CREATE OR REPLACE FUNCTION plat.tg_item_antes() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE mudou_corpo boolean; c uuid;
BEGIN
  IF TG_OP = 'UPDATE' THEN
    -- 2.2 imutáveis
    IF NEW.id <> OLD.id OR NEW.tenant_id <> OLD.tenant_id OR NEW.tipo <> OLD.tipo OR NEW.criado_em <> OLD.criado_em
       OR (NEW.criado_por IS DISTINCT FROM OLD.criado_por AND NEW.criado_por IS NOT NULL)
       OR NEW.versao_atual <> OLD.versao_atual THEN
      RAISE EXCEPTION 'campo_imutavel';
    END IF;
    IF NEW.dono_id <> OLD.dono_id AND current_setting('plat.transferencia', true) IS DISTINCT FROM 'on' THEN
      RAISE EXCEPTION 'dono_so_por_transferencia';
    END IF;
    -- 9.2 proteção: exclusão lógica de item protegido só em modo superadmin (variável + usuário superadmin real)
    IF NEW.apagado_em IS NOT NULL AND OLD.apagado_em IS NULL AND OLD.protegido AND NOT plat.modo_superadmin() THEN
      RAISE EXCEPTION 'item_protegido';
    END IF;
  END IF;
  -- 2.2 coerência de inquilino
  IF NOT EXISTS (SELECT 1 FROM plat.usuario u WHERE u.id = NEW.dono_id AND u.tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'usuario_de_outro_inquilino';
  END IF;
  IF NEW.pasta_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM plat.pasta p WHERE p.id = NEW.pasta_id AND p.tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'pasta_de_outro_inquilino';
  END IF;
  FOREACH c IN ARRAY NEW.categorias LOOP
    IF NOT EXISTS (SELECT 1 FROM plat.categoria k WHERE k.id = c AND k.tenant_id = NEW.tenant_id) THEN
      RAISE EXCEPTION 'categoria_de_outro_inquilino';
    END IF;
  END LOOP;
  -- 9.3 autoritativo liga proteção; 6.1 público exige o inquilino autorizar
  IF NEW.status = 'autoritativo' AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'autoritativo') THEN
    NEW.protegido := true;
  END IF;
  IF NEW.acesso = 'publico' AND (TG_OP = 'INSERT' OR OLD.acesso <> 'publico') AND NOT plat.tenant_permite_publico(NEW.tenant_id) THEN
    RAISE EXCEPTION 'publico_desligado';
  END IF;
  -- versão: só quando o retrato muda (2.2, seção 4); pontuação sempre recalculada
  mudou_corpo := TG_OP = 'INSERT' OR plat.item_retrato(NEW) <> plat.item_retrato(OLD);
  NEW.pontuacao := plat.item_pontuacao(NEW);
  IF mudou_corpo THEN
    NEW.versao_atual := CASE WHEN TG_OP = 'INSERT' THEN 1 ELSE OLD.versao_atual + 1 END;
  END IF;
  IF TG_OP = 'UPDATE' AND (mudou_corpo OR NEW.pasta_id IS DISTINCT FROM OLD.pasta_id OR NEW.acesso <> OLD.acesso
     OR NEW.status IS DISTINCT FROM OLD.status OR NEW.protegido <> OLD.protegido
     OR NEW.miniatura_chave IS DISTINCT FROM OLD.miniatura_chave OR NEW.dono_id <> OLD.dono_id) THEN
    NEW.modificado_em := now();
    NEW.modificado_por := coalesce(plat.usuario_atual(), NEW.modificado_por);
  END IF;
  IF TG_OP = 'INSERT' THEN
    NEW.modificado_por := coalesce(NEW.modificado_por, plat.usuario_atual());
    NEW.criado_por := coalesce(NEW.criado_por, plat.usuario_atual());
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS item_antes ON plat.item;
CREATE TRIGGER item_antes BEFORE INSERT OR UPDATE ON plat.item FOR EACH ROW EXECUTE FUNCTION plat.tg_item_antes();
REVOKE EXECUTE ON FUNCTION plat.tg_item_antes() FROM PUBLIC, plat_app;
