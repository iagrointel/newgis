-- item L5-20-sites-paginas-publicas, continuação da 20260908T1134_site_paginas_publicas.sql (arquivo novo
-- porque aquela já está aplicada; migração aplicada nunca é editada).
-- depende: 20260908T1134_site_paginas_publicas.sql
--
-- Motivo, medido ao rodar o teste: o cartão de mapa/aplicativo precisa saber se o item citado tem uma
-- publicação em /p/<inquilino>/<slug>, e a página do site é ANÔNIMA — sem contexto de sessão, a RLS de
-- plat.item_publicacao (tenant_atual() + pode_editar) devolve zero linha, e o cartão silenciava. A leitura
-- passa a ser por função SECURITY DEFINER, escopada ao inquilino do site e só para item que já é público.

CREATE OR REPLACE FUNCTION plat.site_publicacao_slug(p_tenant int, p_item uuid)
RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT p.slug
  FROM plat.item_publicacao p JOIN plat.item i ON i.id = p.item_id
  WHERE p.item_id = p_item AND p.tenant_id = p_tenant AND i.tenant_id = p_tenant
    AND i.apagado_em IS NULL AND i.versao_publicada IS NOT NULL
    AND i.acesso = 'publico' AND plat.tenant_permite_publico(p_tenant)
$$;

REVOKE EXECUTE ON FUNCTION plat.site_publicacao_slug(int, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.site_publicacao_slug(int, uuid) TO plat_app;
