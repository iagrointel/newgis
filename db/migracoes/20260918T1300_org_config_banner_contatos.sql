-- Config da organização: banner/termo pré-login e contatos administrativos (item L0-07-a-configuracoes-org).
--
-- Duas mudanças:
--
-- 1) `plat.tenant_publico` passa a devolver também `banner_aviso` e `termo_acesso` (de `tenant.config`).
--    A tela /entrar chama esta função ANTES de qualquer credencial (pré-contexto, SECURITY DEFINER) e o
--    portão do item manda o banner de aviso e o termo de acesso aparecerem ali. Devolver o par aqui é o
--    mesmo desenho já usado para slug/nome/ativo: o mínimo de dado público, sem sessão, sem RLS no caminho.
--    PostgreSQL não troca o tipo de retorno com CREATE OR REPLACE, então é DROP + CREATE — os chamadores
--    (rotas_login.provedores, oidc, saml, cli) usam `SELECT *`, coluna a mais não quebra nenhum. Os GRANTs
--    refazem exatamente o trio medido no schema (app, worker, leitor — todos só EXECUTE).
--
-- 2) Semeia `config.contatos_admin` dos inquilinos que ainda não têm a chave: o admin ATIVO mais antigo
--    do inquilino — é quem criou o inquilino na prática (a instalação começa por ele), o mesmo papel que o
--    "initial administrator account" vira contato no ArcGIS Enterprise. Sem esta semente o PUT full-replace
--    de /api/org (que exige contatos_admin ≥ 1, refutação do adversário: "define contato administrativo
--    vazio" = 422) trancaria a PRIMEIRA gravação de qualquer inquilino antigo. Idempotente: o WHERE só
--    toca quem não tem a chave.

DROP FUNCTION IF EXISTS plat.tenant_publico(text);
CREATE FUNCTION plat.tenant_publico(p_slug text)
RETURNS TABLE (id int, slug text, nome text, ativo boolean, banner_aviso text, termo_acesso text)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT t.id, t.slug, t.nome, t.ativo,
         NULLIF(btrim(t.config ->> 'banner_aviso'), ''),
         NULLIF(btrim(t.config ->> 'termo_acesso'), '')
  FROM plat.tenant t WHERE t.slug = p_slug
$$;

REVOKE ALL ON FUNCTION plat.tenant_publico(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.tenant_publico(text) TO plat_app, plat_worker, plat_leitor;

UPDATE plat.tenant t
SET config = config || jsonb_build_object('contatos_admin', jsonb_build_array(u.login))
FROM (
  SELECT DISTINCT ON (tenant_id) tenant_id, login
  FROM plat.usuario
  WHERE perfil = 'admin' AND ativo
  ORDER BY tenant_id, id
) u
WHERE t.id = u.tenant_id AND NOT (t.config ? 'contatos_admin');
