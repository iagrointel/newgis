-- 017_item_ler_por_linha (medido no L0-03 com o corpus de 10 mil): a política de leitura de plat.item era
-- `plat.pode_ler(id)`, uma função chamada UMA VEZ POR LINHA candidata. Cada chamada relia plat.item pela chave
-- primária e reavaliava plat.tem(...), que não depende da linha. Medida antes: GET /api/itens?tipo=mapa&limite=50
-- com 11 mil itens = 457 ms p95, 38.862 buffers para 1.453 linhas; a busca por texto = 2.813 ms p95.
-- Esta migração escreve o MESMO predicado direto na política, com duas mudanças de forma e nenhuma de significado:
--   1. as colunas da linha (dono_id, acesso, apagado_em, id) são lidas da própria linha, sem reler a tabela;
--   2. tudo o que não depende da linha vai dentro de (SELECT ...), que o planejador avalia uma vez por consulta
--      (InitPlan) em vez de uma vez por linha.
-- plat.pode_ler continua existindo e continua sendo a política das tabelas dependentes (item_versao, item_relacao,
-- item_grupo, favorito, link), onde a chamada é por item e não por página de resultado.
-- Idempotente.
DROP POLICY IF EXISTS p_item_ler ON plat.item;
CREATE POLICY p_item_ler ON plat.item FOR SELECT TO plat_app USING (
  tenant_id = (SELECT plat.tenant_atual())
  AND (apagado_em IS NULL OR (SELECT current_setting('plat.lixeira', true)) = 'on')
  AND (
       -- link anônimo: só os itens listados no link desta requisição
       ((SELECT plat.usuario_atual()) IS NULL
        AND id::text = ANY (SELECT unnest(string_to_array(current_setting('plat.link_itens', true), ','))))
    OR -- público (anônimo ou autenticado), só com o inquilino autorizando
       (acesso = 'publico' AND (SELECT plat.tenant_permite_publico(plat.tenant_atual())))
    OR -- console do superadmin (variável + usuário superadmin real)
       (SELECT plat.modo_superadmin())
    OR -- usuário autenticado DO inquilino
       ((SELECT plat.usuario_do_inquilino()) AND (
            dono_id = (SELECT plat.usuario_atual())
         OR (SELECT plat.tem('conteudo.ver_tudo'))
         OR (acesso = 'inquilino' AND (SELECT plat.tem('conteudo.ver_inquilino')))
         OR EXISTS (SELECT 1 FROM plat.item_grupo ig
                    JOIN plat.grupo_membro gm ON gm.grupo_id = ig.grupo_id
                     AND gm.usuario_id = (SELECT plat.usuario_atual()) AND gm.estado = 'ativo'
                    WHERE ig.item_id = item.id)))
  )
);
