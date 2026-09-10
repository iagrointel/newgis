-- Fecha EXECUTE para PUBLIC nas funções que nasceram depois da 20260906T1615. Idempotente.
-- depende: 20260906T1900_amc_modelo.sql
--
-- ACHADO ao juntar este ramo com master: a 20260906T1615 fez a mesma varredura e fechou o que existia
-- naquele minuto, mas `db/migracoes/20260906T1900_amc_modelo.sql` (deste ramo) cria seis funções DEPOIS
-- dela — amc_execucao_guarda, amc_marcar_modelo_executado, amc_materializado_guarda,
-- amc_materializado_tenant, amc_modelo_guarda e tg_amc_atualizado_em — com `GRANT EXECUTE ... TO plat_app`
-- e sem o `REVOKE ... FROM PUBLIC` que é o padrão da casa. `CREATE FUNCTION` dá EXECUTE a PUBLIC por
-- padrão, então as seis ficaram abertas e a guarda de master
-- `tests/api/catalogo/test_eventos_e_seguranca.py::test_funcoes_do_catalogo_sem_public_e_worker_fechado_a_plat_app`
-- reprova. O laço é o mesmo da 20260906T1615, genérico de propósito: fecha o que estiver aberto NESTA base,
-- sem citar nome de função, e não quebra se a função não existir. Só o privilégio de PUBLIC sai; os GRANT
-- nominais (plat_app, plat_worker) ficam intactos. Função de gatilho não perde nada: o PostgreSQL cobra
-- EXECUTE da função de gatilho em CREATE TRIGGER, não a cada disparo.
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
