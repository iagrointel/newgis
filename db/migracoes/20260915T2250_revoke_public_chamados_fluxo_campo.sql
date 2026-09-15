-- Fecha EXECUTE para PUBLIC nas funções que nasceram depois da 20260908T1031_revoke_public_amc. Idempotente.
--
-- ACHADO G2-8 (regressão, medida 15/09/2026 em tests/api/catalogo/test_adversario_g2.py, achado transversal do
-- laudo laco/handoffs/T3/ataque-g2-ADVERSARIO.md): 13 funções do schema plat com EXECUTE para PUBLIC —
-- plat.chamado_fila_operador, plat.chamado_operador_anexo_chave, plat.chamado_operador_anexos,
-- plat.chamado_operador_comentarios, plat.chamado_operador_estado, plat.chamado_operador_responder,
-- plat.chamado_operador_ver (20260908T2230_chamados_suporte.sql), plat.fluxo_particao_garantir
-- (20260908T1237_fluxo_ingestao.sql), plat.rede_medicao_particao_garantir (20260910T2351_rede_medicao.sql),
-- plat.tg_campo_fila_atualizado_em / plat.tg_campo_visita_marca_alvo (20260910T2245_campo.sql) e
-- plat.tg_fluxo_fonte_atualizado_em / plat.tg_formulario_atualizado_em (20260910T2350_formulario.sql).
-- Mesma causa raiz das duas varreduras anteriores (20260906T1615, 20260908T1031): `CREATE FUNCTION` dá EXECUTE
-- a PUBLIC por padrão, e nenhuma das seis migrações acima repetiu o `REVOKE EXECUTE ... FROM PUBLIC` que é o
-- padrão da casa — confirmado que `ALTER DEFAULT PRIVILEGES ... REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC` (001
-- fundação + 003 identidade) não alcança função nova nenhuma, mesmo com o default_acl do schema já sem PUBLIC
-- (medido diretamente: `CREATE FUNCTION` numa base de teste com o default_acl correto ainda devolve
-- `{=X/...}` no proacl). Enquanto isso não tiver conserto estrutural (ex.: um gatilho de evento em
-- `ddl_command_end` que feche PUBLIC automaticamente), o remédio é a mesma varredura de sempre repetida.
--
-- O laço é genérico de propósito: fecha o que estiver aberto NESTA base, sem citar nome de função, e não
-- quebra se a função não existir. Só o privilégio de PUBLIC sai; os GRANT nominais (plat_app, plat_worker)
-- ficam intactos. Função de gatilho não perde nada com isso: o PostgreSQL cobra EXECUTE da função de gatilho
-- em CREATE TRIGGER, não a cada disparo.
DO $$
DECLARE f record;
BEGIN
  FOR f IN
    SELECT p.oid::regprocedure AS assinatura
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'plat'
      AND (p.proacl IS NULL OR EXISTS (SELECT 1 FROM unnest(p.proacl) a WHERE a::text LIKE '=%'))
  LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f.assinatura);
  END LOOP;
END $$;
