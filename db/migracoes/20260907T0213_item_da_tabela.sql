-- 20260907T0213_item_da_tabela: item L2-01-b-martin-tiles-vetoriais. Achado do adversário nesta mesma
-- rodada (registrado em docs/adr/0023): a rota /internal/tiles/verificar (auth_request do nginx antes do
-- Martin, porque martin-core classifica QUALQUER erro do Postgres como 500 e nunca devolve 401) recebia o
-- `item` de QUERY PARAM do cliente. Um token amplo ("camada:ler", sem uuid — o formato de token de
-- serviço/admin) de um inquilino QUALQUER passava `plat.escopo_cobre` para QUALQUER item que o cliente
-- alegasse, porque `escopo_cobre` só compara strings do próprio token — quem checa se o item pertence ao
-- MESMO inquilino do token é, hoje, só a função de tile (`ctx IS DISTINCT FROM tid`, hardcoded na criação
-- por `camada_tile_garantir`). A rota de verificação não tinha esse hardcode: o resultado medido foi um
-- pedido com token largo do inquilino B, mas citando o item do inquilino A, autenticando com 200 (deveria
-- ser 401/403) — e pior, com o cache do nginx chaveado só por (uri, versão), o tile de A ficava visível
-- para B pelo cache, não só pela consulta. Os dois achados (verificação e cache) estão corrigidos: esta
-- migração resolve o primeiro (a rota agora deriva o item/inquilino da TABELA que está na própria URL,
-- nunca do que o cliente diz), o segundo está em `laco_var/nginx/nginx_trilha.conf` (cache key inclui o
-- inquilino já autenticado).
--
-- `plat.item_da_tabela(p_tabela)`: acha o item do catálogo (id + tenant_id) dono de uma tabela `c_<hex>`,
-- pela mesma varredura de `plat.item` que `camada_tile_garantir` já fazia no retroativo (dados->>'tabela'),
-- SECURITY DEFINER porque a rota de verificação conecta como `plat_leitor` (sem SELECT em `plat.item`).
CREATE OR REPLACE FUNCTION plat.item_da_tabela(p_tabela text)
RETURNS TABLE(item_id uuid, tenant_id int)
LANGUAGE sql SECURITY DEFINER STABLE SET search_path = plat, public AS $$
  SELECT i.id, i.tenant_id
  FROM plat.item i
  WHERE i.tipo = 'camada_vetorial' AND i.apagado_em IS NULL
    AND i.dados->>'tabela' = p_tabela
  LIMIT 1
$$;
REVOKE ALL ON FUNCTION plat.item_da_tabela(text) FROM PUBLIC;
DO $$
DECLARE papel text := plat.papel_leitor();
BEGIN
  EXECUTE format('GRANT EXECUTE ON FUNCTION plat.item_da_tabela(text) TO %I', papel);
END $$;
GRANT EXECUTE ON FUNCTION plat.item_da_tabela(text) TO plat_app;
