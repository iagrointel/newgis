-- 018_item_ler_durante_transferencia (achado do teste de transferência depois da 017): ao trocar o dono, o
-- PostgreSQL confere a linha NOVA contra a política de leitura da tabela. Enquanto a política era plat.pode_ler(id),
-- a função SECURITY DEFINER relia plat.item e enxergava a linha ANTIGA, então a checagem passava por acidente. Com o
-- predicado escrito na própria linha, a checagem passou a ver o dono novo e a transferência do editor para outra
-- pessoa parava com 'new row violates row-level security policy'.
-- A transferência já roda em modo próprio: executar() liga plat.transferencia dentro da transação, e é essa variável
-- que o gatilho tg_item_antes exige para deixar dono_id mudar. A política passa a aceitar a linha enquanto esse modo
-- está ligado, DENTRO do inquilino da sessão e só para usuário do inquilino: o recorte por tenant_id continua sendo a
-- primeira condição e não muda. Idempotente.
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
         OR -- transferência de dono em curso nesta transação: a linha recém-gravada já tem o dono novo
            (SELECT current_setting('plat.transferencia', true)) = 'on'
         OR (SELECT plat.tem('conteudo.ver_tudo'))
         OR (acesso = 'inquilino' AND (SELECT plat.tem('conteudo.ver_inquilino')))
         OR EXISTS (SELECT 1 FROM plat.item_grupo ig
                    JOIN plat.grupo_membro gm ON gm.grupo_id = ig.grupo_id
                     AND gm.usuario_id = (SELECT plat.usuario_atual()) AND gm.estado = 'ativo'
                    WHERE ig.item_id = item.id)))
  )
);
