-- Anexos por feição: miniatura + ceife de órfãos (item L2-03-e-anexos).
--
-- 1) `mini_chave`: chave do objeto Garage com a miniatura (PNG ≤ 256 px, gerada no envio para imagem por
--    PIL e para PDF por pdftoppm). NULL = anexo sem miniatura (tipo sem prévia, ou geração falhou — o
--    anexo nunca é recusado por causa da miniatura).
-- 2) `plat.feicao_anexo_orfaos` / `plat.feicao_anexo_chave_limpar`: o ceife de objetos órfãos
--    (app/edicao/anexos.py::ceifar_orfaos, tarefa `edicao.anexos_ceifar`) roda SEM contexto de inquilino —
--    um varredor por inquilino deixaria o objeto físico para trás em todo inquilino cujo job não rodou.
--    A tabela é FORCE RLS (migração 20260907T1035), então o varredor cross-inquilino só existe como
--    SECURITY DEFINER, mesma classe de `plat.uso_tenants_ativos` (sem tenant_id por argumento: nada a
--    conferir com `plat.contexto_confere`, ver 20260906T1601).
--
-- Segurança da seleção: uma linha apagada (lógico) só é órfã quando NENHUMA linha VIVA usa a mesma chave —
-- o dedup por sha256 de app/objetos.py faz dois anexos idênticos da mesma feição dividirem chave, e o
-- DELETE físico de um não pode derrubar o outro. MVCC cobre a corrida com quem apaga AGORA: a marcação
-- não commitada ainda é vista como viva por esta consulta, logo o objeto dela não entra na lista.

ALTER TABLE plat.feicao_anexo ADD COLUMN IF NOT EXISTS mini_chave text;

CREATE OR REPLACE FUNCTION plat.feicao_anexo_orfaos(p_limite int DEFAULT 1000)
RETURNS TABLE (id uuid, tenant_id int, chave text, mini_chave text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT a.id, a.tenant_id, a.chave, a.mini_chave
    FROM plat.feicao_anexo a
   WHERE a.apagado_em IS NOT NULL
     AND a.chave IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM plat.feicao_anexo v
                      WHERE v.chave = a.chave AND v.apagado_em IS NULL)
     AND (a.mini_chave IS NULL OR NOT EXISTS (SELECT 1 FROM plat.feicao_anexo v
                                               WHERE v.mini_chave = a.mini_chave AND v.apagado_em IS NULL))
   ORDER BY a.apagado_em
   LIMIT greatest(1, p_limite)
$$;

-- Limpa chave/mini_chave das linhas já ceifadas (o sha256 fica para auditoria). Só toca linha APAGADA:
-- mesmo que um id vivo chegue por engano, a guarda `apagado_em IS NOT NULL` o devolve intacto.
CREATE OR REPLACE FUNCTION plat.feicao_anexo_chave_limpar(p_ids uuid[])
RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int;
BEGIN
  UPDATE plat.feicao_anexo SET chave = NULL, mini_chave = NULL
   WHERE id = ANY(p_ids) AND apagado_em IS NOT NULL;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

REVOKE ALL ON FUNCTION plat.feicao_anexo_orfaos(int) FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.feicao_anexo_chave_limpar(uuid[]) FROM PUBLIC;
-- plat_app: a suíte chama o ceife pela conexão da aplicação; plat_worker: o periódico roda lá.
GRANT EXECUTE ON FUNCTION plat.feicao_anexo_orfaos(int) TO plat_app, plat_worker;
GRANT EXECUTE ON FUNCTION plat.feicao_anexo_chave_limpar(uuid[]) TO plat_app, plat_worker;
